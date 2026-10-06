# Strata Flash v0.1.40 comparison

[Interactive report and recorded race](https://llm.ciru.ai/strataflash/) · [Detailed results](benchmark/REPORT.md) · [Comparison CSV](site/data/comparison.csv) · [Engine release](https://github.com/Niko1221/Strata/releases/tag/v0.1.40)

One selected run of the active Flash comparison on a 128 GB AMD Strix Halo, with each model's own pinned model-card recommendations. This repository contains the report source, benchmark runners, frozen requests, sanitized execution evidence, build and runtime receipts, and the pinned Strata engine source. No inference was performed while preparing the publication.

| Strata panel | Observed result |
|---|---:|
| HE0–9 native decode, thinking off | 75.836 tok/s; 10/10 usable |
| Cold 64,000-token prefill | 762.5 tok/s |
| Tools TC70–84, recommended nonthinking sampler | 77/100; 15 cases |
| Hermes recommended thinking | 91 / 91; 20 cases in each of two passes |
| Full-vocabulary fidelity | KL 0.059757; top-1 93.945%; PPL 2.086310 |
| Append cached-prefix replay | Zero in all 18 cells |
| Clean counting output | 2/18 first outcomes |
| Serving assets | 89.410 GiB, filesystem-object deduplicated |

Native clocks and historical cache lifecycles differ. Strata includes the first prediction and terminal EOS in its decode numerator; llama baselines use `(n−1)/time`, while Gufo and Halogen use `n/time`. HE0–9 is a speed panel, not a correctness score. First output deviations remain results; decode measurements from malformed counting output are diagnostic. These saved runs do not establish an isolated engine-only speed gain.

The release reports 1,370 PP/s at 64K for the same quant; this run measured about 762.5, or 44.3% lower. The cause is unconfirmed. See the [advertised-prefill audit](benchmark/advertised-prefill-audit.json) and [pinned upstream methodology](https://github.com/Niko1221/Strata/blob/1735d6471df29b42c26170efaac1f1446a58640f/docs/STRIX_HALO.md).

## Repository map

- `site/`: complete static page, charts, replay, vendored ECharts and its license, and normalized chart/race data.
- `report/templates/` and `report/inputs/`: page sources, original replay renderer, and selected baseline inputs.
- `scripts/build_page.py`: regenerate the page from saved evidence; makes no model calls.
- `scripts/verify_public.py`: verify every evidence hash, distribution checksums and result/replay invariants; makes no model calls.
- `benchmark/`: actual Strata runners and adapter, validators, cards, contracts, requests, results, native journals, resource samples, execution audits, diagnostics and restoration receipts.
- `engine/Strata/`: pinned v0.1.40 text source, upstream license, and isolated `generate_benchmark.cpp` instrumentation. Canonical model computation remains pinned; the benchmark controls add exact-depth cache guards and passive logits readback.
- `harnesses/`: the frozen Tool-Eval and HermesAgent-20 evaluation code, including verifier sources and manifests.
- `api/`: the existing hosted comparator's control code and selected two 20-case summaries. Pass 1 retains the user-authorized HA-04 adapter correction; repair pauses are excluded from scored case wall.
- `publication/`: source-to-public hashes, exclusions, sanitization and verification receipts.

Historical baseline logs and sources are published separately in [Strix Showdown](https://github.com/ciru-ai/strix-showdown-20261001/tree/1acfd764). The selected baseline JSON input hashes are recorded in `benchmark/comparison-source-receipt.json`; superseded Hermes diagnostics are not used.

## Inspect or rebuild

```sh
python3 scripts/verify_public.py
python3 scripts/build_page.py
python3 scripts/serve_page.py
```

Open `http://localhost:8000/strataflash/`. Rebuilding this page only reads saved records. Benchmark execution is a separate, explicit operation; consult [METHODOLOGY.md](METHODOLOGY.md) and the frozen per-panel contracts before adapting the runners to another host.

## Evidence and privacy

Original private evidence is retained. The public manifest records each original hash alongside the published and uncompressed public hashes. Sanitization removes credentials, private host identifiers and paths, personal information, and synthetic fixture secrets. Numerical JSON/JSONL values, scores, timing fields, sampling values, revisions, first attempts and tool correlation IDs are preserved. Large text files are gzip-compressed when needed; decompress before inspecting or scanning them.

Weights, native packs, runtime executables, live databases, environment-home snapshots and binary logits are not distributed. Fidelity hashes and scorer code remain public, and the full-vocabulary capture is retained in the benchmark archive. Redacted fixture data may require substituting equivalent synthetic placeholders for a fresh execution; publication reconstruction uses the preserved saved measurements.

The page and report source are by Ciru. Imported engine, harness, chart library and artwork retain their respective upstream attribution and licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).
