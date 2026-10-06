"""Isolated readback and cache controls; canonical generation source stays pinned."""
import hashlib, json, subprocess
from pathlib import Path
TASK=Path('/benchmark-storage')
SOURCE=TASK/'source'
original=(SOURCE/'src/program/generate.cpp').read_text(encoding='utf-8-sig')
reset='''            if (line == "BENCH_RESET") {
                // Benchmark-only control. Retain expert and lookup history; invalidate conversation reuse.
                if (!bs.empty() || conversations.size() != 0 || !ver.wait_commit(err)) {
                    std::printf("ERR BENCH_RESET requires an idle single slot without parked conversations\\n");
                    std::fflush(stdout);
                    continue;
                }
                cudaStreamSynchronize(main_stream);
                live.clear(); live_imgs.clear(); checks.clear(); live_ok = false;
                std::printf("BENCH_RESET_OK\\n");
                std::fflush(stdout);
                continue;
            }
            if (line.rfind("BENCH_PIN_PREFIX ", 0) == 0) {
                const int64_t L = std::strtoll(line.c_str() + 17, nullptr, 10);
                // Snapshot the completed primer state, without generating or rereading any token.
                if (L < 1 || !live_ok || (int64_t) live.size() != L || (int64_t) cur.size() < L ||
                    !live_imgs.empty() || !bs.empty() || conversations.size() != 0 || o.prompt_cache <= 0 ||
                    !std::equal(live.begin(), live.end(), cur.begin()) || !ver.wait_commit(err) ||
                    cudaStreamSynchronize(main_stream) != cudaSuccess || !checkpoint_at(L)) {
                    std::printf("ERR BENCH_PIN_PREFIX requires the exact completed primer state\\n");
                    std::fflush(stdout);
                    continue;
                }
                std::printf("BENCH_PREFIX_OK %lld\\n", (long long) L);
                std::fflush(stdout);
                continue;
            }
'''
needle='            if (line == "QUIT") break;'
assert original.count(needle)==1
modified=original.replace(needle,reset+needle)
needle='            int req_ckpt = 1;'
assert modified.count(needle)==1
modified=modified.replace(needle,needle+'\n            int64_t bench_reuse = -1;   // benchmark-only: require exactly this cached depth, or reject before prefill')
needle='                    else if (key == "ckpt") req_ckpt = std::atoi(tok.c_str() + eq + 1) != 0;'
assert modified.count(needle)==1
modified=modified.replace(needle,needle+'\n                    else if (key == "bench_reuse") bench_reuse = std::strtoll(tok.c_str() + eq + 1, nullptr, 10);')
needle='            // --batch: an idle slot that holds the start of this prompt'
assert modified.count(needle)==1
guard='''            if (bench_reuse >= 0) {
                // No fallback to an earlier periodic checkpoint and no extra prefix reuse.
                // This guard runs before cache mutation, checkpoint restore, or any prefill work.
                bool exact = bench_reuse == 0;
                from_live = false;
                if (bench_reuse > 0 && o.prompt_cache > 0 && want_cvec == cvec_cached) {
                    if (live_ok && (int64_t) live.size() == bench_reuse && starts_with(live, live_imgs)) {
                        exact = true; from_live = true;
                    } else {
                        for (const ConvCheckpoint& c : checks)
                            if ((int64_t) c.ids.size() == bench_reuse && starts_with(c.ids, c.imgs)) exact = true;
                    }
                }
                if (!exact || bench_reuse >= n || !bs.empty() || conversations.size() != 0 ||
                    !req_imgs.empty() || std::getenv("STRATA_CKPT_REREAD") != nullptr) {
                    std::printf("ERR BENCH_NO_PREFIX_REPLAY exact cached depth %lld unavailable\\n", (long long) bench_reuse);
                    std::fflush(stdout);
                    continue;
                }
                resume = bench_reuse;
            }
'''
modified=modified.replace(needle,guard+needle)
needle2='''        sp.on_chunk = [&](const float* R_rows, int64_t T, int64_t p0, std::string& e) -> bool {
'''
assert original.count(needle2)==1
capture='''            if (const char* path = std::getenv("STRATA_BENCH_LOGITS")) {
                // Read the frozen tail from the completed prefill residuals. No target layers are rerun.
                // One normal serving head per row; temporary head buffers do not alter R_rows or model state.
                std::FILE* f = std::fopen(path, "ab");
                if (!f || !native_head.loaded()) { if (f) std::fclose(f); e = "benchmark logits open/head"; return false; }
                std::vector<float> row((size_t) n_vocab);
                for (int64_t t = 0; t < T; ++t) {
                    const int64_t pos = p0 + t;
                    if (pos < 384 || pos >= 512) continue;
                    auto bb = ss.block;
                    bb.R = const_cast<float*>(R_rows + (size_t) t * (size_t) (g.hc * g.n_embd));
                    if (!strata::core::lm_head_mix(wt, g, bb, main_cs, e) ||
                        !native_head.run(bb.mixed, d_logits, main_cs, e) ||
                        cudaStreamSynchronize(main_stream) != cudaSuccess ||
                        cudaMemcpy(row.data(), d_logits, (size_t) n_vocab * sizeof(float), cudaMemcpyDeviceToHost) != cudaSuccess) {
                        std::fclose(f); if (e.empty()) e = "benchmark logits readback"; return false;
                    }
                    const int64_t record[2] = {pos, n_vocab};
                    if (std::fwrite(record, sizeof(record), 1, f) != 1 ||
                        std::fwrite(row.data(), sizeof(float), row.size(), f) != row.size()) {
                        std::fclose(f); e = "benchmark logits write"; return false;
                    }
                }
                if (std::fclose(f) != 0) { e = "benchmark logits close"; return false; }
            }
'''
modified=modified.replace(needle2,needle2+capture)
target=SOURCE/'src/program/generate_benchmark.cpp'
if target.exists():
    prior=TASK/'diagnostics/pre-zero-replay-benchmark-source.cpp'
    if not prior.exists():prior.parent.mkdir(parents=True,exist_ok=True);prior.write_bytes(target.read_bytes())
target.write_text(modified)
cmake=SOURCE/'CMakeLists.txt'
if 'add_executable(strata-benchmark ' not in cmake.read_text():
    with cmake.open('a') as stream:stream.write('''\n# Isolated benchmark target: normal inference code with cache control and passive logits readback.
add_executable(strata-benchmark src/program/generate_benchmark.cpp)
target_include_directories(strata-benchmark PRIVATE ${_strata_gpu_include_directories})
target_link_libraries(strata-benchmark PRIVATE strata_engine strata_prefill strata_spec ${_strata_gpu_runtime_target})
''')
diff=subprocess.run(['diff','-u',str(SOURCE/'src/program/generate.cpp'),str(target)],capture_output=True,check=False)
assert diff.returncode==1
(TASK/'benchmark-source.diff').write_bytes(diff.stdout)
subprocess.run(['cmake','--build',str(TASK/'build-halo'),'--target','strata-benchmark','-j8'],check=True)
(TASK/'benchmark-build-receipt.json').write_text(json.dumps(dict(status='BUILT',upstream_revision='1735d6471df29b42c26170efaac1f1446a58640f',original_source_sha256=hashlib.sha256((SOURCE/'src/program/generate.cpp').read_bytes()).hexdigest(),benchmark_source_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),benchmark_binary_sha256=hashlib.sha256((TASK/'build-halo/strata-benchmark').read_bytes()).hexdigest(),behavior='BENCH_RESET invalidates conversation state; BENCH_PIN_PREFIX snapshots a completed primer; bench_reuse rejects missing exact-depth cache before prefill; passive normal-head logits readback; no model math changes'),indent=2)+'\n')
