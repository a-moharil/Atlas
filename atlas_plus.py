"""Careful source-grounded digests and geophysical live layers for ATLAS.

This module deliberately does not infer article ideology from a headline.
Environmental data is fetched from first-party public endpoints; results are
cached and failures visible rather than silently treated as empty live datasets.
"""
import datetime as dt
import json
import re
import urllib.parse
from contextlib import closing

LAYER_SOURCES = {
    'wildfires': {'label':'NASA EONET · active wildfire reports', 'url':'https://eonet.gsfc.nasa.gov/api/v3/events?category=wildfires&status=open&limit=140', 'credit':'https://eonet.gsfc.nasa.gov/docs/v3'},
    'storms': {'label':'NASA EONET · active severe storms', 'url':'https://eonet.gsfc.nasa.gov/api/v3/events?category=severeStorms&status=open&limit=80', 'credit':'https://eonet.gsfc.nasa.gov/docs/v3'},
    'earthquakes': {'label':'USGS · M4.5+ earthquakes, last 24 hours', 'url':'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson', 'credit':'https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php'},
    'wind': {'label':'Open-Meteo · sampled current 10m wind, NOT a continuous field', 'url':'https://api.open-meteo.com/v1/forecast', 'credit':'https://open-meteo.com/en/docs'}
}
WIND_LOCATIONS = [(-122.3,37.8),(-73.9,40.7),(-2.2,51.5),(12.5,41.9),(30.5,50.5),(37.6,55.8),(55.3,25.2),(77.2,28.6),(72.9,19.1),(116.4,39.9),(121.5,31.2),(139.7,35.7),(103.8,1.3),(151.2,-33.9),(18.4,-33.9),(-47.9,-15.8),(31.2,-1.3),(80.2,13.1),(-70.7,-33.5),(103.9,30.6)]

def init_geo(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS geo_layers(
      name TEXT PRIMARY KEY, retrieved TEXT, state TEXT NOT NULL,
      error TEXT NOT NULL DEFAULT '', points_json TEXT NOT NULL DEFAULT '[]')''')
    conn.commit()

def _lonlat_from_geometry(geometry):
    if not isinstance(geometry,dict):return None
    typ=geometry.get('type','')
    p=geometry.get('coordinates',[])
    if typ=='Point' and len(p)>=2:return p[:2]
    if typ=='Polygon' and p and p[0] and p[0][0]:return p[0][0][:2]
    if typ=='MultiPolygon' and p and p[0] and p[0][0] and p[0][0][0]:return p[0][0][0][:2]
    return None

def normalize_geo(name,data):
    out=[]
    if name in ('wildfires','storms'):
        for x in data.get('events',[]):
            geo=(x.get('geometry') or [])
            if not geo:continue
            last=geo[-1]
            xy=_lonlat_from_geometry(last)
            if not xy:continue
            try:lon,lat=map(float,xy)
            except (ValueError,TypeError):continue
            out.append({'id':str(x.get('id',''))[:100], 'lat':lat,'lon':lon,'title':str(x.get('title',''))[:160], 'date':str(last.get('date',''))[:32], 'url':str(x.get('link',''))[:250], 'kind':name})
    if name=='earthquakes':
        for x in data.get('features',[]):
            props=x.get('properties') or {};xy=_lonlat_from_geometry(x.get('geometry'))
            if not xy:continue
            try:lon,lat=map(float,xy)
            except (ValueError,TypeError):continue
            date=''
            if props.get('time'):
                date=dt.datetime.fromtimestamp(props['time']/1000,dt.timezone.utc).isoformat()
            out.append({'id':str(x.get('id',''))[:100], 'lat':lat,'lon':lon,'title':str(props.get('title','Earthquake'))[:160], 'date':date,'url':str(props.get('url',''))[:250], 'kind':name,'mag':props.get('mag')})
    if name=='wind':
        locations=data if isinstance(data,list) else [data]
        for i,x in enumerate(locations[:len(WIND_LOCATIONS)]):
            point=x.get('current') or {}
            if point.get('wind_speed_10m') is None:continue
            lon,lat=WIND_LOCATIONS[i]
            out.append({'id':f'wind-{i}', 'lat':lat,'lon':lon,'title':f"Wind {point['wind_speed_10m']} km/h",'date':point.get('time',''),'kind':'wind','speed':point.get('wind_speed_10m'),'direction':point.get('wind_direction_10m'),'temp':point.get('temperature_2m')})
    return out[:160]

def wind_url():
    lons=','.join(str(x[0]) for x in WIND_LOCATIONS)
    lats=','.join(str(x[1]) for x in WIND_LOCATIONS)
    return LAYER_SOURCES['wind']['url']+'?'+urllib.parse.urlencode({'latitude':lats,'longitude':lons,'current':'temperature_2m,wind_speed_10m,wind_direction_10m','timezone':'UTC'})

def fetch_one_layer(name,fetch_bytes,db_connect,utc_now):
    cfg=LAYER_SOURCES[name]
    try:
        raw=fetch_bytes(wind_url() if name=='wind' else cfg['url'],1_800_000)
        pts=normalize_geo(name,json.loads(raw.decode('utf-8')))
        with closing(db_connect()) as con:
            init_geo(con)
            con.execute('''INSERT INTO geo_layers(name,retrieved,state,error,points_json) VALUES(?,?,?,?,?)
              ON CONFLICT(name) DO UPDATE SET retrieved=excluded.retrieved,state=excluded.state,error=excluded.error,points_json=excluded.points_json''',
              (name,utc_now(),'ok','',json.dumps(pts)))
            con.commit()
    except Exception as e:
        # Preserve cached points; distinguish stale data from empty.
        with closing(db_connect()) as con:
            init_geo(con)
            con.execute('''INSERT INTO geo_layers(name,retrieved,state,error,points_json) VALUES(?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET state=excluded.state,error=excluded.error''',
               (name,None,'error',f'{type(e).__name__}: {str(e)[:170]}','[]'))
            con.commit()

def geo_state(db_connect):
    with closing(db_connect()) as con:
        init_geo(con)
        rows={r['name']:dict(r) for r in con.execute('SELECT * FROM geo_layers')}
    return {name:{'name':name,'label':cfg['label'],'credit':cfg['credit'],
      'retrieved':rows.get(name,{}).get('retrieved'),
      'state':rows.get(name,{}).get('state','pending'),
      'error':rows.get(name,{}).get('error',''),
      'points':json.loads(rows.get(name,{}).get('points_json','[]'))} for name,cfg in LAYER_SOURCES.items()}

def source_digest(entry,related):
    """Only source-attributed excerpts, not invented full-article summaries."""
    raw=re.sub(r'\s+',' ',(entry.get('summary') or '')).strip()
    head=entry.get('title','').strip()
    sentences=re.split(r'(?<=[.!?])\s+(?=[A-Z])',raw)
    digest=' '.join(sentences[:2]).strip()[:440] if raw else ''
    related_unique=[]
    for r in related:
        if r['id']!=entry['id'] and r['source_id']!=entry['source_id'] and r['medium']=='article':
            related_unique.append({'id':r['id'],'title':r['title'],'source':r['source'],'source_id':r['source_id'],'url':r['url'],'summary':r.get('summary','')[:240],'origin_host':r.get('origin_host',''),'published':r.get('published')})
        if len(related_unique)>=8:break
    cues=[]
    for word in ['allegedly','claims','claimed','reportedly','critics','condemned','slammed','warned','vowed','unprecedented','historic','controversial','blasted','accused']:
        if re.search(r'\b'+word+r'\b',head+' '+raw,re.I):cues.append(word)
    return {'id':entry['id'],'title':head,'source':entry.get('source'),
      'digest':digest,'digest_basis':'RSS / Atom summary supplied by publisher or aggregation feed' if raw else 'No summary supplied by feed; title alone is insufficient',
      'can_assess_full_article':False,
      'cues':cues[:5], 'cue_method':'Lexical screening only; cannot determine left/right ideology, factual reliability or motivation',
      'related':related_unique, 'checklist':['Read the original article for full context.','Check primary sources and quote attribution.','Compare independently reported details and missing perspectives.'],
      'limits':'This is a source-grounded excerpt, not independent fact-checking or a full-article political analysis.'}
