"""ATLAS v4: reversible, provenance-preserving content-genre exclusion.

The genre classifier uses conservative headline-first lexical rules. It is not a
political-position classifier and does not infer intent, credibility or ideology.
All classifications are inspectable; false positives are possible. Existing
records are never deleted by a cleanup preference change.
"""
from __future__ import annotations
import re
from contextlib import closing

# Reviewable and deliberately narrow; broad overlapping policy domains are not excluded.
CATEGORIES = [
    dict(id='crime',name='Crime & policing',label='CRIME',
         description='Reported murders, thefts, assaults, kidnappings and local criminal investigations. Policy and geopolitical reporting is retained.',accent='#D99191',default=False,
         examples='murder investigation · burglary · robbery suspect'),
    dict(id='astrology',name='Astrology & horoscopes',label='HOROSCOPES',
         description='Zodiac predictions, numerology, star-sign advice and daily horoscopes.',accent='#BE9EF0',default=True,
         examples='horoscope today · daily rashifal · zodiac prediction'),
    dict(id='celebrity',name='Celebrity gossip',label='GOSSIP',
         description='Celebrity romance, paparazzi, rumours and social-personality gossip.',accent='#E4A0BD',default=False,
         examples='celebrity dating rumour · celebrity breakup'),
    dict(id='entertainment',name='Film, TV & entertainment',label='ENTERTAINMENT',
         description='Movie reviews, streaming releases, TV recaps and entertainment awards.',accent='#CBB1FF',default=False,
         examples='movie box office · Netflix series review'),
    dict(id='sports',name='Sports results',label='SPORTS',
         description='Sports scores, match predictions, fixtures and fantasy team tips.',accent='#80BCDA',default=False,
         examples='IPL score · football fixtures · match highlights'),
    dict(id='lifestyle',name='Lifestyle & fashion',label='LIFESTYLE',
         description='Fashion trends, routine beauty tips and lifestyle trends.',accent='#E3AF90',default=False,
         examples='fashion trends · outfit ideas · skincare routine'),
    dict(id='shopping',name='Shopping & promotions',label='PROMOTIONS',
         description='Product discounts, seasonal sales, vouchers and consumer deal lists.',accent='#D3B572',default=False,
         examples='best deals under ₹ · discount coupon · flash sale'),
    dict(id='travel',name='Travel & leisure',label='LEISURE',
         description='Holiday itineraries, resort recommendations and tourism listicles.',accent='#7BBBC0',default=False,
         examples='best places to visit · weekend getaway'),
    dict(id='gaming',name='Gaming & pop culture',label='GAMING',
         description='Video-game walkthroughs, game-release reviews and pop-culture trivia.',accent='#97A9EA',default=False,
         examples='game walkthrough · PlayStation game review'),
    dict(id='food',name='Recipes & food trends',label='FOOD',
         description='Cooking recipes, restaurant-trend listicles and food hacks.',accent='#C5C88E',default=False,
         examples='easy paneer recipe · cooking hacks'),
]
IDS={x['id'] for x in CATEGORIES}
DEFAULT={x['id'] for x in CATEGORIES if x['default']}

# Normalized, bounded title tests. Catch stories typical of individual genres,
# avoiding generic keywords such as "star", "market", "war", or "security".
RULES={
 'crime': [r'\b(?:murders?|murdered|homicide|burglary|burglaries|robbery|robberies|rape|raped|molestation|kidnapp(?:ed|ing)|stabb(?:ed|ing)|shoplifting|carjacking)\b', r'\b(?:police|cops)\b.{0,65}\b(?:arrest|arrests|arrested|theft|assault|suspect)\b'],
 'astrology': [r'\b(?:horoscopes?|rashifal|rashiphal|zodiac|astrolog(?:y|er|ical)|numerolog(?:y|ist)|tarot\s+(?:reading|cards?))\b',
               r'\b(?:aries|taurus|gemini|cancer|leo|virgo|libra|scorpio|sagittarius|capricorn|aquarius|pisces)\s+(?:horoscope|zodiac|prediction|today)\b'],
 'celebrity': [r'\b(?:celebrity|bollywood\s+(?:star|actor)|film\s+star|reality\s+star)\b.{0,70}\b(?:dating|breakup|wedding|divorce|romance|rumou?r|gossip|paparazzi)\b',
               r'\b(?:paparazzi|celebrity\s+gossip|celebrity\s+breakup|star\s+couple)\b'],
 'entertainment': [r'\b(?:movie|film|web\s+series|tv\s+show|netflix\s+series|ott\s+release)\b.{0,65}\b(?:review|trailer|box\s+office|recap|episode|ending\s+explained|streaming\s+date)\b',
                   r'\b(?:box\s+office\s+(?:collection|numbers)|movie\s+review|film\s+review|television\s+recap)\b'],
 'sports': [r'\b(?:cricket|football|soccer|tennis|badminton|ipl|premier\s+league|nba|world\s+cup)\b.{0,65}\b(?:score|scores|fixture|result|fantasy\s+(?:xi|team)|highlights|match\s+prediction|lineup)\b',
            r'\b(?:live\s+score|match\s+highlights|football\s+fixtures|fantasy\s+cricket|match\s+scorecard)\b'],
 'lifestyle': [r'\b(?:fashion\s+trends?|outfit\s+ideas|skincare\s+routine|beauty\s+hacks|makeup\s+tips|home\s+decor\s+tips|hairstyle\s+ideas)\b'],
 'shopping': [r'\b(?:best\s+deals?|flash\s+sale|shopping\s+discounts?|discount\s+codes?|coupon\s+codes?|promo\s+codes?|top\s+discounts?)\b',
              r'\b(?:save\s+\d+\s*%\s+on|buy\s+now\s+at|sale\s+ends\s+today)\b'],
 'travel': [r'\b(?:weekend\s+getaways?|places\s+to\s+visit|best\s+(?:beaches|hotels|resorts|vacation|holiday\s+destinations)|travel\s+hacks|tourist\s+spots)\b'],
 'gaming': [r'\b(?:video\s+game\s+review|gaming\s+walkthrough|game\s+walkthrough|ps5\s+games?|playstation\s+games?|xbox\s+game\s+review|gaming\s+release|gameplay\s+tips)\b'],
 'food': [r'\b(?:easy\s+recipes?|homemade\s+recipes?|cooking\s+hacks|food\s+hacks|paneer\s+recipe|chicken\s+recipe|how\s+to\s+cook|restaurant\s+listicle|best\s+brunch\s+spots)\b'],
}
COMPILED={k:[re.compile(p,re.I) for p in pats] for k,pats in RULES.items()}
# Institutional or policy articles mentioning a classified term are kept if the
# dominant headline is about regulation, economics, security or social impact.
POLICY_CONTEXT=re.compile(r'\b(?:lawmakers?|parliament|government|policy|regulat(?:ion|or|ory)|legislation|trade|ban\s+on|tax|economic\s+impact|supreme\s+court|court\s+rules|election|war|geopolitic|national\s+security|industry\s+analysis)\b',re.I)

def classify(title,summary=''):
    """Single mutually exclusive genre, or '' for core/general intelligence.

    Title-driven to reduce misclassification from unrelated feed summaries.
    We retain policy stories even when they mention entertainment or sports.
    """
    title=(title or '')[:400]
    if not title.strip():return ''
    for genre, pats in COMPILED.items():
        if any(p.search(title) for p in pats):
            if genre!='astrology' and POLICY_CONTEXT.search(title):continue
            return genre
    return ''

def init(con):
    con.execute('''CREATE TABLE IF NOT EXISTS cleanup_preferences (
       genre TEXT PRIMARY KEY, enabled INTEGER NOT NULL, updated TEXT NOT NULL)''')
    cols={r[1] for r in con.execute('PRAGMA table_info(entries)')}
    if 'genre' not in cols:con.execute("ALTER TABLE entries ADD COLUMN genre TEXT NOT NULL DEFAULT ''")
    now='2026-11-16T00:00:00Z'
    for c in CATEGORIES:
        con.execute('INSERT OR IGNORE INTO cleanup_preferences VALUES(?,?,?)',(c['id'],int(c['default']),now))
    # Reclassify existing unclassified rows on first migration; a migration flag
    # prevents rewriting categories on every restart.
    con.execute('CREATE TABLE IF NOT EXISTS cleanup_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS cleanup_skips (item_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, genre TEXT NOT NULL, first_seen TEXT NOT NULL)')
    if not con.execute("SELECT 1 FROM cleanup_meta WHERE key='genre_migration_v42'").fetchone():
        entries=con.execute('SELECT id,title,summary FROM entries').fetchall()
        con.executemany('UPDATE entries SET genre=? WHERE id=?',[(classify(r['title'],r['summary']),r['id']) for r in entries])
        con.execute("INSERT INTO cleanup_meta VALUES('genre_migration_v42','complete')")
    con.commit()

def active(con):
    return {r[0] for r in con.execute('SELECT genre FROM cleanup_preferences WHERE enabled=1') if r[0] in IDS}

# Optional extra visibility rule (v5: globally blocked publishers). Set by server.
EXTRA_FILTER=None

def where_visible(con,alias=''):
    selected=sorted(active(con))
    prefix=(alias+'.') if alias else ''
    sql,vals='1=1',()
    if selected:
        sql,vals=f"COALESCE({prefix}genre,'') NOT IN ({','.join('?' for _ in selected)})",tuple(selected)
    if EXTRA_FILTER is not None:
        extra_sql,extra_vals=EXTRA_FILTER(con,alias)
        if extra_sql!='1=1':
            sql,vals=(extra_sql,tuple(extra_vals)) if sql=='1=1' else (sql+' AND '+extra_sql,vals+tuple(extra_vals))
    return sql,vals

def apply(con,enabled,now):
    if not isinstance(enabled,list) or any(not isinstance(x,str) or x not in IDS for x in enabled):
        raise ValueError('Unknown cleanup genre.')
    if len(set(enabled))!=len(enabled):raise ValueError('Duplicate cleanup genre.')
    selected=set(enabled)
    for c in CATEGORIES:
        con.execute('UPDATE cleanup_preferences SET enabled=?,updated=? WHERE genre=?', (int(c['id'] in selected),now,c['id']))
    con.commit()

def snapshot(con):
    selected=active(con)
    stat={r['genre']:(r['count'],r['latest']) for r in con.execute("SELECT genre,COUNT(*) AS count,MAX(retrieved) AS latest FROM entries WHERE medium='article' GROUP BY genre")}
    skips={row[0]:row[1] for row in con.execute('SELECT genre,COUNT(*) FROM cleanup_skips GROUP BY genre')}
    result=[]
    for c in CATEGORIES:
        total,last=stat.get(c['id'],(0,None))
        examples=[dict(r) for r in con.execute("SELECT id,title,source FROM entries WHERE genre=? AND medium='article' ORDER BY COALESCE(published,retrieved) DESC LIMIT 3",(c['id'],))]
        result.append({**c,'stored':total,'ignored_new':skips.get(c['id'],0),'enabled':c['id'] in selected,'examples':examples,'last_seen':last})
    sum_hidden=sum(stat.get(x,(0,None))[0] for x in selected)
    visible=con.execute("SELECT COUNT(*) FROM entries WHERE medium='article'").fetchone()[0]-sum_hidden
    return {'categories':result,'active':sorted(selected),'visible_articles':visible,'hidden_in_archive':sum_hidden,'ignored_new_unique':sum(skips.values()),
            'method':'Conservative headline-first lexical genre rules, inspectable and fallible. Only catalogued genres are blocked; unmatched material remains. Existing records stay archived. New matching feed items are skipped before storage. No changes to publisher feeds or external APIs.'}
