"""Bounded, deduplicated background retrieval with persistent last-good responses."""
import hashlib,json,threading,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
POOL=ThreadPoolExecutor(max_workers=3,thread_name_prefix='research-data')
LOCK=threading.RLock()
JOBS={}

def request(key, loader, directory, force=False, ttl=21600):
    directory=Path(directory); token=hashlib.sha256(key.encode()).hexdigest()
    path=directory/(token+'.json');now=time.time()
    with LOCK:
        job=JOBS.get(key)
        if job is None:
            job={'data':None,'checked':0,'running':False,'error':None};JOBS[key]=job
            try:
                saved=json.loads(path.read_text());job.update(data=saved['data'],checked=saved['checked'])
            except (OSError,ValueError,KeyError):pass
        due=now-job['checked']>(60 if job['error'] or (job['data'] or {}).get('data_status')=='partial' else ttl)
        if not job['running'] and (force or due):
            # Cap queued work too, so repeated selections cannot create an unbounded queue.
            if sum(j['running'] for j in JOBS.values())>=12:
                return {**(job['data'] or {'points':[]}), 'pending':False,'error':'Retrieval queue is full. Retry shortly.','data_status':'unavailable'}
            job['running']=True
            def work():
                try:
                    result=loader()
                    if result.get('data_status')=='unavailable' or result.get('status')=='unavailable':
                        raise RuntimeError(result.get('error','Provider unavailable'))
                    with LOCK:
                        job.update(data=result,checked=time.time(),error=None)
                        try:
                            directory.mkdir(parents=True,exist_ok=True)
                            temp=path.with_suffix('.tmp');temp.write_text(json.dumps({'data':result,'checked':job['checked']}));temp.replace(path)
                        except OSError:pass
                except Exception as exc:
                    with LOCK:job.update(error=str(exc)[:400],checked=time.time())
                finally:
                    with LOCK:job['running']=False
            POOL.submit(work)
        out=dict(job['data'] or {'points':[],'value_usd':None})
        out.update(pending=job['running'],last_checked=job['checked'],error=job['error'])
        if job['running']:out.update(cache_state='cached; updating' if job['data'] else 'retrieving',note='Provider retrieval is running in the background. This view polls for completion.')
        elif job['error']:out.update(cache_state='stale cache' if job['data'] else 'unavailable',data_status='stale' if job['data'] else 'unavailable',status='stale' if job['data'] else 'unavailable')
        return out
