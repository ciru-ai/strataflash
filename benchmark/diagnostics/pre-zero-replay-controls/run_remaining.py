"""One frozen queue; never retry a completed panel or replace first outcomes."""
import json,subprocess,time
from benchmark_common import *
def main():
    deadline=time.monotonic()+7200
    while not (TASK/'ownership/he09/restoration.json').exists():
        assert time.monotonic()<deadline,'HE owner completion deadline';time.sleep(2)
    restored=json.loads((TASK/'ownership/he09/restoration.json').read_text());assert restored['main_active_state_restored'] and restored['benchmark_gpu_released']
    assert json.loads((TASK/'results/he09/summary.json').read_text())['status']=='COMPLETE'
    completed=['he09']
    for panel in ['counting-zero-replay','fidelity','tools','hermes']:
        save(TASK/'status.json',dict(status='RUNNING',completed_panels=completed,current=panel))
        subprocess.run([str(TASK/'python/bin/python3'),str(TASK/'run_owner.py'),'--panel',panel],check=True)
        completed.append(panel)
    save(TASK/'status.json',dict(status='ALL_REQUESTED_GENERATION_COMPLETE_PENDING_AUDIT',completed_panels=completed,current='audit'))
if __name__=='__main__':main()
