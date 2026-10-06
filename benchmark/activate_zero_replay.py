"""CPU-only staging of compiled benchmark controls and immutable receipts."""
import hashlib,json,shutil,subprocess
from pathlib import Path
TASK=Path('/benchmark-storage')
REMOTE='/srv/llm/work/strata-v0140-20261006'
def sha(path):return hashlib.file_digest(Path(path).open('rb'),'sha256').hexdigest()
assert subprocess.check_output(['git','-C',str(TASK/'source'),'rev-parse','HEAD'],text=True).strip()=='1735d6471df29b42c26170efaac1f1446a58640f'
commands=subprocess.check_output(['ninja','-C',str(TASK/'build-halo'),'-t','commands','strata-benchmark'],text=True).splitlines()
hip=[r for r in commands if '--offload-arch=gfx1151' in r and ' -c ' in r]
assert len(hip)>=64 and all('-O3' in r and '-DNDEBUG' in r for r in hip)
(TASK/'zero-replay-hip-commands.txt').write_text('\n'.join(hip)+'\n')
old=json.loads((TASK/'optimized-build-receipt.json').read_text())
assert sha(TASK/'build-halo/strata')==old['binaries']['strata']
unit=subprocess.run(['ssh','sozo-usb4','systemctl --user is-active strata-v0140-remaining-20261006.service'],capture_output=True,text=True)
assert unit.stdout.strip()=='inactive',unit.stdout
listeners=subprocess.check_output(['ssh','sozo-usb4',"ss -Hltn '( sport = :18140 )'"],text=True)
assert not listeners.strip(),'Owned benchmark endpoint still running'
diag=TASK/'diagnostics/pre-zero-replay-controls';diag.mkdir(parents=True,exist_ok=True)
names=[p.name for p in (TASK/'zero-replay-update').iterdir() if p.is_file()]
for name in names+['optimized-build-receipt.json']:
    if (TASK/name).exists() and not (diag/name).exists():shutil.copy2(TASK/name,diag/name)
for name in names:shutil.copy2(TASK/'zero-replay-update'/name,TASK/name)
subprocess.run(['ssh','sozo-usb4','mkdir -p '+REMOTE+'/diagnostics/pre-zero-replay-controls && cp '+REMOTE+'/optimized-build-receipt.json '+REMOTE+'/benchmark_frontend.py '+REMOTE+'/run_counting.py '+REMOTE+'/diagnostics/pre-zero-replay-controls/'],check=True)
new=dict(old,zero_replay_cache_guard=True,zero_replay_contract_sha256=sha(TASK/'zero-replay-contract.json'),
    zero_replay_hip_commands_sha256=sha(TASK/'zero-replay-hip-commands.txt'),
    prior_build_receipt_sha256=sha(diag/'optimized-build-receipt.json'),
    benchmark_source_sha256=sha(TASK/'source/src/program/generate_benchmark.cpp'),
    binaries=dict(old['binaries'],**{'strata-benchmark':sha(TASK/'build-halo/strata-benchmark')}))
(TASK/'optimized-build-receipt.json').write_text(json.dumps(new,indent=2)+'\n')
for name in names+['optimized-build-receipt.json','benchmark-build-receipt.json','benchmark-source.diff','zero-replay-hip-commands.txt']:
    subprocess.run(['scp',str(TASK/name),'sozo-usb4:'+REMOTE+'/'+name],check=True)
subprocess.run(['scp',str(TASK/'build-halo/strata-benchmark'),'sozo-usb4:'+REMOTE+'/bin/strata-benchmark'],check=True)
subprocess.run(['ssh','sozo-usb4','sha256sum '+REMOTE+'/bin/strata-benchmark'],check=True)
archive=TASK/'diagnostics/periodic-prefix-replay';archive.mkdir(parents=True,exist_ok=True)
for tree in ['ownership','results']:
    destination=archive/tree;destination.mkdir(exist_ok=True)
    subprocess.run(['rsync','-a','sozo-usb4:'+REMOTE+'/'+tree+'/counting',str(destination)+'/'],check=True)
(archive/'diagnostic-status.json').write_text(json.dumps(dict(status='STOPPED_BY_USER_CACHE_REQUIREMENT',ranked=False,
    corrected_protocol='zero-replay-contract.json',completed_requests=16,first_outputs_preserved=True),indent=2)+'\n')
print(json.dumps(dict(status='STAGED',benchmark_sha256=new['binaries']['strata-benchmark'],canonical_unchanged=True,optimized_hip_commands=len(hip))))
