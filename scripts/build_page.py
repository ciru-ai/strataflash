"""Build the static publication from frozen saved results, with no inference."""
from pathlib import Path
import csv, io, json, shutil

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'; SITE.mkdir(exist_ok=True)
INPUT=ROOT/'report/inputs'
def read(p):
    p=ROOT/p
    if p.exists(): return json.loads(p.read_text())
    import gzip
    return json.loads(gzip.decompress(p.with_name(p.name+'.gz').read_bytes()))
comparison=read(Path('benchmark/comparison.json'))
base=read(Path('report/inputs/nonhermes.json'))
hermes=read(Path('report/inputs/hermes.json'))
models=json.loads((INPUT/'models.json').read_text()); badges=json.loads((INPUT/'badges.json').read_text())
rows={r['id']:r for r in comparison['rows']}
models['strata']={'name':'Strata v0.1.40','short':'Strata','color':'#f3eee0','tag':'UD-IQ4_XS'}
badges['strata']='assets/strata-mark.svg'
models['orca']['name']='Orca';models['orca']['short']='Orca'
models['carlos']['name']='ROCmFPX2';models['carlos']['short']='ROCmFPX2'
key=lambda k: {'strata-v0140':'strata','qwen-api':'qwenapi'}.get(k,k)

tools=base['panels']['toolsRecommended']
tasks=[dict(id=t['taskId'],title=t['title']) for t in tools['taskDefinitions']]
lanes=[]
for item in comparison['rows']:
    if item.get('tools_score') is None: continue
    if item['id']=='strata-v0140':
        raw=read(Path('benchmark/results/tools/full/report.json'))['scores']['scenario_results']
        rr=[dict(s=t['duration_seconds'],st=t['status'],p=t['points'],c=len(t['tool_calls_made']),sum=t['summary']) for t in raw]
        ids=[t['scenario_id'] for t in raw]
    else:
        raw=[t for t in tools['cases'] if t['modelId']==item['id']]
        rr=[dict(s=t['durationSeconds'],st=t['status'],p=t['points'],c=t['toolCallCount'],sum=t['summary']) for t in raw]
        ids=[t['taskId'] for t in raw]
    assert ids==[t['id'] for t in tasks]
    assert len(rr)==15 and abs(sum(t['s'] for t in rr)-item['tools_wall'])<.002
    assert round(sum(t['p'] for t in rr)/30*100)==item['tools_score']
    lanes.append(dict(key=key(item['id']),score=item['tools_score'],rows=rr))

race={'toolsRec':dict(label='Tools · recommended sampler',kind='tools',speed=10,
    blurb='15 cases · nonthinking · each model’s card sampler · case wall time. Lights show the original verifier outcomes. ROCmFPX2 uses its official 73/100; the separate reviewed score is 80.',tasks=tasks,lanes=lanes)}
htasks=[dict(id=t['id'],title=t['label']) for t in hermes['tasks']]
passes={1:[],2:[]}
for item in comparison['rows']:
    if item['id']=='strata-v0140':
        for n in [1,2]:
            paths=list((ROOT/f'benchmark/results/hermes/pass{n}/cases').glob('*/summary.json'))
            assert len(paths)==1
            raw=json.loads(paths[0].read_text())['resultsByModel']['strata-v0.1.40']
            rr=[dict(s=t['wallSeconds'],st=t['status'],p=t['score'],c=t['primaryToolCalls'],sum=t['verifier']['summary']) for t in raw]
            assert [t['scenarioId'] for t in raw]==[t['id'] for t in htasks]
            passes[n].append(dict(key='strata',score=item['hermes_pass_scores'][n-1],rows=rr))
    elif item['id']=='qwen-api':
        for n in [1,2]:
            raw=read(Path(f'api/pass{n}/summary.json'))['resultsByModel']
            assert len(raw)==1
            raw=next(iter(raw.values()))
            assert [t['scenarioId'] for t in raw]==[t['id'] for t in htasks]
            rr=[dict(s=t['wallSeconds'],st=t['status'],p=t['score'],c=t['primaryToolCalls'],sum=t['verifier']['summary']) for t in raw]
            assert abs(sum(t['s'] for t in rr)-item['source_passes'][n-1]['case_wall_sum_seconds'])<.002
            passes[n].append(dict(key='qwenapi',score=item['hermes_pass_scores'][n-1],rows=rr))
    else:
        m=next(m for m in hermes['models'] if m['id']==item['id'])
        for run in m['runs']:
            n=run['pass']; raw=run['tasks']
            assert [t['id'] for t in raw]==[t['id'] for t in htasks]
            rr=[dict(s=t['wall_seconds'],st=t['status'],p=t['score'],c=t['tools'],sum=t.get('verifier_summary',t.get('summary',''))) for t in raw]
            assert run['official_score']==item['hermes_pass_scores'][n-1]
            passes[n].append(dict(key=item['id'],score=run['official_score'],rows=rr))

mean=[]
for a,b in zip(passes[1],passes[2]):
    assert a['key']==b['key'] and len(a['rows'])==len(b['rows'])==20
    rr=[dict(s=(x['s']+y['s'])/2,st=x['st'] if x['st']==y['st'] else 'mixed',p=(x['p']+y['p'])/2,
        c=(x['c']+y['c'])/2 if x['c'] is not None and y['c'] is not None else None,sum=f"Pass 1: {x['sum']} Pass 2: {y['sum']}") for x,y in zip(a['rows'],b['rows'])]
    item=next(r for r in comparison['rows'] if key(r['id'])==a['key'])
    assert abs(sum(t['s'] for t in rr)-item['hermes_mean_case_wall'])<.002
    assert (a['score']+b['score'])/2==item['hermes_score']
    mean.append(dict(key=a['key'],score=item['hermes_score'],rows=rr))
for mode,label,ls in [('hermesMean','Hermes · mean',mean),('hermes1','Hermes · pass 1',passes[1]),('hermes2','Hermes · pass 2',passes[2])]:
    race[mode]=dict(label=label,kind='hermes',speed=10,tasks=htasks,lanes=ls,
        blurb='20 cases in each pass · recommended thinking sampler · scored case wall only. Mean averages corresponding cases from both passes. Qwen API includes the authorized HA-04 correction; the adapter repair pause is excluded.')
race_template=(ROOT/'report/templates/race.js').read_text()
(SITE/'race.js').write_text(race_template.replace('__MODELS__',json.dumps(models,ensure_ascii=False)).replace('__BADGES__',json.dumps(badges)).replace('__RACE__',json.dumps(race,ensure_ascii=False)))
(SITE/'race.css').write_text((ROOT/'report/templates/race.css').read_text())
data={'rows':comparison['rows'],'models':models,'memory':comparison['memory'],
    'append':[], 'cold':[], 'resources':[], 'race':race}
for panel,out,fields in [('appendPrefill','append',['modelId','promptTokens','depthTokens','pp','tg','ttfpMs','replayTokens','equal512Output']),('coldPrefill','cold',['modelId','inputTokens','tps']),('memory','resources',['modelId','packageGiB','servingGiB','hostPressureGiB','method'])]:
    data[out]=[{k:r.get(k) for k in fields} for r in base['panels'][panel]['rows']]
for r in comparison['append_rows']:
    data['append'].append(dict(modelId='strata',promptTokens=r['prompt'],depthTokens=r['depth'],pp=r['native_pp'],tg=r['native_tg'],ttfpMs=r['ttfp_seconds']*1000,replayTokens=0,equal512Output=r['output_audit']['clean_counting']))
for r in comparison['cold_rows']:
    data['cold'].append(dict(modelId='strata',inputTokens=r['native_timings']['prompt_tokens'],tps=r['native_pp']))
data['resources'].insert(0,dict(modelId='strata',packageGiB=comparison['rows'][0]['serving_asset_gib'],
    servingGiB=max(r['peak_extra_ram_bytes'] or 0 for r in comparison['memory'])/2**30,
    hostPressureGiB=max(r['peak_extra_ram_bytes'] or 0 for r in comparison['memory'])/2**30,
    method='Peak host MemAvailable drop from post-production-stop pre-load sample'))
for r in data['rows']:
    r.pop('source_paths',None);r.pop('source_passes',None)
    r['key']=key(r['id']);r['name']=models[r['key']]['name'];r['color']=models[r['key']]['color']
(SITE/'data').mkdir(exist_ok=True)
(SITE/'data/report.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
(SITE/'data.js').write_text('window.STRATA_DATA='+json.dumps(data,ensure_ascii=False)+';\n')
csvout=io.StringIO();fields=['model','he09_native_tg','he09_timing','he09_wall','tools_score','tools_wall','hermes_score','hermes_mean_case_wall','fidelity_kl','fidelity_top1','fidelity_ppl']
w=csv.DictWriter(csvout,fields,extrasaction='ignore');w.writeheader();w.writerows(data['rows'])
(SITE/'data/comparison.csv').write_text(csvout.getvalue())
for name in ['index.html','style.css','charts.js']:
    shutil.copyfile(ROOT/'report/templates'/name,SITE/name)
print(json.dumps(dict(status='BUILT',models=len(data['rows']),tools_cases=15,hermes_cases_per_pass=20,hermes_passes=2,zero_replay_cells=len(comparison['append_rows']),inference_performed=False)))
