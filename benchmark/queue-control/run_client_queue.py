"""Wait for the Sozo queue's two agent panels, run each once, archive results."""
import json,subprocess,time
from pathlib import Path
from benchmark_common import save
TASK=Path('/benchmark-storage');REMOTE='/srv/llm/work/strata-v0140-20261006'
def main():
    for panel in ['tools','hermes']:
        deadline=time.monotonic()+36000
        while True:
            receipt=subprocess.run(['ssh','-o','BatchMode=yes','sozo-usb4','cat '+REMOTE+'/ownership/'+panel+'/ready.json'],capture_output=True)
            if receipt.returncode==0:break
            assert time.monotonic()<deadline,'Sozo queue readiness deadline';time.sleep(10)
        subprocess.run([str(TASK/'python/bin/python3'),str(TASK/'run_remote_clients.py'),'--panel',panel],check=True)
    save(TASK/'client-queue-complete.json',dict(status='COMPLETE',panels=['hard_tool_15','hermesagent20'],first_attempt_only=True))
if __name__=='__main__':main()
