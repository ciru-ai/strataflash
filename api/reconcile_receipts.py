#!/usr/bin/env python3
"""Correct two proxy-stage labeling races using submitted stage seeds."""
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
moves=[]
for request in list(ROOT.glob('*/http/*/wire-request-body.json')):
    wire=json.loads(request.read_text())
    expected={160915:'hermes-smoke',160916:'hermes-pass1',160917:'hermes-pass2'}.get(wire.get('seed'))
    folder=request.parent
    if expected and folder.parent.parent.name!=expected:
        assert (folder/'transport.json').exists(),'Wait for complete receipt'
        target=ROOT/expected/'http'/folder.name
        assert not target.exists()
        moves.append({'from':str(folder.relative_to(ROOT)),'to':str(target.relative_to(ROOT)),
                      'reason':'Folder stage captured before helper adapter refreshed stage; actual submitted seed establishes panel'})
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(folder),target)
        meta=json.loads((target/'transport.json').read_text())
        meta['original_folder_stage']=meta['stage'];meta['stage']=expected
        (target/'transport.json').write_text(json.dumps(meta,indent=2)+'\n')
prior=ROOT/'receipt-stage-corrections.json'
if prior.exists():moves=json.loads(prior.read_text())+moves
prior.write_text(json.dumps(moves,indent=2)+'\n')
print(json.dumps({'stage_receipt_moves':moves}))
