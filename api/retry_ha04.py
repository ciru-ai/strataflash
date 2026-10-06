#!/usr/bin/env python3
"""User-authorized correction of only pass-1 HA-04; retain original attempt."""
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import threading
import time

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('retry_cloud',ROOT/'run_cloud.py')
cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud)
cloud.STAGE='hermes-pass1'
cloud.COUNTER=max(int(p.name) for p in ROOT.glob('*/http/*'))+1
out=ROOT/'hermes-pass1-ha04-correction'
assert not out.exists(),'This authorized correction can run only once'
out.mkdir()
cloud.save(out/'authorization.json',dict(request='isnt a broken adapter your fault? retry 4 with corrected and amend pass1',
    scope='Only HA-04 from pass1; original seed160916; no other case repeated',
    original_invalid_artifact=str(ROOT/'remote/hermes-pass1'),runner_sha256=cloud.sha(__file__)))
cloud.scope('hermesagent20')
server=cloud.ThreadingHTTPServer(('127.0.0.1',18738),cloud.Proxy)
threading.Thread(target=server.serve_forever,daemon=True).start()
ssh=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ExitOnForwardFailure=yes',
     '-o','ServerAliveInterval=30','-i','/home/benchmark/.ssh/id_ed25519_omarchy_migration',
     '-N','-R','127.0.0.1:18738:127.0.0.1:18738','crown@127.0.0.1']
tunnel=subprocess.Popen(ssh)
try:
    time.sleep(.5);assert tunnel.poll() is None
    cmd=['node',cloud.LAB+'/runs/20260929-flash-hermes-recommended-thinking/run-hermesagent20-sweep-v2.mjs',
         '--profile','Token Plan Qwen3.8 Flash','--skip-switch','--skip-import','--image','hermesagent20-verifier:artifact-v5',
         '--base-url','http://127.0.0.1:18738/v1','--model-id',cloud.MODEL,'--auth-mode','bearer','--api-key','local',
         '--scenario-timeout-ms','1800000','--fetch-retries','0','--temperature','.6','--reasoning-effort','xhigh',
         '--request-extra-body',json.dumps(dict(top_k=20,presence_penalty=0.,seed=160916,enable_thinking=True,preserve_thinking=True)),
         '--run-root',cloud.REMOTE+'/hermes-pass1-ha04-correction/cases','--scenario','HA-04']
    cloud.save(out/'command.json',cmd)
    cloud.remote('BENCHLAB_ROOT='+shlex.quote(cloud.LAB)+' '+shlex.join(cmd),out/'runner.log')
    cloud.save(out/'COMPLETE.json',dict(case='HA-04',seed=160916,scored_case_retries=1,user_authorized=True))
finally:
    tunnel.terminate();tunnel.wait(timeout=15)
    server.shutdown();server.server_close()
    cloud.save(out/'cleanup.json',dict(proxy_closed=True,tunnel_closed=True,production_services_untouched=True))
