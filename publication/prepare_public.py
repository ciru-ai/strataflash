"""Publish saved evidence only. No model calls, benchmark reruns, or credentials."""
from pathlib import Path
import collections, gzip, hashlib, json, re, shutil

WORK = Path(__file__).resolve().parents[1]
PROJECT = WORK.parents[1]
TASK = PROJECT / 'strata-v0140-20261006'
OUT = WORK / 'public-repo'
PREVIOUS = PROJECT / 'publication/strix-showdown-20261002/public-repo'
OUT.mkdir(exist_ok=True)
selected = {}
excluded = []
skip = {'hermes-home', '.git', '__pycache__', 'node_modules', '.venv', '.cache', '.uv-cache', '.pytest_cache'}
extensions = {'.json','.jsonl','.log','.txt','.md','.py','.mjs','.js','.ts','.tsx','.sh','.yaml','.yml','.csv','.tsv','.prom','.diff','.patch','.sse','.raw','.html','.toml','.lock','.cfg','.ini','.cpp','.hpp','.h','.c','.cu','.nix','.bin','.jinja','.cmake','.dp','.bat','.ps1','.qrc'}

def tree(src, dest):
    src = Path(src)
    for p in src.rglob('*'):
        rel = p.relative_to(src)
        if not p.is_file() or p.is_symlink() or set(rel.parts) & skip: continue
        if p.name.startswith('.env') or p.name.endswith(('.sqlite3','.db')): continue
        if not str(dest).startswith('engine/') and p.suffix not in extensions and p.name not in {'LICENSE','COPYING','CMakeLists.txt','Dockerfile','Makefile','benchlocal'}: continue
        selected[str(Path(dest)/rel)] = p

tree(TASK, 'benchmark')
# Archives duplicate the selected text evidence; source lives in its own directory.
selected = {k:v for k,v in selected.items() if not k.startswith('benchmark/source/')}
tree(TASK/'source', 'engine/Strata')
selected['engine/Strata/src/program/generate_benchmark.cpp'] = WORK/'private-input/generate_benchmark.cpp'
tree(PREVIOUS/'evidence/ciru/tools/clones/tool-eval-bench', 'harnesses/tool-eval-bench')
tree(PREVIOUS/'evidence/ciru/runs/20260929-flash-hermes-recommended-thinking/HermesAgent-20', 'harnesses/HermesAgent-20')
selected['harnesses/run-hermesagent20-sweep-v2.mjs'] = PREVIOUS/'evidence/ciru/runs/20260929-flash-hermes-recommended-thinking/run-hermesagent20-sweep-v2.mjs'
for name in ['hermes','nonhermes']:
    selected['report/inputs/'+name+'.json'] = PROJECT/'reports/ultimate-qwen-flash-strix/data'/(name+'.json')
for p in (PROJECT/'token-plan-qwen38-20261002').iterdir():
    if p.is_file() and p.suffix in {'.py','.mjs','.js','.md','.json','.sh'}: selected['api/'+p.name]=p
api = json.loads((TASK/'saved-api-comparator.json').read_text())
for row in json.loads((TASK/'comparison.json').read_text())['rows']:
    if row['id']=='qwen-api':
        for item in row['source_passes']:
            selected[f"api/pass{item['pass_number']}/summary.json"] = Path(item['source'])

prefixes = [
    (str(TASK)+'/','benchmark/'),
    ('/srv/ssd/p3700ba/data/strata-v0140-20261006/','benchmark/'),
    ('/srv/llm/work/strata-v0140-20261006/','benchmark/'),
    ('/home/crown/Documents/ChatGPT/','evidence/local/'),
    ('/srv/ssd/p3700ba/data/llm-benchmarking-lab/','evidence/ciru/'),
]
rules = [
    ('credential', re.compile(r'(?<![\w-])(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,})'), '[REDACTED_CREDENTIAL]'),
    ('credential', re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._~+/-]{8,}'), r'\1REDACTED'),
    ('private_key', re.compile(r'-----BEGIN [^-]*PRIVATE KEY[^-]*-----.*?-----END [^-]*PRIVATE KEY[^-]*-----', re.S), '[REDACTED_PRIVATE_KEY]'),
    ('jwt', re.compile(r'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'), '[REDACTED_JWT]'),
    ('private_address', re.compile(r'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3})\b'), '127.0.0.1'),
    ('hardware_address', re.compile(r'\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b'), '[REDACTED_MAC]'),
    ('local_home', re.compile(r'/home/(?!benchmark\b|user\b|test\b)[A-Za-z0-9._-]+'), '/home/benchmark'),
    ('private_storage', re.compile(r'/srv/(?:ssd|desktop-data)/[A-Za-z0-9._/-]+'), '/benchmark-storage'),
    ('fixture_password', re.compile(r'(?i)(password\s*:\s*)[^\s\\"\x27<>]{4,}'), r'\1[REDACTED_FIXTURE_SECRET]'),
]
secret_key = re.compile(r'^(?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|password|passwd|secret|client[_-]?secret|authorization|cookie|set-cookie|ssh[_-]?private[_-]?key|machine[_-]?id|serial[_-]?number)$', re.I)

def scrub_text(s, counts, is_engine=False):
    for old,new in prefixes:
        n=s.count(old); counts['source_path']+=n; s=s.replace(old,new)
    for category,pattern,replacement in rules:
        s,n=pattern.subn(replacement,s); counts[category]+=n
    if not is_engine:
        s,n=re.subn(r'\b[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@(?!(?:example\.(?:com|org|net)|localhost|ciru\.ai)\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b','redacted@example.com',s)
        counts['personal_email']+=n
    return s

def scrub_json(x, counts, is_engine=False):
    if isinstance(x,dict): return {scrub_text(k,counts,is_engine):('[REDACTED_SECRET]' if secret_key.match(k) and isinstance(v,str) and v else scrub_json(v,counts,is_engine)) for k,v in x.items()}
    if isinstance(x,list): return [scrub_json(v,counts,is_engine) for v in x]
    if isinstance(x,str): return scrub_text(x,counts,is_engine)
    return x

def numbers(x):
    if isinstance(x,dict): return [n for v in x.values() for n in numbers(v)]
    if isinstance(x,list): return [n for v in x for n in numbers(v)]
    return [x] if isinstance(x,(float,int,bool)) else []

manifest=[]; checks=0; totals=collections.Counter()
for target,p in sorted(selected.items()):
    raw=p.read_bytes()
    try: text=raw.decode('utf-8')
    except UnicodeDecodeError:
        excluded.append(dict(path=target,reason='binary artifact',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())); continue
    if '\0' in text:
        excluded.append(dict(path=target,reason='binary artifact',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())); continue
    counts=collections.Counter(); is_engine=target.startswith('engine/')
    if p.suffix=='.json':
        try:
            original=json.loads(text); clean=scrub_json(original,counts,is_engine); assert numbers(original)==numbers(clean),target
            text=json.dumps(clean,ensure_ascii=False,indent=2)+'\n'; checks+=1
        except json.JSONDecodeError: text=scrub_text(text,counts,is_engine)
    elif p.suffix=='.jsonl':
        lines=[]
        for line in text.splitlines():
            try:
                original=json.loads(line); clean=scrub_json(original,counts,is_engine); assert numbers(original)==numbers(clean),target
                lines.append(json.dumps(clean,ensure_ascii=False)); checks+=1
            except json.JSONDecodeError: lines.append(scrub_text(line,counts,is_engine))
        text='\n'.join(lines)+'\n'
    else: text=scrub_text(text,counts,is_engine)
    clean_bytes=text.encode(); stored=clean_bytes
    dest=OUT/target
    if len(stored)>8_000_000: dest=dest.with_name(dest.name+'.gz'); stored=gzip.compress(stored,mtime=0)
    dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(stored)
    manifest.append(dict(path=str(dest.relative_to(OUT)),logical_path=target,bytes=len(stored),original_sha256=hashlib.sha256(raw).hexdigest(),published_sha256=hashlib.sha256(stored).hexdigest(),uncompressed_sha256=hashlib.sha256(clean_bytes).hexdigest(),redactions={k:v for k,v in counts.items() if v}))
    totals.update(counts)

pub=OUT/'publication'; pub.mkdir(exist_ok=True)
(pub/'evidence-manifest.json').write_text(json.dumps(dict(schema_version=1,inference_performed=False,json_numeric_preservation_checks=checks,redaction_totals=dict(totals),files=manifest),indent=2)+'\n')
(pub/'exclusions.json').write_text(json.dumps(dict(policy='Credentials, private identifiers, synthetic fixture secrets, environment homes, runtime binaries, weights, caches, and binary tensors are excluded. Textual HTTP response-body.bin files are retained. Fidelity logits are retained privately with public hashes and scorer source.',files=excluded),indent=2)+'\n')
print(json.dumps(dict(files=len(manifest),bytes=sum(x['bytes'] for x in manifest),numeric_checks=checks,redactions=dict(totals),binary_exclusions=len(excluded))))
