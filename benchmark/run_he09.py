import difflib, gzip, hashlib, json, re, subprocess, time
from pathlib import Path
from benchmark_common import *
from validate_he09_protocol import validate_request,validate_panel
def main():
    out=TASK/'results/he09';assert not out.exists();out.mkdir(parents=True)
    subprocess.run([str(TASK/'python/bin/python3'),str(TASK/'validate_sweep_scope.py'),'he09_speed','--source-path',str(TASK/'scope-latest-suite.json')],check=True)
    contract=json.loads((TASK/'he09-contract.json').read_text());shared=contract['shared'];profile=contract['models']['Strata v0.1.40']
    dataset=Path('/home/benchmark/flash-combined-20260916/humaneval-decode-20260917/HumanEval.jsonl.gz')
    assert sha(dataset)==shared['dataset_sha256']
    with gzip.open(dataset,'rt') as stream:tasks={row['task_id']:row for row in map(json.loads,stream)}
    meta=api('/bench/meta');assert meta['generation_count']==0 and meta['context']==262144
    assert meta['args'][meta['args'].index('--prompt-cache')+1]=='0'
    lock=dict(panel_id='he09_speed',context=262144,thinking=False,fresh_server=True,generative_warmups=0,concurrency=1,
        task_ids=shared['task_ids'],model='Strata v0.1.40',request_profile=profile,dataset_sha256=sha(dataset),
        timeout_seconds=180,retries=0,first_attempt_only=True,cache_prompt=False,stream=False,
        output_policy=shared['output_policy'],measurement='Strata native generated/decode_ms; retain native DONE and HTTP usage separately',
        timing_boundary='Native prompt_ms includes prompt processing and first prediction; decode_ms is the subsequent engine loop (may include EOS bookkeeping).',
        runtime_identity=meta)
    save(out/'protocol.lock.json',lock)
    planned=[]
    for i,task in enumerate(shared['task_ids']):
        payload=dict(model=MODEL,messages=[dict(role='user',content=tasks[task]['prompt'])],**profile['sampling'],**shared['request_settings'])
        validate_request(payload,task,'Strata v0.1.40',contract)
        template=api('/apply-template',payload)
        assert re.search(r'<think>\s*</think>\s*$',template['prompt'])
        user=re.search(r'<\|im_start\|>user\n(.*?)<\|im_end\|>',template['prompt'],re.S).group(1)
        assert user==tasks[task]['prompt'].strip()
        case=out/f'HumanEval-{i}';case.mkdir();save(case/'request.json',payload);save(case/'rendered-template.json',template)
        (case/'canonical-prompt.txt').write_text(tasks[task]['prompt']);planned.append((task,case,payload))
    save(out/'planned-request-validation.json',validate_panel(out,'Strata v0.1.40',contract))
    rows=[]
    for task,case,payload in planned:
        assert resources()['ram_available']>4.5*1024**3
        validate_request(payload,task,'Strata v0.1.40',contract)
        save(case/'native-before.json',api('/bench/meta'));started=time.monotonic()
        with Samples() as samples:
            with request('/v1/chat/completions',payload,180) as response:raw=response.read()
        (case/'response.json').write_bytes(raw);save(case/'samples.json',samples.rows)
        data=json.loads(raw);meta=api('/bench/meta');save(case/'native-after.json',meta)
        last=meta['last'];choice=data['choices'][0];message=choice['message'];content=message.get('content') or ''
        valid=bool(content) and choice['finish_reason']=='stop' and not message.get('reasoning_content') and '<think>' not in content
        row=dict(task=task,valid_speed_case=valid,finish_reason=choice['finish_reason'],usage=data['usage'],timings=data.get('timings'),
            native_timings=last,native_tg=last['generated']*1000/last['decode_ms'] if last['decode_ms']>0 else None,
            native_pp=last.get('prompt_read',last['prompt_tokens'])*1000/last['prompt_ms'] if last['prompt_ms']>0 else None,
            wall_seconds=time.monotonic()-started,memory=samples.summary(),content_sha256=hashlib.sha256(content.encode()).hexdigest(),first_attempt=True)
        assert last['reused']==0
        save(case/'summary.json',row);(case/'content.txt').write_text(content);rows.append(row)
        save(out/'progress.json',dict(rows=rows));print(json.dumps(dict(event='HE_COMPLETE',**row)),flush=True)
    usable=[row for row in rows if row['valid_speed_case']]
    save(out/'summary.json',dict(status='COMPLETE',cases=10,usable_cases=len(usable),rows=rows,
        native_tg=sum(row['native_timings']['generated'] for row in usable)*1000/sum(row['native_timings']['decode_ms'] for row in usable) if usable else None,
        native_pp=sum(row['native_timings'].get('prompt_read',row['native_timings']['prompt_tokens']) for row in usable)*1000/sum(row['native_timings']['prompt_ms'] for row in usable) if usable else None,
        code_correctness_scored=False,comparison_boundary=lock['measurement']))
if __name__=='__main__':main()
