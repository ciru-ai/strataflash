import concurrent.futures, hashlib, json, subprocess
from pathlib import Path
TASK = Path('/benchmark-storage')
META = json.loads((TASK/'weights-repository-metadata.json').read_text())
REV = '38bb39ee97821de2c9009abb7e93950eec396e66'
assert META['sha'] == REV
FILES = [s for s in META['siblings'] if s['rfilename'].startswith('UD-IQ4_XS/')]
assert len(FILES) == 3
def get(info):
    path = TASK/'weights'/info['rfilename']
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = path.with_suffix('.receipt.json')
    if receipt.exists():
        assert json.loads(receipt.read_text())['sha256'] == info['lfs']['sha256']
        assert path.stat().st_size == info['size']
        return json.loads(receipt.read_text())
    url = f'https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/resolve/{REV}/{info["rfilename"]}?download=true'
    with path.with_suffix('.download.log').open('ab') as log:
        subprocess.run(['curl','-fL','--retry','3','-C','-',url,'-o',str(path)],stdout=log,stderr=log,check=True)
    assert path.stat().st_size == info['size']
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert digest == info['lfs']['sha256']
    record = dict(path=str(path),repo=META['id'],revision=REV,size_bytes=info['size'],sha256=digest)
    receipt.write_text(json.dumps(record,indent=2)+'\n')
    return record
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    records = list(pool.map(get, FILES))
(TASK/'weights-complete.json').write_text(json.dumps(dict(status='VERIFIED',files=records),indent=2)+'\n')
