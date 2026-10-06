"""Audit actual agent calls against completed tool events and observations."""
import hashlib,json
from pathlib import Path
TASK=Path('/benchmark-storage')
MODEL='strata-v0.1.40'
def sha(path):return hashlib.file_digest(Path(path).open('rb'),'sha256').hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def response_calls(raw,stream):
    if not stream:
        data=json.loads(raw)
        return [call for choice in data.get('choices',[]) for call in choice.get('message',{}).get('tool_calls') or []]
    calls={};done=False
    for line in raw.decode('utf-8').splitlines():
        if not line.startswith('data:'):continue
        payload=line[5:].strip()
        if payload=='[DONE]':done=True;continue
        data=json.loads(payload)
        for choice in data.get('choices',[]):
            for fragment in choice.get('delta',{}).get('tool_calls') or []:
                key=(choice.get('index',0),fragment['index'])
                call=calls.setdefault(key,dict(function=dict(name='',arguments='')))
                if fragment.get('id'):call['id']=fragment['id']
                for field in ['name','arguments']:
                    part=(fragment.get('function') or {}).get(field)
                    if part is not None:call['function'][field]+=part
    assert done,'Preserved SSE stream did not complete'
    return list(calls.values())
def hermes_extract(path):
    raw=Path(path).read_bytes();d=json.loads(raw);calls={}
    for message in d.get('messages',[]):
        if message.get('role')=='assistant':
            for call in message.get('tool_calls') or []:
                calls[call.get('id',call.get('call_id'))]=(call.get('function') or {}).get('name')
    observations={m.get('tool_call_id') for m in d.get('messages',[]) if m.get('role')=='tool'}
    complete=[]
    for event in d.get('toolEvents',[]):
        if event.get('phase')!='complete':continue
        ident=event.get('toolCallId');result=event.get('result')
        text=result if isinstance(result,str) else json.dumps(result,sort_keys=True)
        complete.append(dict(order=event.get('order'),name=event.get('name'),call_id=ident,
            agent_originated=ident in calls,has_observation=ident in observations or result is not None,
            observation_sha256=hashlib.sha256(text.encode()).hexdigest() if result is not None else None))
    verified=[e for e in complete if e['agent_originated'] and e['has_observation']]
    return dict(source=str(path),sha256=hashlib.sha256(raw).hexdigest(),agent_call_count=len(calls),
        reported_completed=d.get('toolCallsCompleted'),completed_events=len(complete),
        verified_completed_count=len(verified),tool_names=sorted({e['name'] for e in verified}),events=complete)
def main():
    root=TASK/'results';tool=root/'tools/full';report=json.loads((tool/'report.json').read_text())
    expected=[f'TC-{i}' for i in range(70,85)];rows=report['scores']['scenario_results']
    assert report['status']=='completed' and [r['scenario_id'] for r in rows]==expected
    initial=json.loads((TASK/'initial-requests.json').read_text())
    fixture_cases={next(m['content'] for m in b['messages'] if m['role']=='user'):case for b,case in zip(initial,expected)}
    assert len(fixture_cases)==15
    wire_calls=[]
    for folder in sorted((tool/'http').iterdir()):
        meta=json.loads((folder/'transport.json').read_text())
        if meta.get('classification')!='scored':continue
        assert meta['status']==200 and not meta.get('error')
        body=json.loads((folder/'request-body.json').read_text())
        prompt=next(m['content'] for m in body['messages'] if m['role']=='user');case=fixture_cases[prompt]
        for call in response_calls((folder/'response-body.bin').read_bytes(),body.get('stream',False)):
            function=call.get('function') or {};arguments=function.get('arguments')
            if isinstance(arguments,str):
                try:arguments=json.loads(arguments)
                except ValueError:arguments=None
            wire_calls.append(dict(case=case,id=call.get('id'),function=function,parsed_arguments=arguments,source=str(folder),
                response_sha256=sha(folder/'response-body.bin')))
    cases=[]
    for row in rows:
        trace=row['raw_log'];events=[]
        lines=trace.splitlines()
        for i,line in enumerate(lines):
            if not line.startswith('tool_call='):continue
            payload=line.split('=',1)[1];name=payload.split(' ',1)[0]
            try:arguments=json.loads(payload.split(' ',1)[1])
            except (IndexError,ValueError):arguments=None
            following=next((s for s in lines[i+1:] if s.startswith('tool_result=') or s.startswith('tool_call=')),None)
            observed=following is not None and following.startswith('tool_result=')
            matches=[c for c in wire_calls if c['case']==row['scenario_id'] and (c['function'] or {}).get('name')==name
                and arguments is not None and c['parsed_arguments']==arguments]
            events.append(dict(name=name,agent_originated=bool(matches),has_environment_observation=observed,
                observation_sha256=hashlib.sha256(following.encode()).hexdigest() if observed else None,
                wire_sources=sorted({c['source'] for c in matches})))
        assert all(e['agent_originated'] for e in events),row['scenario_id']
        cases.append(dict(case=row['scenario_id'],status=row['status'],points=row['points'],events=events,
            verified_execution_count=sum(e['agent_originated'] and e['has_environment_observation'] for e in events)))
    save(tool/'execution-evidence.json',dict(status='AUDITED',cases=cases,wire_calls=wire_calls,
        basis='Model response tool_calls plus actual mock-environment tool_call/tool_result trace. Empty execution is retained as a model outcome.'))
    passes=[]
    for stage in ['smoke','pass1','pass2']:
        folder=root/'hermes'/stage;files=list((folder/'cases').glob('*/summary.json'));assert len(files)==1
        summary=json.loads(files[0].read_text());expected=['HA-01','HA-05','HA-20'] if stage=='smoke' else [f'HA-{i:02d}' for i in range(1,21)]
        assert summary['status']=='completed' and summary['scenarioCount']==len(expected)
        rows=summary['resultsByModel'][MODEL];assert [r['scenarioId'] for r in rows]==expected
        evidence=[]
        for row in rows:
            assert row['attempt']==1
            ev=hermes_extract(Path(row['artifactDir'])/'agent-result.json');ev.update(case=row['scenarioId'],status=row['status'],score=row['score'],wall_seconds=row['wallSeconds'])
            assert ev['reported_completed']==row.get('primaryToolCalls'),row['scenarioId']
            evidence.append(ev)
        transport=[];ancillary=[];status_counts={}
        for http in sorted((folder/'http').iterdir()):
            meta=json.loads((http/'transport.json').read_text());assert not meta.get('error'),http
            key=str(meta['status']);status_counts[key]=status_counts.get(key,0)+1
            validation=http/'request-validation.json'
            if meta['path'].startswith('/v1/chat/completions'):
                assert meta['method']=='POST' and meta['status']==200 and validation.exists(),http
                checked=json.loads(validation.read_text());assert checked['status']=='PASS',http
                transport.append(checked)
            else:
                assert meta['method']=='GET' and (meta['status']==200 or
                    (meta['status']==404 and meta['path'] in ('/api/v1/models','/api/tags','/v1/props'))),http
                if meta['status']==404:ancillary.append(dict(path=meta['path'],status=404,source=str(http),
                    classification='Unscored optional provider autodiscovery; no model generation'))
        assert transport
        receipt=dict(status='AUDITED',stage=stage,cases=len(rows),official_score=summary['scores'][MODEL]['totalScore'],
            summary_path=str(files[0]),summary_sha256=sha(files[0]),case_wall_sum_seconds=sum(r['wallSeconds'] for r in rows),
            verified_tool_executions=sum(e['verified_completed_count'] for e in evidence),case_evidence=evidence,
            all_chat_http_status_200=True,validated_chat_requests=len(transport),
            http_status_counts=status_counts,ancillary_404_probes=ancillary,first_attempt_only=True)
        save(folder/'execution-evidence.json',receipt);passes.append(receipt)
    save(root/'agent-evidence-audit.json',dict(status='AUDITED',tools_cases=15,hermes_smoke_cases=3,hermes_scored_cases=40,
        tools_execution_count=sum(c['verified_execution_count'] for c in cases),
        hermes_execution_count=sum(p['verified_tool_executions'] for p in passes if p['stage']!='smoke'),
        hermes_pass_scores=[p['official_score'] for p in passes if p['stage']!='smoke']))
    print((root/'agent-evidence-audit.json').read_text())
if __name__=='__main__':main()
