import json, os, re, shutil, subprocess
from pathlib import Path
task=Path('/benchmark-storage')
sdk=task/'rocm-7.14.1'
out=task/'runtime'
out.mkdir(exist_ok=True)
env=dict(os.environ, LD_LIBRARY_PATH=':'.join(map(str,[sdk/'lib',sdk/'rocm_sysdeps/lib',sdk/'lib/llvm/lib',Path('/nix/store/si4q3zks5mn5jhzzyri9hhd3cv789vlm-gcc-15.2.0-lib/lib')])))
data=subprocess.check_output(['ldd',str(task/'build-halo/strata')],env=env,text=True)
assert 'not found' not in data,data
store=set()
for raw in re.findall(r'(?:=> )?(/\S+)',data):
    path=Path(raw)
    if str(path).startswith(str(sdk)+'/'):
        target=out/path.relative_to(sdk)
        target.parent.mkdir(parents=True,exist_ok=True)
        # Store a real file under the SONAME path; ldd already resolves the transitive closure.
        shutil.copy2(path,target)
    elif str(path).startswith('/nix/store/'):
        store.add('/'.join(str(path).split('/')[:4]))
for name in ['hipblaslt/library','rocblas/library']:
    shutil.copytree(sdk/'lib'/name,out/'lib'/name,dirs_exist_ok=True)
shutil.copytree(sdk/'.kpack',out/'.kpack',dirs_exist_ok=True,ignore=shutil.ignore_patterns('fft_*','rocalution_*','rand_*','hiptensor_*','rccl_*'))
(task/'runtime-ldd.txt').write_text(data)
python=(task/'python').resolve()
refs=subprocess.check_output(['nix-store','-q','--references',str(python)],text=True).splitlines()
store.update(refs)
store.discard(str(python))
subprocess.run(['nix-copy-closure','--to','sozo-usb4',*sorted(store)],check=True)
# Only this locally generated environment is unsigned. Import that exact local build as root;
# the underlying packages were copied with normal trusted signatures, without changing Nix policy.
export=task/'python-env.nar'
with export.open('wb') as stream:
    subprocess.run(['nix-store','--export',str(python)],stdout=stream,check=True)
with export.open('rb') as stream:
    subprocess.run(['ssh','sozo-usb4','sudo -n nix-store --import'],stdin=stream,check=True)
dest='/srv/llm/work/strata-v0140-20261006'
subprocess.run(['ssh','-o','BatchMode=yes','sozo-usb4',f'mkdir -p {dest}/bin {dest}/runtime {dest}/source {dest}/pack {dest}/mtp; test $(df -B1 --output=avail /srv | tail -1) -gt 4500000000'],check=True)
for name in ['runtime','pack','source','mtp']:
    command=['rsync','-a','--partial']
    if name=='source':command += ['--exclude=.git']
    subprocess.run(command+[str(task/name)+'/',f'sozo-usb4:{dest}/{name}/'],check=True)
subprocess.run(['rsync','-a',str(task/'build-halo/strata'),str(task/'build-halo/strata-benchmark'),f'sozo-usb4:{dest}/bin/'],check=True)
subprocess.run(['ssh','sozo-usb4',f'ln -s {python} {dest}/python'],check=True)
subprocess.run(['ssh','sozo-usb4',f'df -h / /srv; sha256sum {dest}/bin/*'],check=True)
(task/'runtime-staged.json').write_text(json.dumps(dict(status='STAGED',python=str(python),closure_paths=sorted(store),ldd=data,transport='direct Ciru to Sozo USB4'),indent=2)+'\n')
