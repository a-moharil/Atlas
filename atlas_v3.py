"""Source provenance, honest ingestion telemetry and provider-owned map features.
Data are actual completed requests. Provider map images are never fabricated locally.
"""
from __future__ import annotations
import collections, datetime as dt, json, re, time, urllib.parse
from contextlib import closing

def init(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS ingestion_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT NOT NULL,
        finished TEXT, status TEXT NOT NULL DEFAULT 'running',
        attempted INTEGER NOT NULL DEFAULT 0, succeeded INTEGER NOT NULL DEFAULT 0,
        failed INTEGER NOT NULL DEFAULT 0, returned INTEGER NOT NULL DEFAULT 0,
        inserted INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS ingestion_attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, source_id TEXT NOT NULL,
        started TEXT NOT NULL, finished TEXT NOT NULL,
        elapsed_ms INTEGER NOT NULL, success INTEGER NOT NULL,
        returned INTEGER NOT NULL, inserted INTEGER NOT NULL,
        error TEXT NOT NULL DEFAULT '',
        FOREIGN KEY(run_id) REFERENCES ingestion_runs(id));
    CREATE INDEX IF NOT EXISTS attempts_time_idx ON ingestion_attempts(finished DESC);
    CREATE INDEX IF NOT EXISTS attempts_source_time_idx ON ingestion_attempts(source_id,finished DESC);
    ''')
    con.commit()

def run_start(db_connect, now):
    with closing(db_connect()) as con:
        cur=con.execute('INSERT INTO ingestion_runs(started) VALUES(?)',(now(),))
        con.commit(); return cur.lastrowid

def run_finish(db_connect, run_id, now):
    with closing(db_connect()) as con:
        con.execute('''UPDATE ingestion_runs SET finished=?,status='complete',
          attempted=(SELECT count(*) FROM ingestion_attempts WHERE run_id=?),
          succeeded=(SELECT count(*) FROM ingestion_attempts WHERE run_id=? AND success=1),
          failed=(SELECT count(*) FROM ingestion_attempts WHERE run_id=? AND success=0),
          returned=(SELECT coalesce(sum(returned),0) FROM ingestion_attempts WHERE run_id=?),
          inserted=(SELECT coalesce(sum(inserted),0) FROM ingestion_attempts WHERE run_id=?) WHERE id=?''',
          (now(),run_id,run_id,run_id,run_id,run_id,run_id))
        con.commit()

def record(db_connect,run_id,source_id,started,finished,success,returned,inserted,error,elapsed_ms):
    with closing(db_connect()) as con:
        con.execute('''INSERT INTO ingestion_attempts
          (run_id,source_id,started,finished,elapsed_ms,success,returned,inserted,error)
          VALUES(?,?,?,?,?,?,?,?,?)''',
          (run_id,source_id,started,finished,int(elapsed_ms),int(success),int(returned),int(inserted),str(error)[:300]))
        con.commit()

def metrics(db_connect,feeds,channels,research,last_cycle,running):
    configs = feeds + [dict(id=c['id'],name=c['name'],desk='Video',tier='video',region=c.get('region','Global'),mode='YouTube Atom') for c in channels] + [dict(id='openalex_'+q['id'],name=q['name'],desk='Research',tier='research',region='Global',mode='OpenAlex') for q in research]
    lookup={c['id']:c for c in configs}
    with closing(db_connect()) as con:
        runs=[dict(x) for x in con.execute('SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 60')]
        attempts=[dict(x) for x in con.execute('SELECT * FROM ingestion_attempts ORDER BY id DESC LIMIT 6000')]
        rows=[dict(x) for x in con.execute('SELECT source_id,medium,count(*) AS records,MAX(published) AS latest_publication,MAX(retrieved) AS last_seen FROM entries GROUP BY source_id,medium')]
        status={x['id']:dict(x) for x in con.execute('SELECT * FROM feeds_status')}
        num=sum(x['records'] for x in rows)
        published=[dict(r) for r in con.execute("SELECT source_id,substr(published,1,10) AS day,count(*) AS n FROM entries WHERE published>=datetime('now','-14 days') AND published IS NOT NULL GROUP BY source_id,substr(published,1,10)")]
        # published timestamps use ISO 8601 and are strictly source metadata.

    results={x['source_id']:x for x in rows}
    attempts_by=collections.defaultdict(list)
    for a in attempts: attempts_by[a['source_id']].append(a)
    bysource=[]
    for id,c in lookup.items():
        a=attempts_by.get(id,[])
        last=a[0] if a else None
        stored=results.get(id,{})
        s=status.get(id,{})
        bysource.append(dict(id=id,name=c['name'],desk=c.get('desk','World'),tier=c.get('tier','reporting'),mode=c.get('mode','RSS'),
             attempts=len(a),successes=sum(t['success'] for t in a),records=stored.get('records',0),
             latest_publication=stored.get('latest_publication'), last_success=s.get('success'),
             last_attempt=last['finished'] if last else s.get('attempted'), last_returned=last['returned'] if last else 0,
             last_new=last['inserted'] if last else 0,last_result=('ok' if last['success'] else 'error') if last else s.get('state','never'),
             latency_ms=last['elapsed_ms'] if last else None,error=last['error'] if last else s.get('error','')))
    bysource.sort(key=lambda x:(-x['records'],x['name']))
    freq=collections.defaultdict(lambda:collections.defaultdict(int))
    for x in published:freq[x['source_id']][x['day']]+=x['n']
    bypub=[]
    for s in bysource:
        days=freq.get(s['id'],{})
        bypub.append(dict(id=s['id'],name=s['name'],desk=s['desk'],last_14d=sum(days.values()),daily=[dict(day=d,n=n) for d,n in sorted(days.items())]))
    bypub.sort(key=lambda x:-x['last_14d'])
    # Real completed UTC time buckets, no estimated publisher counts.
    bucket=collections.defaultdict(lambda:dict(checks=0,success=0,failed=0,returned=0,new=0))
    for a in attempts:
        hour=a['finished'][:16]+':00Z'
        b=bucket[hour];b['checks']+=1;b['success']+=a['success'];b['failed']+=(1-a['success']);b['returned']+=a['returned'];b['new']+=a['inserted']
    timeline=[dict(time=k,**v) for k,v in sorted(bucket.items())[-72:]]
    desk_counts=collections.defaultdict(lambda:dict(feeds=0,with_records=0,records=0,healthy=0))
    for x in bysource:
        d=desk_counts[x['desk']];d['feeds']+=1;d['records']+=x['records'];d['with_records']+=(x['records']>0);d['healthy']+=(x['last_result']=='ok')
    for run in runs:
        if run['status']=='running':
            current=[a for a in attempts if a['run_id']==run['id']]
            run.update(attempted=len(current),succeeded=sum(a['success'] for a in current),failed=sum(not a['success'] for a in current),returned=sum(a['returned'] for a in current),inserted=sum(a['inserted'] for a in current))
    latest=runs[0] if runs else None
    return dict(configured_sources=len(configs),stored_entries=num,
        last_cycle=last_cycle,server_polling=running, latest_run=latest,
        totals=dict(attempts=len(attempts),succeeded=sum(a['success'] for a in attempts),failed=sum(not a['success'] for a in attempts)),
        timeline=timeline,publication_by_source=bypub,desk_distribution=[dict(desk=k,**v) for k,v in sorted(desk_counts.items(),key=lambda x:-x[1]['records'])],
        sources=bysource,runs=runs[:24], method='Actual SQLite ingestion logs only; counts are retrieved feed items and newly inserted entries, not article readership, underlying publisher output, or source quality.')

# EONET and USGS event catalogues provide real geometry and event properties, not inferred impact fields.
MAP_CATALOG={
    'wildfire_events':'https://eonet.gsfc.nasa.gov/api/v3/events/geojson?category=wildfires&status=open&limit=160',
    'storm_events':'https://eonet.gsfc.nasa.gov/api/v3/events/geojson?category=severeStorms&status=open&limit=100',
    'earthquakes':'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson'
}
CACHE={}

def map_catalog(layer,fetch_bytes):
    if layer not in MAP_CATALOG:raise ValueError('Unsupported map data layer')
    key='map:'+layer
    hit=CACHE.get(key)
    if hit and time.monotonic()-hit['t']<900:return {**hit['value'],'cached':True}
    try:
        data=json.loads(fetch_bytes(MAP_CATALOG[layer],2_500_000).decode('utf-8'))
        feats=data.get('features',[])
        if not isinstance(feats,list):raise ValueError('Invalid provider FeatureCollection')
        feats=feats[:180]
        result={'type':'FeatureCollection','features':feats,'provider':MAP_CATALOG[layer],'status':'ok','count':len(feats),'cached':False,
                'retrieved':dt.datetime.now(dt.timezone.utc).isoformat()}
        CACHE[key]={'t':time.monotonic(),'value':result}
        return result
    except Exception as e:
        if hit:return {**hit['value'],'cached':True,'status':'stale','error':type(e).__name__+': '+str(e)[:130]}
        return {'type':'FeatureCollection','features':[],'provider':MAP_CATALOG[layer],'status':'error','count':0,'error':type(e).__name__+': '+str(e)[:150]}

def shakemap(detail_url,fetch_bytes):
    # Official USGS event-details URL supplied by its earthquake feed, never arbitrary user URL.
    p=urllib.parse.urlparse(detail_url)
    if p.scheme!='https' or p.hostname!='earthquake.usgs.gov' or not p.path.startswith('/earthquakes/feed/v1.0/detail/') or not p.path.endswith('.geojson'):
        raise ValueError('Only canonical USGS earthquake detail URLs are accepted.')
    data=json.loads(fetch_bytes(detail_url,3_000_000).decode('utf-8'))
    products=(data.get('properties',{}).get('products') or {}).get('shakemap',[])
    if not products:
        return {'status':'unavailable','reason':'USGS has not published a ShakeMap for this earthquake.','source':detail_url}
    contents=products[0].get('contents',{})
    candidates=[(k,v.get('url','')) for k,v in contents.items() if re.search(r'cont_mmi\.json$',k,re.I)]
    if not candidates:
        return {'status':'unavailable','reason':'No official macroseismic intensity contour GeoJSON in current ShakeMap product.','source':detail_url}
    url=candidates[0][1]
    p2=urllib.parse.urlparse(url)
    if p2.scheme!='https' or p2.hostname!='earthquake.usgs.gov' or '/product/shakemap/' not in p2.path:raise ValueError('Untrusted intensity product URL')
    contours=json.loads(fetch_bytes(url,2_000_000).decode('utf-8'))
    return {'status':'ok','features':contours,'source':url,'detail':detail_url,'warning':'USGS smoothed intensity contours are for visualization, not loss estimation.'}
