#!/usr/bin/env python3
"""Audit saved cloud receipts and create a comparison addendum; no generation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parent


def read(path):return json.loads(Path(path).read_text())
def save(path,obj):Path(path).write_text(json.dumps(obj,indent=2)+'\n')
def link(path,label):return f'[{label}](<{path}>)'


def metrics(stage):
    rows=[]
    for path in sorted((ROOT/stage/'http').glob('*/transport.json')):
        row=read(path)
        if row.get('status')!=200:continue
        assert row.get('request_validated_before_generation') and row['retries']==0
        if row.get('unscored_transport_probe'):continue
        rows.append(row)
    wall=sum(r['wall_seconds'] for r in rows)
    tokens=sum(r.get('usage',{}).get('completion_tokens',0) for r in rows)
    streamed=[r for r in rows if 'observed_stream_tokens_per_second' in r]
    span=sum(r['last_generated_delta_seconds']-r['first_generated_delta_seconds'] for r in streamed)
    return dict(requests=len(rows),output_tokens=tokens,request_wall_seconds=wall,
        output_tokens_per_second_end_to_end=tokens/wall if wall else None,
        streamed_requests=len(streamed),
        observed_stream_rate=sum(r['usage']['completion_tokens']-1 for r in streamed)/span if span else None,
        median_time_to_first_generated_delta=statistics.median([r['first_generated_delta_seconds'] for r in streamed]) if streamed else None,
        cached_prompt_tokens=sum(r.get('usage',{}).get('prompt_tokens_details',{}).get('cached_tokens',0) for r in rows),
        native_pp=None,native_tg=None)


def tools_audit():
    spec=importlib.util.spec_from_file_location('tool_audit',WORK/'hcq8-20260930/recommended-tools-20261001/audit_results.py')
    # Reuse only its pure parser, avoiding the host-specific audit entrypoint.
    source=(WORK/'hcq8-20260930/recommended-tools-20261001/audit_results.py').read_text()
    start=source.index('def objects(');end=source.index('def audit(')
    scope={'json':json};exec(source[start:end],scope)
    reference=read(WORK/'hcq8-20260930/recommended-tools-20261001/initial-requests.json')
    calls=[];observations={};initial=[]
    for folder in sorted((ROOT/'tools/http').iterdir()):
        meta=read(folder/'transport.json')
        if 'status' not in meta:
            assert meta.get('error_type')=='KeyError'
            continue
        assert meta['status']==200 and not meta.get('error_type'),meta
        if meta.get('unscored_transport_probe'):continue
        body=read(folder/'request-body.json')
        case='TC-'+str(next(i for i,r in enumerate(reference) if r['messages'][:2]==body['messages'][:2])+70)
        if len(body['messages'])==2:initial.append(case)
        obs=scope['objects'](body,(folder/'response-body.bin').read_bytes())
        for obj in obs:
            assert obj['model']=='qwen3.8-flash'
            for choice in obj.get('choices',[]):
                message=choice.get('delta',choice.get('message',{}))
                assert not message.get('reasoning_content')
        for call in scope['response_calls'](obs):
            if call.get('id'):calls.append(dict(case=case,response=str(folder/'response-body.bin'),**call))
        for message in body['messages']:
            if message['role']=='tool':observations[(case,message.get('tool_call_id'))]=message['content']
    origins={(c['case'],c['id']) for c in calls}
    assert all(k in origins for k in observations)
    for call in calls:
        key=(call['case'],call['id'])
        call['environment_observation']=observations.get(key)
        call['executed']=key in observations
    assert initial==[f'TC-{i}' for i in range(70,85)],initial
    save(ROOT/'tools/tool-execution-evidence.json',calls)
    return dict(model_originated_calls=len(calls),calls_with_environment_observations=sum(c['executed'] for c in calls),
                initial_order=initial,first_attempts_preserved=True)


def hermes_execution_audit(stage, summary_paths):
    source=(WORK/'hcq8-20260930/recommended-tools-20261001/audit_results.py').read_text()
    parsers={'json':json};exec(source[source.index('def objects('):source.index('def audit(')],parsers)
    origins={}
    for folder in sorted((ROOT/stage/'http').iterdir()):
        meta=read(folder/'transport.json')
        if meta.get('status')!=200:continue
        body=read(folder/'request-body.json')
        for call in parsers['response_calls'](parsers['objects'](body,(folder/'response-body.bin').read_bytes())):
            if call['id']:origins[call['id']]=call
    events=[];integrity=[]
    for summary in summary_paths:
        for path in summary.parent.glob('artifacts/*/agent-result.json'):
            result=read(path)
            completed={e['toolCallId']:e for e in result['toolEvents'] if e['phase']=='complete'}
            for event in result['toolEvents']:
                if event['phase']!='start':continue
                identifier=event['toolCallId']
                assert identifier in origins,(path,identifier,'Missing provider-originated tool call')
                assert identifier in completed,(path,identifier,'Missing environment completion')
                assert completed[identifier].get('name')==origins[identifier]['name']
                events.append(dict(case=path.parent.name,tool_call_id=identifier,
                    name=origins[identifier]['name'],model_arguments=origins[identifier]['arguments'],
                    environment_result=completed[identifier].get('result'),source=str(path)))
        integrity.extend(read(p) for p in summary.parent.glob('integrity/*.json'))
    save(ROOT/stage/'tool-execution-evidence.json',events)
    return dict(captured_parent_calls_with_environment_results=len(events),
                valid_cases=sum(r['status']=='valid-agent-evidence' for r in integrity),
                invalid_cases=[r['case'] for r in integrity if r['status']!='valid-agent-evidence'])


def main():
    data={'model':'qwen3.8-flash','classification':'Hosted extension, outside controlled local hardware ranking',
          'metrics':{stage:metrics(stage) for stage in ['he09','tools','hermes-smoke','hermes-pass1','hermes-pass2']}}
    text=['# Token Plan Qwen3.8-Flash — Flash comparison addendum','',
          'Runs on October 2, 2026. Canonical prompts, task fixtures and scoring come from the active Flash comparison. '+
          'First attempts are retained, with only the explicitly authorized HA-04 adapter correction replacing its invalid pass-1 attempt. The required unscored tool transport probe and Hermes smoke are retained. '+
          'HumanEval/0–9 is a thinking-off speed/completion panel, with no correctness score.','',
          '**Hosted service results are separate from the controlled local GPU comparison.** '+
          'Provider weights, hardware, runtime, physical context and implicit cache cannot be fixed or inspected. '+
          'The model alias is rolling, and output limits differ from the local physical-context policy. '+
          'Every actual request was validated before being sent, and both harness requests and hosted wire requests were saved.','',
          link(ROOT/'protocol.lock.json','Protocol and prelaunch mismatch decisions')+' · '+
          link(WORK/'reports/flash-benchmarks-20260928/FLASH-COMPARISON-RESULTS-20261001.md','Existing local comparison')+'.','',
          '## Speed','',
          '| Panel | Requests | Output tokens | Request wall s | End-to-end output tok/s | Observed streaming tok/s | Cached input tokens |',
          '|---|---:|---:|---:|---:|---:|---:|']
    for stage,m in data['metrics'].items():
        if not m['requests']:continue
        rate=f"{m['observed_stream_rate']:.2f}" if m['observed_stream_rate'] else 'Unavailable'
        text.append(f"| {stage} | {m['requests']} | {m['output_tokens']} | {m['request_wall_seconds']:.2f} | {m['output_tokens_per_second_end_to_end']:.2f} | {rate} | {m['cached_prompt_tokens']} |")
    text+=['','End-to-end throughput is provider output-token usage divided by summed request wall time. '+
           'The streaming estimate is sum(completion_tokens − 1) divided by summed time between the first and last generated deltas; '+
           'chunks may contain several tokens, and networking/batching affects this estimate. It is not native GPU TG. '+
           'Hermes completion usage includes reported reasoning tokens. Smoke metrics are unscored.','',
           'Request timing begins when the serialized proxy submits the upstream request. Waiting for that local serialization lock is excluded from request-level timing; '+
           'the Hermes case clock includes all waiting, tool work and verifier overhead.','',
           '**Native PP and native TG are unavailable.** No prompt/decode computation times were returned. '+
           'Time to first delta includes queueing, network and generation, so dividing input tokens by it would not establish PP. '+
           'The raw token-ID append/cold-prefix grid, full-vocabulary fidelity and server RAM/weight/disk panels are unsupported by this hosted interface.','',
           '## Scores','']
    report=ROOT/'remote/tools/report.json'
    if report.exists():
        tool=read(report);assert tool['status']=='completed' and tool['total_scenarios']==15
        audit=tools_audit();data['tools']=dict(score=tool['final_score'],audit=audit,cases=tool['scores']['scenario_results'])
        text+=[f"Hard tools TC70–84: **{tool['final_score']}/100**, {tool['scores']['total_points']}/30 points. "+
               f"{audit['calls_with_environment_observations']}/{audit['model_originated_calls']} captured model tool calls have matching environment observations.",'',
               '| Case | Status | Points /2 |','|---|---|---:|']
        for row in tool['scores']['scenario_results']:text.append(f"| {row['scenario_id']} | {row['status']} | {row['points']} |")
        text+=['',link(report,'Official tool report')+' · '+link(ROOT/'tools/tool-execution-evidence.json','Tool execution evidence')+'.','']
    for stage in ['hermes-smoke','hermes-pass1','hermes-pass2']:
        summaries=list((ROOT/'remote'/stage/'cases').glob('*/summary.json'))
        if not summaries:continue
        assert len(summaries)==1
        summary=read(summaries[0])
        recovered = stage=='hermes-pass1' and (ROOT/'hermes-recovery.json').exists()
        assert summary['status']=='completed' or recovered
        profile='Token Plan Qwen3.8 Flash'
        score=summary['scores'][profile]
        cases=summary['resultsByModel'][profile]
        audit_paths=[summaries[0]]
        if recovered:
            additional=list((ROOT/'remote/hermes-pass1-continuation/cases').glob('*/summary.json'))
            assert len(additional)==1 and read(additional[0])['status']=='completed'
            cases+=read(additional[0])['resultsByModel'][profile]
            failed=read(summaries[0].parent/'raw/HA-04.json')
            failed.update(status='invalid-harness',score=None)
            cases.append(failed)
            cases.sort(key=lambda row:row['scenarioId'])
            assert [r['scenarioId'] for r in cases]==[f'HA-{i:02d}' for i in range(1,21)]
            score={'totalScore':None,'reason':'HA-04 first attempt failed client retry integrity; no valid full-pass score'}
            audit_paths+=additional
        amended=ROOT/'remote/amended-pass1/summary.json'
        amended_selected=stage=='hermes-pass1' and amended.exists()
        if amended_selected:
            amended_summary=read(amended)
            cases=amended_summary['resultsByModel'][profile]
            score=amended_summary['scores'][profile]
            corrected=list((ROOT/'remote/hermes-pass1-ha04-correction/cases').glob('*/summary.json'))
            assert len(corrected)==1 and read(corrected[0])['status']=='completed'
            audit_paths+=corrected
            assert len(cases)==20 and all(r['score'] is not None for r in cases)
        execution=hermes_execution_audit(stage,audit_paths)
        if stage!='hermes-smoke':
            assert [r['scenarioId'] for r in cases]==[f'HA-{i:02d}' for i in range(1,21)]
            if amended_selected or not recovered:
                assert execution['valid_cases']==20,execution
                assert execution['invalid_cases']==(['HA-04-attempt-1'] if amended_selected else []),execution
        data[stage]=dict(score=score,cases=cases,summary=str(amended if amended_selected else summaries[0]),execution=execution,
                        selected_cases=len(cases),all20_valid=stage!='hermes-smoke' and all(r['score'] is not None for r in cases) and len(cases)==20)
        label=(f"Amended verifier score: **{score['totalScore']}/100**, all 20 selected cases valid. Only HA-04 was replaced by its explicitly authorized corrected attempt; the original failed attempt is preserved." if amended_selected else
            'No valid full-pass score; 19 valid first cases and one invalid first case (HA-04), preserved without retry.' if recovered else f"Verifier score: **{score['totalScore']}/100**. "+('Unscored smoke.' if stage=='hermes-smoke' else 'All 20 selected cases valid.'))
        text+=[f"### {stage}",'',label,'',
               '| Case | Status | Score /100 | Wall s |','|---|---|---:|---:|']
        for row in cases:
            wall=row.get('timings',{}).get('durationMs',0)/1000
            text.append(f"| {row['scenarioId']} | {row['status']} | {row.get('score',0)} | {wall:.2f} |")
        text+=['',link(summaries[0],'Summary and per-case artifacts')+'.','']
        if amended_selected:text+=[link(amended,'Amended all-20 summary')+'.','']
        text+=[f"Verified {execution['captured_parent_calls_with_environment_results']} parent-agent tool calls against captured provider call IDs and environment completions. "+
               link(ROOT/stage/'tool-execution-evidence.json','Execution evidence')+'.','']
    inventory=read(WORK/'reports/flash-benchmarks-20260928/data/comparison-inventory-20261001.json')
    local_tools={row['model']:row for row in inventory['recommended_tools_extension']['models']}
    text+=['## Alongside the saved local results','',
           'These are the same task panels, with each stack\'s own recommended settings. Hosted and local hardware/cache/runtime conditions differ; this table does not establish a controlled hardware ranking.','',
           '| Model | HE0–9 request seconds | Hard tools /100 | Hermes P1 / P2 /100 |','|---|---:|---:|---|']
    for row in inventory['model_rows']:
        model=row['model']
        he=inventory['corrected_he09'][model]
        tool=local_tools.get(model)
        text.append(f"| {model} | {he['wall_seconds']:.2f} | {tool['score'] if tool else 'Skipped'} | {' / '.join(map(str,row['hermes_pass_scores']))} |")
    hs=[]
    for stage in ['hermes-pass1','hermes-pass2']:
        hs.append(('Invalid (HA-04)' if data[stage]['score']['totalScore'] is None else str(data[stage]['score']['totalScore'])) if stage in data else 'Pending')
    text.append(f"| Token Plan Qwen3.8 Flash (hosted) | {data['metrics']['he09']['request_wall_seconds']:.2f} | {data.get('tools',{}).get('score','Pending')} | {' / '.join(hs)} |")
    text+=['',link(WORK/'reports/flash-benchmarks-20260928/data/comparison-inventory-20261001.json','Local source inventory')+'.','',
           '## Serving and sampling','',
           'The hosted model uses its own official settings: thinking-off temperature 0.7, presence penalty 1.5; '+
           'thinking-on temperature 0.6, xhigh effort and preserved reasoning, presence penalty 0. '+
           'Top-k is 20; top-p is omitted in accordance with the provider recommendation to set one sampling control. '+
           'All seeds are retained (123 for HE/tools, 160915/160916/160917 for Hermes smoke/pass1/pass2). '+
           'Unsupported neutral local fields are removed by a recorded adapter. No custom scored output cap is added.','',
           'Provider references: [Qwen3.8-Flash guide](https://docs.qwencloud.com/developer-guides/getting-started/latest-model), '+
           '[OpenAI API](https://docs.qwencloud.com/api-reference/chat/openai-chat). '+
           'The model catalog and HTML documentation snapshots are stored beside this report.','',
           'The tool harness report calls its OpenAI-compatible client adapter `llamacpp`; that field does not identify the hosted provider runtime. '+
           'The provider runtime and effective seed/sampler values are not echoed. The saved hosted wire request is authoritative for submitted settings; '+
           'returned reasoning content verifies the requested thinking mode, and cache usage is recorded directly.','',
           'Bailian CLI was upgraded with authorization from 2.0.1 to 2.1.0. `bl config list`, `bl auth status` and '+
           '`bl model list --enrich` confirmed the saved Token Plan profile and catalog; benchmark requests used its existing key through a loopback proxy. '+
           'No key was copied to the benchmark host. Production model services were untouched.','',
           'A local adapter initially rejected the unscored transport probe before sending it to the provider. '+
           'Its failure receipt is preserved; fixing it repeated no provider generation or scored case.']
    if (ROOT/'hermes-recovery.json').exists():
        text+=['','In Hermes pass 1, the adapter rejected the native session-search internal summarizer (temperature 0.1, 10000-token internal limit) before provider generation. '+
               'The agent produced a passing HA-04 outcome after client errors, but the frozen integrity audit rejected its retries. '+
               'The original HA-04 remains invalid for scoring. The remaining 16 first-pass cases and full second pass proceeded after fixing the adapter. '+
               'The internal summarizer keeps its 10000-token limit and canonical messages, and uses hosted recommended 0.6/xhigh thinking. '+
               'This adaptation and all failed pre-provider requests are retained.']
    if (ROOT/'remote/amended-pass1/summary.json').exists():
        text+=['','The user then explicitly requested retrying HA-04 and amending pass 1. Only that case was rerun with seed 160916 and the corrected adapter, '+
               'after the complete second pass. The amended score uses 19 original valid cases and one authorized correction, evaluated by the original pinned scoring function. '+
               'The first-pass transport speed totals retain all attempts, including the original invalid HA-04 and its correction, and are diagnostic. '+
               link(ROOT/'hermes-pass1-ha04-correction/authorization.json','Correction authorization')+'.']
    if (ROOT/'helper-switch-receipt.json').exists():
        text+=['','Before delegation cases, inspection of the pinned helper code showed that child agents do not inherit the parent sampling overrides. '+
               'The proxy was updated to normalize child tool-agent requests to the stage sampler, matching the original local comparison proxy. '+
               'Only this run\'s verifier was briefly paused; all current provider requests drained before its tunnel was switched. '+
               'The same verifier resumed, and no scenario or generation was restarted. First-pass wall times include this maintenance pause; '+
               'second-pass timing uses the settled adapter. '+link(ROOT/'helper-switch-receipt.json','Switch receipt')+'.']
    save(ROOT/'results.json',data)
    (ROOT/'RESULTS.md').write_text('\n'.join(text)+'\n')
    files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and p.name not in ['receipt-manifest.json'] and '__pycache__' not in str(p)}
    save(ROOT/'receipt-manifest.json',files)
    print(json.dumps({stage: {'requests':m['requests'],'output_toks':m['output_tokens'],'wall_s':m['request_wall_seconds'],'stream_tps':m['observed_stream_rate']} for stage,m in data['metrics'].items()}))


if __name__=='__main__':main()
