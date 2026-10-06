# Strata v0.1.40 comparison

All requested panels completed and audited: 18 append cells, five cold prefixes, 16 fidelity windows, HE0–9, 15 tool cases, and **20 cases in each Hermes pass**. The three required Hermes smoke cases are separate.

Strata reported **75.8 native tokens/s** on HE0–9, **77/100** on tools, and **91/100** across the two Hermes passes (91/91). HE0–9 measures usable output and speed; code correctness is not scored.

| Model | HE native TG/s | Tools /100 | Hermes /100 | Hermes 20-case time s | Fidelity KL ↓ | Top-1 agreement | Tail PPL ↓ |
|---|---:|---:|---:|---:|---:|---:|---:|
| Strata v0.1.40 · UD-IQ4_XS | 75.8 | 77 | 91.0 | 919.9 | 0.05976 | 93.95 | 2.0863 |
| Ciru v4.4.1 | 56.0 | — | 97.0 | 872.8 | 0.08674 | 92.72 | 2.0925 |
| Ciru v5.0 | 55.3 | 80 | 96.0 | 1052.8 | 0.04954 | 94.38 | 2.0442 |
| HaloBox HIP | 45.7 | 70 | 96.0 | 1357.9 | 0.02918 | 96.14 | 2.0364 |
| Gufo | 57.6 | 73 | 90.0 | 898.9 | 0.02797 | 96.44 | 2.0350 |
| AgentionAI AP-Q5_K_XL | 44.3 | 83 | 99.0 | 1355.9 | 0.02914 | 96.44 | 2.0264 |
| Halogen | 54.3 | 80 | 96.5 | 799.1 | 0.08590 | 92.77 | 2.0797 |
| Carlos ROCmFPX2 · HC-Q8 | 46.3 | 73 | 95.0 | 2734.7 | 0.18563 | 89.16 | 2.1976 |
| Orca | — | — | 94.5 | 1141.2 | — | — | — |
| Qwen3.8 Flash API | — | — | 98.5 | 876.5 | — | — | — |

Strata native decode_ms starts before the first prediction; llama.cpp baselines use (n−1) and exclude first-token prediction. Keep reported native clocks separate.
Fidelity uses the unchanged BF16 teacher, all 248320 logits, and the last 128 positions of each of the 16 frozen 512-token windows. Top-1 agreement is a percentage.
Tools uses the recommended non-thinking sampler. Hermes uses the recommended thinking sampler and unchanged verifier. Carlos ROCmFPX2 has an official tool score of 73 and a separately reviewed score of 80. The table retains the official score.
Hermes time is the mean across the two passes of the sum of 20 individual case times. Carlos ran on Ciru; the other local Hermes rows ran on Sozo. Historical output-cap differences are retained in the comparison JSON. These times do not establish a controlled same-host engine ranking.
The saved Qwen API comparison uses both complete 20-case passes, including the authorized HA-04 adapter correction. Its scored case time excludes repair pauses. Unavailable panels are left blank.

## Prefill and append sweep

Every timed append reused exactly its D-token prefix and processed only its P new tokens. **Zero cached-prefix replay** was verified in all 18 native receipts. Clean counting output: **2/18**. First malformed outputs are retained; their TG is diagnostic for that output.

| Cached depth | PP/s P512 | PP/s P2048 | PP/s P4096 | TG/s P512 | TG/s P2048 | TG/s P4096 |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 405.0 | 685.7 | 761.1 | 67.0 | 65.7 | 66.0 |
| 32000 | 343.8 | 564.6 | 651.5 | 62.9 | 61.9 | 59.3 |
| 64000 | 327.2 | 528.3 | 607.8 | 60.9 | 60.2 | 62.2 |
| 120000 | 308.2 | 481.9 | 548.0 | 60.3 | 57.3 | 59.4 |
| 192000 | 277.4 | 412.6 | 461.7 | 56.6 | 57.4 | 58.6 |
| 256000 | 260.7 | 376.5 | 416.6 | 54.0 | 53.7 | 52.8 |

| Cold prefix tokens | Native PP/s | Request wall s |
|---:|---:|---:|
| 32000 | 795.1 | 40.39 |
| 64000 | 762.5 | 84.17 |
| 120000 | 709.1 | 169.63 |
| 192000 | 631.0 | 304.85 |
| 256000 | 584.9 | 438.46 |

Saved deployment PP observations at P2048 are shown below. The full saved grid and cold-prefix rows, with their original conditions and cache caveats, remain in `comparison.json`.

| Model | Append PP/s D0 | Append PP/s D64K | Append PP/s D256K | Cold 64K PP/s |
|---|---:|---:|---:|---:|
| Strata v0.1.40 · UD-IQ4_XS | 685.7 | 528.3 | 376.5 | 762.5 |
| Ciru v4.4.1 | 840.3 | 716.5 | 453.8 | 942.5 |
| Ciru v5.0 | 918.7 | 881.7 | 571.4 | 1259.6 |
| HaloBox HIP | 1046.3 | 836.5 | 579.1 | 1105.3 |
| Gufo | 1488.7 | 1227.9 | 1046.1 | 1322.6 |
| AgentionAI AP-Q5_K_XL | 706.1 | 596.9 | 439.0 | 850.6 |
| Halogen | 1335.4 | 1196.5 | 1025.8 | 1424.8 |
| Carlos ROCmFPX2 · HC-Q8 | 537.4 | 420.9 | 271.8 | 476.9 |

## Advertised prefill gap

The [v0.1.40 release](https://github.com/Niko1221/Strata/releases/tag/v0.1.40) reports 1370 PP/s at 64K for UD-IQ4_XS on a 128GB Strix Halo. This run measured **762.5 PP/s**, a **44.3% lower** observation.
The [pinned Strix Halo methodology](https://github.com/Niko1221/Strata/blob/1735d6471df29b42c26170efaac1f1446a58640f/docs/STRIX_HALO.md) describes optional kernels that change numerics, and also gives a default-config remeasurement of 1299 PP/s at 128K. The default figure is also substantially higher than our observation; optional switches have not been established as the cause. The optimized HIP build, ROCm version, accepted tuning table and 18 automatic gfx1151 defaults were checked.
Known differences include workload, host OS/kernel/IOMMU configuration, serving context and a single selected-protocol run rather than interleaved medians. Their causal contribution has not been established. An exact reproduction of the publisher workload has not been performed; no additional reruns or host changes were made. `advertised-prefill-audit.json` retains the evidence.

The original one-warmup / five-primer / 18-append request bodies, sampler, order, seed and output limits are unchanged. Exact-depth snapshots use native checkpoint save/restore; pinning performs no generation and is outside the timed append. A native guard rejects missing exact-depth state before prefill. The superseded periodic-checkpoint sweep remains a diagnostic archive.
Native PP counts the last input token while its work is charged to the decode clock. The source timing addendum retains that boundary. Historical stacks have different server lifecycles, and Carlos has unrecovered prior lookup history; this does not establish an engine-only or warmed-cache speedup.

## Resources and reproduction

Serving weights, native pack and MTP total **89.41 GiB** (96002720984 bytes), deduplicated by filesystem object. SDK and build caches are excluded.

| Panel | Ready host RAM GiB | Peak host RAM GiB | Minimum available GiB |
|---|---:|---:|---:|
| he09 | 80.28 | 80.43 | 44.65 |
| counting-zero-replay | 80.23 | 81.46 | 43.63 |
| fidelity | 78.86 | 79.12 | 45.97 |
| tools | 80.24 | 81.18 | 43.90 |
| hermes | 80.63 | 81.45 | 43.64 |

| Deployment | Serving assets GiB | Recorded host pressure GiB | Memory method |
|---|---:|---:|---|
| Strata v0.1.40 · UD-IQ4_XS | 89.41 | 79.29 | Peak MemAvailable drop from post-production-stop, pre-load sample |
| Ciru v4.4.1 | 126.63 | 100.63 | Sozo MemAvailable drop |
| Ciru v5.0 | 119.84 | 100.15 | Sozo MemAvailable drop |
| HaloBox HIP | 106.28 | 110.44 | Sozo MemAvailable drop |
| Gufo | 106.28 | 91.49 | Sozo MemAvailable drop |
| AgentionAI AP-Q5_K_XL | 115.11 | 115.87 | Sozo MemAvailable drop |
| Halogen | 117.94 | 43.74 | Halogen measured pinned allocations |
| Carlos ROCmFPX2 · HC-Q8 | 86.01 | 82.61 | Ciru MemAvailable drop from ~114.6 GiB baseline (approximate) |
| Orca | 126.63 | 101.47 | Sozo MemAvailable drop |

Historical package and memory methods have their original scope; the saved owner lifecycle and memory caveats remain in comparison.json. The new peak includes the measured panel lifecycle. HE0–9 has no matching pre-load global sample, so its ready and per-case peaks are retained separately.
Host RAM, GTT, VRAM and process RSS overlap on this UMA host. These are host measurements, not quantities to add. Every owner verified exclusive GPU access and restored qwen-main with unchanged hardware settings.
Runtime: pinned v0.1.40 / ROCm 7.14.1 / gfx1151, context262144, prefill16384, int8 KV, resident experts, MTP spec4, lookup chain3, MTP Q4 all. Fidelity is target-only with --spec2 and no MTP; native IQ packs require that startup setting. The first missing-spec startup refused before generation and remains infrastructure evidence. Optional numeric fast kernels are off. All 64 HIP compilation commands use -O3 -DNDEBUG.

Requests, raw responses, native DONE lines, resource samples and audits are under `results/` and `ownership/`. `experiment-plan.json`, `zero-replay-contract.json`, `timing-definition-addendum.json`, `comparison-source-receipt.json` and the source/build receipts pin the protocol. Large fidelity logits and their verified hashes remain in the Ciru task archive.
No Core-19, pagoda/garden, engineering/wide fidelity, full164 HumanEval or HumanEval+ was added. No baseline model was rerun. The unoptimized HIP setup attempt is retained as infrastructure evidence.
