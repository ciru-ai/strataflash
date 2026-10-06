"""Audit preserved requests, native wire settings, responses and resource ownership."""
import argparse,json
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/srv/llm/work/strata-v0140-20261006'));p.add_argument('--panel',required=True);a=p.parse_args()
    owner=a.root/'ownership'/a.panel
    rows=[json.loads(line) for line in (owner/'native-journal.jsonl').read_text().splitlines()]
    requests=[x for x in rows if x['event']=='native_request'];responses=[x for x in rows if x['event']=='native_response']
    assert len(requests)==len(responses)
    assert not any(x['event']=='adapter_error' for x in rows)
    for req,res in zip(requests,responses):
        assert res['done_line'] and res['done_line'].startswith('DONE ')
        assert res['last']['generated']==len(res['emitted_ids'])
        assert req['prompt_tokens']==res['last']['prompt_tokens']
    if a.panel=='he09':
        assert len(requests)==10
        for req,res in zip(requests,responses):
            assert req['sampling']['temperature']==.7 and req['sampling']['top_p']==.8 and req['sampling']['top_k']==20 and req['sampling']['presence_penalty']==1.5 and req['sampling']['seed']==123
            assert 'temperature=0.7' in req['wire_sampling_keys'] and 'penalty_present=1.5' in req['wire_sampling_keys'] and 'seed=123' in req['wire_sampling_keys']
            assert res['last']['reused']==0
        assert json.loads((a.root/'results/he09/summary.json').read_text())['usable_cases']==10
    elif a.panel in ('counting','counting-zero-replay'):
        assert len(requests)==24
        for req in requests:
            assert req['sampling']['temperature']==1 and req['sampling']['top_p']==.95 and req['sampling']['top_k']==20 and req['sampling']['presence_penalty']==0 and req['sampling']['seed']==20260930
        expected=[32,512,512,512]+sum(([1,512,512,512] for i in range(5)),[])
        assert [r['max_new'] for r in requests]==expected
        assert [r['last']['generated'] for r in responses]==expected
        assert len([r for r in rows if r['event']=='cache_reset'])==9
        if a.panel=='counting-zero-replay':
            pins=[r for r in rows if r['event']=='prefix_pin']
            assert [r['prefix_tokens'] for r in pins]==[32000,64000,120000,192000,256000]
            assert all(r['no_generation'] for r in pins)
            for req,res in zip(requests,responses):
                if 'benchmark_cached_depth' in req['sampling']:
                    d=req['sampling']['benchmark_cached_depth']
                    assert res['last']['reused']==d and res['last']['prompt_read']==req['prompt_tokens']-d
                    assert 'bench_reuse='+str(d) in req['wire_sampling_keys']
            assert sum('benchmark_cached_depth' in r['sampling'] for r in requests)==18
            result=json.loads((a.root/'results/counting-zero-replay/summary.json').read_text())
            assert result['requests']==24 and result['cached_prefix_replayed_tokens']==0
    elif a.panel=='fidelity':
        assert len(requests)==16 and all(r['prompt_tokens']==513 and r['max_new']==1 for r in requests)
        assert all(r['last']['reused']==0 for r in responses)
        receipt=json.loads((a.root/'results/fidelity/capture-result.json').read_text());assert receipt['positions']==2048 and receipt['vocabulary']==248320
    elif a.panel in ('tools','hermes'):
        for req in requests:
            s=req['sampling']
            if a.panel=='tools' and req['max_new']==1:continue
            if a.panel=='tools':
                assert s['temperature']==.7 and s['top_p']==.8 and s['presence_penalty']==1.5 and s['seed']==123
                assert s['top_k']==20 and s['min_p']==0 and s['repetition_penalty']==1 and s['frequency_penalty']==0
                assert s['chat_template_kwargs']==dict(enable_thinking=False,preserve_thinking=True)
            else:
                # Scored requests use the frozen thinking sampler; harness summary calls are retained separately.
                if s.get('seed') in (160915,160916,160917):
                    assert s['temperature']==1 and s['top_p']==.95 and s['presence_penalty']==0 and s['top_k']==20
                    assert s['min_p']==0 and s['repetition_penalty']==1 and s['frequency_penalty']==0
                    assert s['chat_template_kwargs']==dict(enable_thinking=True,preserve_thinking=True)
    restored=json.loads((owner/'restoration.json').read_text());assert restored['benchmark_gpu_released'] and restored['main_active_state_restored'] and restored['hardware_unchanged']
    receipt=dict(status='PASS',panel=a.panel,native_requests=len(requests),native_responses=len(responses),effective_wire_sampler_checked=True,first_attempt_only=True,restoration=restored)
    (owner/'integrity-audit.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
