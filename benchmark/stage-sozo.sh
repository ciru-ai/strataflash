#!/usr/bin/env bash
set -euo pipefail
TASK=/benchmark-storage
DEST=/srv/llm/work/strata-v0140-20261006
ROOT_DEST=/home/benchmark/strata-v0140-weights-20261006
cd "$TASK"
test -f weights-complete.json
ip route get 127.0.0.1 | rg 'dev thunderbolt0 src 127.0.0.1'
test "$(ssh -o BatchMode=yes sozo-usb4 hostname)" = sozo
ssh -o BatchMode=yes sozo-usb4 "mkdir -p '$DEST/weights' '$ROOT_DEST'; test \$(df -B1 --output=avail /srv | tail -1) -gt 55500000000; test \$(df -B1 --output=avail / | tail -1) -gt 47000000000"
rsync -a --partial weights/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf weights/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf sozo-usb4:"$DEST/weights/"
rsync -a --partial weights/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf sozo-usb4:"$ROOT_DEST/"
ssh -o BatchMode=yes sozo-usb4 "ln -s '$ROOT_DEST/Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf' '$DEST/weights/Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf'; sha256sum '$DEST/weights/'*.gguf; df -h / /srv" > weights-sozo-verification.log
printf '{"status":"COPIED_PENDING_RECEIPT_AUDIT","transport":"Ciru to Sozo direct USB4","second_shard_filesystem":"/srv","third_shard_filesystem":"/"}\n' > weights-sozo-staged.json
