import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CONTRACT=json.loads((ROOT/'contract.json').read_text())
assert hashlib.sha256((ROOT/'initial-requests.json').read_bytes()).hexdigest()==CONTRACT['reference_sha256']
REFERENCE=json.loads((ROOT/'initial-requests.json').read_text())
def validate_request(body,model):
 assert body.get('model')==model
 if body.get('max_tokens')==1 and not body.get('tools') and 'chat_template_kwargs' not in body:return 'transport-probe'
 match=[r for r in REFERENCE if r['messages'][:2]==body['messages'][:2]]
 assert len(match)==1,'Task or fixture differs from retained Carlos protocol'
 ref=match[0]
 assert body.get('tools')==ref['tools'],'Tool schemas differ'
 expected={k:v for k,v in ref.items() if k not in ['model','messages','tools','stream']}
 actual={k:v for k,v in body.items() if k not in ['model','messages','tools','stream']}
 assert actual==expected,('Request settings mismatch',actual,expected)
 assert body.get('stream',False) in (True,False)
 return 'scored'
if __name__=='__main__':
 for r in REFERENCE:validate_request(r,r['model'])
 print(json.dumps(dict(status='PASS',planned_requests=15,inference_performed=False)))
