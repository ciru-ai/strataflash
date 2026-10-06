"""Archive task-owned evidence over USB4 after every generation panel finishes."""
import hashlib,json,subprocess
from pathlib import Path

TASK=Path('/benchmark-storage')
REMOTE='/srv/llm/work/strata-v0140-20261006'
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def main():
    assert json.loads((TASK/'client-queue-complete.json').read_text())['status']=='COMPLETE'
    status=json.loads(subprocess.check_output(['ssh','sozo-usb4','cat '+REMOTE+'/status.json']))
    assert status['status']=='ALL_REQUESTED_GENERATION_COMPLETE_PENDING_AUDIT'
    for name in ['results','ownership','diagnostics']:
        destination=TASK/name;destination.mkdir(exist_ok=True)
        # Preserve existing Ciru client results; the Sozo tree contains native panels.
        subprocess.run(['rsync','-a','--checksum','sozo-usb4:'+REMOTE+'/'+name+'/',str(destination)+'/'],check=True)
    subprocess.run(['rsync','-a','--checksum','sozo-usb4:'+REMOTE+'/fidelity-capture.bin',str(TASK/'results/fidelity/fidelity-capture.bin')],check=True)
    for name in ['fidelity-launch-correction.json']:
        subprocess.run(['rsync','-a','--checksum','sozo-usb4:'+REMOTE+'/'+name,str(TASK/name)],check=True)
    receipt=json.loads((TASK/'results/fidelity/capture-result.json').read_text())
    files={}
    for name in ['candidate.f32le','fidelity-capture.bin']:
        path=TASK/'results/fidelity'/name
        files[name]=dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))
    assert files['candidate.f32le']['sha256']==receipt['candidate_sha256']
    # The native capture hash is verified directly against the source before cleanup.
    raw_sha=subprocess.check_output(['ssh','sozo-usb4','sha256sum '+REMOTE+'/fidelity-capture.bin'],text=True).split()[0]
    assert files['fidelity-capture.bin']['sha256']==raw_sha
    verification=dict(status='VERIFIED',source='sozo-usb4:'+REMOTE,
        destination=str(TASK),transport='Ciru-to-Sozo USB4',files=files,
        source_receipt_sha256=sha(TASK/'results/fidelity/capture-result.json'))
    save(TASK/'fidelity-archive-verification.json',verification)
    subprocess.run(['ssh','sozo-usb4','cat > '+REMOTE+'/fidelity-archive-verification.json'],input=json.dumps(verification).encode(),check=True)
    print(json.dumps(verification),flush=True)
if __name__=='__main__':main()
