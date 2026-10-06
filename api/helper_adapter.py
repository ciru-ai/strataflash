#!/usr/bin/env python3
"""Retain pinned Hermes proxy behavior for delegated agent requests."""
import copy
import importlib.util
import json
import subprocess
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cloud_adapter',ROOT/'run_cloud.py')
cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud)
original=cloud.wire_request


def validate_and_translate(body):
    log=(ROOT/'controller-hermes-continuation.log').read_text()
    cloud.STAGE='hermes-pass2' if 'START hermes-pass2' in log else 'hermes-pass1'
    canonical=copy.deepcopy(body)
    if canonical.get('tools'):
        # The frozen local proxy also applies stage sampling to child agents,
        # whose pinned delegate tool does not inherit request_overrides.
        canonical.update(temperature=.6,reasoning_effort='xhigh',
            seed=160917 if cloud.STAGE=='hermes-pass2' else 160916)
        canonical.pop('max_tokens',None)
        canonical.pop('max_completion_tokens',None)
    return original(canonical)


cloud.wire_request=validate_and_translate
cloud.COUNTER=max(int(p.name) for p in ROOT.glob('*/http/*'))+1
server=cloud.ThreadingHTTPServer(('127.0.0.1',18739),cloud.Proxy)
threading.Thread(target=server.serve_forever,daemon=True).start()
cloud.save(ROOT/'helper-adapter-ready.json',dict(port=18739,runner_sha256=cloud.sha(__file__),
    correction='Match pinned local proxy normalization for child tool-agent requests; preserve internal session summarizer limit',
    no_scored_case_repeated=True))
ssh=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ExitOnForwardFailure=yes',
     '-o','ServerAliveInterval=30','-i','/home/benchmark/.ssh/id_ed25519_omarchy_migration',
     '-N','-R','127.0.0.1:18738:127.0.0.1:18739','crown@127.0.0.1']
# The operator first pauses only this run's verifier and retires its old tunnel.
while not (ROOT/'SWITCH-HELPER-TUNNEL').exists():time.sleep(.1)
tunnel=subprocess.Popen(ssh)
time.sleep(.5)
assert tunnel.poll() is None
cloud.save(ROOT/'helper-tunnel-ready.json',dict(pid=tunnel.pid))
try:
    while not (ROOT/'COMPLETE.json').exists() and not (ROOT/'failure.json').exists():time.sleep(1)
finally:
    tunnel.terminate();tunnel.wait(timeout=15)
    server.shutdown();server.server_close()
    cloud.save(ROOT/'helper-adapter-cleanup.json',dict(proxy_closed=True,tunnel_closed=True))
