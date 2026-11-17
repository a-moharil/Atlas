"""ATLAS expert workspaces: explicitly sourced event register and optional World Bank statistical retrieval.

No invented interpretation: topic/actor overlaps are labelled as discovery hypotheses,
not diplomatic connections. Economic data are returned only after successful API retrieval.
"""
from __future__ import annotations
import datetime as dt
import concurrent.futures
import json
import re
import time
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
EVENTS=json.loads((ROOT/'expert_events.json').read_text(encoding='utf-8'))
ACTORS={
 'India':r'\b(india|indian|bharat|new delhi|modi|jaishankar|quad)\b',
 'United States':r'\b(us|u\.s\.|united states|washington|white house|trump|american)\b',
 'China':r'\b(china|chinese|beijing|xi jinping)\b',
 'Russia':r'\b(russia|russian|moscow|kremlin|putin)\b',
 'European Union':r'\b(european union|\beu\b|brussels|european commission|eeas)\b',
 'Ukraine':r'\b(ukraine|ukrainian|kyiv|zelensky)\b',
 'ASEAN':r'\b(asean|southeast asia)\b',
 'Japan':r'\b(japan|japanese|tokyo)\b',
 'Australia':r'\b(australia|australian|canberra)\b',
 'United Nations':r'\b(united nations|\bun\b|security council|general assembly)\b',
 'Iran':r'\b(iran|iranian|tehran|hormuz)\b',
 'Gulf':r'\b(saudi|gulf|uae|qatar|oman|abu dhabi|riyadh)\b',
}
ISSUES={
 'Security':r'\b(security|nato|military|deterren|ceasefire|missile|war|defence|defense|sanctions)\b',
 'Trade':r'\b(trade|tariff|supply chain|export|import|corridor|customs|investment)\b',
 'Technology':r'\b(technology|artificial intelligence|\bai\b|chips|semiconductor|critical mineral|cyber)\b',
 'Energy':r'\b(energy|oil|gas|lng|nuclear|power grid|petroleum|renewable)\b',
 'Climate':r'\b(climate|emissions|cop31|carbon|drought|flood|extreme weather)\b',
 'Diplomacy':r'\b(summit|foreign minister|foreign ministry|bilateral|negotiat|diploma|dialogue|agreement)\b',
 'Maritime':r'\b(maritime|strait|shipping|naval|port|south china sea|indian ocean|red sea)\b',
}
PORTALS=[
 ('India','Ministry of External Affairs','https://www.mea.gov.in/press-releases.htm','India: official releases and briefings'),
 ('United States','State Department','https://www.state.gov/press-releases/','US diplomatic positions and readouts'),
 ('China','Ministry of Foreign Affairs','https://www.fmprc.gov.cn/mfa_eng/','Chinese foreign-ministry releases'),
 ('Russia','Ministry of Foreign Affairs','https://mid.ru/en/','Russian official statements'),
 ('European Union','EEAS','https://www.eeas.europa.eu/','EU external-action statements'),
 ('United Kingdom','FCDO','https://www.gov.uk/government/organisations/foreign-commonwealth-development-office','UK government releases'),
 ('Japan','Ministry of Foreign Affairs','https://www.mofa.go.jp/','Japan official diplomacy'),
 ('Australia','Department of Foreign Affairs and Trade','https://www.dfat.gov.au/','Australia official diplomacy'),
 ('United Nations','Security Council programme of work','https://main.un.org/securitycouncil/en/content/programme-work','Current provisional programme'),
 ('United Nations','UN meetings calendar','https://www.un.org/calendar/en/date','Organisational session schedule'),
 ('United Nations','UN Digital Library','https://digitallibrary.un.org/','Official resolutions, records and agendas'),
 ('India / trade','DGFT','https://www.dgft.gov.in/','Trade policy notifications'),
 ('Global trade','WTO statistics','https://www.wto.org/english/res_e/statis_e/statis_e.htm','Trade releases and datasets'),
 ('Energy','IEA Data and Statistics','https://www.iea.org/data-and-statistics','Energy research and datasets'),
 ('Macroeconomics','IMF Data','https://data.imf.org/','WEO and macroeconomic projections'),
 ('Financial stability','BIS Statistics','https://www.bis.org/statistics/','Banking and international financial statistics'),
]
INDICATORS={
 'NY.GDP.MKTP.KD.ZG':dict(name='Real GDP growth',unit='% year on year',domain='macro',cadence='Annual'),
 'FP.CPI.TOTL.ZG':dict(name='Consumer price inflation',unit='% year on year',domain='macro',cadence='Annual'),
 'NE.TRD.GNFS.ZS':dict(name='Trade openness',unit='% of GDP',domain='trade',cadence='Annual'),
 'NE.EXP.GNFS.ZS':dict(name='Exports of goods and services',unit='% of GDP',domain='trade',cadence='Annual'),
 'TX.VAL.TECH.MF.ZS':dict(name='High-technology exports',unit='% of manufactured exports',domain='technology',cadence='Annual'),
 'GB.XPD.RSDV.GD.ZS':dict(name='Research & development expenditure',unit='% of GDP',domain='technology',cadence='Annual'),
 'EN.ATM.CO2E.PC':dict(name='CO₂ emissions per capita',unit='tonnes per person',domain='climate',cadence='Annual'),
 'EG.FEC.RNEW.ZS':dict(name='Renewable share of final energy',unit='% of final energy',domain='climate',cadence='Annual'),
 'EG.IMP.CONS.ZS':dict(name='Energy imports, net',unit='% of energy use',domain='energy',cadence='Annual'),
 'EG.USE.PCAP.KG.OE':dict(name='Energy use per capita',unit='kg oil equivalent per person',domain='energy',cadence='Annual'),
}
COUNTRIES={'IND':'India','USA':'United States','CHN':'China','DEU':'Germany','JPN':'Japan','BRA':'Brazil','RUS':'Russia','ZAF':'South Africa','IDN':'Indonesia','SAU':'Saudi Arabia','AUS':'Australia','GBR':'United Kingdom'}
CACHE={}
def geopolitics(entries,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:now=now.replace(tzinfo=dt.timezone.utc)
    items=[e for e in entries if e.get('medium')=='article'][:2400]
    recent=[]
    for e in items:
        when=e.get('published') or e.get('retrieved')
        try:
            stamp=dt.datetime.fromisoformat(when.replace('Z','+00:00'))
            if abs((now-stamp).days)>21:continue
        except Exception:continue
        body=' '.join([e.get('title') or '',e.get('summary') or ''])
        actors=[x for x,pat in ACTORS.items() if re.search(pat,body,re.I)]
        topics=[x for x,pat in ISSUES.items() if re.search(pat,body,re.I)]
        if not actors and not topics:continue
        recent.append({**{k:e.get(k) for k in ('id','title','source','url','summary','published','retrieved','tier','source_id')},'actors':actors,'topics':topics})
    # Co-mentions are not evidence of cooperation, causality, agreements or direct meetings.
    links=Counter()
    evidence=defaultdict(list)
    for e in recent:
        for i,a in enumerate(e['actors']):
            for b in e['actors'][i+1:]:
                edge=tuple(sorted((a,b)));links[edge]+=1
                if len(evidence[edge])<4:evidence[edge].append(dict(title=e['title'],url=e['url'],source=e['source']))
    network=[dict(a=a,b=b,mention_count=n,evidence=evidence[(a,b)],kind='Co-mentioned in collected source briefs; analytical lead, not proven diplomatic link') for (a,b),n in links.most_common(36)]
    topics=Counter(t for e in recent for t in e['topics'])
    actors=Counter(a for e in recent for a in e['actors'])
    highlights=sorted(recent,key=lambda x:(x.get('published') or x.get('retrieved') or ''),reverse=True)
    statements=[e for e in highlights if e.get('source_id','').startswith('official_')]
    meeting_leads=[e for e in highlights if re.search(r'\b(summit|committee|agenda|ministerial|meeting|conference|dialogue|briefing)\b',e.get('title',''),re.I)][:24]
    meetings=[]
    today=now.date()
    for ev in EVENTS['events']:
        start=dt.date.fromisoformat(ev['start']);end=dt.date.fromisoformat(ev.get('end',ev['start']))
        status='completed' if end<today else 'in progress' if start<=today<=end else 'upcoming'
        meetings.append({**ev,'status':status,'verification':ev.get('verification','official')})
    meetings.sort(key=lambda x: (0 if x['status']=='upcoming' else 1 if x['status']=='in progress' else 2, dt.date.fromisoformat(x['start']).toordinal() if x['status']=='upcoming' else -dt.date.fromisoformat(x['start']).toordinal()))
    return dict(snapshot=now.isoformat(),events=meetings,institutions=EVENTS.get('institutions',[]),event_register_date=EVENTS.get('as_of'),calendars=EVENTS['calendars'],portals=[dict(region=a,name=b,url=c,scope=d) for a,b,c,d in PORTALS],situation=highlights[:70],statements=statements[:35],meeting_leads=meeting_leads,connections=network,topics=dict(topics),actors=dict(actors),retrieved_count=len(highlights),method='Source brief metadata only. Co-mentions and keyword matches are discovery signals, not verified geopolitical relations. Meeting dates reflect a separately dated official-document register and are not continuously revalidated.')

def macro_data(indicator,countries,fetch_bytes):
    if indicator not in INDICATORS:raise ValueError('Unknown or unapproved World Bank indicator')
    selected=sorted(set(countries))
    if not selected or len(selected)>8 or any(c not in COUNTRIES for c in selected):raise ValueError('Choose 1–8 approved country codes')
    key=(indicator,tuple(selected));old=CACHE.get(key)
    if old and time.monotonic()-old['t']<21600:return {**old['data'],'cache_state':'fresh cache'}
    request=f"https://api.worldbank.org/v2/country/{';'.join(selected)}/indicator/{indicator}?format=json&per_page=1500&date=2010%3A2026"
    try:
        def country_rows(code):
            endpoint=f"https://api.worldbank.org/v2/country/{code}/indicator/{indicator}?format=json&per_page=100&date={dt.datetime.now(dt.timezone.utc).year-6}%3A{dt.datetime.now(dt.timezone.utc).year-1}"
            parsed=json.loads(fetch_bytes(endpoint,2_500_000).decode('utf-8'))
            if not isinstance(parsed,list) or len(parsed)<2 or not isinstance(parsed[1],list):raise ValueError('Unexpected World Bank API response')
            return [row for row in parsed[1] if row.get('countryiso3code','').upper()==code]
        rows=[];errors={}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            work={pool.submit(country_rows,code):code for code in selected}
            for future in concurrent.futures.as_completed(work):
                try:rows.extend(future.result())
                except Exception as exc:errors[work[future]]=str(exc)[:180]
        if len(errors)==len(selected):raise RuntimeError('; '.join(code+': '+error for code,error in errors.items()))
        series=[]
        for row in rows:
            code=(row.get('countryiso3code') or '').upper()
            yr=str(row.get('date',''))
            val=row.get('value')
            if code not in selected or not yr.isdigit() or val is None:continue
            if not isinstance(val,(float,int)) or isinstance(val,bool):continue
            series.append(dict(country=code,year=int(yr),value=val))
        data=dict(indicator=indicator,**INDICATORS[indicator],countries={x:COUNTRIES[x] for x in selected},points=sorted(series,key=lambda x:(x['country'],x['year'])),source='World Bank Indicators API v2',source_url='https://data.worldbank.org/indicator/'+indicator,retrieved=dt.datetime.now(dt.timezone.utc).isoformat(),data_status='retrieved',note='Six most recent completed calendar years. Annual indicator observations: latest available year varies by country; absence is not zero. Not a live financial-market price.')
        data['country_errors']=errors
        if errors:data.update(data_status='partial',note=data['note']+' Some country requests failed: '+', '.join(errors))
        CACHE[key]={'t':time.monotonic(),'data':data};return {**data,'cache_state':'new retrieval'}
    except Exception as exc:
        if old:return {**old['data'],'cache_state':'stale cache','data_status':'stale','error':str(exc)[:200]}
        return dict(indicator=indicator,**INDICATORS[indicator],countries={x:COUNTRIES[x] for x in selected},points=[],source='World Bank Indicators API v2',source_url='https://data.worldbank.org/indicator/'+indicator,data_status='unavailable',error=type(exc).__name__+': '+str(exc)[:200],retrieved=None,note='No data returned: the server cannot currently reach or parse the official dataset.')

COMTRADE_CODES={'IND':'699','USA':'842','CHN':'156','DEU':'276','JPN':'392','BRA':'076','RUS':'643','ZAF':'710','IDN':'360','SAU':'682','AUS':'036','GBR':'826'}
def trade_preview(reporter,partner,year,flow,fetch_bytes):
    """Preview only, no-key UN Comtrade endpoint; not exhaustive bilateral trade coverage."""
    if reporter not in COMTRADE_CODES or partner not in COMTRADE_CODES or reporter==partner:raise ValueError('Choose two different supported countries')
    if not isinstance(year,int) or not 2019<=year<=2026:raise ValueError('Invalid annual period')
    if flow not in ('X','M'):raise ValueError('Flow must be exports (X) or imports (M)')
    q=urllib.parse.urlencode(dict(reporterCode=COMTRADE_CODES[reporter],partnerCode=COMTRADE_CODES[partner],period=year,flowCode=flow,cmdCode='TOTAL'))
    source='https://comtradeapi.un.org/public/v1/preview/C/A/HS?'+q
    try:
        j=json.loads(fetch_bytes(source,1_800_000).decode('utf-8'))
        lines=j.get('data',[])
        if not isinstance(lines,list):raise ValueError('No valid data array supplied by UN Comtrade')
        rows=[x for x in lines if isinstance(x,dict)]
        vals=[x.get('primaryValue') for x in rows if x.get('primaryValue') is not None and str(x.get('cmdCode','TOTAL')).upper()=='TOTAL']
        value=vals[0] if vals else None
        if not isinstance(value,(float,int)) or isinstance(value,bool):value=None
        return dict(status='ok' if value is not None else 'no preview record',reporter=reporter,partner=partner,year=year,flow=flow,value_usd=value,records=len(rows),source_url=source,provider='UN Comtrade public preview',retrieved=dt.datetime.now(dt.timezone.utc).isoformat(),warning='The no-key public endpoint supplies a limited preview, not a complete or guaranteed current trade dataset. Values are current US dollars where published; check classification, revisions and coverage.')
    except Exception as exc:
        return dict(status='unavailable',reporter=reporter,partner=partner,year=year,flow=flow,value_usd=None,source_url=source,provider='UN Comtrade public preview',retrieved=None,error=type(exc).__name__+': '+str(exc)[:190],warning='UN Comtrade could not be retrieved or returned an error. No trade value inferred.')
