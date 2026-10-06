# Token Plan Qwen3.8-Flash — Flash comparison addendum

Runs on October 2, 2026. Canonical prompts, task fixtures and scoring come from the active Flash comparison. First attempts are retained, with only the explicitly authorized HA-04 adapter correction replacing its invalid pass-1 attempt. The required unscored tool transport probe and Hermes smoke are retained. HumanEval/0–9 is a thinking-off speed/completion panel, with no correctness score.

**Hosted service results are separate from the controlled local GPU comparison.** Provider weights, hardware, runtime, physical context and implicit cache cannot be fixed or inspected. The model alias is rolling, and output limits differ from the local physical-context policy. Every actual request was validated before being sent, and both harness requests and hosted wire requests were saved.

[Protocol and prelaunch mismatch decisions](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/protocol.lock.json>) · [Existing local comparison](<evidence/local/Qwen3.8flash/reports/flash-benchmarks-20260928/FLASH-COMPARISON-RESULTS-20261001.md>).

## Speed

| Panel | Requests | Output tokens | Request wall s | End-to-end output tok/s | Observed streaming tok/s | Cached input tokens |
|---|---:|---:|---:|---:|---:|---:|
| he09 | 10 | 1637 | 34.25 | 47.79 | Unavailable | 0 |
| tools | 62 | 6984 | 221.84 | 31.48 | 91.30 | 54016 |
| hermes-smoke | 14 | 1756 | 53.31 | 32.94 | 90.85 | 25600 |
| hermes-pass1 | 133 | 33566 | 773.17 | 43.41 | 75.63 | 321280 |
| hermes-pass2 | 115 | 27723 | 641.13 | 43.24 | 73.65 | 271616 |

End-to-end throughput is provider output-token usage divided by summed request wall time. The streaming estimate is sum(completion_tokens − 1) divided by summed time between the first and last generated deltas; chunks may contain several tokens, and networking/batching affects this estimate. It is not native GPU TG. Hermes completion usage includes reported reasoning tokens. Smoke metrics are unscored.

Request timing begins when the serialized proxy submits the upstream request. Waiting for that local serialization lock is excluded from request-level timing; the Hermes case clock includes all waiting, tool work and verifier overhead.

**Native PP and native TG are unavailable.** No prompt/decode computation times were returned. Time to first delta includes queueing, network and generation, so dividing input tokens by it would not establish PP. The raw token-ID append/cold-prefix grid, full-vocabulary fidelity and server RAM/weight/disk panels are unsupported by this hosted interface.

## Scores

Hard tools TC70–84: **83/100**, 25/30 points. 53/53 captured model tool calls have matching environment observations.

| Case | Status | Points /2 |
|---|---|---:|
| TC-70 | pass | 2 |
| TC-71 | pass | 2 |
| TC-72 | pass | 2 |
| TC-73 | pass | 2 |
| TC-74 | pass | 2 |
| TC-75 | fail | 0 |
| TC-76 | partial | 1 |
| TC-77 | pass | 2 |
| TC-78 | pass | 2 |
| TC-79 | pass | 2 |
| TC-80 | pass | 2 |
| TC-81 | pass | 2 |
| TC-82 | pass | 2 |
| TC-83 | partial | 1 |
| TC-84 | partial | 1 |

[Official tool report](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/remote/tools/report.json>) · [Tool execution evidence](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/tools/tool-execution-evidence.json>).

### hermes-smoke

Verifier score: **100/100**. Unscored smoke.

| Case | Status | Score /100 | Wall s |
|---|---|---:|---:|
| HA-01 | pass | 100 | 8.19 |
| HA-05 | pass | 100 | 33.33 |
| HA-20 | pass | 100 | 26.57 |

[Summary and per-case artifacts](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/remote/hermes-smoke/cases/20261002T152208Z-hermesagent20-token-plan-qwen3-8-flash/summary.json>).

Verified 13 parent-agent tool calls against captured provider call IDs and environment completions. [Execution evidence](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/hermes-smoke/tool-execution-evidence.json>).

### hermes-pass1

Amended verifier score: **98/100**, all 20 selected cases valid. Only HA-04 was replaced by its explicitly authorized corrected attempt; the original failed attempt is preserved.

| Case | Status | Score /100 | Wall s |
|---|---|---:|---:|
| HA-01 | pass | 100 | 18.28 |
| HA-02 | pass | 100 | 74.22 |
| HA-03 | pass | 100 | 7.11 |
| HA-04 | pass | 100 | 31.37 |
| HA-05 | pass | 100 | 48.35 |
| HA-06 | pass | 100 | 57.17 |
| HA-07 | pass | 100 | 158.32 |
| HA-08 | pass | 100 | 75.61 |
| HA-09 | pass | 100 | 31.34 |
| HA-10 | pass | 100 | 36.10 |
| HA-11 | pass | 100 | 26.92 |
| HA-12 | pass | 100 | 39.45 |
| HA-13 | pass | 100 | 129.12 |
| HA-14 | pass | 100 | 10.98 |
| HA-15 | pass | 100 | 15.28 |
| HA-16 | pass | 100 | 12.99 |
| HA-17 | fail | 70 | 103.60 |
| HA-18 | pass | 100 | 16.50 |
| HA-19 | partial | 80 | 40.41 |
| HA-20 | pass | 100 | 25.65 |

[Summary and per-case artifacts](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/remote/hermes-pass1/cases/20261002T152318Z-hermesagent20-token-plan-qwen3-8-flash/summary.json>).

[Amended all-20 summary](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/remote/amended-pass1/summary.json>).

Verified 142 parent-agent tool calls against captured provider call IDs and environment completions. [Execution evidence](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/hermes-pass1/tool-execution-evidence.json>).

### hermes-pass2

Verifier score: **99/100**. All 20 selected cases valid.

| Case | Status | Score /100 | Wall s |
|---|---|---:|---:|
| HA-01 | pass | 100 | 9.48 |
| HA-02 | pass | 100 | 83.61 |
| HA-03 | pass | 100 | 7.40 |
| HA-04 | pass | 100 | 27.46 |
| HA-05 | pass | 100 | 32.66 |
| HA-06 | pass | 100 | 87.67 |
| HA-07 | pass | 100 | 95.55 |
| HA-08 | pass | 100 | 82.31 |
| HA-09 | pass | 100 | 21.33 |
| HA-10 | pass | 100 | 33.15 |
| HA-11 | pass | 100 | 25.93 |
| HA-12 | pass | 100 | 19.30 |
| HA-13 | pass | 100 | 80.29 |
| HA-14 | pass | 100 | 10.45 |
| HA-15 | pass | 100 | 16.70 |
| HA-16 | pass | 100 | 12.04 |
| HA-17 | fail | 70 | 82.06 |
| HA-18 | pass | 100 | 17.77 |
| HA-19 | pass | 100 | 27.14 |
| HA-20 | pass | 100 | 21.84 |

[Summary and per-case artifacts](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/remote/hermes-pass2/cases/20261002T154143Z-hermesagent20-token-plan-qwen3-8-flash/summary.json>).

Verified 127 parent-agent tool calls against captured provider call IDs and environment completions. [Execution evidence](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/hermes-pass2/tool-execution-evidence.json>).

## Alongside the saved local results

These are the same task panels, with each stack's own recommended settings. Hosted and local hardware/cache/runtime conditions differ; this table does not establish a controlled hardware ranking.

| Model | HE0–9 request seconds | Hard tools /100 | Hermes P1 / P2 /100 |
|---|---:|---:|---|
| Ciru v4.4.1 | 38.21 | Skipped | 99 / 95 |
| Ciru v5.0 | 37.48 | 80 | 93 / 99 |
| HaloBox HIP | 43.02 | 70 | 98 / 94 |
| Gufo | 33.10 | 73 | 89 / 91 |
| AgentionAI AP-Q5_K_XL | 42.63 | 83 | 99 / 99 |
| Halogen | 34.55 | 80 | 99 / 94 |
| Carlos HC-Q8 | 40.95 | 73 | 99 / 91 |
| Token Plan Qwen3.8 Flash (hosted) | 34.25 | 83 | 98 / 99 |

[Local source inventory](<evidence/local/Qwen3.8flash/reports/flash-benchmarks-20260928/data/comparison-inventory-20261001.json>).

## Serving and sampling

The hosted model uses its own official settings: thinking-off temperature 0.7, presence penalty 1.5; thinking-on temperature 0.6, xhigh effort and preserved reasoning, presence penalty 0. Top-k is 20; top-p is omitted in accordance with the provider recommendation to set one sampling control. All seeds are retained (123 for HE/tools, 160915/160916/160917 for Hermes smoke/pass1/pass2). Unsupported neutral local fields are removed by a recorded adapter. No custom scored output cap is added.

Provider references: [Qwen3.8-Flash guide](https://docs.qwencloud.com/developer-guides/getting-started/latest-model), [OpenAI API](https://docs.qwencloud.com/api-reference/chat/openai-chat). The model catalog and HTML documentation snapshots are stored beside this report.

The tool harness report calls its OpenAI-compatible client adapter `llamacpp`; that field does not identify the hosted provider runtime. The provider runtime and effective seed/sampler values are not echoed. The saved hosted wire request is authoritative for submitted settings; returned reasoning content verifies the requested thinking mode, and cache usage is recorded directly.

Bailian CLI was upgraded with authorization from 2.0.1 to 2.1.0. `bl config list`, `bl auth status` and `bl model list --enrich` confirmed the saved Token Plan profile and catalog; benchmark requests used its existing key through a loopback proxy. No key was copied to the benchmark host. Production model services were untouched.

A local adapter initially rejected the unscored transport probe before sending it to the provider. Its failure receipt is preserved; fixing it repeated no provider generation or scored case.

In Hermes pass 1, the adapter rejected the native session-search internal summarizer (temperature 0.1, 10000-token internal limit) before provider generation. The agent produced a passing HA-04 outcome after client errors, but the frozen integrity audit rejected its retries. The original HA-04 remains invalid for scoring. The remaining 16 first-pass cases and full second pass proceeded after fixing the adapter. The internal summarizer keeps its 10000-token limit and canonical messages, and uses hosted recommended 0.6/xhigh thinking. This adaptation and all failed pre-provider requests are retained.

The user then explicitly requested retrying HA-04 and amending pass 1. Only that case was rerun with seed 160916 and the corrected adapter, after the complete second pass. The amended score uses 19 original valid cases and one authorized correction, evaluated by the original pinned scoring function. The first-pass transport speed totals retain all attempts, including the original invalid HA-04 and its correction, and are diagnostic. [Correction authorization](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/hermes-pass1-ha04-correction/authorization.json>).

Before delegation cases, inspection of the pinned helper code showed that child agents do not inherit the parent sampling overrides. The proxy was updated to normalize child tool-agent requests to the stage sampler, matching the original local comparison proxy. Only this run's verifier was briefly paused; all current provider requests drained before its tunnel was switched. The same verifier resumed, and no scenario or generation was restarted. First-pass wall times include this maintenance pause; second-pass timing uses the settled adapter. [Switch receipt](<evidence/local/Qwen3.8flash/token-plan-qwen38-20261002/helper-switch-receipt.json>).
