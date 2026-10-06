import hashlib, json, threading, time, urllib.request
from pathlib import Path
TASK=Path(__file__).resolve().parent
MODEL='strata-v0.1.40'
BASE='http://127.0.0.1:18140'
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def request(route,payload=None,timeout=10):
    req=urllib.request.Request(BASE+route,data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    return urllib.request.urlopen(req,timeout=timeout)
def api(route,payload=None,timeout=10):
    with request(route,payload,timeout) as response:return json.load(response)
def resources():
    mem={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split())>=2}
    gpu=Path('/sys/class/drm/card1/device')
    data={k:int((gpu/k).read_text()) for k in ('mem_info_gtt_used','mem_info_gtt_total','mem_info_vram_used','mem_info_vram_total') if (gpu/k).exists()}
    return dict(at=time.time(),ram_total=mem['MemTotal'],ram_available=mem['MemAvailable'],ram_used=mem['MemTotal']-mem['MemAvailable'],gpu=data)
class Samples:
    def __init__(self):self.rows=[];self.stop=threading.Event()
    def run(self):
        while not self.stop.is_set():self.rows.append(resources());self.stop.wait(.25)
    def __enter__(self):self.thread=threading.Thread(target=self.run);self.thread.start();return self
    def __exit__(self,*unused):self.stop.set();self.thread.join();self.rows.append(resources())
    def summary(self):return dict(min_ram_available=min(row['ram_available'] for row in self.rows),max_ram_used=max(row['ram_used'] for row in self.rows),uma_overlap=True)

