"""Verify the saved publication without generating model output."""
from pathlib import Path
import gzip,hashlib,json

ROOT=Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((ROOT/'publication/evidence-manifest.json').read_text())
for row in manifest['files']:
    p=ROOT/row['path'];assert sha(p)==row['published_sha256'],str(p)
    b=gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()
    assert hashlib.sha256(b).hexdigest()==row['uncompressed_sha256'],str(p)
comparison=json.loads((ROOT/'benchmark/comparison.json').read_text())
assert comparison['status']=='COMPLETE_AUDITED'
assert len(comparison['append_rows'])==18
assert all(r['cached_prefix_replayed_tokens']==0 and r['native_timings']['prompt_read']==r['prompt'] and r['native_timings']['reused']==r['depth'] for r in comparison['append_rows'])
assert comparison['clean_counting_cells']==2
data=json.loads((ROOT/'site/data/report.json').read_text())
assert len(data['rows'])==10 and len(data['race']['toolsRec']['tasks'])==15
for mode in ['hermesMean','hermes1','hermes2']:
    assert len(data['race'][mode]['tasks'])==20
    assert len(data['race'][mode]['lanes'])==10
    assert all(len(l['rows'])==20 for l in data['race'][mode]['lanes'])
    assert next(l for l in data['race'][mode]['lanes'] if l['key']=='strata')['score']==91
assert next(l for l in data['race']['hermes1']['lanes'] if l['key']=='qwenapi')['score']==98
assert next(l for l in data['race']['hermes2']['lanes'] if l['key']=='qwenapi')['score']==99
assert data['models']['carlos']['name']=='ROCmFPX2'
assert data['models']['qwenapi']['name']=='Qwen3.8 Flash · API'
checksums=ROOT/'SHA256SUMS'
count=0
if checksums.exists():
    for line in checksums.read_text().splitlines():
        h,rel=line.split('  ',1);assert sha(ROOT/rel)==h,rel;count+=1
print(json.dumps(dict(status='PASS',evidence_files=len(manifest['files']),distribution_files=count,
    numeric_preservation_checks=manifest['json_numeric_preservation_checks'],hermes_cases_per_pass=20,
    zero_replay_cells=18,inference_performed=False)))
