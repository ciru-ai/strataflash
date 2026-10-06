"""Read compact progress from preserved receipts; perform no inference."""
import json
from pathlib import Path

TASK=Path('/benchmark-storage')
for stage in ['smoke','pass1','pass2']:
    folder=TASK/'results/hermes'/stage
    if not folder.exists():continue
    for file in (folder/'cases').glob('*/summary.json'):
        data=json.loads(file.read_text());rows=data['resultsByModel'].get('strata-v0.1.40',[])
        case=lambda r:dict(case=r['scenarioId'],score=r['score'],status=r['status'],wall_seconds=round(r['wallSeconds'],2))
        out=dict(stage=stage,status=data['status'],finished=len(rows),last_cases=[case(r) for r in rows[-3:]],
            nonfull_scores=[case(r) for r in rows if r['score']<100])
        if data['status']=='completed':
            out['official_score']=data['scores']['strata-v0.1.40']['totalScore']
            out['case_wall_sum_seconds']=round(sum(r['wallSeconds'] for r in rows),3)
        statuses={};validated=0
        for transport in (folder/'http').glob('*/transport.json'):
            meta=json.loads(transport.read_text());key=str(meta['status']);statuses[key]=statuses.get(key,0)+1
            validated+=(transport.parent/'request-validation.json').exists()
        out.update(http_status_counts=statuses,validated_chat_requests=validated)
        print(json.dumps(out),flush=True)
for file in ['tools-client-exit.json','hermes-client-exit.json','client-queue-complete.json']:
    path=TASK/file
    if path.exists():print(file,path.read_text().strip(),flush=True)
