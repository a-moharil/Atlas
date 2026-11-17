"""India government research workspace. Directory entries are not live applications.
Keyword-based associations are inspectable leads, never inferred policy intentions.
"""
import json,re,datetime as dt
from collections import Counter,defaultdict
from pathlib import Path
from urllib.parse import urlparse
CATALOGUE=json.loads((Path(__file__).parent/'mygov_catalogue.json').read_text())
TOPICS={
 'Digital':r'\b(?:upi|digital|aadhaar|digilocker|indiaai|semiconductor|artificial intelligence|broadband|ondc)\b',
 'Research':r'\b(?:research|doctoral|ph\.?d|jrf|anrf|innovation|fellowship|quantum)\b',
 'Energy':r'\b(?:energy|solar|hydrogen|electricity|renewable|coal|petroleum)\b',
 'Infrastructure':r'\b(?:infrastructure|railway|railways|roads?|ports?|logistics|gati\s*shakti)\b',
 'Agriculture':r'\b(?:agriculture|farmer|farmers|kisan|fisheries|irrigation)\b',
 'Welfare':r'\b(?:welfare|housing|nutrition|beneficiar|pension|health|ayushman|scholarship)\w*\b',
 'Finance':r'\b(?:budget|expenditure|allocation|investment|finance|credit|crore|lakh)\b',
 'Employment':r'\b(?:employment|apprentice|skills?|livelihood|entrepreneur|msme)\w*\b',
 'Climate':r'\b(?:climate|environment|emission|carbon|water|forest)\w*\b',
}
STAGES=[('Audit / evaluation',r'\b(?:audit|evaluation|evaluated|cag|committee report)\b'),('Reported expenditure',r'\b(?:spent|disbursed|expenditure incurred|released funds)\b'),('Budget / allocation',r'\b(?:budget|allocated|allocation|outlay|corpus)\b'),('Application / call lead',r'\b(?:applications?|apply|deadline|call for proposals|admissions?)\b'),('Approval / launch',r'\b(?:approved|approval|launched|launch|cabinet)\b')]
POSTDOC=re.compile(r'\bpost[\s-]?(?:doc(?:toral)?|doctorate)\b',re.I)
def classify(entry,configs):
 f=configs.get(entry.get('source_id'),{});text=(entry.get('title','')+' '+entry.get('summary',''))
 if entry.get('medium')=='paper' and not re.search(r'\b(?:india|indian|bharat|upi|aadhaar|pradhan mantri)\b',entry.get('title',''),re.I):return None
 direct=f.get('mygov') or entry.get('source_id','').startswith(('mygov_','openalex_mygov_'))
 if not direct and not re.search(r'\b(?:india|indian|bharat|pradhan mantri|modi|mygov|anrf|upi)\b',text,re.I):return None
 if not direct and not re.search(r'\b(?:scheme|mission|policy|budget|research|fellowship|government|upi|investment|ministry|minister)\b',text,re.I):return None
 mid=f.get('ministry');mids=[mid] if mid else []
 for m in CATALOGUE['ministries']:
  if m['id'] not in mids and re.search(re.escape(m['name']),text,re.I):mids.append(m['id'])
 topics=[k for k,p in TOPICS.items() if re.search(p,text,re.I)]
 kind='Scholarly metadata' if entry.get('medium')=='paper' else 'Independent analysis' if entry.get('source_id')=='mygov_evaluation' else 'Official release' if f.get('tier')=='primary' and f.get('mygov') else 'Discovery lead'
 stage=next((n for n,p in STAGES if re.search(p,text,re.I)),'Statement / update')
 return {**entry,'ministries':mids,'topics':topics,'evidence_type':kind,'stage_hint':stage,'stage_verified':False,'pm_related':entry.get('source_id')=='mygov_pmo' or bool(re.search(r'\b(?:prime minister|pradhan mantri|PMO|Narendra Modi)\b',text,re.I)),'postdoc':bool(POSTDOC.search(text))}

def payload(entries,feeds,status,days=30,now=None):
 if not isinstance(days,int) or days not in (7,30,90,365):raise ValueError('Choose 7, 30, 90 or 365 days')
 now=now or dt.datetime.now(dt.timezone.utc);config={f['id']:f for f in feeds};records=[];seen=set();undated=0
 for entry in entries:
  row=classify(entry,config)
  if row is None:continue
  # Papers are metadata; date is from provider. Undated records are separately counted.
  stamp=row.get('published') or row.get('retrieved')
  try:
   when=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
   if when.tzinfo is None:when=when.replace(tzinfo=dt.timezone.utc)
   if when>now+dt.timedelta(days=1) or (now-when).days>days:continue
  except (ValueError,TypeError,AttributeError):undated+=1;continue
  key=re.sub(r'\W+',' ',row.get('title','').lower()).strip()
  if not key or key in seen:continue
  seen.add(key);records.append(row)
 records.sort(key=lambda e:e.get('published') or e.get('retrieved') or '',reverse=True)
 sources=[]
 for f in feeds:
  if not f.get('mygov'):continue
  s=status.get(f['id'],{})
  sources.append({k:f.get(k) for k in ('id','name','ministry','sector','mode','url','site','tier')}|{'state':s.get('state','never'),'attempted':s.get('attempted'),'last_success':s.get('success'),'returned':s.get('count',0),'error':s.get('error','')})
 counts=Counter(mid for r in records for mid in r['ministries']);topics=Counter(t for r in records for t in r['topics']);stages=Counter(r['stage_hint'] for r in records)
 weekly=defaultdict(Counter)
 for r in records:
  day=(r.get('published') or r.get('retrieved') or '')[:10]
  for t in r['topics']:weekly[day][t]+=1
 return {**CATALOGUE,'records':records[:1500],'matching_records':len(records),'truncated':len(records)>1500,'sources':sources,'ministry_counts':dict(counts),'topics':dict(topics),'stages':dict(stages),'timeline':[{'date':d,'counts':dict(c)} for d,c in sorted(weekly.items())],'days':days,'refreshed':now.isoformat(),'undated_omitted':undated,'source_health':dict(configured=len(sources),successful=sum(s['state']=='ok' for s in sources),failed=sum(s['state']=='error' for s in sources),never=sum(s['state']=='never' for s in sources)),
 'method':'Counts measure distinct retrieved headlines, not policy effort, expenditure or real-world outcomes. Site-filtered search feeds are discovery routes, not direct ministry APIs. Ministry and stage associations are lexical and require checking the original. Programme cards are a dated directory; unknown application status remains unknown.'}
