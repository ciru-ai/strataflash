#!/usr/bin/env python3
"""Frozen HC-Q8 hard-tool extension; validate every request before inference."""
import argparse
import difflib
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import urllib.request

LAB = Path('/benchmark-storage')
EXT = LAB / 'runs/20260930-hcq8-extension'
BASE = None
IDENTITY = None
UPSTREAM_PORT = 18207
PROFILE = EXT / 'start-publisher-current-262k.sh'
MODEL = 'qwen38-flash-next-hcq8'
SOURCE = LAB / 'tools/clones/tool-eval-bench'
ROOT = None
SAMPLER = dict(temperature=.7, top_p=.8, top_k=20, min_p=0.,
               presence_penalty=1.5, frequency_penalty=0., repeat_penalty=1., seed=123)
EXTRA = dict(SAMPLER, cache_prompt=True, max_tokens=-1,
             chat_template_kwargs=dict(enable_thinking=False, preserve_thinking=True))


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(p, x):
    Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=2) + '\n')


def fetch(route, body=None):
    req = urllib.request.Request('http://127.0.0.1:18207' + route,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization': 'Bearer local', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as f:
        return f.read()


def validate(body):
    from validate_recommended_tool import validate_request
    return validate_request(body, MODEL)


class Capture(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    index = 0
    counter = threading.Lock()

    def log_message(self, *args):
        pass

    def relay(self):
        with Capture.counter:
            index = Capture.index
            Capture.index += 1
        out = ROOT / 'http' / f'{index:04d}'
        out.mkdir(parents=True)
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        (out / 'request-body.json').write_bytes(raw)
        meta = dict(method=self.command, path=self.path)
        start = time.monotonic()
        connection = None
        try:
            if raw and self.path.endswith('/chat/completions'):
                meta['classification'] = validate(json.loads(raw))
                meta['request_validated_before_generation'] = True
            wire=raw
            if raw and self.path.endswith('/chat/completions') and IDENTITY['benchmark_backend']=='gufo':
                body=json.loads(raw)
                if body.get('max_tokens')==-1:body.pop('max_tokens')
                wire=json.dumps(body).encode()
                (out/'wire-request-body.json').write_bytes(wire)
                meta['adapter']='Gufo max_tokens=-1 translated to omission; verified native unlimited default'
            connection = http.client.HTTPConnection('127.0.0.1', 18207, timeout=1800)
            connection.request(self.command, self.path, body=wire or None,
                headers={'Authorization': 'Bearer local', 'Content-Type': 'application/json'})
            upstream = connection.getresponse()
            meta['status'] = upstream.status
            self.send_response(upstream.status)
            for key in ['Content-Type', 'Content-Length']:
                value = upstream.getheader(key)
                if value is not None:
                    self.send_header(key, value)
            self.send_header('Connection', 'close')
            self.end_headers()
            with (out / 'response-body.bin').open('xb') as output:
                while chunk := upstream.read1(65536):
                    meta.setdefault('first_byte_seconds', time.monotonic() - start)
                    output.write(chunk)
                    output.flush()
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except BaseException as error:
            meta['error'] = dict(type=type(error).__name__, message=str(error))
            raise
        finally:
            if connection:
                connection.close()
            if meta.get('classification')=='scored' and meta.get('status')==200 and IDENTITY['benchmark_backend']=='llama':
                try:
                    effective=json.loads(fetch('/slots'));save(out/'effective-slot-settings.json',effective)
                    for key,value in dict(SAMPLER,max_tokens=-1).items():
                        assert abs(effective[0]['params'][key]-value)<1e-6,(key,effective[0]['params'].get(key),value)
                except BaseException as error:meta['effective_settings_error']=str(error)
            meta['wall_seconds'] = time.monotonic() - start
            save(out / 'transport.json', meta)

    do_POST = relay
    do_GET = relay


def audit(cases):
    report = json.loads((ROOT / 'report.json').read_text())
    assert report['status'] == 'completed'
    assert report['config']['model'] == MODEL
    rows = report['scores']['scenario_results']
    assert [r['scenario_id'] for r in rows] == cases
    requests = []
    for folder in sorted((ROOT / 'http').iterdir()):
        meta = json.loads((folder / 'transport.json').read_text())
        assert meta.get('status') == 200 and not meta.get('error') and not meta.get('effective_settings_error'), (folder, meta)
        if meta.get('classification') not in ['scored', 'smoke']:
            continue
        response = (folder / 'response-body.bin').read_bytes()
        body = json.loads((folder / 'request-body.json').read_text())
        validate(body)
        if body.get('stream'):
            objects = [json.loads(line[6:]) for line in response.splitlines()
                       if line.startswith(b'data: ') and line[6:] != b'[DONE]']
        else:
            objects = [json.loads(response)]
        evidence = []
        for obj in objects:
            assert obj.get('model') == MODEL, obj.get('model')
            for choice in obj.get('choices', []):
                message = choice.get('delta', choice.get('message', {}))
                assert not message.get('reasoning_content') and not message.get('reasoning')
                evidence.append(bool(message.get('content') or message.get('tool_calls')))
        assert any(evidence), folder
        requests.append(dict(path=str(folder), request_sha256=sha(folder / 'request-body.json'),
            response_sha256=sha(folder / 'response-body.bin')))
    assert requests
    log = (ROOT / 'runner.log').read_text()
    assert 'benchmark_complete' in log
    assert not any(x in log for x in ['Traceback (most recent call last)', 'HTTPStatusError', 'ConnectError'])
    # The smoke must exercise real mocked tool actions, including final follow-ups.
    if ROOT.name == 'smoke':
        traces = '\n'.join(p.read_text() for p in (ROOT / 'artifacts').rglob('*')
                           if p.is_file() and p.suffix in ['.txt', '.md', '.json', '.jsonl'])
        assert 'create_calendar_event' in traces and 'send_email' in traces
        assert '2pm' in traces and 'book' in traces
    receipt = dict(status='COMPLETE', score=report['final_score'], cases=cases,
        requests=requests, all_requests_validated_before_generation=True,
        thinking=False, retries=0, card_sampler=SAMPLER,
        report_sha256=sha(ROOT / 'report.json'))
    save(ROOT / 'integrity.json', receipt)
    return receipt


def main():
    global ROOT, BASE, MODEL, IDENTITY
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--slug', required=True)
    p.add_argument('--identity', type=Path, required=True)
    args = p.parse_args()
    args.stage = 'full'
    MODEL = args.model
    BASE = Path('benchmark/results/tools')
    IDENTITY = json.loads(args.identity.read_text())
    cards=json.loads(Path(__file__).with_name('contract.json').read_text())
    profile=cards['models'][IDENTITY['display_model']]
    assert dict(profile['sampling'],seed=123)==SAMPLER
    ROOT = BASE / 'full'
    assert not ROOT.exists(), ROOT
    # The frozen HC harness smoke already proved its mocked tool environment.
    # Preserve first attempts; do not add three model-specific smoke repeats.
    subprocess.run(['/home/benchmark/.nix-profile/bin/python3',str(Path(__file__).with_name('validate_sweep_scope.py')),'hard_tool_15','--source-path',str(Path(__file__).with_name('scope-latest-suite.json'))],check=True)
    ROOT.mkdir(parents=True)
    cases = ['TC-70', 'TC-74', 'TC-84'] if args.stage == 'smoke' else [f'TC-{i}' for i in range(70, 85)]
    frozen = json.loads(Path('/home/benchmark/flash-v5-common-suite-20260928/harness-manifest.json').read_text())
    for path, digest in frozen['files_sha256'].items():
        if '/tool-eval-bench/' in path or path.endswith('quality-tool-eval-bench'):
            assert sha(path) == digest, path
    backend=IDENTITY['benchmark_backend']
    props = json.loads(fetch('/props')) if backend in ('llama','strata') else json.loads(fetch('/v1/models' if backend=='gufo' else '/health'))
    models = json.loads(fetch('/v1/models'))
    assert any(x['id'] == MODEL for x in models['data'])
    if backend in ('llama','strata'):assert props['default_generation_settings']['n_ctx'] == 262144
    elif backend=='gufo':assert props['data'][0]['context_length']==262144
    else:assert props['context']==262144
    assert IDENTITY.get('effective_preflight_passed') is True
    save(ROOT / 'props.json', props)
    command = IDENTITY.get('command',IDENTITY.get('container_command'))
    assert IDENTITY['context'] == 262144
    cli = [str(LAB / 'bin/quality-tool-eval-bench'), '--model', MODEL,
        '--base-url', 'http://127.0.0.1:18208/v1', '--api-key', 'local', '--backend', 'llamacpp',
        '--hardmode-only', '--no-think', '--temperature', '.7', '--top-p', '.8', '--top-k', '20',
        '--min-p', '0', '--repeat-penalty', '1', '--seed', '123',
        '--backend-kwargs', json.dumps(EXTRA), '--structured-response-format', 'json_object',
        '--max-turns', '32', '--trials', '1', '--parallel', '1', '--timeout', '1800',
        '--no-warmup', '--no-probe-engine', '--skip-coherence', '--no-live',
        '--output-dir', str(ROOT / 'artifacts'), '--json-file', str(ROOT / 'report.json'),
        '--scenarios', *cases]
    lock = dict(classification='local-custom', model=MODEL,
        server_identity=IDENTITY,
        identity_receipt_sha256=sha(args.identity),
        server_command=command,
        chat_template_sha256=hashlib.sha256(props['chat_template'].encode()).hexdigest() if backend in ('llama','strata') else None,
        harness_commit=frozen['commits'][str(SOURCE)], source_files=frozen,
        sampler=SAMPLER, thinking=False, context=262144, request_output_cap=None,
        server_n_predict='remaining context; upstream Strata unlimited sentinel', max_turns=32, request_timeout_seconds=1800, cases=cases,
        canonical_fixture_date='2026-03-20 (Friday)', parallel=1, samples=1, retries=0,
        cache='profile cache retained; exact reuse counters captured', warmup=False,
        prompt_adapter='Unchanged tool-eval-bench task/system/tool schemas',
        runner_sha256=sha(__file__), command=cli,
        model_card=profile['model_card'], sampler_card=profile['sampler_card'], sampler_inheritance=profile['sampler_inheritance'],
        comparison_scope='New card-sampling, fixture-corrected nonthinking protocol; old greedy/date-override/8-turn rows excluded',
        authorization='User explicitly requests one recommended-settings tool pass for each retained model; reuse completed Carlos, skip deleted original IU4')
    save(ROOT / 'protocol.lock.json', lock)
    preview=ROOT/'rendered-prompts';preview.mkdir()
    reference=json.loads(Path(__file__).with_name('initial-requests.json').read_text())
    for case,original in zip(cases,reference):
        request=dict(original,model=MODEL)
        validate(request)
        save(preview/f'{case}.request.json',request)
        if backend in ('llama','strata'):
            rendered=json.loads(fetch('/apply-template',request))
            assert request['messages'][1]['content'].strip() in rendered['prompt']
            assert '<think>\n\n</think>' in rendered['prompt']
        elif backend=='halogen':
            rendered=json.loads(fetch('/benchmark/tool-preflight',request))
            assert '<think>\n\n</think>' in rendered['rendered_prompt']
            assert rendered['cache_mode']==2 and rendered['thinking'] is False
        else:
            rendered=dict(source_verified=True,identity=IDENTITY['backend_source_proof'],request_sha256=sha(preview/f'{case}.request.json'),generation_suffix='<|im_start|>assistant\n<think>\n\n</think>\n\n',output_encoding='Omit max_tokens: server -1 default becomes scheduler remaining physical context')
        save(preview/f'{case}.rendered.json',rendered)
    (ROOT / 'metrics-before.prom').write_bytes(fetch('/metrics' if backend!='halogen' else '/health'))
    proxy = ThreadingHTTPServer(('127.0.0.1', 18208), Capture)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    proc = None
    start = time.monotonic()
    try:
        with (ROOT / 'runner.log').open('x') as log:
            proc = subprocess.Popen(cli, cwd=LAB, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(json.dumps(dict(event='STARTED', stage=args.stage, root=str(ROOT), pid=proc.pid)), flush=True)
        while proc.poll() is None:
            assert time.monotonic() - start < len(cases) * 3600 + 600, 'Panel resource deadline'
            time.sleep(1)
        assert proc.returncode == 0, proc.returncode
        receipt = audit(cases)
        receipt['wall_seconds'] = time.monotonic() - start
        save(ROOT / 'result.json', receipt)
        print(json.dumps({k:v for k,v in receipt.items() if k != 'requests'}), flush=True)
    except BaseException as error:
        save(ROOT / 'failure.json', dict(type=type(error).__name__, message=str(error),
            classification='requires-integrity-audit', first_trajectories_preserved=True))
        raise
    finally:
        if proc and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=30)
        proxy.shutdown()
        proxy.server_close()
        (ROOT / 'metrics-after.prom').write_bytes(fetch('/metrics' if backend!='halogen' else '/health'))


if __name__ == '__main__':
    main()
