"""Ciru clients against an identity-checked, owned Sozo server; no retries."""
import argparse,json,subprocess,time
from pathlib import Path
from benchmark_common import save
TASK=Path('/benchmark-storage')
REMOTE='/srv/llm/work/strata-v0140-20261006'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--panel',choices=['tools','hermes'],required=True);args=parser.parse_args()
    owner=REMOTE+'/ownership/'+args.panel
    deadline=time.monotonic()+900
    while True:
        receipt=subprocess.run(['ssh','-o','BatchMode=yes','sozo-usb4','cat '+owner+'/ready.json'],capture_output=True)
        if receipt.returncode==0:break
        assert time.monotonic()<deadline,'Owned server readiness timeout';time.sleep(2)
    identity=json.loads(receipt.stdout);assert identity['status']=='READY' and identity['meta']['context']==262144 and identity['meta']['generation_count']==0
    tunnel=None;code=1
    try:
        if args.panel=='tools':
            identity.update(benchmark_backend='strata',display_model='Strata v0.1.40',context=262144,effective_preflight_passed=True,
                command=[identity['meta']['exe'],*identity['meta']['args']],backend_source_proof=identity['meta'])
            save(TASK/'tools-identity.json',identity)
            tunnel=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-N','-L','127.0.0.1:18207:127.0.0.1:18140','sozo-usb4'],stderr=(TASK/'tools-tunnel.log').open('x'))
            time.sleep(1);assert tunnel.poll() is None
            subprocess.run([str(TASK/'python/bin/python3'),str(TASK/'run_tools.py'),'--model','strata-v0.1.40','--slug','strata-v0140','--identity',str(TASK/'tools-identity.json')],check=True)
        else:
            for stage in ['smoke','pass1','pass2']:
                subprocess.run([str(TASK/'python/bin/python3'),str(TASK/'run_hermes.py'),'--model','strata-v0.1.40','--run-id','stratav0140oct06','--stage',stage],check=True)
        code=0
    finally:
        if tunnel and tunnel.poll() is None:tunnel.terminate();tunnel.wait(timeout=10)
        receipt=dict(returncode=code,panel=args.panel,first_attempt_only=True)
        subprocess.run(['ssh','sozo-usb4',"cat > "+owner+'/CLIENT_COMPLETE.json'],input=json.dumps(receipt).encode(),check=True)
        save(TASK/(args.panel+'-client-exit.json'),receipt)
if __name__=='__main__':main()
