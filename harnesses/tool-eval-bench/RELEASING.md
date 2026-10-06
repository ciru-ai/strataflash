# Releasing tool-eval-bench

Checklist for publishing a new release.

## Pre-release

1. **Update version strings** (all three MUST match):
   ```
   pyproject.toml        → version = "X.Y.Z"
   src/tool_eval_bench/__init__.py → __version__ = "X.Y.Z"
   CHANGELOG.md          → ## [X.Y.Z] — YYYY-MM-DD
   ```

2. **Lint and test**:
   ```bash
   ruff check .
   .venv/bin/python -m pytest tests/ --ignore=tests/test_llama_benchy.py
   ```

3. **Install smoke test**:
   ```bash
   uv tool install --force .
   tool-eval-bench --version   # should print X.Y.Z
   tool-eval-bench --help
   ```

4. **Verify dependencies**:
   ```bash
   pip check
   ```

## Tagging

```bash
git add -A
git commit -m "release: vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

## Post-release

- Add a new `## [Unreleased]` section at the top of `CHANGELOG.md`

## Live Certification (recommended before major releases)

Run the full benchmark against at least one backend to verify deployment
compatibility:

```bash
# vLLM
tool-eval-bench --backend vllm --base-url http://localhost:8000

# llama.cpp
tool-eval-bench --backend llamacpp --base-url http://localhost:8080

# LiteLLM
tool-eval-bench --backend litellm --base-url http://localhost:4000
```
