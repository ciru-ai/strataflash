"""Transparent benchmark routes around the pinned Strata HTTP service.

Chat/tool serving remains upstream. Raw requests use the same resident engine
with literal prompt IDs. Receipts retain every effective sampler and DONE line.
"""
import hashlib, json, os, queue, sys, threading, time
from pathlib import Path
TASK=Path(__file__).resolve().parent
sys.path.insert(0,str(TASK/'source'))
from serve import server as upstream

JOURNAL=Path(os.environ['STRATA_BENCH_JOURNAL'])
lock=threading.Lock()
def record(value):
    with lock, JOURNAL.open('a') as stream:
        stream.write(json.dumps(dict(at=time.time(),**value),ensure_ascii=False)+'\n')

old_generate=upstream.StrataEngine.generate
old_done=upstream.StrataEngine._parse_done
def parse_done(self,line):
    old_done(self,line)
    self.bench_done_line=line.strip()
def generate(self,ids,max_new,sampling,cancel,embeddings=None):
    # Passive instrumentation; forward the exact IDs, settings and iterator.
    started=time.monotonic()
    receipt=dict(event='native_request',prompt_tokens=len(ids),
        prompt_ids_sha256=hashlib.sha256(','.join(map(str,ids)).encode()).hexdigest(),
        max_new=max_new,sampling=sampling,wire_sampling_keys=self.sampling_keys(sampling),pid=self.proc.pid)
    record(receipt)
    emitted=[]
    try:
        for token in old_generate(self,ids,max_new,sampling,cancel,embeddings):
            if token is not None:emitted.append(token)
            yield token
    finally:
        record(dict(event='native_response',wall_seconds=time.monotonic()-started,
            emitted_ids=emitted,last=self.last,done_line=getattr(self,'bench_done_line',None)))
upstream.StrataEngine.generate=generate
upstream.StrataEngine._parse_done=parse_done

def reset(engine):
    assert 'strata-benchmark' in engine.spawn[0]
    engine.proc.stdin.write('BENCH_RESET\n');engine.proc.stdin.flush()
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        line=engine.lines.get(timeout=max(.1,deadline-time.monotonic()))
        if line is None or line.startswith('ERR'):raise RuntimeError(str(line))
        if line.strip()=='BENCH_RESET_OK':
            record(dict(event='cache_reset',lookup_and_expert_history_retained=True));return
    raise TimeoutError('BENCH_RESET')

old_make=upstream.make_handler
def make_handler(svc):
    base=old_make(svc)
    class Handler(base):
        def do_GET(self):
            if self.path=='/bench/meta':
                if not self._authorized():return
                self._json(200,dict(engine_info=svc.engine.info,native_pid=svc.engine.proc.pid,
                    args=svc.engine.spawn[1],exe=svc.engine.spawn[0],last=svc.engine.last,
                    journal=str(JOURNAL),context=svc.engine.max_context,
                    generation_count=sum(1 for line in JOURNAL.read_text().splitlines() if '"event": "native_request"' in line) if JOURNAL.exists() else 0))
                return
            return super().do_GET()

        def do_POST(self):
            path=self.path.split('?')[0].rstrip('/')
            if path not in ('/tokenize','/apply-template','/v1/completions','/bench/fidelity'):
                return super().do_POST()
            if not self._authorized():return
            body=json.loads(self._body())
            if path=='/tokenize':
                ids=svc.tok.encode(body['content'],parse_special=body.get('parse_special',True))
                self._json(200,dict(tokens=ids));return
            if path=='/apply-template':
                messages,tools,kwargs=upstream.openai_to_messages(body)
                kwargs.update(body.get('chat_template_kwargs') or {})
                prompt=svc.render_prompt(messages,tools,kwargs)
                ids=svc.encode_prompt(messages,tools,kwargs)
                self._json(200,dict(prompt=prompt,tokens=ids));return
            try:
                with svc.fifo:
                    if path=='/bench/fidelity':
                        ids=body['ids'];assert len(ids)==513 and body['max_tokens']==1
                        reset(svc.engine)
                        emitted=[t for t in svc.engine.generate(ids,1,{},threading.Event()) if t is not None]
                        self._json(200,dict(tokens=emitted,last=svc.engine.last));return
                    assert body['model']==svc.model
                    assert isinstance(body['prompt'],str) and body['stream'] and body['ignore_eos']
                    assert '--eos-ids' in svc.engine.spawn[1]
                    assert svc.engine.spawn[1][svc.engine.spawn[1].index('--eos-ids')+1]=='9999999'
                    ids=svc.tok.encode(body['prompt'],parse_special=True)
                    count=body['max_tokens']
                    assert 0<count and len(ids)+count+8<=svc.engine.max_context
                    if body['cache_prompt'] is False:reset(svc.engine)
                    sampling={key:body[key] for key in ('temperature','top_p','top_k','min_p',
                        'presence_penalty','frequency_penalty','seed')}
                    sampling['repetition_penalty']=body['repeat_penalty']
                    assert sampling['min_p']==0 and sampling['presence_penalty']==0 and sampling['frequency_penalty']==0 and sampling['repetition_penalty']==1
                    self._sse()
                    emitted=[];previous=''
                    def send(value):
                        self.wfile.write(('data: '+json.dumps(value,ensure_ascii=False)+'\n\n').encode());self.wfile.flush()
                    for token in svc.engine.generate(ids,count,sampling,threading.Event()):
                        if token is None:
                            self.wfile.write(b': heartbeat\n\n');self.wfile.flush();continue
                        emitted.append(token)
                        text=svc.tok.decode(emitted)
                        assert text.startswith(previous),'Raw counting decode must be append-only'
                        delta=text[len(previous):];previous=text
                        send(dict(model=svc.model,choices=[dict(index=0,text=delta,finish_reason=None)]))
                    last=svc.engine.last
                    send(dict(model=svc.model,choices=[dict(index=0,text='',finish_reason='length' if last['finish']=='limit' else last['finish'])],
                        usage=dict(prompt_tokens=len(ids),completion_tokens=len(emitted),total_tokens=len(ids)+len(emitted)),
                        timings=upstream.request_timings(len(ids),len(emitted),last),native_timings=last))
                    self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError):raise
            except BaseException as error:
                record(dict(event='adapter_error',type=type(error).__name__,message=str(error)))
                # The client keeps the first transport outcome; never retry here.
                raise
    return Handler
upstream.make_handler=make_handler
if __name__=='__main__':raise SystemExit(upstream.main())
