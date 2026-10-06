"""Read-only asset sizing; deduplicate actual filesystem objects and resolve links."""
import json,socket
from pathlib import Path
TASK=Path('/srv/llm/work/strata-v0140-20261006')
assert socket.gethostname()=='sozo'
rows=[];seen=set();totals={}
for group in ['weights','pack','mtp/rt','bin','runtime']:
    for p in sorted((TASK/group).rglob('*')):
        if not p.is_file():continue
        s=p.stat();identity=(s.st_dev,s.st_ino);duplicate=identity in seen;seen.add(identity)
        rows.append(dict(group=group,path=str(p),resolved_path=str(p.resolve()),bytes=s.st_size,
            allocated_bytes=s.st_blocks*512,duplicate_object=duplicate,symlink=p.is_symlink()))
        if not duplicate:totals[group]=totals.get(group,0)+s.st_size
receipt=dict(status='MEASURED',rows=rows,unique_logical_bytes_by_group=totals,
    serving_assets_unique_logical_bytes=sum(v for k,v in totals.items() if k in ['weights','pack','mtp/rt']),
    runtime_binary_bytes=sum(v for k,v in totals.items() if k in ['runtime','bin']),
    excludes='SDK, build cache, redundant staging, original downloaded archive and benchmark logits',
    weights_integrity='Revision-pinned source and transferred shard hashes were checked before generation; sizing does not reread 94GB weights.')
(TASK/'serving-asset-sizes.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='rows'},indent=2))
