"""Transparent emergency news triage and panel-scoped source governance."""
import datetime as dt,re,hashlib
from collections import Counter,defaultdict
from urllib.parse import urlparse
FAMILIES={'wires':'Wire services','broadcast':'Broadcasters','publications':'News publications','government':'Government & institutions','analysis':'Analysis & research','local':'Local / regional discovery','other':'Other / custom sources'}
WIRES={'reuters.com','apnews.com','ptinews.com','aninews.in','afp.com'}
BROADCAST={'bbc.com','bbc.co.uk','dw.com','france24.com','cnn.com','news18.com','ndtv.com','wionews.com','aljazeera.com','euronews.com','news.sky.com','channelnewsasia.com','cnbc.com','abc.net.au','nhk.or.jp','foxnews.com'}
ALIASES={'bbc.co.uk':'bbc.com','feeds.bbci.co.uk':'bbc.com','edition.cnn.com':'cnn.com','economictimes.indiatimes.com':'economictimes.indiatimes.com'}
CATEGORIES={
 'Conflict & security':r'\b(?:military|missiles?|airstrikes?|air strikes?|ceasefire|invasion|nuclear|troops?|war|border clashes|terror(?:ist|ism)|bombing|hostages?)\b',
 'Government & elections':r'\b(?:election|parliament|president|prime minister|government|cabinet|coup|constitutional|impeach|resign|martial law)\w*\b',
 'Diplomacy & sanctions':r'\b(?:sanctions?|summit|treaty|diploma\w*|foreign minister|peace talks|un security council|tariffs?)\b',
 'Infrastructure & disruption':r'\b(?:cyberattack|cyber attack|power grid|blackout|shipping|strait|pipeline|airspace|internet shutdown|state of emergency)\b',
}
HIGH=r'\b(?:coup|invasion|nuclear emergency|martial law|state of emergency|assassinat\w*|ceasefire collapse\w*|missile attacks?|airstrikes?|air strikes?|terror(?:ist)? attacks?|government collaps\w*|prime minister resign\w*|president resign\w*)\b'
MAJOR=r'\b(?:election results?|wins? election|sanctions?|ceasefire|peace talks|military|missiles?|emergency|resign\w*|parliament dissol\w*|border clashes|hostages?|airspace clos\w*|cyberattack|tariffs?|treaty|summit)\b'
NOISE=r'\b(?:horoscope|cricket|football|box office|movie review|film review|fantasy team|celebrity|recipe|video game|war games? review)\b'
STOP=set('the and for that with from this after says said amid over into will have been their they about news live latest update updates breaking world india government president minister russian ukrainian report reports today'.split())
def source_info(feed):
 host=(urlparse(feed.get('site') or feed.get('url','')).hostname or '').lower().removeprefix('www.')
 host=ALIASES.get(host,host)
 if host in ('news.google.com','google.com') or not host:host='feed:'+feed['id']
 family='local' if feed.get('local_city') or feed.get('local_state') else 'government' if feed.get('tier')=='primary' or (feed.get('mygov') and feed['id']!='mygov_evaluation') else 'analysis' if feed.get('tier') in ('analysis','research') or feed.get('isw') or feed['id']=='mygov_evaluation' else 'wires' if host in WIRES else 'broadcast' if host in BROADCAST else 'other' if feed.get('mode')=='Custom HTTPS RSS' else 'publications'
 publisher=family+':'+host
 return dict(id=feed['id'],name=feed['name'],family=family,publisher=publisher,publisher_name=host if not host.startswith('feed:') else feed['name'],region=feed.get('region','Unknown'),mode=feed.get('mode','RSS'),site=feed.get('site',''),desk=feed.get('desk','Custom'))
def init(con):
 con.executescript('''CREATE TABLE IF NOT EXISTS emergency_source_rules(scope TEXT NOT NULL, key TEXT NOT NULL, excluded INTEGER NOT NULL, PRIMARY KEY(scope,key));
 CREATE TABLE IF NOT EXISTS emergency_settings(id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL);
 INSERT OR IGNORE INTO emergency_settings VALUES(1,0);''');con.commit()
def rules(con):return {(r['scope'],r['key']):bool(r['excluded']) for r in con.execute('SELECT * FROM emergency_source_rules')}
def blocked(info,r):
 for scope,key in [('feed',info['id']),('publisher',info['publisher']),('family',info['family'])]:
  if (scope,key) in r:return r[(scope,key)]
 return False

def update(con,feeds,scope,key,excluded,expected_version):
 infos=[source_info(f) for f in feeds]
 if scope not in ('all','family','publisher','feed') or type(excluded) is not bool:raise ValueError('Invalid source preference')
 if scope=='all' and key!='all':raise ValueError('Invalid all-sources key')
 targets=infos if scope=='all' else [x for x in infos if x['id' if scope=='feed' else scope]==key]
 if not targets:raise ValueError('Unknown source group')
 if type(expected_version) is not int:raise ValueError('Source preference version required')
 con.execute('BEGIN IMMEDIATE')
 try:
  current=con.execute('SELECT version FROM emergency_settings WHERE id=1').fetchone()[0]
  if current!=expected_version:raise ValueError('Source preferences changed. Reload before applying this choice.')
  if scope=='all':
   con.execute('DELETE FROM emergency_source_rules')
   for family in FAMILIES:con.execute('INSERT INTO emergency_source_rules VALUES(?,?,?)',('family',family,int(excluded)))
  else:
   # Parent changes deliberately clear narrower overrides in that subtree.
   if scope in ('family','publisher'):
    for x in targets:
     con.execute('DELETE FROM emergency_source_rules WHERE scope=? AND key=?',('feed',x['id']))
     if scope=='family':con.execute('DELETE FROM emergency_source_rules WHERE scope=? AND key=?',('publisher',x['publisher']))
   con.execute('INSERT INTO emergency_source_rules VALUES(?,?,?) ON CONFLICT(scope,key) DO UPDATE SET excluded=excluded.excluded',(scope,key,int(excluded)))
  con.execute('UPDATE emergency_settings SET version=version+1 WHERE id=1');con.commit()
 except Exception:con.rollback();raise

def source_tree(feeds,r,status):
 families={};infos=[]
 for f in feeds:
  x=source_info(f);x['excluded']=blocked(x,r);s=status.get(x['id'],{});x.update(state=s.get('state','never'),attempted=s.get('attempted'),error=s.get('error',''));infos.append(x)
  fam=families.setdefault(x['family'],{'id':x['family'],'name':FAMILIES[x['family']],'publishers':{}})
  pub=fam['publishers'].setdefault(x['publisher'],{'id':x['publisher'],'name':x['publisher_name'],'feeds':[]});pub['feeds'].append(x)
 out=[]
 for fam in families.values():
  fam['publishers']=sorted(fam['publishers'].values(),key=lambda p:p['name'])
  for pub in fam['publishers']:pub['total']=len(pub['feeds']);pub['enabled']=sum(not f['excluded'] for f in pub['feeds'])
  fam['total']=sum(p['total'] for p in fam['publishers']);fam['enabled']=sum(p['enabled'] for p in fam['publishers']);out.append(fam)
 return sorted(out,key=lambda f:f['name']),infos

def triage(entry,info,now,hours):
 if entry.get('medium')!='article':return None,'not article'
 try:
  t=dt.datetime.fromisoformat(entry['published'].replace('Z','+00:00'))
  if t.tzinfo is None:t=t.replace(tzinfo=dt.timezone.utc)
 except (ValueError,AttributeError,TypeError,KeyError):return None,'undated'
 age=(now-t).total_seconds()/3600
 if age<-.25 or age>hours:return None,'outside window'
 title=entry.get('title','');body=title+' '+entry.get('summary','')[:400]
 if re.search(NOISE,title,re.I):return None,'non-political noise'
 topics=[k for k,p in CATEGORIES.items() if re.search(p,body,re.I)]
 if not topics:return None,'not political'
 high=bool(re.search(HIGH,title,re.I));major=bool(re.search(MAJOR,title,re.I));breaking=bool(re.search(r'\b(?:breaking|urgent|just in)\b',title,re.I))
 if not (high or major or breaking):return None,'below threshold'
 reasons=[];score=0
 if high:score+=55;reasons.append('High-impact term in headline')
 elif major:score+=38;reasons.append('Major political / security development term')
 if breaking:score+=8;reasons.append('Publisher uses breaking/urgent wording; unverified')
 freshness=max(0,24-int(max(age,0)*2));score+=freshness;reasons.append(f'Published {max(age,0):.1f} hours ago')
 if info['family'] in ('wires','government'):score+=4;reasons.append('Wire or institutional source; not a reliability guarantee')
 priority='Priority 1' if high and age<=6 else 'Priority 2'
 return {**entry,'publisher':info['publisher'],'publisher_name':info['publisher_name'],'family':info['family'],'region':info['region'],'topics':topics,'score':score,'priority':priority,'age_hours':round(max(age,0),2),'reasons':reasons,'publisher_breaking':breaking,'tokens':set(re.findall(r'[a-z]{4,}',title.lower()))-STOP},None

def payload(entries,feeds,status,r,version,hours=24,now=None,matcher=None):
 if hours not in (6,12,24,48):raise ValueError('Invalid emergency window')
 now=now or dt.datetime.now(dt.timezone.utc);tree,infos=source_tree(feeds,r,status);lookup={f['id']:f for f in infos};eligible=[];rejected=Counter()
 for e in entries:
  info=lookup.get(e['source_id'])
  if not info:continue
  if info['excluded']:rejected['excluded source']+=1;continue
  row,reason=triage(e,info,now,hours)
  if row:eligible.append(row)
  else:rejected[reason]+=1
 eligible.sort(key=lambda e:(e['score'],e['published']),reverse=True)
 groups=[]
 for row in eligible[:700]:
  best=None;by_meaning=False
  if matcher is not None:best,by_meaning=matcher.assign(row,groups)
  if not by_meaning:
   for g in groups:
    common=row['tokens']&g['_tokens'];union=row['tokens']|g['_tokens']
    if len(common)>=3 and len(common)/max(1,len(union))>=.42:best=g;break
  if best is None:
   best={'id':hashlib.sha256(row['title'].encode()).hexdigest()[:16],'lead':row,'records':[],'_tokens':row['tokens'],'_meaning':0,'_keywords':0};groups.append(best)
  best['_meaning' if by_meaning else '_keywords']=best.get('_meaning' if by_meaning else '_keywords',0)+1
  if matcher is not None:matcher.add(row,best)
  key=(row['publisher'],re.sub(r'\W+',' ',row['title'].lower()))
  if key not in best.get('_seen',set()):best['records'].append(row);best.setdefault('_seen',set()).add(key)
 groups.sort(key=lambda g:g['lead']['score'],reverse=True)
 for g in groups:
  g['publisher_count']=len({r['publisher'] for r in g['records']});g['record_count']=len(g['records']);g['latest']=max(r['published'] for r in g['records'])
  g['regions']=sorted({r['region'] for r in g['records']});g['topics']=sorted({t for r in g['records'] for t in r['topics']});g.pop('_tokens');g.pop('_seen')
  m,k=g.pop('_meaning',0),g.pop('_keywords',0);g['grouping']='meaning' if m and not k else 'mixed' if m and k else 'keywords'
  for row in g['records']:row.pop('tokens',None)
 timeline=Counter(e['published'][:13]+':00Z' for e in eligible)
 return dict(groups=groups[:80],total_groups=len(groups),candidate_count=len(eligible),truncated=len(eligible)>700 or len(groups)>80,hours=hours,checked=now.isoformat(),families=tree,source_version=version,
  health={'configured':len(infos),'enabled':sum(not x['excluded'] for x in infos),'excluded':sum(x['excluded'] for x in infos),'successful':sum(x['state']=='ok' and not x['excluded'] for x in infos)},
  rejections=dict(rejected),timeline=[{'time':t,'count':n} for t,n in sorted(timeline.items())],
  method='Rule-based prioritisation of timestamped publisher headlines. Priority is a reading-order recommendation, not verified severity. Similar-headline groups may be wrong; publisher counts do not establish independent corroboration. No complete global coverage is claimed. Source exclusions affect this newsroom only; genre cleanup remains global.')
