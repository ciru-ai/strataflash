#!/usr/bin/env python3
"""Run one locked Hermes smoke or pass against one owned Sozo server."""
import argparse
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import threading
import time
import urllib.request
import urllib.error

LAB = Path('/benchmark-storage')
CAMPAIGN = LAB / 'runs/20260929-flash-hermes-recommended-thinking'
ROOT = None
SOURCE = CAMPAIGN / 'run-hermesagent20-sweep-v2.mjs'
MODEL = None
IMAGE_TAG = 'hermesagent20-verifier:artifact-v5'
IMAGE = 'sha256:8ded31e7e20c6bee17f53eb17e75e7677606ac7cdb82f0e22266bafebdf85bd8'
BENCHMARK_COMMIT = '57d7766bf3db8c40696e3ed937d43c8c85f4cd6c'
TUNNEL_PORT, PROXY_PORT = 18197, 18198


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2) + '\n')


def fetch(route):
    with urllib.request.urlopen(f'http://127.0.0.1:{TUNNEL_PORT}{route}', timeout=10) as response:
        return response.read()


class Capture(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    index = 0
    seed = None
    counter_lock = threading.Lock()

    def log_message(self, *args):
        pass

    def relay(self):
        with self.counter_lock:
            index = Capture.index; Capture.index += 1
        folder = ROOT / 'http' / f'{index:04d}'
        folder.mkdir(parents=True)
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        (folder / 'request-body.json').write_bytes(body)
        forwarded = body
        if body:
            try:
                request = json.loads(body)
            except ValueError:
                request = None
            if isinstance(request, dict) and request.get('tools'):
                desired = dict(temperature=1.0, top_p=0.95, top_k=20,
                               min_p=0.0, presence_penalty=0.0,
                               reasoning_effort='xhigh', seed=Capture.seed)
                kwargs = request.get('chat_template_kwargs')
                changed = (any(request.get(key) != value for key, value in desired.items())
                           or not isinstance(kwargs, dict)
                           or kwargs.get('enable_thinking') is not True
                           or kwargs.get('preserve_thinking') is not True
                           or 'max_tokens' in request or 'max_completion_tokens' in request)
                if changed:
                    request.update(desired)
                    kwargs = kwargs.copy() if isinstance(kwargs, dict) else {}
                    kwargs.update(enable_thinking=True, preserve_thinking=True)
                    request['chat_template_kwargs'] = kwargs
                    request.pop('max_tokens', None)
                    request.pop('max_completion_tokens', None)
                    forwarded = json.dumps(request, separators=(',', ':')).encode()
                    (folder / 'forwarded-request-body.json').write_bytes(forwarded)
        if body and self.path.startswith('/v1/chat/completions'):
            effective=json.loads(forwarded)
            assert effective.get('model') == MODEL
            assert isinstance(effective.get('messages'),list) and effective['messages']
            if effective.get('tools'):
                for k,v in desired.items(): assert effective.get(k)==v,(k,effective.get(k),v)
                assert effective['chat_template_kwargs']['enable_thinking'] is True
                assert effective['chat_template_kwargs']['preserve_thinking'] is True
                assert effective.get('cache_prompt',True) is True
                assert 'max_tokens' not in effective and 'max_completion_tokens' not in effective
            save(folder/'request-validation.json',dict(status='PASS',mode='recommended-thinking' if effective.get('tools') else 'frozen harness internal summary',request_sha256=hashlib.sha256(forwarded).hexdigest()))
        start = time.monotonic()
        connection = http.client.HTTPConnection('127.0.0.1', TUNNEL_PORT, timeout=1800)
        record = dict(method=self.command, path=self.path, start_monotonic=start,
                      agent_request_rewritten=forwarded != body)
        try:
            headers = {'Content-Type': self.headers.get('Content-Type', 'application/json')}
            connection.request(self.command, self.path, body=forwarded or None, headers=headers)
            upstream = connection.getresponse()
            record.update(status=upstream.status, content_type=upstream.getheader('Content-Type'))
            self.send_response(upstream.status)
            for key in ('Content-Type', 'Content-Length'):
                value = upstream.getheader(key)
                if value is not None:
                    self.send_header(key, value)
            self.send_header('Connection', 'close'); self.end_headers()
            with (folder / 'response-body.bin').open('xb') as output:
                while chunk := upstream.read1(65536):
                    if 'first_byte_seconds' not in record:
                        record['first_byte_seconds'] = time.monotonic() - start
                    output.write(chunk); output.flush()
                    self.wfile.write(chunk); self.wfile.flush()
        except BaseException as error:
            record['error'] = dict(type=type(error).__name__, message=str(error))
            raise
        finally:
            record['wall_seconds'] = time.monotonic() - start
            save(folder / 'transport.json', record)
            connection.close()

    do_POST = relay
    do_GET = relay


def main():
    global ROOT, MODEL
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=['v5.0', 'v4.4', 'HaloBox', 'Gufo',
                                           'AgentionAI AP-Q5_K_XL', 'Halogen', 'strata-v0.1.40'], required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--stage', choices=['smoke', 'pass1', 'pass2'], required=True)
    parser.add_argument('--cases', default=None, help='Comma-separated HA case IDs for a smoke or explicit recovery')
    parser.add_argument('--smoke-exit', type=Path,
                        help='Completed smoke exit from an earlier owned server for a resumed full pass')
    args = parser.parse_args()
    assert args.run_id.isascii() and args.run_id.replace('-', '').isalnum()
    MODEL = args.model
    cases = (args.cases.split(',') if args.cases else
             ['HA-01', 'HA-05', 'HA-20'] if args.stage == 'smoke' else
             [f'HA-{i:02d}' for i in range(1, 21)])
    assert len(cases) == len(set(cases)) and all(c in [f'HA-{i:02d}' for i in range(1,21)] for c in cases)
    native = MODEL in ('v5.0', 'v4.4')
    base = Path('benchmark/results/hermes')
    ROOT = base / args.stage
    assert not ROOT.exists()
    if args.stage != 'smoke':
        smoke_exit = args.smoke_exit or (base / 'smoke/exit.json')
        smoke = json.loads(smoke_exit.read_text())
        assert smoke['returncode'] == 0 and smoke['status'] == 'finished-for-audit'
        prior = json.loads((smoke_exit.parent / 'protocol.lock.json').read_text())
        assert prior['model'] == args.model and prior['stage'] == 'smoke'
    else:
        assert args.smoke_exit is None
    frozen = json.loads((CAMPAIGN / 'protocol.lock.json').read_text())
    for receipt in frozen['source_files']:
        if '/patched/' not in receipt['path']:
            continue
        name = Path(receipt['path']).name
        live = CAMPAIGN / ('HermesAgent-20/verification/' + name if name in
            ('core.mjs', 'agent-runner.py', 'hermes-runtime.mjs') else name)
        assert sha(live) == receipt['sha256'], live
    addendum = json.loads((CAMPAIGN / 'loop-watcher-addendum.json').read_text())
    for filename, digest in addendum['files'].items():
        assert sha(CAMPAIGN / filename) == digest, filename
    actual_harness=LAB/'runs/20260929-flash-hermes-unlimited'
    assert sha(actual_harness/'HermesAgent-20/dist/lib/benchmark.js')==frozen['benchmark']['compiled_benchmark_sha256']
    for receipt in frozen['source_files']:
        if '/patched/' not in receipt['path']:continue
        name=Path(receipt['path']).name
        if name in ('core.mjs','agent-runner.py','hermes-runtime.mjs'):
            live=actual_harness/'HermesAgent-20/verification'/name
            assert sha(live)==receipt['sha256'],live
    for filename,digest in addendum['primary_watcher_v4']['files'].items():
        assert sha(actual_harness/filename)==digest,filename
    assert socket.gethostname() == 'ciru'
    assert subprocess.check_output(['git', '-C', str(CAMPAIGN / 'HermesAgent-20'), 'rev-parse', 'HEAD'], text=True).strip() == BENCHMARK_COMMIT
    image = json.loads(subprocess.check_output([str(LAB / 'bin/bench-docker'), 'image', 'inspect', IMAGE_TAG]))
    assert image[0]['Id'] == IMAGE
    route = subprocess.check_output(['ip', 'route', 'get', '127.0.0.1'], text=True)
    assert 'thunderbolt0' in route and 'src 127.0.0.1' in route
    assert subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'sozo-usb4', 'hostname'], text=True).strip() == 'sozo'
    ROOT.mkdir(parents=True)
    server_receipt = 'benchmark/ownership/hermes/ready.json'
    identity = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'sozo-usb4',
                                        f'cat -- {shlex.quote(server_receipt)}'])
    (ROOT / 'server-receipt.json').write_bytes(identity)
    server_identity = json.loads(identity)
    save(ROOT / 'effective-harness.json', frozen)
    save(ROOT / 'loop-watcher-addendum.json', addendum)
    (ROOT / 'harness.mjs').write_bytes(SOURCE.read_bytes())
    tunnel = proxy = process = None
    started = time.monotonic()
    try:
        tunnel = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes', '-N',
                    '-L', f'127.0.0.1:{TUNNEL_PORT}:127.0.0.1:{18140 if MODEL == 'strata-v0.1.40' else 18097 if native else 18098}', 'sozo-usb4'],
                    stdout=subprocess.DEVNULL, stderr=(ROOT / 'tunnel.log').open('x'))
        deadline = time.monotonic() + 30
        while True:
            assert tunnel.poll() is None, 'Tunnel exited'
            try:
                models = json.loads(fetch('/v1/models'))
                assert any(d.get('id') == MODEL or MODEL in d.get('aliases', []) for d in models['data'])
                break
            except (OSError, ValueError):
                assert time.monotonic() < deadline, 'Tunnel readiness timeout'
                time.sleep(.5)
        save(ROOT / 'models.json', models)
        try:
            props = json.loads(fetch('/props'))
            save(ROOT / 'props.json', props)
            template = props.get('chat_template')
        except (OSError, ValueError, urllib.error.HTTPError):
            template = None
        if native or MODEL in ('HaloBox', 'AgentionAI AP-Q5_K_XL', 'strata-v0.1.40'):
            assert isinstance(template, str) and template
        seed = {'smoke': 160915, 'pass1': 160916, 'pass2': 160917}[args.stage]
        Capture.seed = seed
        extra = dict(top_k=20, min_p=0.0, presence_penalty=0.0, seed=seed,
                     chat_template_kwargs=dict(enable_thinking=True, preserve_thinking=True))
        if MODEL != 'Halogen': extra['cache_prompt'] = True
        else: extra['drafter'] = 'mtp'
        cmd = ['node', str(SOURCE), '--profile', MODEL, '--skip-switch', '--skip-import',
               '--image', IMAGE_TAG,
               '--base-url', f'http://127.0.0.1:{PROXY_PORT}/v1', '--model-id', MODEL,
               '--auth-mode', 'bearer', '--api-key', 'local', '--scenario-timeout-ms', '1800000',
               '--fetch-retries', '0', '--temperature', '1.0', '--top-p', '0.95',
               '--reasoning-effort', 'xhigh',
               '--request-extra-body', json.dumps(extra), '--run-root', str(ROOT / 'cases')]
        for case in cases:
            cmd += ['--scenario', case]
        save(ROOT / 'protocol.lock.json', dict(classification='local-custom-recommended-thinking', stage=args.stage, command=cmd,
            model=MODEL, model_sha256=server_identity['model_sha256'],
            cases=cases, server_identity=server_receipt, server_identity_sha256=hashlib.sha256(identity).hexdigest(),
            runtime_identity=server_identity.get('executable_sha256', server_identity.get('image_id')),
            chat_template_sha256=hashlib.sha256(template.encode()).hexdigest() if template else None,
            campaign_lock_sha256=sha(CAMPAIGN / 'protocol.lock.json'),
            harness_sha256=sha(SOURCE), runner_sha256=sha(__file__), verifier_image=IMAGE,
            benchmark_commit=BENCHMARK_COMMIT, agent_commit='ea74f61d983ebdfd6a863c45761d1b38081f1d08',
            sources=['https://github.com/stevibe/HermesAgent-20','https://github.com/nousresearch/hermes-agent'],
            transport=route.strip(),
            policy='Unchanged scenarios and scoring. No effective turn cap; 30-minute case clock; repeated identical tool cycle stops as failure. First attempt; no fetch retries; stop on failed integrity.',
            smoke_dependency=None if args.stage == 'smoke' else dict(
                path=str(smoke_exit), sha256=sha(smoke_exit)),
            context=262144, thinking=True, preserve_thinking=True, reasoning_effort='xhigh',
            max_tokens=None, max_turns=2147483647, temperature=1.0, top_p=0.95,
            top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0,
            extra_body=extra, seed=seed))
        try: (ROOT / 'metrics-before.prom').write_bytes(fetch('/metrics'))
        except (OSError, urllib.error.HTTPError): pass
        subprocess.run(['python3',str(Path(__file__).parent/'validate_sweep_scope.py'),'hermesagent20','--source-path',str(Path(__file__).parent/'scope-latest-suite.json')],check=True)
        proxy = ThreadingHTTPServer(('127.0.0.1', PROXY_PORT), Capture)
        thread = threading.Thread(target=proxy.serve_forever, daemon=True); thread.start()
        with (ROOT / 'runner.log').open('x') as log:
            run_env = dict(os.environ, BENCHLAB_ROOT=str(LAB))
            run_env.pop('HERMES_AGENT_20_MAX_TOKENS', None)
            process = subprocess.Popen(cmd, cwd=LAB, env=run_env,
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(json.dumps(dict(event='HERMES_STARTED', stage=args.stage, pid=process.pid, root=str(ROOT))), flush=True)
        while process.poll() is None:
            assert time.monotonic() - started < (len(cases)*1800 + 600), 'Task wall deadline exhausted'
            time.sleep(1)
        save(ROOT / 'exit.json', dict(returncode=process.returncode, wall_seconds=time.monotonic()-started,
                                    status='finished-for-audit' if process.returncode == 0 else 'invalid-harness'))
        print((ROOT / 'exit.json').read_text(), flush=True)
        assert process.returncode == 0, 'Hermes integrity or runtime failure: inspect first trajectory'
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
        if tunnel and tunnel.poll() is None:
            try:
                (ROOT / 'metrics-after.prom').write_bytes(fetch('/metrics'))
            except OSError:
                pass
        if proxy:
            proxy.shutdown(); proxy.server_close()
        if tunnel:
            tunnel.terminate(); tunnel.wait(timeout=10)
        save(ROOT / 'cleanup.json', dict(tunnel_exited=tunnel is None or tunnel.poll() is not None,
             runner_exited=process is None or process.poll() is not None, production_service_untouched=True))


if __name__ == '__main__':
    main()
