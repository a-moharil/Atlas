"""Conservative news-to-place attribution for India coverage, no geocoding network required.

This locates *coverage references*, not the true physical location or count of real-world incidents.
State heat represents unique retrieved story records. Weak source-scope assignments are reported separately.
"""
import datetime as dt
import json
import re
import urllib.parse
from collections import defaultdict
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parent

@lru_cache(maxsize=1)
def places():
    return json.loads((ROOT/'static/data/india_places.json').read_text(encoding='utf-8'))

def norm(s):
    return re.sub(r'[^a-z0-9]+',' ',str(s or '').casefold()).strip()

def canonical_url(url):
    try:
        u=urllib.parse.urlsplit(url or '')
        # Prefer the same source's canonical URL over tracking query variations.
        query=urllib.parse.parse_qsl(u.query, keep_blank_values=False)
        query=[(k,v) for k,v in query if k.lower() not in ('utm_source','utm_medium','utm_campaign','utm_term','utm_content','fbclid','gclid')]
        return (u.netloc.casefold().removeprefix('www.'),u.path.rstrip('/'),tuple(sorted(query)))
    except Exception:
        return ('',str(url or ''),())

def article_key(row):
    title=norm(row.get('title'))
    # Two copies of a syndicated identical headline are one coverage event for this map.
    if len(title)>24:
        return ('headline',title,str(row.get('published') or row.get('retrieved') or '')[:10])
    return ('url',canonical_url(row.get('url')))

@lru_cache(maxsize=1)
def _patterns():
    terms=[]
    data=places()
    for st in data['states']:
        for name in [st['name'],*st.get('aliases',[])]:
            if len(name)>=3:terms.append((re.compile(r'(?<!\w)'+re.escape(name.casefold())+r'(?!\w)',re.I),st['name'],None))
    for city in data['cities']:
        for name in [city['name'],*city.get('aliases',[])]:
            if len(name)>=3:terms.append((re.compile(r'(?<!\w)'+re.escape(name.casefold())+r'(?!\w)',re.I),city['state'],city['name']))
    return terms

def geographic_matches(row,registry=None):
    """Returns state confidence plus city, preferring explicit headline references.
       Does not assume that an India publisher reports on the state of its HQ.
    """
    title=str(row.get('title') or '')
    summary=str(row.get('summary') or '')
    for text,confidence in ((title,'headline'),(summary,'excerpt')):
        found={}; cities={}
        for pattern,state,city in _patterns():
            if pattern.search(text):
                found[state]=confidence
                if city:cities.setdefault(state,set()).add(city)
        if found:
            if len(found)>4:return [],'ambiguous',{}
            return sorted(found),'headline' if confidence=='headline' else 'excerpt', {s:sorted(v) for s,v in cities.items()}
    source=(registry or {}).get(row.get('source_id')) or {}
    if source.get('local_state'):
        return [source['local_state']],'source_scope',{source['local_state']:[source.get('local_city')] if source.get('local_city') else []}
    return [],'unlocated',{}

TOPICS={
 'politics':r'\b(election|politic|minister|parliament|assembly|cabinet|party|governor|government)\b',
 'economy':r'\b(economy|economic|market|stocks?|banks?|trade|inflation|rbi|finance|investment|business|rupee)\b',
 'weather':r'\b(weather|rain|flood|cyclone|drought|temperature|storm|monsoon|wildfire|heatwave)\b',
 'infrastructure':r'\b(road|rail|metro|airport|port|bridge|highway|infrastructure|development|transport)\b',
 'technology':r'\b(technology|ai|artificial intelligence|semiconductor|it sector|cyber|startup|digital|software)\b',
 'security':r'\b(security|border|army|military|police|protest|conflict|terror|violence|attack)\b'
}
def topic_match(row,topic):
    return topic=='all' or bool(re.search(TOPICS.get(topic,r'(?!)'),(row.get('title') or '')+' '+(row.get('summary') or ''),re.I))

def india_coverage(records, configs, days=7,topic='all',scope='all',now=None):
    days=max(1,min(365,int(days)))
    now=now or dt.datetime.now(dt.timezone.utc)
    limit=now-dt.timedelta(days=days)
    registry={x['id']:x for x in configs}
    states=defaultdict(lambda:{'count':0,'headline':0,'excerpt':0,'source_scope':0,'cities':defaultdict(int),'records':[]})
    seen=set();total=0;unlocated=0;ambiguous=0;duplicates=0;skipped_time=0
    for row in records:
        if row.get('medium')!='article' or not topic_match(row,topic):continue
        date=row.get('published') or row.get('retrieved')
        try:
            stamp=dt.datetime.fromisoformat(date.replace('Z','+00:00'))
            if stamp < limit:
                skipped_time+=1;continue
        except (AttributeError,ValueError,TypeError):
            skipped_time+=1;continue
        key=article_key(row)
        if key in seen:
            duplicates+=1;continue
        seen.add(key)
        locs,basis,cities=geographic_matches(row,registry)
        if basis=='ambiguous':ambiguous+=1;continue
        if not locs:unlocated+=1;continue
        if scope=='explicit' and basis=='source_scope':continue
        total+=1
        for state in locs:
            slot=states[state];slot['count']+=1;slot[basis]+=1
            for city in cities.get(state,[]):
                if city:slot['cities'][city]+=1
            if len(slot['records'])<30:
                slot['records'].append({'id':row.get('id'),'source':row.get('source'),'title':row.get('title'),'summary':row.get('summary'),
                                        'published':row.get('published'),'url':row.get('url'),'basis':basis,'state':state})
    result=[]
    for st in places()['states']:
        slot=states[st['name']]
        result.append({'name':st['name'],'lat':st['lat'],'lon':st['lon'],'count':slot['count'],
                       'headline':slot['headline'],'excerpt':slot['excerpt'],'source_scope':slot['source_scope'],
                       'cities':sorted(({'name':n,'count':v} for n,v in slot['cities'].items()),key=lambda a:-a['count']),
                       'records':slot['records']})
    return {'days':days,'topic':topic,'scope':scope,'generated':now.isoformat(),'states':result,
            'counts':{'located_distinct_articles':total,'state_assignments':sum(s['count'] for s in result),
                      'unlocated':unlocated,'ambiguous':ambiguous,'duplicate_stories':duplicates,'time_excluded':skipped_time},
            'method':'One unique retrieved headline per story; headline or excerpt geographical mentions; source-scoped local feeds flagged as weaker evidence. Multiple states in one item create multiple state assignments. This is coverage intensity, not an event-incidence or risk map.'}
