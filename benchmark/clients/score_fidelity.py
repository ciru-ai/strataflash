"""CPU scoring with the same full-vocabulary KL, NLL, top1 and RMSE definitions."""
import csv,json,math
from pathlib import Path
import numpy as np
from benchmark_common import save,sha
TASK=Path('/benchmark-storage')
def main():
    out=TASK/'results/fidelity';receipt=json.loads((out/'capture-result.json').read_text());assert receipt['status']=='COMPLETE'
    candidate=out/'candidate.f32le';teacher=TASK/'fidelity/teacher.f32le'
    assert sha(candidate)==receipt['candidate_sha256'];assert sha(teacher)=='1cae8a0896aecd63951ad7a1d7e31d9cf20fab7c28a0ad8903c1938f8a5513e7'
    n,v=2048,248320
    refs=np.memmap(teacher,dtype='<f4',mode='r',shape=(n,v));cands=np.memmap(candidate,dtype='<f4',mode='r',shape=(n,v))
    labels=np.fromfile(TASK/'fidelity/panel/panel.labels.i32le',dtype='<i4')
    metrics={key:np.zeros(n) for key in ['mean_teacher_KL','teacher_top1_agreement','mean_candidate_NLL','mean_teacher_NLL','mean_logit_RMSE','teacher_top1_tie_aware_agreement','teacher_top1_tied_rows']}
    for start in range(0,n,16):
        end=start+16;r=np.asarray(refs[start:end],dtype=np.float64);c=np.asarray(cands[start:end],dtype=np.float64)
        assert np.isfinite(r).all() and np.isfinite(c).all()
        row=np.arange(16);rtop=r.argmax(axis=1);ctop=c.argmax(axis=1)
        metrics['mean_logit_RMSE'][start:end]=np.sqrt(((c-r)**2).mean(axis=1))
        metrics['teacher_top1_agreement'][start:end]=(rtop==ctop)
        metrics['teacher_top1_tie_aware_agreement'][start:end]=(r[row,ctop]==r[row,rtop])
        metrics['teacher_top1_tied_rows'][start:end]=((r==r[row,rtop,None]).sum(axis=1)>1)
        r-=r.max(axis=1,keepdims=True);c-=c.max(axis=1,keepdims=True)
        rlp=r-np.log(np.exp(r).sum(axis=1,keepdims=True));clp=c-np.log(np.exp(c).sum(axis=1,keepdims=True))
        kl=(np.exp(rlp)*(rlp-clp)).sum(axis=1);assert kl.min()>-1e-8
        metrics['mean_teacher_KL'][start:end]=kl
        metrics['mean_candidate_NLL'][start:end]=-clp[row,labels[start:end]]
        metrics['mean_teacher_NLL'][start:end]=-rlp[row,labels[start:end]]
    rows=[]
    for window in range(16):rows.append(dict(tag='window',window=window,rows=128,**{key:float(value[window*128:(window+1)*128].mean()) for key,value in metrics.items()}))
    total=dict(tag='all',window=-1,rows=2048,**{key:float(value.mean()) for key,value in metrics.items()});rows.append(total)
    with (out/'scores.csv').open('x',newline='') as stream:writer=csv.DictWriter(stream,fieldnames=list(total));writer.writeheader();writer.writerows(rows)
    save(out/'summary.json',dict(status='COMPLETE',metrics=total,masked_tail_ppl=math.exp(total['mean_candidate_NLL']),
        source='Same 16x512 frozen input windows, last128 logits, full248320 vocabulary; BF16 teacher unchanged',
        candidate_sha256=receipt['candidate_sha256'],teacher_sha256=sha(teacher),rows=rows))
    print((out/'summary.json').read_text(),flush=True)
if __name__=='__main__':main()
