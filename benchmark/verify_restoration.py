"""Verify final production health and ownership without generating tokens."""
import json,time,urllib.request
from pathlib import Path
from run_owner import gpu_owners,hardware,state
from benchmark_common import save

TASK=Path('/srv/llm/work/strata-v0140-20261006')
def main():
    owner=TASK/'ownership/hermes'
    assert (owner/'completed.json').exists()
    restored=json.loads((owner/'restoration.json').read_text())
    assert restored['benchmark_gpu_released'] and restored['main_active_state_restored'] and restored['hardware_unchanged']
    current=state();assert current['ActiveState']=='active'
    request=urllib.request.Request('http://127.0.0.1:8081/health',headers={'Authorization':'Bearer local'})
    with urllib.request.urlopen(request,timeout=10) as response:
        code=response.status;health=json.load(response)
    assert code==200 and health.get('status')=='ok'
    pid=int(current['MainPID']);actual=gpu_owners();assert actual=={pid},actual
    before=json.loads((owner/'before.json').read_text())['hardware'];assert hardware()==before
    receipt=dict(status='VERIFIED',at=time.time(),main_service=current,health=health,http_status=code,
        gpu_owners=sorted(actual),benchmark_gpu_released=True,hardware_unchanged=True,inference_performed=False)
    save(TASK/'final-restoration-verification.json',receipt);print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
