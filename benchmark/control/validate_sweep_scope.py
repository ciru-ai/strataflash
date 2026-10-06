#!/usr/bin/env python3
"""Reject out-of-scope benchmark launches; this script performs no inference."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('panel_id')
    parser.add_argument('--source-path', type=Path,
                        help='Host-local copy of the frozen source; its hash must still match.')
    args = parser.parse_args()
    contract = json.loads((ROOT / 'active-sweep-contract.json').read_text())
    source = args.source_path or Path(contract['scope_source']['path'])
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != contract['scope_source']['sha256']:
        parser.error('Frozen sweep source changed; reconcile scope before generation.')
    if args.panel_id not in contract['required_panels']:
        parser.error(f'{args.panel_id!r} is outside the active six-stack comparison.')
    print(json.dumps(dict(scope_check='PASS', panel_id=args.panel_id,
                         inference_performed=False, conditions_check_still_required=True)))


if __name__ == '__main__':
    main()
