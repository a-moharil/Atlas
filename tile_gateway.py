"""Fixed-provider map tile gateway, avoiding browser CORS and remote JS dependencies.
No arbitrary URL forwarding, no prefetching or mass-tile storage. Provider attribution
is required in the frontend. Satellite tiles are never fabricated on failure.
"""
from __future__ import annotations
from collections import defaultdict, deque, OrderedDict
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
import hashlib, io, math, re, threading, time

PROVIDERS={
 'esri':{'name':'Esri World Imagery','host':'server.arcgisonline.com','kind':'basemap','max_zoom':18,'credit':'Imagery © Esri, Maxar, Earthstar Geographics, and GIS User Community'},
 'osm':{'name':'OpenStreetMap','host':'tile.openstreetmap.org','kind':'basemap','max_zoom':18,'credit':'© OpenStreetMap contributors'},
 'nasa_base':{'name':'NASA GIBS Blue Marble composite','host':'gibs.earthdata.nasa.gov','kind':'satellite-composite','max_zoom':9,'credit':'NASA Earth Observatory / Blue Marble composite; not current live imagery'},
 'nasa_daily':{'name':'NASA VIIRS daily true-colour satellite','host':'gibs.earthdata.nasa.gov','kind':'daily-satellite','max_zoom':9,'credit':'NASA GIBS VIIRS/Suomi-NPP true-colour; date-dependent, not live continuous imagery'},
 'nasa':{'name':'NASA GIBS thermal anomalies','host':'gibs.earthdata.nasa.gov','kind':'satellite-raster','max_zoom':9,'credit':'NASA GIBS / VIIRS thermal-anomaly imagery'},
 'fwi':{'name':'Copernicus EFFIS fire-weather index','host':'maps.effis.emergency.copernicus.eu','kind':'fire-danger','max_zoom':10,'credit':'Copernicus EFFIS / ECMWF fire-weather index'},
 'burn':{'name':'Copernicus EFFIS burned-area map','host':'maps.effis.emergency.copernicus.eu','kind':'burned-area','max_zoom':10,'credit':'Copernicus EFFIS burned-area mapping'},
}
LAYER_NAMES={'nasa_daily':'VIIRS_SNPP_CorrectedReflectance_TrueColor','nasa_base':'BlueMarble_NextGeneration','nasa':'VIIRS_SNPP_Thermal_Anomalies_375m_All','fwi':'ecmwf007.fwi','burn':'modis.ba.poly.week'}
HEALTH=defaultdict(lambda:{'success':0,'failed':0,'cache_hits':0,'latest':None,'error':None,'last_latency_ms':None,'last_endpoint':None})
LOCK=threading.RLock()
MAX_BYTES=1_400_000
CACHE=OrderedDict()
CACHE_MAX=128
STRIPED_LOCKS=[threading.Lock() for _ in range(32)]
CACHE_TTL=600
FAILED={}
SLOTS=threading.BoundedSemaphore(6)


def _bbox(z,x,y):
    # Web Mercator coordinates, metres: appropriate for EPSG:3857 WMS 1.1.1.
    size=40075016.68557849/(2**z)
    x0=-20037508.342789244 + x*size
    y1= 20037508.342789244 - y*size
    return ','.join(f'{n:.5f}' for n in (x0,y1-size,x0+size,y1))

def provider_url(provider,z,x,y,day=None):
    if provider not in PROVIDERS:raise ValueError('Unknown provider')
    if not all(isinstance(v,int) for v in (z,x,y)) or z<0 or z>min(PROVIDERS[provider]['max_zoom'],18) or x<0 or y<0 or x>=2**z or y>=2**z:
        raise ValueError('Tile coordinate out of supported range')
    if provider=='esri':return f'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    if provider=='osm':return f'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
    if provider!='nasa_base':
        if not day or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise ValueError('A valid observation date is required')
        try:d=datetime.strptime(day,'%Y-%m-%d').date()
        except ValueError:raise ValueError('Invalid date')
        if d>datetime.now(timezone.utc).date()+timedelta(days=1) or d<datetime(2018,1,1).date():raise ValueError('Date out of range')
    host=PROVIDERS[provider]['host']
    base='/wms/epsg3857/best/wms.cgi' if provider in ('nasa','nasa_base','nasa_daily') else '/effis'
    params={'SERVICE':'WMS','VERSION':'1.1.1','REQUEST':'GetMap','LAYERS':LAYER_NAMES[provider],
       'STYLES':'','FORMAT':'image/png','TRANSPARENT':'TRUE','WIDTH':'256','HEIGHT':'256','SRS':'EPSG:3857',
       'BBOX':_bbox(z,x,y)}
    if provider!='nasa_base':params['TIME']=day
    return f'https://{host}{base}?{urlencode(params)}'

class NoRedirectOutside(HTTPRedirectHandler):
    def redirect_request(self, req,fp,code,msg,headers,newurl):
        # Fetches are preconstructed on fixed provider hosts. Prevent cross-host SSRF.
        from urllib.parse import urlparse
        if urlparse(newurl).scheme!='https' or urlparse(newurl).hostname not in ({p['host'] for p in PROVIDERS.values()} | {'gibs-a.earthdata.nasa.gov','gibs-b.earthdata.nasa.gov','gibs-c.earthdata.nasa.gov'}):
            raise ValueError('Provider attempted unexpected redirect')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def tile_candidates(provider,z,x,y,day):
    """NASA WMTS is primary for date-dependent visualizations, WMS a fallback.
    WMTS tiles are only requested within their provider-supported matrix.
    """
    fallback=provider_url(provider,z,x,y,day)
    if provider=='nasa_daily' and z<=9:
        ext='jpeg'
        layer=LAYER_NAMES[provider]
        wmts=(f'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/'
              f'{layer}/default/{day}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.{ext}')
        return [wmts,fallback]
    return [fallback]


def _fetch_image(target,timeout):
    opener=build_opener(NoRedirectOutside())
    req=Request(target,headers={'User-Agent':'ATLAS-SIGNAL/4.1 research GIS viewer (NASA GIBS and Esri)','Accept':'image/png,image/jpeg,image/*;q=0.8'})
    with opener.open(req,timeout=timeout) as res:
        raw=res.read(MAX_BYTES+1);ctype=res.headers.get('Content-Type','')
    if len(raw)>MAX_BYTES:raise ValueError('Tile exceeds provider size limit')
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):kind='image/png'
    elif raw.startswith(b'\xff\xd8\xff'):kind='image/jpeg'
    elif raw.startswith(b'RIFF') and raw[8:12]==b'WEBP':kind='image/webp'
    else:raise ValueError(f'Provider returned non-image response ({ctype}); possible WMS/WMTS exception')
    return raw,kind


def _get_tile(provider,z,x,y,day=None,timeout=10):
    candidates=tile_candidates(provider,z,x,y,day)
    key=(provider,z,x,y,day)
    now=time.monotonic()
    with LOCK:
        item=CACHE.get(key)
        if item and now-item[0]<CACHE_TTL:
            CACHE.move_to_end(key)
            HEALTH[provider]['cache_hits']+=1
            return item[1],item[2]
    # Only one upstream request for the same hash stripe at a time.
    stripe=STRIPED_LOCKS[hash(key)%len(STRIPED_LOCKS)]
    with stripe:
        with LOCK:
            item=CACHE.get(key)
            if item and time.monotonic()-item[0]<CACHE_TTL:
                CACHE.move_to_end(key)
                HEALTH[provider]['cache_hits']+=1
                return item[1],item[2]
        started=time.monotonic();errors=[]
        for target in candidates:
            try:
                raw,kind=_fetch_image(target,timeout)
                with LOCK:
                    CACHE[key]=(time.monotonic(),raw,kind)
                    CACHE.move_to_end(key)
                    while len(CACHE)>CACHE_MAX:CACHE.popitem(last=False)
                    h=HEALTH[provider];h['success']+=1;h['latest']=datetime.now(timezone.utc).isoformat()
                    h['error']=None;h['last_latency_ms']=round((time.monotonic()-started)*1000)
                    h['last_endpoint']='WMTS' if '/wmts/' in target else ('WMS' if '/wms/' in target or '/effis?' in target else 'XYZ')
                return raw,kind
            except Exception as exc:
                errors.append(f'{type(exc).__name__}: {str(exc)[:120]}')
        error='; '.join(errors)
        with LOCK:
            h=HEALTH[provider];h['failed']+=1;h['latest']=datetime.now(timezone.utc).isoformat()
            h['error']=error[:320];h['last_latency_ms']=round((time.monotonic()-started)*1000)
            h['last_endpoint']='WMTS → WMS' if len(candidates)>1 else 'Provider endpoint'
        if errors and all('non-image' in e for e in errors):
            raise ValueError(f'All provider responses were non-image: {error[:300]}')
        raise RuntimeError(f'All {len(candidates)} provider methods failed: {error[:300]}')

def stats():
    with LOCK:return [{'id':name,**meta,**dict(HEALTH[name])} for name,meta in PROVIDERS.items()]

def nasa_capabilities():
    """Read actual availability; do not assume yesterday exists in the archive."""
    import xml.etree.ElementTree as ET
    target='https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml'
    with build_opener(NoRedirectOutside()).open(target,timeout=20) as res:
        raw=res.read(12_000_001)
    if len(raw)>12_000_000:raise ValueError('Capabilities too large')
    ns={'w':'http://www.opengis.net/wmts/1.0','o':'http://www.opengis.net/ows/1.1'}
    root=ET.fromstring(raw);layers={}
    for layer in root.findall('.//w:Layer',ns):
        name=layer.findtext('o:Identifier',namespaces=ns)
        for key in ('nasa','nasa_daily'):
            if name==LAYER_NAMES[key]:
                layers[key]={'latest':layer.findtext('w:Dimension/w:Default',namespaces=ns),'format':layer.findtext('w:Format',namespaces=ns)}
    if len(layers)!=2:raise ValueError('Required NASA layers absent from service catalogue')
    return {'layers':layers,'source':target,'retrieved':datetime.now(timezone.utc).isoformat()}

def get_tile(provider,z,x,y,day=None,timeout=10):
    tile_candidates(provider,z,x,y,day)  # Validate before touching queues or cache.
    key=(provider,z,x,y,day)
    with LOCK:
        failure=FAILED.get(key)
        if failure and time.monotonic()-failure[0]<20:raise RuntimeError('Provider retry cooldown: '+failure[1])
    if not SLOTS.acquire(timeout=0.2):raise RuntimeError('Tile queue busy; retry shortly')
    try:
        return _get_tile(provider,z,x,y,day,timeout)
    except Exception as exc:
        with LOCK:
            FAILED[key]=(time.monotonic(),str(exc)[:200])
            if len(FAILED)>512:FAILED.pop(next(iter(FAILED)))
        raise
    finally:SLOTS.release()
