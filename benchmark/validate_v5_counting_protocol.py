#!/usr/bin/env python3
"""Validate original counting requests without generating or replacing output."""
import hashlib
import json
import re
from pathlib import Path


def digest(body):
    return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_request(body, name, contract):
    assert body['model']=='v5.0'
    reference=next(r for r in contract['reference_requests'] if r['name']==name)
    actual=body.copy();actual.pop('model')
    assert digest(actual)==reference['payload_except_model_sha256'], ('Original counting request mismatch',name)
    assert body['stream'] and body['ignore_eos']
    assert body['stream_options']=={'include_usage':True}
    for key,value in contract['sampling'].items():assert body[key]==value,(name,key)
    assert 'messages' not in body and 'chat_template_kwargs' not in body


def validate_all(plan,sampling,contract,cards):
    assert contract['passes']==1 and contract['baseline_runs']==0 and contract['retries']==0
    assert len(plan)==24 and [row[0] for row in plan]==contract['order']
    assert sampling==contract['sampling']
    for key,filename in [('sampling_card','Qwen3.8-Flash-Next.md'),('derivative_card','ciru-iu4.md')]:
        assert hashlib.sha256((cards/filename).read_bytes()).hexdigest()==contract[key]['card_sha256']
    card=(cards/'Qwen3.8-Flash-Next.md').read_text()
    assert 'Thinking Mode: `temperature=1.0`, `top_p=0.95`, `top_k=20`, `min_p=0.0`, `presence_penalty=0.0`, `repetition_penalty=1.0`' in card
    for name,prompt,count,p,depth,cache in plan:
        body=dict(model='v5.0',prompt=prompt,max_tokens=count,stream=True,
            stream_options={'include_usage':True},cache_prompt=cache,ignore_eos=True,**sampling)
        validate_request(body,name,contract)
        assert count==(512 if name.startswith('p') else 32 if name=='warm' else 1)
        assert len(prompt)>0 and (not name.startswith('p') or cache==bool(depth))


def audit_output(text,contract):
    syntax=bool(re.fullmatch(r'[0-9,\s]+',text))
    fields=[x.strip() for x in text.strip().split(',')]
    completed=fields[:-1]
    ascending=syntax and bool(completed) and all(x==str(21+i) for i,x in enumerate(completed))
    tail=fields[-1]
    valid_tail=not tail or str(21+len(completed)).startswith(tail)
    sha=hashlib.sha256(text.encode()).hexdigest()
    return dict(clean_counting=bool(ascending and valid_tail),exact_Carlos_output=sha==contract['expected_counting_sha256'],
        output_sha256=sha,reasoning_markup='<think>' in text,tool_markup='<tool_call>' in text,
        completed_integer_count=len(completed),first_outcome_preserved=True,retry_performed=False)
