"""Published ISW/CTP viewer directory and metadata, without copying map layers."""
import json,re,datetime as dt
from collections import Counter
MAPS=[
 dict(id='ukraine',title="Russia's invasion of Ukraine",item='36a7f6a6f5a9448496de641cf64bd375',theatre='ukraine',owner='gbarros_understandingwar',credit='Source: Institute for the Study of War',note='Read the assessment timestamp and legend inside the published map. ArcGIS item modification is not the frontline observation time.'),
 dict(id='iran',title='U.S. and Israeli strikes in Iran (2026)',item='089bc1a2fe684405a67d67f13bd31324',theatre='iran',owner='cweinstein_understandingwar',credit='Source: Institute for the Study of War and AEI’s Critical Threats Project',note='Published conflict map, not a live sensor feed. Its assessed events and coverage depend on the publisher.'),
 dict(id='syria',title='Assessed control of terrain in Syria',item='1933cb1d315f4db3a4f4dcc5ef40753a',theatre='syria',owner='thestudyofwar',credit='Source: Institute for the Study of War and AEI’s Critical Threats Project',note='Check the map’s own assessment date. A reachable map may still be historical.'),
 dict(id='gaza',title="Israel's operation in Gaza",item='2e746151991643e39e64780f0674f7dd',theatre='gaza',owner='gbarros_understandingwar',credit='Source: Institute for the Study of War and AEI’s Critical Threats Project',note='Historical/cadence caution: CTP’s January 25, 2026 report states daily Gaza mapping ended in February 2025. Do not assume current frontlines.')]
for m in MAPS:m['url']='https://storymaps.arcgis.com/stories/'+m['item'];m['metadata_url']='https://www.arcgis.com/home/item.html?id='+m['item']
THEATRES=[
 dict(id='ukraine',name='Ukraine / Russia',lat=49,lon=33,pattern=r'\b(?:ukrain\w*|russia\w*|donetsk|kursk|kharkiv|zaporizh\w*)\b',source='https://understandingwar.org/analysis/russia-ukraine/'),
 dict(id='iran',name='Iran / regional conflict',lat=32,lon=54,pattern=r'\b(?:iran\w*|tehran|hormuz)\b',source='https://understandingwar.org/analysis/middle-east/iran-update/'),
 dict(id='syria',name='Syria',lat=35,lon=38,pattern=r'\b(?:syria\w*|damascus|aleppo|hasakah)\b',source='https://understandingwar.org/analysis/middle-east/'),
 dict(id='gaza',name='Gaza / Israel / Lebanon',lat=32,lon=35,pattern=r'\b(?:gaza|israel\w*|leban\w*|hezbollah|hamas)\b',source='https://understandingwar.org/analysis/middle-east/'),
 dict(id='redsea',name='Yemen / Red Sea',lat=16,lon=45,pattern=r'\b(?:yemen\w*|houthi\w*|red sea)\b',source='https://understandingwar.org/analysis/middle-east/')]

def check_maps(fetch):
 results=[]
 for m in MAPS:
  try:
   d=json.loads(fetch('https://www.arcgis.com/sharing/rest/content/items/'+m['item']+'?f=json',400000).decode())
   if d.get('error'):raise ValueError(str(d['error'].get('message','ArcGIS error')))
   if d.get('id')!=m['item'] or d.get('owner')!=m['owner'] or d.get('access')!='public' or d.get('type')!='StoryMap':raise ValueError('Published item identity, owner, type or access changed')
   stamp=dt.datetime.fromtimestamp(d['modified']/1000,dt.timezone.utc).isoformat() if d.get('modified') else None
   results.append(dict(id=m['id'],state='public item verified',title=d.get('title'),owner=d['owner'],modified=stamp,viewer_verified=False))
  except Exception as exc:results.append(dict(id=m['id'],state='unavailable',error=str(exc)[:180],viewer_verified=False))
 return {'maps':results,'checked':dt.datetime.now(dt.timezone.utc).isoformat()}

def payload(entries,feeds,status,days=30,now=None):
 if days not in (7,30,90):raise ValueError('Choose 7, 30 or 90 days')
 now=now or dt.datetime.now(dt.timezone.utc);source_ids={f['id'] for f in feeds if f.get('isw')};reports=[];seen=set();context=[]
 for e in entries:
  if e.get('medium')!='article':continue
  try:
   when=dt.datetime.fromisoformat(e['published'].replace('Z','+00:00'))
   if when.tzinfo is None:when=when.replace(tzinfo=dt.timezone.utc)
   if (now-when).total_seconds()< -900 or (now-when).total_seconds()>days*86400:continue
  except (ValueError,AttributeError,KeyError,TypeError):continue
  title=e.get('title','');theatres=[t['id'] for t in THEATRES if re.search(t['pattern'],title,re.I)]
  if not theatres:continue
  item={k:e.get(k) for k in ('id','title','url','published','source','source_id')};item['theatres']=theatres
  if e['source_id'] in source_ids:
   key=re.sub(r'\W+',' ',title.lower()).strip()
   if key in seen:continue
   seen.add(key);reports.append(item)
  elif re.search(r'\b(?:war|military|ceasefire|frontline|strikes?|troops?|advanc\w*)\b',title,re.I):context.append(item)
 reports.sort(key=lambda r:r['published'],reverse=True);context.sort(key=lambda r:r['published'],reverse=True)
 return dict(maps=MAPS,theatres=[{k:v for k,v in t.items() if k!='pattern'} for t in THEATRES],reports=reports[:300],context=context[:100],days=days,checked=now.isoformat(),counts=dict(Counter(t for r in reports for t in r['theatres'])),timeline=[dict(day=d,count=n) for d,n in sorted(Counter(r['published'][:10] for r in reports).items())],
 sources=[dict(id=f['id'],name=f['name'],state=status.get(f['id'],{}).get('state','never'),error=status.get(f['id'],{}).get('error',''),attempted=status.get(f['id'],{}).get('attempted')) for f in feeds if f.get('isw')],
 method='Statistics count discovered report headlines by publication date and keyword theatre. They do not measure battles, casualties, frontline displacement or territory. Theatre markers are approximate navigation anchors, not combat locations or assessments of current activity. ISW/CTP materials remain in the publisher’s unmodified viewer; no map layers or shapefiles are copied.',policy='https://understandingwar.org/fair-use-and-attribution-policy/',map_room='https://understandingwar.org/analysis/map-room/')
