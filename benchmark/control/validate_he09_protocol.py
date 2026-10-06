#!/usr/bin/env python3
"""Check real or planned HE0–9 requests against shared conditions and individual cards."""
import argparse
import hashlib
import json
from pathlib import Path


def validate_request(payload, task, model, contract):
    shared = contract['shared']
    profile = contract['models'][model]
    assert task in shared['task_ids'], 'Unexpected task'
    messages = payload.get('messages')
    assert isinstance(messages, list) and len(messages) == 1 and messages[0].get('role') == 'user', 'Require exactly one canonical user message'
    assert set(messages[0]) == {'role', 'content'}, 'Unexpected message fields'
    prompt_hash = hashlib.sha256(messages[0]['content'].encode()).hexdigest()
    assert prompt_hash == shared['prompt_sha256'][task], 'Canonical prompt changed'
    expected = dict(model=profile['api_model'], messages=messages,
        **profile['sampling'], **shared['request_settings'],
        **profile.get('backend_request_fields', {}))
    assert payload == expected, 'Request mode, sampler, cache, seed, stream, limit, or extra fields differ from contract'


def validate_panel(panel, model, contract):
    protocol = json.loads((panel / 'protocol.lock.json').read_text())
    shared = contract['shared']
    assert protocol['context'] == shared['context'], 'Context capacity differs'
    assert protocol['thinking'] == shared['thinking'], 'Thinking mode differs'
    assert protocol['fresh_server'] == shared['fresh_server'], 'Warm history differs'
    assert protocol['generative_warmups'] == shared['generative_warmups'], 'Warmup policy differs'
    assert protocol['concurrency'] == shared['concurrency'], 'Concurrency differs'
    assert protocol['task_ids'] == shared['task_ids'], 'Task set or order differs'
    for i, task in enumerate(shared['task_ids']):
        validate_request(json.loads((panel / f'HumanEval-{i}/request.json').read_text()), task, model, contract)
    return {'status': 'PASS', 'model': model, 'checked_requests': len(shared['task_ids']),
            'contract_sha256': hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=Path, default=Path(__file__).with_name('he09-contract.json'))
    parser.add_argument('--model', required=True)
    parser.add_argument('--panel', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate_panel(args.panel, args.model, json.loads(args.contract.read_text()))))
