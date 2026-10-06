"""Finite, exclusive Sozo ownership with production-service restoration."""
import argparse, fcntl, json, os, signal, socket, subprocess, time, urllib.request
from pathlib import Path
from benchmark_common import *
def state():
    return dict(row.split('=',1) for row in subprocess.check_output(['systemctl','--user','show','qwen-main.service','-p','ActiveState','-p','MainPID','-p','UnitFileState'],text=True).splitlines())
def gpu_owners():
    result=set()
    for fd in Path('/proc').glob('[0-9]*/fd/*'):
        try:
            if fd.readlink()==Path('/dev/kfd'):result.add(int(fd.parts[2]))
        except (OSError,PermissionError):pass
    return result
def hardware():
    gpu=Path('/sys/class/drm/card1/device')
    return dict(host=socket.gethostname(),performance_level=(gpu/'power_dpm_force_performance_level').read_text().strip(),
        cpu_governors=sorted(set(p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_governor'))),
        power_limits={p.name:p.read_text().strip() for p in (gpu/'hwmon').glob('hwmon*/power1_cap*') if p.is_file()})
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--panel',choices=['he09','counting','counting-zero-replay','fidelity','tools','hermes'],required=True);parser.add_argument('--seconds',type=int,default=90000);parser.add_argument('--wait-seconds',type=int,default=3600);args=parser.parse_args()
    assert socket.gethostname()=='sozo'
    deadline=time.monotonic()+args.wait_seconds;stable=None
    while True:
        current=state();owners=gpu_owners()
        expected={int(current['MainPID'])} if current['ActiveState']=='active' else set()
        # Let another controller finish restoring production before taking the host.
        free=current['ActiveState']=='active' and owners==expected
        if free:
            try:
                req=urllib.request.Request('http://127.0.0.1:8081/slots',headers={'Authorization':'Bearer local'})
                with urllib.request.urlopen(req,timeout=5) as response:free=all(not row['is_processing'] for row in json.load(response))
            except (OSError,ValueError):free=False
        stable=(stable or time.monotonic()) if free else None
        if stable and time.monotonic()-stable>=15:break
        assert time.monotonic()<deadline,'Host busy; no inference launched'
        time.sleep(2)
    out=TASK/'ownership'/args.panel;assert not out.exists();out.mkdir(parents=True)
    guard=Path('/tmp/flash-corrected-controller.lock').open('a');fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    prior=state();assert prior['ActiveState'] in ('active','inactive')
    expected={int(prior['MainPID'])} if prior['ActiveState']=='active' else set()
    assert gpu_owners()==expected,('Unexpected GPU owner',gpu_owners(),expected)
    if expected:
        req=urllib.request.Request('http://127.0.0.1:8081/slots',headers={'Authorization':'Bearer local'})
        with urllib.request.urlopen(req,timeout=10) as response:assert all(not x['is_processing'] for x in json.load(response))
    policy=hardware();save(out/'before.json',dict(main=prior,hardware=policy,resources=resources()))
    instrumented=args.panel in ('counting','counting-zero-replay','fidelity')
    exe=TASK/'bin'/('strata-benchmark' if instrumented else 'strata')
    build=json.loads((TASK/'optimized-build-receipt.json').read_text())
    assert build['all_hip_commands_optimized'] and build['binaries'][exe.name]==sha(exe)
    native=["--native",str(TASK/'weights/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf'),"--pack",str(TASK/'pack'),
        '--max-context','262144','--prefill','16384','--kv','int8','--resident-experts',
        '--expert-profile',str(TASK/'source/data/expert-profile.bin'),'--prompt-cache','0' if args.panel=='he09' else '6']
    if args.panel!='fidelity':native+=['--mtp',str(TASK/'mtp/rt'),'--spec','4','--lookup-chain','3','--mtp-q4','all']
    if args.panel in ('counting','counting-zero-replay'):native+=['--eos-ids','9999999']
    cfg=dict(exe=str(exe),args=native,cwd=str(TASK/'source'),tokenizer=str(TASK/'pack/tokenizer'),
        model_name=MODEL,log=str(out/'engine.log'),host='127.0.0.1',backend='hip',repeat_stop_tokens=0,
        engine_silence_s=1800,reasoning_loop_recovery=False,
        sampling=dict(temperature=1,top_p=.95,top_k=20,min_p=0,presence_penalty=0,repetition_penalty=1,frequency_penalty=0))
    save(out/'config.json',cfg)
    env=dict(os.environ,PATH='/run/current-system/sw/bin:'+str(TASK/'python/bin'),
        LD_LIBRARY_PATH=':'.join(map(str,[TASK/'runtime/lib',TASK/'runtime/rocm_sysdeps/lib',TASK/'runtime/lib/llvm/lib',Path('/nix/store/si4q3zks5mn5jhzzyri9hhd3cv789vlm-gcc-15.2.0-lib/lib')])),
        STRATA_HIPBLASLT_TUNING=str(TASK/'source/tools/hip/gfx1151-hipblaslt-100401.txt'),
        STRATA_BENCH_JOURNAL=str(out/'native-journal.jsonl'))
    if args.panel=='fidelity':env['STRATA_BENCH_LOGITS']=str(TASK/'fidelity-capture.bin')
    command=[str(TASK/'python/bin/python3'),str(TASK/'benchmark_frontend.py'),'--engine','strata','--config',str(out/'config.json'),'--port','18140']
    save(out/'protocol.lock.json',dict(panel=args.panel,command=command,config=cfg,context=262144,
        executable_sha256=sha(exe),model_sha256='5ce89370720f8bf90890f439361282104c1aa1482d4013bb9a50923e758e71a4',
        build_receipt_sha256=sha(TASK/'optimized-build-receipt.json'),
        experiment_plan_sha256=sha(TASK/'experiment-plan.json'),optional_numeric_fast_kernels=False,environment={k:v for k,v in env.items() if k.startswith('STRATA_')},
        zero_replay_contract_sha256=sha(TASK/'zero-replay-contract.json') if args.panel=='counting-zero-replay' else None,
        cpu_arena_policy='native mmap with resident CPU complement; avoid duplicating GPU-cached expert blobs in UMA'))
    server=None;stopped=False;error=None;samples=None
    try:
        if expected:subprocess.run(['systemctl','--user','stop','qwen-main.service'],check=True);stopped=True
        assert not gpu_owners()
        samples=Samples().__enter__()
        server=subprocess.Popen(command,env=env,stdout=(out/'server.log').open('x'),stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+900
        while True:
            assert server.poll() is None,'Server startup failed'
            try:
                meta=api('/bench/meta');break
            except (OSError,ValueError):assert time.monotonic()<deadline,'Server startup deadline';time.sleep(1)
        assert meta['context']==262144 and meta['generation_count']==0
        assert gpu_owners()=={meta['native_pid']},gpu_owners()
        assert hardware()==policy
        text=(out/'engine.log').read_text()
        assert 'hipBLASLt tuning enabled (90 rows' in text,'Pinned tuning table not loaded'
        assert 'gfx1151' in text,'Architecture not verified'
        save(out/'ready.json',dict(status='READY',native_pid=meta['native_pid'],pid=server.pid,base_url=BASE,
            executable_sha256=sha(exe),model_sha256='5ce89370720f8bf90890f439361282104c1aa1482d4013bb9a50923e758e71a4',meta=meta,resources=resources()))
        print(json.dumps(dict(event='READY',panel=args.panel,meta=meta)),flush=True)
        client=TASK/('run_he09.py' if args.panel=='he09' else 'run_counting.py' if args.panel in ('counting','counting-zero-replay') else 'run_fidelity.py' if args.panel=='fidelity' else 'absent-external-client')
        if client.exists():subprocess.run([str(TASK/'python/bin/python3'),str(client)],check=True)
        else:
            deadline=time.monotonic()+args.seconds
            while not (out/'CLIENT_COMPLETE.json').exists():
                assert not (out/'STOP').exists(),'Requested stop'
                assert server.poll() is None and time.monotonic()<deadline,'External client/owner deadline'
                assert resources()['ram_available']>4.5*1024**3,'RAM safety floor'
                time.sleep(1)
            completion=json.loads((out/'CLIENT_COMPLETE.json').read_text());assert completion['returncode']==0,completion
        save(out/'completed.json',dict(status='COMPLETE',panel=args.panel))
    except BaseException as failure:
        error=failure;save(out/'failure.json',dict(type=type(failure).__name__,message=str(failure),retry=False));raise
    finally:
        if samples:
            samples.__exit__();save(out/'resource-samples.json',samples.rows);save(out/'resource-summary.json',samples.summary())
        if server and server.poll() is None:
            os.killpg(server.pid,signal.SIGTERM)
            try:server.wait(timeout=30)
            except subprocess.TimeoutExpired:os.killpg(server.pid,signal.SIGKILL);server.wait(timeout=10)
        released=not gpu_owners()
        if stopped and released:
            subprocess.run(['systemctl','--user','start','qwen-main.service'],check=True)
            deadline=time.monotonic()+600
            while time.monotonic()<deadline:
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=5) as response:
                        if json.load(response).get('status')=='ok':break
                except OSError:pass
                time.sleep(2)
        after=state();save(out/'restoration.json',dict(before=prior,after=after,benchmark_gpu_released=released,
            main_active_state_restored=after['ActiveState']==prior['ActiveState'],hardware_unchanged=hardware()==policy))
        fcntl.flock(guard,fcntl.LOCK_UN);guard.close()
        assert released and after['ActiveState']==prior['ActiveState'],'Production service restoration failed'
def interrupted(signum,frame):raise SystemExit('Signal '+str(signum))
signal.signal(signal.SIGTERM,interrupted)
if __name__=='__main__':main()
