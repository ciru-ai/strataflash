#!/usr/bin/env bash
set -euo pipefail
TASK=/benchmark-storage
cd "$TASK"
test -f weights-complete.json
test -f build-complete.json
nix-build --expr 'with import <nixpkgs> {}; python3.withPackages (ps: [ ps.numpy ps.jinja2 ps.regex ps.requests ps.psutil ps.pyyaml ])' -o "$TASK/python"
export STRATA_GGUF_PY="$TASK/build-halo/_deps/strata_llamacpp-src/gguf-py"
"$TASK/python/bin/python3" source/tools/iq_pack.py --gguf "$TASK/weights/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf" --out "$TASK/pack" --compat-bf16
sha256sum fidelity/panel/panel.json fidelity/panel/panel.tokens.i32le fidelity/panel/panel.labels.i32le fidelity/teacher.f32le > fidelity/inputs.sha256
du -sh pack mtp/rt
printf '{"status":"PREPARED","pack":"native GGUF in place with documented BF16 compatibility conversions","mtp":"copied pinned Strata runtime, original checkpoint draft"}\n' > assets-complete.json
