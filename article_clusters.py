"""Dependency-free, reproducible article clustering and three-axis semantic projection.

Text fields are feed headlines and source-provided excerpts, not full articles.
Spherical TF-IDF cosine k-means provides semantic clusters; PCA-like projections
are calculated by power iteration on the sparse document-term matrix.
Source grouping is categorical; combined views keep both groupings in metadata.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import math
import random
import re

STOP=set('the and are for with from into over amid says after before under about this that they their them there what when where which who how why has have had was were will would could should these those today latest live news update updates analysis report reports world india indian new first more some at on of to in as is an a by or us uk 2026 2025 2024 2023 2022 said says say than against through near between rising amid via after this'.split())
TOKEN=re.compile(r"[a-z][a-z0-9\-]{2,}")
DESKS={'all','India','World','Technology','Finance','Energy','Research','Policy','Climate','Geopolitics'}

def tokens(text):
    return [w for w in TOKEN.findall((text or '').lower()) if w not in STOP and not w.isdigit()][:210]

def norm(v):
    n=math.sqrt(sum(x*x for x in v.values())) or 1
    return {k:x/n for k,x in v.items()}

def dot(a,b):
    if len(a)>len(b):a,b=b,a
    return sum(v*b.get(k,0) for k,v in a.items())

def keyhash(x):
    return int(hashlib.sha256(str(x).encode()).hexdigest()[:15],16)

def select_records(rows,registry,focus='all',domain='all',sources='',days=30,limit=600,query=''):
    # Provide domain and focus independently: India news is not one single source/desk.
    source_desk={r['id']:r.get('desk','World') for r in registry}
    source_region={r['id']:r.get('region','World') for r in registry}
    source_ids={s.strip() for s in sources.split(',') if s.strip()}
    cutoff=datetime.now(timezone.utc)-timedelta(days=days)
    find=query.lower().strip()
    result=[]; seen=set()
    for r in rows:
        if r.get('medium') not in ('article','paper'):continue
        title=(r.get('title') or '').strip()
        if not title:continue
        sid=r.get('source_id','')
        text=title+' '+(r.get('summary') or '')
        desk=source_desk.get(sid,'Research' if r.get('medium')=='paper' else 'World')
        if domain!='all':
            if domain=='Research':
                if r.get('medium')!='paper' and r.get('tier') not in ('analysis','research','primary') and desk not in ('Research','Policy'):continue
            elif domain=='Geopolitics':
                if desk not in ('World','India','Policy','Research') and not re.search(r'\b(diplomac|summit|sanction|war|military|treaty|nato|united nations|geopolitic|security)\b',text,re.I):continue
            elif desk!=domain:continue
        is_india=(r.get('region')=='India' or source_region.get(sid)=='India' or bool(re.search(r'\b(india|indian|modi|bharat|new delhi|mumbai|kolkata|bengaluru|chennai|rbi|maharashtra|karnataka|hyderabad)\b',text,re.I)))
        if focus=='India' and not is_india:continue
        if focus=='World' and is_india:continue
        if source_ids and sid not in source_ids:continue
        if find and find not in text.lower() and find not in r.get('source','').lower():continue
        stamp=r.get('published') or r.get('retrieved') or ''
        if days<3650:
            try:
                t=datetime.fromisoformat(stamp.replace('Z','+00:00'))
                if t.tzinfo is None:t=t.replace(tzinfo=timezone.utc)
                if t<cutoff:continue
            except (ValueError,TypeError):continue
        dedup=re.sub(r'[^a-z0-9]','',title.lower())[:140]
        if dedup in seen:continue
        seen.add(dedup)
        result.append({**r,'desk':desk,'is_india':is_india})
        if len(result)>=limit:break
    return result

def tfidf_vectors(records):
    wordlists=[]; df=Counter()
    for r in records:
        # Headlines signal high salience; excerpts are noisy and often incomplete.
        t=tokens((r.get('title','')+' ')*2+(r.get('summary','') or '')[:950]);wordlists.append(t);df.update(set(t))
    n=len(records);vects=[]
    for words in wordlists:
        counts=Counter(words)
        weights={w:(1+math.log(c))*math.log(1+(n+1)/(df[w]+.5)) for w,c in counts.items() if df[w]<n*.9}
        vects.append(norm(weights))
    return vects

def kmeans(vectors,k,seed=42,passes=16):
    n=len(vectors)
    if n==0:return [],[]
    k=max(1,min(k,n))
    rng=random.Random(seed)
    first=rng.randrange(n)
    centers=[vectors[first]]
    chosen={first}
    for _ in range(1,k):
        # Farthest-point seeding is deterministic and yields diverse prototypes.
        candidate=max((i for i in range(n) if i not in chosen),key=lambda i: min(1-dot(vectors[i],c) for c in centers))
        chosen.add(candidate);centers.append(vectors[candidate])
    assignments=[0]*n
    for iteration in range(passes):
        nxt=[max(range(k),key=lambda j:dot(v,centers[j])) for v in vectors]
        if iteration>0 and nxt==assignments:break
        assignments=nxt;groups=[defaultdict(float) for _ in range(k)]
        for i,g in enumerate(assignments):
            for key,val in vectors[i].items():groups[g][key]+=val
        centers=[norm(dict(g)) if g else centers[j] for j,g in enumerate(groups)]
    return assignments,centers

def three_axes(vectors):
    """Sparse truncated principal directions, without numpy dependency.
    Power iteration on X Xᵀ (document Gram operator), orthogonalizing earlier axes.
    """
    n=len(vectors)
    if n==0:return []
    axes=[]
    for axis in range(3):
        rr=random.Random(817+axis*47)
        x=[rr.uniform(-1,1) for _ in range(n)]
        for _ in range(25):
            word=defaultdict(float)
            for v,weight in zip(vectors,x):
                if weight:
                    for key,val in v.items():word[key]+=val*weight
            y=[sum(weight*word.get(key,0) for key,weight in v.items()) for v in vectors]
            avg=sum(y)/n;y=[t-avg for t in y]
            for prev in axes:
                factor=sum(a*b for a,b in zip(y,prev));y=[a-factor*b for a,b in zip(y,prev)]
            mag=math.sqrt(sum(t*t for t in y))
            if mag<1e-9:break
            x=[t/mag for t in y]
        axes.append(x)
    pts=[[axes[j][i] for j in range(3)] for i in range(n)]
    for j in range(3):
        arr=sorted(abs(pt[j]) for pt in pts)
        scale=arr[min(len(arr)-1,int(len(arr)*.94))] or .1
        for pt in pts:pt[j]=max(-2,min(2,pt[j]/scale))
    return pts

def label_group(group,records,vecs):
    indices=list(group)
    counts=Counter()
    for i in indices:
        words=set(tokens(records[i].get('title','')))
        for w in words:
            if len(w)>=4:counts[w]+=1
    words=[w for w,_ in counts.most_common(9) if counts[w]>=max(1,len(indices)*.15)]
    return ' · '.join(words[:3]) if words else 'Mixed coverage'

def make_clusters(records,mode='semantic'):
    n=len(records)
    if not n:return {'nodes':[],'groups':[],'links':[],'method':{'algorithm':'TF-IDF + spherical cosine k-means + sparse power-iteration 3D projection','count':0}}
    vectors=tfidf_vectors(records)
    k=max(2,min(10,int(math.sqrt(n/2)))) if n>=4 else n
    sem,centers=kmeans(vectors,k)
    coords=three_axes(vectors)
    sources=[r.get('source') or r.get('source_id') or 'Unknown source' for r in records]
    distinct=Counter(sources)
    top_sources={s for s,_ in distinct.most_common(18)}
    src_labels=[s if s in top_sources else 'Other publishers' for s in sources]
    if mode=='source':labels=src_labels
    elif mode=='combined':labels=[f'Topic {sem[i]+1}' for i in range(n)]
    else:labels=[f'Topic {sem[i]+1}' for i in range(n)]
    buckets=defaultdict(list)
    for i,label in enumerate(labels):buckets[label].append(i)
    groups=[];group_index={}
    for g,(label,ids) in enumerate(sorted(buckets.items(),key=lambda t:-len(t[1]))):
        group_index[label]=g
        summary=label_group(ids,records,vectors) if mode!='source' else label
        top=Counter(sources[i] for i in ids).most_common(3)
        groups.append({'id':g,'name':label,'topic':summary,'count':len(ids),'sources':[{'name':s,'count':c} for s,c in top], 'type':'source' if mode=='source' else 'semantic'})
    # Use genuine semantic axes as the principal geometry. Mild group separation
    # makes source mode readable without claiming metric-correct source distances.
    centroid=[]
    for g in groups:
        ids=buckets[g['name']]
        centroid.append([sum(coords[i][d] for i in ids)/len(ids) for d in range(3)])
    nodes=[]
    for i,r in enumerate(records):
        gid=group_index[labels[i]]
        p=coords[i][:]
        if mode=='source':
            angle=2*math.pi*gid/max(1,len(groups)); ring=1.5+0.35*(gid//8)
            target=[math.cos(angle)*ring,math.sin(angle)*ring, ((gid%5)-2)*.42]
            p=[.25*(p[d]-centroid[gid][d])+.75*target[d] for d in range(3)]
        elif mode=='combined':
            hh=keyhash(src_labels[i]); angle=(hh%360)/180*math.pi
            p=[p[0]+.14*math.cos(angle),p[1]+.14*math.sin(angle),p[2]+.14*((hh%7)-3)]
        nodes.append({'id':r['id'],'title':r.get('title',''),'source':r.get('source',''),'source_id':r.get('source_id',''),'url':r.get('url',''),'published':r.get('published') or r.get('retrieved'),'summary':(r.get('summary') or '')[:400], 'desk':r.get('desk',''),'is_india':r.get('is_india',False),'group':gid,'semantic_group':int(sem[i]),'position':[round(x,4) for x in p]})
    # Collision-aware rendering offset for near-identical excerpts. This offsets
    # overlapping points only for display; it does not change cluster assignments.
    near=defaultdict(list)
    for i,node in enumerate(nodes):
        near[(node['group'],*(round(x,2) for x in node['position']))].append(i)
    for indices in near.values():
        if len(indices)<2:continue
        radius=min(.76,.105*math.sqrt(len(indices)))
        for j,i in enumerate(sorted(indices,key=lambda idx:nodes[idx]['id'])):
            a=2*math.pi*j/len(indices)
            nodes[i]['position']=[round(nodes[i]['position'][0]+radius*math.cos(a),4),
                                   round(nodes[i]['position'][1]+radius*math.sin(a),4),
                                   round(nodes[i]['position'][2]+radius*.55*math.cos(2*a),4)]
    # Tight edges in semantic space (limited for readability; no causal assertions).
    links=[]
    if mode!='source' and n<=700:
        for i in range(n):
            similarities=[]
            for j in range(i+1,n):
                if sem[i]!=sem[j]:continue
                v=dot(vectors[i],vectors[j])
                if v>.38:similarities.append((v,j))
            for s,j in sorted(similarities,reverse=True)[:2]:
                links.append({'a':i,'b':j,'similarity':round(s,3)})
    return {'nodes':nodes,'groups':groups,'links':links[:900],'method':{'algorithm':'TF-IDF + spherical cosine k-means + sparse top-3 principal projection','count':n,'dimensions':3,'semantic_clusters':k,'mode':mode,'caveat':'Coordinates show approximate excerpt similarity, not factual relationships or causal links. Source labels are categorical. Based on feed headlines and excerpts only.'}}

def cluster_payload(records,registry,focus='all',domain='all',sources='',days=30,limit=600,query='',mode='semantic'):
    if mode not in ('semantic','source','combined'):raise ValueError('Invalid cluster mode')
    if focus not in ('all','India','World'):raise ValueError('Invalid focus')
    if domain not in DESKS:raise ValueError('Invalid domain')
    if not 1<=days<=3650:raise ValueError('Invalid days')
    if not 10<=limit<=750:raise ValueError('Invalid limit')
    picked=select_records(records,registry,focus,domain,sources,days,limit,query)
    result=make_clusters(picked,mode)
    result.update({'scope':{'focus':focus,'domain':domain,'days':days,'sources':sources,'query':query,'limit':limit},'retrieved_scope':'Local article and paper database; no live feed fetched by cluster request.'})
    return result
