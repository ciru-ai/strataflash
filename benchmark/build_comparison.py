"""Build the comparison from audited saved results, without inference."""
import csv,hashlib,json,statistics
from pathlib import Path
TASK=Path(__file__).resolve().parent
def load(name):return json.loads((TASK/name).read_text())
def save(name,value):(TASK/name).write_text(json.dumps(value,indent=2)+'\n')
def show(value,digits=1):return '—' if value is None else f'{value:.{digits}f}'
def main():
    final_restore=load('final-restoration-verification.json')
    assert final_restore['status']=='VERIFIED' and final_restore['health']['status']=='ok'
    assert final_restore['benchmark_gpu_released'] and final_restore['hardware_unchanged']
    audits={p:load('ownership/'+p+'/integrity-audit.json') for p in ['he09','counting-zero-replay','fidelity','tools','hermes']}
    assert all(d['status']=='PASS' for d in audits.values())
    agent=load('results/agent-evidence-audit.json');assert agent['status']=='AUDITED' and agent['hermes_scored_cases']==40
    he=load('results/he09/summary.json');grid=load('results/counting-zero-replay/summary.json');fid=load('results/fidelity/summary.json')
    tools=load('results/tools/full/report.json');tool_audit=load('results/tools/full/integrity.json')
    assert he['status']==grid['status']==fid['status']==tool_audit['status']=='COMPLETE'
    assert he['usable_cases']==10 and grid['scored_cells']==18 and grid['cached_prefix_replayed_tokens']==0
    stages=[load('results/hermes/'+stage+'/execution-evidence.json') for stage in ['pass1','pass2']]
    assert all(s['cases']==20 and s['first_attempt_only'] for s in stages)
    assets=load('serving-asset-sizes.json');memory=[]
    for panel in audits:
        owner=TASK/'ownership'/panel;ready=json.loads((owner/'ready.json').read_text())['resources']
        f=owner/'resource-summary.json'
        if f.exists():
            peak=json.loads(f.read_text());samples=json.loads((owner/'resource-samples.json').read_text());idle=samples[0]
            # Samples begin after production has stopped and before the benchmark process starts.
            memory.append(dict(panel=panel,ready_ram_used_bytes=ready['ram_used'],peak_ram_used_bytes=peak['max_ram_used'],
                minimum_available_bytes=peak['min_ram_available'],pre_load_ram_used_bytes=idle['ram_used'],
                peak_extra_ram_bytes=max(0,peak['max_ram_used']-idle['ram_used']),uma_overlap=True))
        else:
            peak=max(row['memory']['max_ram_used'] for row in he['rows']);available=min(row['memory']['min_ram_available'] for row in he['rows'])
            memory.append(dict(panel=panel,ready_ram_used_bytes=ready['ram_used'],peak_ram_used_bytes=peak,
                minimum_available_bytes=available,pre_load_ram_used_bytes=None,peak_extra_ram_bytes=None,uma_overlap=True))
    new=dict(id='strata-v0140',model='Strata v0.1.40 · UD-IQ4_XS',he09_native_tg=he['native_tg'],
        he09_timing='generated/decode_ms, including first prediction and terminal EOS',
        he09_wall=sum(r['wall_seconds'] for r in he['rows']),tools_score=tools['final_score'],
        tools_wall=sum(r['duration_seconds'] for r in tools['scores']['scenario_results']),
        hermes_score=statistics.mean(s['official_score'] for s in stages),hermes_pass_scores=[s['official_score'] for s in stages],
        hermes_mean_case_wall=statistics.mean(s['case_wall_sum_seconds'] for s in stages),
        fidelity_kl=fid['metrics']['mean_teacher_KL'],fidelity_top1=fid['metrics']['teacher_top1_agreement']*100,
        fidelity_ppl=fid['masked_tail_ppl'],serving_asset_gib=assets['serving_assets_unique_logical_bytes']/2**30)
    baselines=load('saved-comparators.json')['rows'];api=load('saved-api-comparator.json')
    for row in baselines:
        if row['id']=='carlos':row['model']='Carlos ROCmFPX2 · HC-Q8'
    rows=[new]+baselines+[api];saved=load('saved-panel-comparators.json')
    comparison=dict(status='COMPLETE_AUDITED',model_release='https://github.com/Niko1221/Strata/releases/tag/v0.1.40',
        revision=load('experiment-plan.json')['runtime_revision'],rows=rows,memory=memory,
        append_rows=[r for r in grid['rows'] if r['scored']],cold_rows=[r for r in grid['rows'] if r['name'].endswith('-primer')],
        clean_counting_cells=grid['clean_counting_cells'],total_counting_cells=18,zero_prefix_replay=True,
        audits=audits,agent_evidence=agent,final_restoration=final_restore,saved_baseline_conditions=saved,
        advertised_prefill_audit=load('advertised-prefill-audit.json'),
        timing_note='Strata native decode_ms starts before the first prediction; llama.cpp baselines use (n−1) and exclude first-token prediction. Keep reported native clocks separate.',
        comparison_note='Deployment comparison: different quants and runtimes; historical cache histories and owner lifecycles differ. No baseline reruns.',
        excluded_panels=load('active-sweep-contract.json').get('excluded_panels',[]))
    save('comparison.json',comparison)
    fields=['model','he09_native_tg','he09_wall','tools_score','hermes_score','hermes_mean_case_wall','fidelity_kl','fidelity_top1','fidelity_ppl']
    with (TASK/'comparison.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    lines=['# Strata v0.1.40 comparison','',
        f"All requested panels completed and audited: 18 append cells, five cold prefixes, 16 fidelity windows, HE0–9, 15 tool cases, and **20 cases in each Hermes pass**. The three required Hermes smoke cases are separate.",'',
        f"Strata reported **{new['he09_native_tg']:.1f} native tokens/s** on HE0–9, **{new['tools_score']:g}/100** on tools, and **{new['hermes_score']:g}/100** across the two Hermes passes ({'/'.join(str(s) for s in new['hermes_pass_scores'])}). HE0–9 measures usable output and speed; code correctness is not scored.",'',
        '| Model | HE native TG/s | Tools /100 | Hermes /100 | Hermes 20-case time s | Fidelity KL ↓ | Top-1 agreement | Tail PPL ↓ |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:lines.append(f"| {row['model']} | {show(row.get('he09_native_tg'))} | {show(row.get('tools_score'),0)} | {show(row.get('hermes_score'))} | {show(row.get('hermes_mean_case_wall'))} | {show(row.get('fidelity_kl'),5)} | {show(row.get('fidelity_top1'),2)} | {show(row.get('fidelity_ppl'),4)} |")
    lines+=['',comparison['timing_note'],
        'Fidelity uses the unchanged BF16 teacher, all 248320 logits, and the last 128 positions of each of the 16 frozen 512-token windows. Top-1 agreement is a percentage.',
        'Tools uses the recommended non-thinking sampler. Hermes uses the recommended thinking sampler and unchanged verifier. Carlos ROCmFPX2 has an official tool score of 73 and a separately reviewed score of 80. The table retains the official score.',
        'Hermes time is the mean across the two passes of the sum of 20 individual case times. Carlos ran on Ciru; the other local Hermes rows ran on Sozo. Historical output-cap differences are retained in the comparison JSON. These times do not establish a controlled same-host engine ranking.',
        'The saved Qwen API comparison uses both complete 20-case passes, including the authorized HA-04 adapter correction. Its scored case time excludes repair pauses. Unavailable panels are left blank.',
        '', '## Prefill and append sweep','',
        f"Every timed append reused exactly its D-token prefix and processed only its P new tokens. **Zero cached-prefix replay** was verified in all 18 native receipts. Clean counting output: **{grid['clean_counting_cells']}/18**. First malformed outputs are retained; their TG is diagnostic for that output.",'',
        '| Cached depth | PP/s P512 | PP/s P2048 | PP/s P4096 | TG/s P512 | TG/s P2048 | TG/s P4096 |',
        '|---:|---:|---:|---:|---:|---:|---:|']
    for depth in [0,32000,64000,120000,192000,256000]:
        r={row['prompt']:row for row in grid['rows'] if row['scored'] and row['depth']==depth}
        lines.append('| '+str(depth)+' | '+' | '.join(show(r[p][key]) for key in ['native_pp','native_tg'] for p in [512,2048,4096])+' |')
    lines+=['','| Cold prefix tokens | Native PP/s | Request wall s |','|---:|---:|---:|']
    for row in comparison['cold_rows']:lines.append(f"| {row['native_timings']['prompt_tokens']} | {row['native_pp']:.1f} | {row['wall_seconds']:.2f} |")
    lines+=['', 'Saved deployment PP observations at P2048 are shown below. The full saved grid and cold-prefix rows, with their original conditions and cache caveats, remain in `comparison.json`.', '',
        '| Model | Append PP/s D0 | Append PP/s D64K | Append PP/s D256K | Cold 64K PP/s |',
        '|---|---:|---:|---:|---:|']
    for row in rows:
        if row['id']=='strata-v0140':
            vals=[next(r['native_pp'] for r in grid['rows'] if r['scored'] and r['prompt']==2048 and r['depth']==d) for d in [0,64000,256000]]
            cold=next(r['native_pp'] for r in comparison['cold_rows'] if r['native_timings']['prompt_tokens']==64000)
        else:
            vals=[next((r['pp'] for r in saved['append']['rows'] if r['modelId']==row['id'] and r['promptTokens']==2048 and r['depthTokens']==d),None) for d in [0,64000,256000]]
            cold=next((r['tps'] for r in saved['cold']['rows'] if r['modelId']==row['id'] and r['inputTokens']==64000),None)
        if any(v is not None for v in vals) or cold is not None:
            lines.append('| '+row['model']+' | '+' | '.join(show(v) for v in [*vals,cold])+' |')
    cold64=next(r['native_pp'] for r in comparison['cold_rows'] if r['native_timings']['prompt_tokens']==64000)
    gap=(cold64/1370-1)*100
    lines+=['', '## Advertised prefill gap', '',
        f"The [v0.1.40 release](https://github.com/Niko1221/Strata/releases/tag/v0.1.40) reports 1370 PP/s at 64K for UD-IQ4_XS on a 128GB Strix Halo. This run measured **{cold64:.1f} PP/s**, a **{abs(gap):.1f}% lower** observation.",
        'The [pinned Strix Halo methodology](https://github.com/Niko1221/Strata/blob/1735d6471df29b42c26170efaac1f1446a58640f/docs/STRIX_HALO.md) describes optional kernels that change numerics, and also gives a default-config remeasurement of 1299 PP/s at 128K. The default figure is also substantially higher than our observation; optional switches have not been established as the cause. The optimized HIP build, ROCm version, accepted tuning table and 18 automatic gfx1151 defaults were checked.',
        'Known differences include workload, host OS/kernel/IOMMU configuration, serving context and a single selected-protocol run rather than interleaved medians. Their causal contribution has not been established. An exact reproduction of the publisher workload has not been performed; no additional reruns or host changes were made. `advertised-prefill-audit.json` retains the evidence.',
        '',
        'The original one-warmup / five-primer / 18-append request bodies, sampler, order, seed and output limits are unchanged. Exact-depth snapshots use native checkpoint save/restore; pinning performs no generation and is outside the timed append. A native guard rejects missing exact-depth state before prefill. The superseded periodic-checkpoint sweep remains a diagnostic archive.',
        'Native PP counts the last input token while its work is charged to the decode clock. The source timing addendum retains that boundary. Historical stacks have different server lifecycles, and Carlos has unrecovered prior lookup history; this does not establish an engine-only or warmed-cache speedup.',
        '', '## Resources and reproduction','',
        f"Serving weights, native pack and MTP total **{new['serving_asset_gib']:.2f} GiB** ({assets['serving_assets_unique_logical_bytes']} bytes), deduplicated by filesystem object. SDK and build caches are excluded.",'',
        '| Panel | Ready host RAM GiB | Peak host RAM GiB | Minimum available GiB |',
        '|---|---:|---:|---:|']
    for row in memory:lines.append('| '+row['panel']+' | '+' | '.join(f'{row[key]/2**30:.2f}' for key in ['ready_ram_used_bytes','peak_ram_used_bytes','minimum_available_bytes'])+' |')
    new_pressure=max(r['peak_extra_ram_bytes'] for r in memory if r['peak_extra_ram_bytes'] is not None)/2**30
    lines+=['', '| Deployment | Serving assets GiB | Recorded host pressure GiB | Memory method |',
        '|---|---:|---:|---|',
        f"| {new['model']} | {new['serving_asset_gib']:.2f} | {new_pressure:.2f} | Peak MemAvailable drop from post-production-stop, pre-load sample |"]
    for row in saved['memory']['rows']:
        label='Carlos ROCmFPX2 · HC-Q8' if row['modelId']=='carlos' else row['model']
        lines.append(f"| {label} | {show(row.get('packageGiB'),2)} | {show(row.get('hostPressureGiB'),2)} | {row['method']} |")
    lines+=['',
        'Historical package and memory methods have their original scope; the saved owner lifecycle and memory caveats remain in comparison.json. The new peak includes the measured panel lifecycle. HE0–9 has no matching pre-load global sample, so its ready and per-case peaks are retained separately.',
        'Host RAM, GTT, VRAM and process RSS overlap on this UMA host. These are host measurements, not quantities to add. Every owner verified exclusive GPU access and restored qwen-main with unchanged hardware settings.',
        'Runtime: pinned v0.1.40 / ROCm 7.14.1 / gfx1151, context262144, prefill16384, int8 KV, resident experts, MTP spec4, lookup chain3, MTP Q4 all. Fidelity is target-only with --spec2 and no MTP; native IQ packs require that startup setting. The first missing-spec startup refused before generation and remains infrastructure evidence. Optional numeric fast kernels are off. All 64 HIP compilation commands use -O3 -DNDEBUG.',
        '',
        'Requests, raw responses, native DONE lines, resource samples and audits are under `results/` and `ownership/`. `experiment-plan.json`, `zero-replay-contract.json`, `timing-definition-addendum.json`, `comparison-source-receipt.json` and the source/build receipts pin the protocol. Large fidelity logits and their verified hashes remain in the Ciru task archive.',
        'No Core-19, pagoda/garden, engineering/wide fidelity, full164 HumanEval or HumanEval+ was added. No baseline model was rerun. The unoptimized HIP setup attempt is retained as infrastructure evidence.',
        '']
    (TASK/'REPORT.md').write_text('\n'.join(lines))
    save('status.json',dict(status='COMPLETE_AUDITED',panels=['append_speed_grid','cold_prefix','short_fidelity','he09_speed','hard_tool_15','hermesagent20','memory_and_disk'],hermes_pass_cases=[20,20],zero_prefix_replay=True))
    print(json.dumps(new,indent=2))
if __name__=='__main__':main()
