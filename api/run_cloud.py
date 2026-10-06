#!/usr/bin/env python3
"""One-pass hosted extension; secrets remain in Arche's existing config."""
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
LAB = '/benchmark-storage'
REMOTE = LAB + '/runs/20261002-token-plan-qwen38-flash'
WRAPPER = '/home/benchmark/.codex/skills/work-on-home-servers/scripts/server.sh'
PORT = 18738
MODEL = 'qwen3.8-flash'
STAGE = 'he09'
COUNTER = 0
MUTEX = threading.Lock()
SERIAL = threading.Lock()
REASONS = {}


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HECONTRACT = json.loads((WORK/'hcq8-20260930/speed-audit/he09-contract.json').read_text())
HEVALID = module('he_validator', WORK/'hcq8-20260930/speed-audit/validate_he09_protocol.py')
TOOLVALID = module('tool_validator', WORK/'hcq8-20260930/recommended-tools-20261001/validate_recommended_tool.py')
CONFIG = json.loads(Path('/home/benchmark/.bailian/config.json').read_text())['token-plan']
assert 'token-plan.' in CONFIG['base_url']
ENDPOINT = CONFIG['base_url'].rstrip('/') + '/compatible-mode/v1/chat/completions'


def wire_request(body):
    assert body['model'] == MODEL
    thinking = STAGE.startswith('hermes')
    probe = STAGE=='tools' and body.get('max_tokens')==1 and not body.get('tools')
    nested = thinking and not body.get('tools')
    if STAGE == 'he09':
        task = next(t for t,h in HECONTRACT['shared']['prompt_sha256'].items()
                    if hashlib.sha256(body['messages'][0]['content'].encode()).hexdigest() == h)
        canonical = dict(body, model=HECONTRACT['models']['HC-Q8']['api_model'])
        HEVALID.validate_request(canonical, task, 'HC-Q8', HECONTRACT)
    elif STAGE == 'tools':
        TOOLVALID.validate_request(body, MODEL)
    else:
        assert body.get('messages'), 'Hermes must originate agent messages'
        if nested:
            assert set(body)=={'model','messages','max_tokens','temperature'}
            assert body['max_tokens']==10000 and body['temperature']==.1
            assert body['messages'][0]['role']=='system'
            assert body['messages'][0]['content'].startswith('You are reviewing a past conversation transcript to help recall what happened.')
        else:
            assert body.get('temperature') == .6
            assert body.get('reasoning_effort') == 'xhigh'
            assert body.get('seed') == {'hermes-smoke':160915,'hermes-pass1':160916,'hermes-pass2':160917}[STAGE]
            assert not any(k in body for k in ['max_tokens','max_completion_tokens','stop'])
    wire = copy.deepcopy(body)
    # Hosted official recommendations: set temperature only, keep published top_p default.
    for key in ['chat_template_kwargs','cache_prompt','min_p','repeat_penalty',
                'repetition_penalty','top_p']:
        wire.pop(key, None)
    if wire.get('max_tokens') == -1:
        wire.pop('max_tokens')
    wire.update(temperature=.6 if thinking else .7, top_k=20,
                presence_penalty=0. if thinking else 1.5, enable_thinking=thinking)
    if probe:
        assert body['messages']==[{'role':'system','content':'You are a helpful assistant.'},{'role':'user','content':'Say hello.'}]
        wire['seed']=123
    if thinking:
        wire['preserve_thinking'] = True
        if nested:
            wire['reasoning_effort']='xhigh'
            wire['seed']={'hermes-smoke':160915,'hermes-pass1':160916,'hermes-pass2':160917}[STAGE]
        for message in wire['messages']:
            calls = message.get('tool_calls') or []
            if message.get('role') == 'assistant' and calls and not message.get('reasoning_content'):
                ids = [c.get('id') for c in calls]
                reasons = [REASONS[i] for i in ids if i in REASONS]
                if reasons:
                    message['reasoning_content'] = reasons[0]
    if wire.get('stream'):
        wire['stream_options'] = {'include_usage': True}
    assert wire['enable_thinking'] == thinking
    assert wire['temperature'] == (.6 if thinking else .7)
    assert wire['seed'] == (123 if not thinking else {'hermes-smoke':160915,'hermes-pass1':160916,'hermes-pass2':160917}[STAGE])
    assert not any(k in wire for k in ['max_completion_tokens','stop','cache_prompt','min_p'])
    assert 'max_tokens' not in wire or (probe and wire['max_tokens']==1) or (nested and wire['max_tokens']==10000)
    return wire


class Proxy(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'object':'list','data':[{'id':MODEL}]}).encode())

    def do_POST(self):
        global COUNTER
        with SERIAL:
            with MUTEX:
                index = COUNTER
                COUNTER += 1
                stage = STAGE
            folder = ROOT/stage/'http'/f'{index:04d}'
            folder.mkdir(parents=True, exist_ok=False)
            raw = self.rfile.read(int(self.headers['Content-Length']))
            (folder/'request-body.json').write_bytes(raw)
            meta = {'stage':stage,'retries':0,'native_pp_available':False,'native_tg_available':False}
            start = time.monotonic()
            try:
                wire = wire_request(json.loads(raw))
                save(folder/'wire-request-body.json', wire)
                meta['request_validated_before_generation'] = True
                meta['unscored_transport_probe'] = wire.get('max_tokens')==1
                request = urllib.request.Request(ENDPOINT, json.dumps(wire).encode(),
                    headers={'Authorization':'Bearer '+CONFIG['api_key'],'Content-Type':'application/json'})
                response = urllib.request.urlopen(request, timeout=180 if stage=='he09' else 1800)
                meta['status'] = response.status
                meta['response_headers'] = {k:v for k,v in response.headers.items()
                    if k.lower() in ['content-type','x-request-id','x-dashscope-request-id']}
                self.send_response(response.status)
                self.send_header('Content-Type',response.headers.get('Content-Type','application/json'))
                self.end_headers()
                reason = ''
                callids = {}
                with (folder/'response-body.bin').open('xb') as output:
                    if wire.get('stream'):
                        with (folder/'events.jsonl').open('x') as events:
                            for line in response:
                                output.write(line); output.flush()
                                elapsed = time.monotonic()-start
                                if line.startswith(b'data: ') and line.strip()!=b'data: [DONE]':
                                    obj=json.loads(line[6:])
                                    events.write(json.dumps({'elapsed_seconds':elapsed,'data':obj})+'\n');events.flush()
                                    if obj.get('usage'):meta['usage']=obj['usage']
                                    for choice in obj.get('choices',[]):
                                        delta=choice.get('delta',{})
                                        if delta.get('reasoning_content'):reason+=delta['reasoning_content']
                                        if any(delta.get(k) for k in ['content','reasoning_content','tool_calls']):
                                            meta.setdefault('first_generated_delta_seconds',elapsed)
                                            meta['last_generated_delta_seconds']=elapsed
                                        for call in delta.get('tool_calls',[]):
                                            if call.get('id'):callids[call.get('index',0)]=call['id']
                                        if choice.get('finish_reason'):meta['finish_reason']=choice['finish_reason']
                                self.wfile.write(line);self.wfile.flush()
                    else:
                        content=response.read();output.write(content)
                        obj=json.loads(content)
                        meta['usage']=obj.get('usage',{})
                        meta['finish_reason']=obj.get('choices',[{}])[0].get('finish_reason')
                        message=obj.get('choices',[{}])[0].get('message',{})
                        reason=message.get('reasoning_content','')
                        callids={i:c['id'] for i,c in enumerate(message.get('tool_calls',[])) if c.get('id')}
                        self.wfile.write(content)
                if reason:
                    for identifier in callids.values():REASONS[identifier]=reason
                if not wire['enable_thinking']:
                    assert not reason, 'Hosted endpoint returned thinking in a thinking-off panel'
            except urllib.error.HTTPError as error:
                meta.update(status=error.code,error_type='HTTPError')
                content=error.read()
                (folder/'response-body.bin').write_bytes(content)
                self.send_response(error.code);self.end_headers();self.wfile.write(content)
            except Exception as error:
                meta.update(error_type=type(error).__name__,error=str(error))
                try:self.send_response(502);self.end_headers()
                except OSError:pass
            finally:
                meta['wall_seconds']=time.monotonic()-start
                if meta.get('usage',{}).get('completion_tokens'):
                    n=meta['usage']['completion_tokens']
                    meta['end_to_end_output_tokens_per_second']=n/meta['wall_seconds']
                    first=meta.get('first_generated_delta_seconds')
                    last=meta.get('last_generated_delta_seconds')
                    if first is not None and last is not None and last>first:
                        meta['observed_stream_tokens_per_second']=(n-1)/(last-first)
                        meta['stream_rate_definition']='(provider completion_tokens - 1)/(last generated delta - first generated delta); includes chunk batching and network; not native GPU TG'
                save(folder/'transport.json',meta)


def remote(command, logfile):
    with logfile.open('x') as log:
        proc=subprocess.Popen([WRAPPER,'ciru','run',command],stdout=log,stderr=subprocess.STDOUT)
        while proc.poll() is None:
            time.sleep(1)
        assert proc.returncode==0, f'Remote harness exit {proc.returncode}: {logfile}'


def scope(panel):
    subprocess.run(['python3',str(WORK/'hcq8-20260930/validate_sweep_scope.py'),panel],check=True)


def main():
    global STAGE
    resume = '--resume-after-probe-adapter-fix' in sys.argv
    hermes_resume = '--continue-unattempted-hermes' in sys.argv
    if hermes_resume:
        assert read_failure_stage()=='hermes-pass1'
        global COUNTER
        COUNTER=max(int(p.name) for p in ROOT.glob('*/http/*'))+1
        for name in ['failure.json','cleanup.json']:
            (ROOT/name).rename(ROOT/('hermes-initial-'+name))
        save(ROOT/'hermes-recovery.json',dict(first_pass_invalid_case='HA-04',case_not_retried=True,
             first_pass_remaining=[f'HA-{i:02d}' for i in range(5,21)],
             reason='Local adapter rejected native session_search summarizer before provider generation; agent internal retries invalidate first HA04 evidence',
             nested_request_policy='Retain summarizer messages and 10000-token internal limit; use provider .6/xhigh recommendation and stage seed'))
    elif resume:
        assert (ROOT/'STARTED.json').exists()
        receipts=[json.loads(p.read_text()) for p in (ROOT/'he09/http').glob('*/transport.json')]
        assert len(receipts)==10 and all(r['status']==200 and r['finish_reason']=='stop' for r in receipts)
        prior=[json.loads(p.read_text()) for p in (ROOT/'tools/http').glob('*/transport.json')]
        assert len(prior)==1 and 'status' not in prior[0], 'No tool generation may be repeated'
        for name in ['failure.json','cleanup.json']:
            (ROOT/name).rename(ROOT/('preflight-'+name))
        (ROOT/'tools/runner.log').rename(ROOT/'tools/preflight-runner.log')
        COUNTER=11
    else:
        assert not (ROOT/'STARTED.json').exists(), 'Never repeat preserved first attempts'
    scope('he09_speed');scope('hard_tool_15');scope('hermesagent20')
    save(ROOT/'protocol.lock.json',dict(model=MODEL, endpoint=CONFIG['base_url'],
        classification='Hosted service extension; excluded from controlled local-hardware rankings',
        requested_panels=['he09_speed','hard_tool_15','hermesagent20'],
        unsupported_panels=dict(append_speed_grid='No raw token-ID completion/tokenize/slot-reset interface',
            cold_prefix='Native prompt timing and verified cold cache unavailable',
            short_fidelity='Full vocabulary logits and exact deployed weights unavailable',
            memory_and_disk='Provider weight files, RAM, GPU and disk metrics unavailable'),
        mismatch_corrections=dict(hardware='Hosted hardware/runtime/weights/template revision cannot be pinned; separate hosted panel',
            context='Hosted 1M capacity versus local 262144; physical capacity cannot be forced; no claim of controlled equivalence',
            cache='Provider implicit cache uncontrolled; capture returned cached_tokens; no cold-cache claim',
            sampler='Use hosted model guide: thinking .6/xhigh, off .7; omit top_p per provider recommendation; top_k20; own presence defaults',
            native_fields='Remove unsupported neutral min_p/repeat penalties/cache_prompt; max_tokens=-1 becomes documented default maximum',
            output='No custom cap; hosted documented max output 131072, thinking 262144; local unlimited to context differs',
            timings='Capture client wall/stream deltas and provider usage; native PP/TG cannot be substituted',
            model_identity='qwen3.8-flash rolling hosted alias; official release catalog pinned as evidence, served weights unobservable'),
        he09=dict(thinking=False,concurrency=1,seed=123,warmups=0,timeout=180,stream=False),
        tools=dict(thinking=False,concurrency=1,seed=123,warmups=0,max_turns=32,timeout=1800),
        hermes=dict(thinking=True,passes=2,smoke=['HA-01','HA-05','HA-20'],seeds=[160915,160916,160917],case_timeout=1800),
        retries=0,first_attempt_only=True,runner_sha256=sha(__file__),
        source_sha256={str(p.relative_to(WORK)):sha(p) for p in [WORK/'hcq8-20260930/active-sweep-contract.json',WORK/'hcq8-20260930/recommended-tools-20261001/initial-requests.json',ROOT/'model-catalog.json',ROOT/'model-guide.html']},
        guide_url='https://docs.qwencloud.com/developer-guides/getting-started/latest-model'))
    dataset=WORK/'humaneval-decode-20260917/HumanEval.jsonl.gz'
    assert sha(dataset)==HECONTRACT['shared']['dataset_sha256']
    with gzip.open(dataset,'rt') as stream:tasks={r['task_id']:r for r in map(json.loads,stream)}
    payloads=[]
    for task in HECONTRACT['shared']['task_ids']:
        payload=dict(model=MODEL,messages=[dict(role='user',content=tasks[task]['prompt'])],
                     **HECONTRACT['models']['HC-Q8']['sampling'],**HECONTRACT['shared']['request_settings'])
        wire_request(payload)
        save(ROOT/'he09'/(task.replace('/','-')+'.planned-request.json'),payload)
        payloads.append(payload)
    STAGE='tools'
    for index,original in enumerate(TOOLVALID.REFERENCE):
        payload=dict(original,model=MODEL)
        wire=wire_request(payload)
        save(ROOT/'tools/planned'/f'TC-{index+70}.json',wire)
    STAGE='he09'
    save(ROOT/'STARTED.json',dict(started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    proxy=ThreadingHTTPServer(('127.0.0.1',PORT),Proxy)
    threading.Thread(target=proxy.serve_forever,daemon=True).start()
    ssh=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ExitOnForwardFailure=yes',
         '-o','ServerAliveInterval=30','-i','/home/benchmark/.ssh/id_ed25519_omarchy_migration',
         '-N','-R',f'127.0.0.1:{PORT}:127.0.0.1:{PORT}','crown@127.0.0.1']
    tunnel=subprocess.Popen(ssh,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        time.sleep(1);assert tunnel.poll() is None,'Reverse tunnel failed'
        for index,payload in enumerate([] if resume or hermes_resume else payloads):
            request=urllib.request.Request(f'http://127.0.0.1:{PORT}/v1/chat/completions',json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=190) as response:
                obj=json.load(response)
            save(ROOT/'he09'/f'HumanEval-{index}.response.json',obj)
            print(json.dumps(dict(stage='he09',task=index,usage=obj.get('usage'),finish=obj['choices'][0]['finish_reason'])),flush=True)
        subprocess.run([WRAPPER,'ciru','run','mkdir -p '+shlex.quote(REMOTE)],check=True)
        STAGE='tools'
        scope('hard_tool_15')
        extra=dict(temperature=.7,top_p=.8,top_k=20,min_p=0.,presence_penalty=1.5,frequency_penalty=0.,repeat_penalty=1.,seed=123,
                   cache_prompt=True,max_tokens=-1,chat_template_kwargs=dict(enable_thinking=False,preserve_thinking=True))
        cmd=[LAB+'/bin/quality-tool-eval-bench','--model',MODEL,'--base-url',f'http://127.0.0.1:{PORT}/v1','--api-key','local',
             '--backend','llamacpp','--hardmode-only','--no-think','--temperature','.7','--top-p','.8','--top-k','20','--min-p','0',
             '--repeat-penalty','1','--seed','123','--backend-kwargs',json.dumps(extra),'--structured-response-format','json_object',
             '--max-turns','32','--trials','1','--parallel','1','--timeout','1800','--no-warmup','--no-probe-engine','--skip-coherence','--no-live',
             '--output-dir',REMOTE+'/tools/artifacts','--json-file',REMOTE+'/tools/report.json','--scenarios',*[f'TC-{i}' for i in range(70,85)]]
        save(ROOT/'tools/command.json',cmd)
        if not hermes_resume:
            print('START hard_tool_15',flush=True)
            remote(shlex.join(cmd),ROOT/'tools/runner.log')
        for name in (['pass1','pass2'] if hermes_resume else ['smoke','pass1','pass2']):
            STAGE='hermes-'+name
            scope('hermesagent20')
            seed={'smoke':160915,'pass1':160916,'pass2':160917}[name]
            extra=dict(top_k=20,presence_penalty=0.,seed=seed,enable_thinking=True,preserve_thinking=True)
            cmd=['node',LAB+'/runs/20260929-flash-hermes-recommended-thinking/run-hermesagent20-sweep-v2.mjs',
                 '--profile','Token Plan Qwen3.8 Flash','--skip-switch','--skip-import','--image','hermesagent20-verifier:artifact-v5',
                 '--base-url',f'http://127.0.0.1:{PORT}/v1','--model-id',MODEL,'--auth-mode','bearer','--api-key','local',
                 '--scenario-timeout-ms','1800000','--fetch-retries','0','--temperature','.6','--reasoning-effort','xhigh',
                 '--request-extra-body',json.dumps(extra),'--run-root',REMOTE+'/hermes-'+name+('-continuation' if hermes_resume and name=='pass1' else '')+'/cases']
            cases=['HA-01','HA-05','HA-20'] if name=='smoke' else [f'HA-{i:02d}' for i in range(1,21)]
            if hermes_resume and name=='pass1':cases=[f'HA-{i:02d}' for i in range(5,21)]
            for case in cases:cmd+=['--scenario',case]
            suffix='-continuation' if hermes_resume and name=='pass1' else ''
            save(ROOT/STAGE/('command'+suffix+'.json'),cmd)
            print('START '+STAGE,flush=True)
            remote('BENCHLAB_ROOT='+shlex.quote(LAB)+' '+shlex.join(cmd),ROOT/STAGE/('runner'+suffix+'.log'))
        save(ROOT/'COMPLETE.json',dict(completed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),remote=REMOTE))
    except Exception as error:
        save(ROOT/'failure.json',dict(type=type(error).__name__,error=str(error),stage=STAGE,retries=0))
        raise
    finally:
        tunnel.terminate();tunnel.wait(timeout=15)
        proxy.shutdown();proxy.server_close()
        save(ROOT/'cleanup.json',dict(proxy_closed=True,tunnel_closed=True,production_services_untouched=True))


def read_failure_stage():
    return json.loads((ROOT/'failure.json').read_text())['stage']


if __name__=='__main__':
    main()
