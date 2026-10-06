import json,os,struct,subprocess,time
import numpy as np
from benchmark_common import *
def main():
    out=TASK/'results/fidelity';assert not out.exists();out.mkdir(parents=True)
    subprocess.run([str(TASK/'python/bin/python3'),str(TASK/'validate_sweep_scope.py'),'short_fidelity','--source-path',str(TASK/'scope-latest-suite.json')],check=True)
    panel=TASK/'fidelity-panel';manifest=json.loads((panel/'panel.json').read_text())
    assert sha(panel/'panel.json')=='bf511a01fc410421b303196a4e716f49dd77bffcc5a49a4379d1fd5d747eb0b2'
    assert sha(panel/'panel.tokens.i32le')==manifest['panel_sha256']
    assert sha(panel/'panel.labels.i32le')==manifest['label_sha256']
    tokens=np.fromfile(panel/'panel.tokens.i32le',dtype='<i4').reshape(16,512)
    labels=np.fromfile(panel/'panel.labels.i32le',dtype='<i4').reshape(16,128)
    meta=api('/bench/meta');assert meta['generation_count']==0 and '--mtp' not in meta['args']
    capture=TASK/'fidelity-capture.bin';assert not capture.exists()
    save(out/'protocol.lock.json',dict(panel='short_fidelity',windows=16,input_tokens=512,positions_per_window=128,vocab=248320,
        scored_positions=list(range(384,512)),mode='Raw teacher-forced target-only prefill; no MTP',
        engine=meta,context_capacity=262144,cache_prompt=False,retries=0,first_attempt_only=True,
        capture='Completed prefill residuals read through the normal serving head; no target layers rerun',
        terminal_known_label='Append next label at position 512 so serving prefill covers exactly the original 512-input window; terminal prediction is unscored',
        teacher_sha256='1cae8a0896aecd63951ad7a1d7e31d9cf20fab7c28a0ad8903c1938f8a5513e7',
        panel_manifest_sha256=sha(panel/'panel.json'),tokens_sha256=manifest['panel_sha256'],labels_sha256=manifest['label_sha256']))
    requests=[]
    for i in range(16):
        ids=list(map(int,tokens[i]))+[int(labels[i,-1])];assert all(0<=t<248320 for t in ids)
        # The causal label for each selected input position is its following token.
        assert np.array_equal(tokens[i,385:512],labels[i,:127])
        body=dict(ids=ids,max_tokens=1);save(out/f'window-{i:02d}-request.json',body);requests.append(body)
    generated=out/'candidate.f32le';progress=[]
    offset=0;row_bytes=248320*4;record_bytes=16+row_bytes
    with generated.open('xb') as output:
        for i,body in enumerate(requests):
            assert resources()['ram_available']>4.5*1024**3
            started=time.monotonic()
            with Samples() as samples:response=api('/bench/fidelity',body,1200)
            save(out/f'window-{i:02d}-response.json',response);save(out/f'window-{i:02d}-samples.json',samples.rows)
            assert capture.stat().st_size==offset+128*record_bytes,(i,capture.stat().st_size,offset)
            with capture.open('rb') as stream:
                stream.seek(offset)
                for pos in range(384,512):
                    assert struct.unpack('<qq',stream.read(16))==(pos,248320)
                    raw=stream.read(row_bytes);values=np.frombuffer(raw,dtype='<f4');assert values.size==248320 and np.isfinite(values).all()
                    output.write(raw)
            output.flush();offset+=128*record_bytes
            row=dict(window=i,positions=128,wall_seconds=time.monotonic()-started,memory=samples.summary(),native_timings=response['last'])
            progress.append(row);save(out/'progress.json',dict(rows=progress));print(json.dumps(dict(event='FIDELITY_WINDOW_COMPLETE',**row)),flush=True)
    assert generated.stat().st_size==2034237440
    # Capture and normalized logits are both retained until a verified archive exists.
    save(out/'capture-result.json',dict(status='COMPLETE',windows=16,positions=2048,vocabulary=248320,
        candidate_sha256=sha(generated),capture_sha256=sha(capture),rows=progress))
if __name__=='__main__':main()
