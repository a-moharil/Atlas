"""ATLAS v5 publisher intelligence.

* Resolves every feed and every article to a *publisher* (a host), including the
  original publisher behind Google News discovery feeds.
* Supplies outlet-level bias ratings (MBFC / AllSides, averaged Ground-News style),
  factuality, ownership and paywall model from ``publishers.json``.
* Detects individual premium (subscriber-only) article URLs.
* Clusters retrieved headlines into stories and computes the left / centre / right
  spread of publishers covering each story, which drives the per-article gauge.
* Stores global source preferences: *primary* publishers are promoted in the UI and
  *blocked* publishers are neither fetched nor shown anywhere.

Everything here is deterministic and inspectable. A rating describes an outlet, not an
article; story clusters are approximate headline-similarity groups.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / 'publishers.json').read_text(encoding='utf-8'))
PUBLISHERS: dict = DATA['publishers']
SCALE = DATA['scale']
LEAN_NAMES = {-2: 'Left', -1: 'Lean Left', 0: 'Center', 1: 'Lean Right', 2: 'Right'}
NAME_INDEX = {re.sub(r'[^a-z0-9]', '', v['name'].lower()): k for k, v in PUBLISHERS.items()}
NAME_INDEX.update({'thehindu': 'thehindu.com', 'indianexpress': 'indianexpress.com', 'timesofindia': 'timesofindia.indiatimes.com',
                   'theeconomictimes': 'economictimes.indiatimes.com', 'economictimes': 'economictimes.indiatimes.com',
                   'livemint': 'livemint.com', 'ndtvprofit': 'ndtv.com', 'cnnnews18': 'news18.com', 'reutersindia': 'reuters.com',
                   'bbc': 'bbc.com', 'bbcnews': 'bbc.com', 'theguardian': 'theguardian.com', 'apnews': 'apnews.com',
                   'deutschewelle': 'dw.com', 'ptiprestrustofindia': 'ptinews.com', 'pti': 'ptinews.com', 'swarajyamag': 'swarajyamag.com',
                   'businessstandard': 'business-standard.com', 'hindustantimes': 'hindustantimes.com', 'theprint': 'theprint.in',
                   'scrollin': 'scroll.in', 'thewire': 'thewire.in', 'wion': 'wionews.com', 'aninews': 'aninews.in', 'firstpost': 'firstpost.com'})
ALIASES = {'bbc.co.uk': 'bbc.com', 'feeds.bbci.co.uk': 'bbc.com', 'rss.dw.com': 'dw.com', 'edition.cnn.com': 'cnn.com',
           'feeds.arstechnica.com': 'arstechnica.com', 'feeds.marketwatch.com': 'marketwatch.com',
           'feeds.content.dowjones.io': 'wsj.com', 'm.thewire.in': 'thewire.in', 'amp.scroll.in': 'scroll.in',
           'theindianexpress.com': 'indianexpress.com', 'thehindu.co.in': 'thehindu.com'}
LOCK = threading.RLock()
FEED_HOST: dict[str, str] = {}
_STORY_CACHE = {'key': None, 'value': {}}


# ------------------------------------------------------------------ resolution

def norm_host(host: str) -> str:
    host = (host or '').lower().strip().rstrip('.')
    host = host.removeprefix('www.').removeprefix('m.').removeprefix('amp.')
    host = ALIASES.get(host, host)
    if host in PUBLISHERS:
        return host
    # Section sub-domains collapse to their registered parent (e.g. tech.economictimes...)
    parts = host.split('.')
    for i in range(1, len(parts) - 1):
        parent = '.'.join(parts[i:])
        if parent in PUBLISHERS and parent not in ('indiatimes.com',):
            return parent
    return host


def host_of(url: str) -> str:
    try:
        return norm_host(urllib.parse.urlparse(url or '').hostname or '')
    except ValueError:
        return ''


def feed_host(feed: dict) -> str:
    """Publisher host for a configured feed (site: query wins over a proxy host)."""
    m = re.search(r'site%3A([a-z0-9.\-]+)', feed.get('url', ''), re.I)
    if m:
        return norm_host(m.group(1))
    h = host_of(feed.get('site') or feed.get('url', ''))
    if h in ('news.google.com', 'google.com', ''):
        return 'feed:' + feed['id']
    return h


def set_feeds(feeds):
    with LOCK:
        FEED_HOST.clear()
        FEED_HOST.update({f['id']: feed_host(f) for f in feeds})


def title_publisher(title: str) -> str:
    """Google News titles end with ' - Publisher'. Map that to a registered host."""
    m = re.search(r'\s[-–|]\s([^-–|]{2,60})$', title or '')
    if not m:
        return ''
    key = re.sub(r'[^a-z0-9]', '', m.group(1).lower())
    return NAME_INDEX.get(key, '')


def entry_host(entry: dict) -> str:
    origin = norm_host(entry.get('origin_host') or '')
    if origin:
        return origin
    h = FEED_HOST.get(entry.get('source_id', ''), '')
    if h.startswith('feed:') or not h:
        guess = title_publisher(entry.get('title', ''))
        if guess:
            return guess
        uh = host_of(entry.get('url', ''))
        if uh and uh != 'news.google.com':
            return uh
    return h


def lean_value(p: dict):
    vals = [SCALE[p[k]] for k in ('mbfc', 'allsides') if p.get(k) in SCALE]
    if not vals:
        return None
    return sum(vals) / len(vals)


def lean_bucket(v):
    if v is None:
        return None
    if v < -1.25:
        return -2
    if v < -0.25:
        return -1
    if v <= 0.25:
        return 0
    if v <= 1.25:
        return 1
    return 2


# Your own calibration of an outlet's lean: host -> {'lean': -2..2 or None, 'note', 'updated'}.
# Applied inside profile(), so cards, gauges, story spreads and the coverage graph all use it.
OVERRIDES: dict = {}
_OVERRIDE_VERSION = [0]


def profile(host: str, fallback_name: str = '') -> dict:
    p = PUBLISHERS.get(host)
    gov = host.endswith(('.gov.in', '.nic.in', '.gov', '.gov.uk', '.go.jp', '.gov.au', '.int')) or host.endswith('europa.eu')
    if not p:
        name = fallback_name or (host[5:] if host.startswith('feed:') else host)
        p = {'name': name, 'masthead': 'institution' if gov else 'grotesk', 'paywall': 'free' if gov else 'unknown',
             'paywall_note': 'Official publication' if gov else 'Paywall model not yet classified',
             'kind': 'government' if gov else 'unclassified', 'ownership': 'Government' if gov else ''}
    v = lean_value(p)
    b = lean_bucket(v)
    raters = []
    if p.get('mbfc') in SCALE:
        raters.append({'provider': 'Media Bias/Fact Check', 'rating': LEAN_NAMES[SCALE[p['mbfc']]]})
    if p.get('allsides') in SCALE:
        raters.append({'provider': 'AllSides', 'rating': LEAN_NAMES[SCALE[p['allsides']]]})
    kind = p.get('kind') or 'news'
    published = {'lean_original': b, 'lean_original_label': LEAN_NAMES.get(b, 'Not rated'), 'lean_user': False, 'lean_note': ''}
    o = OVERRIDES.get(host)
    if o is not None:
        b = o['lean']
        published.update(lean_user=True, lean_note=o.get('note', ''))
    return {**published,
        'host': host, 'name': p['name'], 'country': p.get('country', ''), 'ownership': p.get('ownership', ''),
        'masthead': p.get('masthead', 'grotesk'), 'kind': kind,
        'lean': b, 'lean_score': None if v is None else round(v, 2), 'lean_label': LEAN_NAMES.get(b, 'Not rated' if kind == 'news' else 'Institutional · not rated'),
        'raters': raters, 'factual': p.get('factual', ''), 'questionable': bool(p.get('questionable')),
        'state_media': bool(p.get('state_media')), 'rating_url': p.get('rating_url', ''), 'rating_caveat': p.get('rating_caveat', ''),
        'paywall': p.get('paywall', 'unknown'), 'paywall_label': DATA['paywall_levels'].get(p.get('paywall'), 'Not classified'),
        'paywall_note': p.get('paywall_note', ''),
        'logo': '/api/publisher-logo?host=' + urllib.parse.quote(host) if not host.startswith('feed:') else '',
    }


def article_paywall(entry: dict, host: str) -> str:
    """'premium' (subscriber-only URL), 'hard', 'metered', 'freemium', 'free' or 'unknown'."""
    p = PUBLISHERS.get(host, {})
    url = (entry.get('url') or '').lower()
    for pat in p.get('premium_patterns', []):
        if pat in url:
            return 'premium'
    if re.search(r'/(premium|subscriber-only|members-only|plus)/', url) and p.get('paywall') in ('freemium', 'metered'):
        return 'premium'
    return p.get('paywall', 'free' if host.endswith(('.gov.in', '.nic.in')) else 'unknown')


# ------------------------------------------------------------- preferences

def init(con):
    con.executescript('''CREATE TABLE IF NOT EXISTS source_prefs(
        host TEXT PRIMARY KEY, state TEXT NOT NULL CHECK(state IN ('primary','blocked')), updated TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS lean_overrides(
        host TEXT PRIMARY KEY, lean INTEGER CHECK(lean IS NULL OR lean BETWEEN -2 AND 2), note TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL);''')
    con.commit()
    load_overrides(con)


def load_overrides(con) -> dict:
    global OVERRIDES
    try:
        OVERRIDES = {r[0]: {'lean': r[1], 'note': r[2], 'updated': r[3]} for r in con.execute('SELECT host,lean,note,updated FROM lean_overrides')}
    except Exception:
        OVERRIDES = {}
    _OVERRIDE_VERSION[0] += 1
    return OVERRIDES


def set_lean(con, host: str, lean, note: str, now: str) -> dict:
    """lean: -2..2, None ('not rated' in your view) or 'reset' (use the published rating again)."""
    host = norm_host(host) if not host.startswith('feed:') else host
    if not re.fullmatch(r'(feed:[A-Za-z0-9_\-]{2,80}|[a-z0-9][a-z0-9.\-]{1,120})', host or ''):
        raise ValueError('Invalid publisher')
    note = re.sub(r'\s+', ' ', str(note or '')).strip()[:300]
    if lean == 'reset':
        con.execute('DELETE FROM lean_overrides WHERE host=?', (host,))
    else:
        if lean is not None:
            try:
                if isinstance(lean, bool) or (isinstance(lean, float) and not lean.is_integer()):
                    raise ValueError
                lean = int(lean)
            except (TypeError, ValueError):
                raise ValueError('Lean must be -2 (left) to 2 (right), none, or reset')
            if lean not in (-2, -1, 0, 1, 2):
                raise ValueError('Lean must be -2 (left) to 2 (right), none, or reset')
        con.execute('INSERT INTO lean_overrides VALUES(?,?,?,?) ON CONFLICT(host) DO UPDATE SET lean=excluded.lean,note=excluded.note,updated=excluded.updated',
                    (host, lean, note, now))
    con.commit()
    return load_overrides(con)


def prefs(con) -> dict:
    try:
        return {r[0]: r[1] for r in con.execute('SELECT host,state FROM source_prefs')}
    except Exception:
        return {}


def set_pref(con, host: str, state: str, now: str):
    host = norm_host(host) if not host.startswith('feed:') else host
    if not re.fullmatch(r'(feed:[A-Za-z0-9_\-]{2,80}|[a-z0-9][a-z0-9.\-]{1,120})', host or ''):
        raise ValueError('Invalid publisher')
    if state not in ('primary', 'blocked', 'normal'):
        raise ValueError('Invalid source preference')
    if state == 'normal':
        con.execute('DELETE FROM source_prefs WHERE host=?', (host,))
    else:
        con.execute('INSERT INTO source_prefs VALUES(?,?,?) ON CONFLICT(host) DO UPDATE SET state=excluded.state,updated=excluded.updated',
                    (host, state, now))
    con.commit()


def blocked_hosts(con) -> set:
    return {h for h, s in prefs(con).items() if s == 'blocked'}


def feed_blocked(feed: dict, blocked: set) -> bool:
    return feed_host(feed) in blocked


def visibility_clause(con, alias=''):
    """SQL fragment hiding records of blocked publishers (used by content_cleanup)."""
    blocked = blocked_hosts(con)
    if not blocked:
        return '1=1', ()
    prefix = (alias + '.') if alias else ''
    with LOCK:
        ids = sorted(k for k, h in FEED_HOST.items() if h in blocked)
    parts, vals = [], []
    if ids:
        parts.append(f"{prefix}source_id NOT IN ({','.join('?' for _ in ids)})")
        vals += ids
    hosts = sorted(blocked)
    parts.append(f"COALESCE({prefix}origin_host,'') NOT IN ({','.join('?' for _ in hosts)})")
    vals += hosts
    return ' AND '.join(parts), tuple(vals)


# ------------------------------------------------------------- story spread

STOP = set('''about after again against amid among another around because before being between could during every first
from have having into just last more most much over says said should since some such than that their them then there these
they this those through under until upon very were what when where which while will with would your news live latest update
updates india indian world today report reports breaking video watch photos year years week amid also new says''' .split())


def tokens(title: str) -> set:
    t = re.sub(r'\s[-–|]\s[^-–|]{2,60}$', '', (title or '').lower())
    return {w for w in re.findall(r'[a-z][a-z0-9]{3,}', t) if w not in STOP}


def stories(entries: list, meaning: dict | None = None) -> dict:
    """Map entry id -> story summary.

    ``meaning`` (from semantic.story_groups) maps entry id -> {'group', 'similarity'} for
    articles grouped by the local language model; any article it does not cover is
    grouped by headline keyword overlap and its story is marked method='keywords'."""
    arts = [e for e in entries if e.get('medium') == 'article']
    meaning = meaning or {}
    key = (len(arts), max((e.get('retrieved') or '' for e in arts), default=''), arts[0]['id'] if arts else '', id(meaning), len(meaning))
    key = key + (_OVERRIDE_VERSION[0],)
    with LOCK:
        if _STORY_CACHE['key'] == key:
            return _STORY_CACHE['value']
    parent = list(range(len(arts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    first = {}
    for i, e in enumerate(arts):
        m = meaning.get(e['id'])
        if m:
            if m['group'] in first:
                parent[find(i)] = find(first[m['group']])
            else:
                first[m['group']] = i
    toks = [tokens(e.get('title', '')) if e['id'] not in meaning else set() for e in arts]
    index: dict[str, list[int]] = {}
    for i, ts in enumerate(toks):
        for t in ts:
            index.setdefault(t, []).append(i)
    for i, ts in enumerate(toks):
        if len(ts) < 3:
            continue
        counts: dict[int, int] = {}
        for t in ts:
            bucket = index[t]
            if len(bucket) > 80:
                continue
            for j in bucket:
                if j > i:
                    counts[j] = counts.get(j, 0) + 1
        for j, c in counts.items():
            if c >= 3 and c / len(ts | toks[j]) >= 0.34:
                a, b = find(i), find(j)
                if a != b:
                    parent[b] = a
    groups: dict[int, list[int]] = {}
    for i in range(len(arts)):
        groups.setdefault(find(i), []).append(i)
    out = {}
    for root, members in groups.items():
        seen = {}
        for i in members:
            h = entry_host(arts[i])
            if h and h not in seen:
                seen[h] = profile(h).get('lean')
        dist = {'left': 0, 'center': 0, 'right': 0, 'unrated': 0}
        for v in seen.values():
            dist['unrated' if v is None else 'left' if v < 0 else 'right' if v > 0 else 'center'] += 1
        sid = arts[root]['id']
        sem = [meaning[arts[i]['id']] for i in members if arts[i]['id'] in meaning]
        summary = {'id': sid, 'sources': len(seen), 'articles': len(members), 'dist': dist,
                   'method': 'meaning' if sem else 'keywords',
                   'similarity': round(sum(x['similarity'] for x in sem) / len(sem), 3) if sem else None}
        for i in members:
            out[arts[i]['id']] = summary
    with LOCK:
        _STORY_CACHE.update(key=key, value=out)
    return out


def enrich(entries: list, meaning: dict | None = None) -> dict:
    """Annotate entries in place; return the publisher directory for the hosts seen."""
    spread = stories(entries, meaning)
    seen = {}
    for e in entries:
        h = entry_host(e)
        e['publisher'] = h
        if h not in seen:
            seen[h] = profile(h, e.get('source', '').split(' · ')[0])
        e['paywall'] = article_paywall(e, h)
        s = spread.get(e['id'])
        if s:
            e['story'] = s
    return seen


def directory(feeds: list, statuses: dict, counts: dict, con) -> list:
    """Every configured publisher with its feeds, health, preference and record count."""
    pref = prefs(con)
    groups: dict[str, dict] = {}
    for f in feeds:
        h = feed_host(f)
        g = groups.setdefault(h, {**profile(h, f['name'].split(' · ')[0]), 'feeds': [], 'records': 0, 'desks': set(), 'regions': set()})
        st = statuses.get(f['id'], {})
        g['feeds'].append({'id': f['id'], 'name': f['name'], 'state': st.get('state', 'never'), 'attempted': st.get('attempted'),
                           'error': (st.get('error') or '')[:160], 'desk': f.get('desk', '')})
        g['records'] += counts.get(f['id'], 0)
        g['desks'].add(f.get('desk', ''))
        g['regions'].add(f.get('region', ''))
    for h, n in counts.items():
        if h.startswith('origin:'):
            host = h[7:]
            g = groups.setdefault(host, {**profile(host), 'feeds': [], 'records': 0, 'desks': set(), 'regions': set(), 'via_aggregator': True})
            g['records'] += n
    out = []
    for h, g in groups.items():
        g['desks'] = sorted(x for x in g['desks'] if x)
        g['regions'] = sorted(x for x in g['regions'] if x)
        g['pref'] = pref.get(h, 'normal')
        g['healthy'] = sum(x['state'] == 'ok' for x in g['feeds'])
        out.append(g)
    out.sort(key=lambda g: (g['pref'] != 'primary', g['kind'] != 'news', -g['records'], g['name'].lower()))
    return out
