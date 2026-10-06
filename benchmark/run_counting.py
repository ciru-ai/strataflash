import hashlib,json,re,subprocess,time
from pathlib import Path
from benchmark_common import *
from validate_v5_counting_protocol import validate_request,audit_output
def main():
    out=TASK/'results/counting-zero-replay';assert not out.exists();out.mkdir(parents=True)
    for panel in ['append_speed_grid','cold_prefix']:
        subprocess.run([str(TASK/'python/bin/python3'),str(TASK/'validate_sweep_scope.py'),panel,'--source-path',str(TASK/'scope-latest-suite.json')],check=True)
    contract=json.loads((TASK/'counting-contract.json').read_text())
    cache_contract=json.loads((TASK/'zero-replay-contract.json').read_text())
    assert cache_contract['request_contract_sha256']==sha(TASK/'counting-contract.json')
    meta=api('/bench/meta');assert meta['generation_count']==0
    assert sha(TASK/'base-model-card.md')==contract['sampling_card']['card_sha256']
    planned=[];primers={}
    for name in contract['order']:
        body=json.loads((TASK/'counting-requests'/(name+'.json')).read_text());assert body['model']==MODEL
        normalized=dict(body,model='v5.0');validate_request(normalized,name,contract)
        ids=api('/tokenize',dict(content=body['prompt'],parse_special=True),60)['tokens']
        match=re.fullmatch(r'p(\d+)-d(\d+)',name)
        expected=int(match[1])+int(match[2]) if match else int(name[1:7]) if name.endswith('primer') else 12960
        assert len(ids)==expected,(name,len(ids),expected)
        if name.endswith('-primer'):primers[int(name[1:7])]=ids
        if match and int(match[2])>0:assert ids[:int(match[2])]==primers[int(match[2])],name
        case=out/name;case.mkdir();save(case/'request.json',body)
        save(case/'planned-request-validation.json',dict(status='PASS',prompt_tokens=len(ids),prompt_ids_sha256=hashlib.sha256(','.join(map(str,ids)).encode()).hexdigest(),exact_except_model_alias=True,exact_primer_prefix_validated=bool(match and int(match[2])>0)))
        planned.append((name,case,body))
    save(out/'protocol.lock.json',dict(panel_ids=['append_speed_grid','cold_prefix'],context=262144,concurrency=1,
        model=MODEL,order=contract['order'],sampling=contract['sampling'],generative_warmups=1,
        warmup_policy='Retained 12960 input / 32 output warmup',cache_policy=cache_contract,
        scored_cells=18,cold_prefix_observations=5,all_24_requests_validated_before_generation=True,
        timeout_seconds=1800,retries=0,first_attempt_only=True,runtime_identity=meta,
        measurement='Native prompt_read/prompt_ms and generated/decode_ms; useful append P/prompt_ms separately',
        historical_cache_limitation=contract['historical_cache_limitation']))
    rows=[]
    for name,case,body in planned:
        assert resources()['ram_available']>4.5*1024**3
        validate_request(dict(body,model='v5.0'),name,contract)
        match=re.fullmatch(r'p(\d+)-d(\d+)',name);p=int(match[1]) if match else None;depth=int(match[2]) if match else None
        headers={'X-Benchmark-Cached-Depth':str(depth)} if match else {}
        save(case/'request-headers.json',headers)
        started=time.monotonic();first=None;events=[];content='';rawlines=[]
        with Samples() as samples,request('/v1/completions',body,1800,headers=headers) as response:
            for line in response:
                rawlines.append(line)
                if not line.startswith(b'data: '):continue
                if line[6:].strip()==b'[DONE]':break
                value=json.loads(line[6:]);events.append(value)
                for choice in value.get('choices',[]):
                    delta=choice.get('text') or ''
                    if delta and first is None:first=time.monotonic()-started
                    content+=delta
        wall=time.monotonic()-started
        (case/'response.sse').write_bytes(b''.join(rawlines));(case/'content.txt').write_text(content)
        save(case/'events.json',events);save(case/'samples.json',samples.rows)
        meta=api('/bench/meta');save(case/'native-after.json',meta)
        final=next(v for v in reversed(events) if 'native_timings' in v);last=final['native_timings']
        count=body['max_tokens'];assert last['generated']==count and final['usage']['completion_tokens']==count,(name,last,final)
        if match:assert last['reused']==depth and last['prompt_read']==p,(name,last)
        elif name.endswith('-primer'):
            prefix=int(name[1:7]);assert last['reused']==0 and last['prompt_read']==prefix,(name,last)
            receipt=api('/bench/prefix-pin',dict(depth=prefix),60);save(case/'prefix-pin.json',receipt)
        audit=audit_output(content,contract) if match else dict(first_outcome_preserved=True,unscored_warmup=name=='warm')
        save(case/'output-audit.json',audit)
        row=dict(name=name,scored=bool(match),prompt=p,depth=depth,usage=final['usage'],native_timings=last,timings=final['timings'],
            native_pp=last.get('prompt_read',last['prompt_tokens']-last.get('reused',0))*1000/last['prompt_ms'] if last['prompt_ms']>0 else None,
            useful_append_pp=p*1000/last['prompt_ms'] if p and last['prompt_ms']>0 else None,
            native_tg=last['generated']*1000/last['decode_ms'] if last['decode_ms']>0 else None,
            ttfp_seconds=first,wall_seconds=wall,memory=samples.summary(),output_audit=audit,
            cached_prefix_replayed_tokens=0 if match else None)
        save(case/'result.json',row);rows.append(row);save(out/'progress.json',dict(rows=rows))
        print(json.dumps(dict(event='COUNTING_COMPLETE',**row)),flush=True)
    save(out/'summary.json',dict(status='COMPLETE',requests=len(rows),scored_cells=18,cold_prefix_observations=5,rows=rows,
        clean_counting_cells=sum(row['output_audit'].get('clean_counting',False) for row in rows if row['scored']),
        first_attempt_only=True,retries=0,exact_cached_depth=True,cached_prefix_replayed_tokens=0))
if __name__=='__main__':main()
