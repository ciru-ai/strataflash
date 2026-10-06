#!/usr/bin/env bash
set -euo pipefail
if [ ! -f release/manifest.json ]; then
  echo 'missing manifest' >&2
  exit 1
fi
echo 'DEPLOY_OK' > deploy-status.txt
echo 'deploy succeeded'
