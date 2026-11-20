"""Who governs: the people in office for a level and region of the Elections page.

Sources, in the order they are tried (each step is reported to the page as it runs):
  1. Wikipedia's current-office lists, which editors keep up to date within hours of a change:
     "List of current Indian chief ministers", "... deputy chief ministers", "... governors",
     "... lieutenant governors and administrators", and the "Union Council of Ministers" article.
  2. The state's current ministry article, linked from the chief-ministers list, for the cabinet.
     If the link is missing, Wikipedia search finds "<State> Council of Ministers".
  3. Wikidata (CC0), for office websites, government email addresses and photos.
  4. Wikipedia page images for anyone still without a photo (free-licence images only).
  5. election_officials.json, which ships with Sanjaya: corrections, and the mayors Wikidata lacks.

Contacts are official channels only: the office's own website, and an email address when it is on a
government domain. No personal numbers, no residences. Photos are Wikimedia Commons / Wikipedia files
loaded by the browser at view time and credited to their file page; nothing is stored in the repository.
"""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import re
import threading
import time
import urllib.parse
from pathlib import Path

import wikitables as W

ROOT = Path(__file__).resolve().parent
OVERRIDES_FILE = ROOT / 'election_officials.json'
SPARQL = 'https://query.wikidata.org/sparql'
WP_API = 'https://en.wikipedia.org/w/api.php'
TTL = 12 * 3600
PAGE_TTL = 6 * 3600
OFFICIAL_DOMAINS = ('.gov.in', '.nic.in', 'sansad.in', '.gov')
ROLE_WORDS = re.compile(r'\b(President|Vice President|Prime Minister|Minister|Governor|Mayor|Speaker|Administrator)\b', re.I)
SKIP_WORDS = re.compile(r'\b(Member of|Leader of the Opposition|Secretary|former|Shadow|Chief Justice|Judge)\b', re.I)
LIST_PAGES = {
    'cm': 'List of current Indian chief ministers',
    'dcm': 'List of current Indian deputy chief ministers',
    'gov': 'List of current Indian governors',
    'lg': 'List of current Indian lieutenant governors and administrators',
    'union': 'Union Council of Ministers',
}
NATIONAL_FIRST = ['Minister of Home Affairs', 'Minister of Defence', 'Minister of Finance', 'Minister of External Affairs']
GROUPS = ['Constitutional office', 'Head of government', 'Cabinet ministers', 'Ministers of State (Independent Charge)',
          'Ministers of State', 'Elected by the corporation', 'Other offices']
APOLITICAL = ('President of India', 'Vice President of India', 'Governor', 'Lieutenant Governor', 'Administrator')


def _load_overrides():
    try:
        return json.loads(OVERRIDES_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'scopes': {}}


def place_name(state_key):
    """Elections state key (Jammu_&_Kashmir) -> English name (Jammu and Kashmir)."""
    return str(state_key or '').replace('_', ' ').replace(' & ', ' and ').strip()


def parse_scope(scope):
    scope = str(scope or '').strip()
    if scope in ('', 'IN', 'national'):
        return 'national', 'IN', None
    kind, _, key = scope.partition(':')
    if kind not in ('state', 'city') or not re.fullmatch(r"[A-Za-z_&\- ]{2,60}", key or ''):
        raise ValueError('Unknown scope. Use IN, state:<State_key> or city:<City>.')
    return kind, f'{kind}:{key}', key


def norm_person(n):
    n = re.sub(r'\([^)]*\)', '', str(n or '').lower())
    n = re.sub(r'^(shri|smt|dr|sri|thiru|selvi)\.?\s+', '', n.strip())
    return re.sub(r'[^a-z]', '', n)


def same_person(a, b):
    a, b = norm_person(a), norm_person(b)
    return bool(a) and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.86)


def same_place(a, b):
    a = re.sub(r'[^a-z]', '', str(a or '').lower().replace('&', 'and').replace('nctof', ''))
    b = re.sub(r'[^a-z]', '', str(b or '').lower().replace('&', 'and').replace('nctof', ''))
    return bool(a) and (a == b or (len(a) > 4 and (a.startswith(b) or b.startswith(a))))


# ------------------------------------------------------------------ Wikidata (secondary)
def _lit(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"@en'


def query_for(kind, key):
    """Current holders of executive offices in the place. Offices are narrowed by label *before* holders
    are joined, so the query stays small enough to answer well inside the public endpoint's time limit."""
    if kind == 'national':
        where = 'VALUES ?jur { wd:Q668 }'
    elif kind == 'state':
        name = place_name(key)
        where = f'VALUES ?headLabel {{ {_lit("Chief Minister of " + name)} {_lit("Governor of " + name)} {_lit("Lieutenant Governor of " + name)} }} ?head rdfs:label ?headLabel ; wdt:P1001 ?jur .'
    else:
        where = f'VALUES ?headLabel {{ {_lit("Mayor of " + place_name(key))} }} ?head rdfs:label ?headLabel ; wdt:P1001 ?jur .'
    return f'''SELECT ?pos ?posLabel ?person ?personLabel ?start ?image ?partyLabel ?site ?email ?posSite ?article WHERE {{
  {{ SELECT DISTINCT ?pos WHERE {{
    {where}
    ?pos wdt:P1001 ?jur ; rdfs:label ?pl .
    FILTER(LANG(?pl) = "en" && REGEX(?pl, "^(President|Vice President|Prime Minister|Minister|Governor|Lieutenant Governor|Chief Minister|Deputy Chief Minister|Mayor|Deputy Mayor)"))
  }} LIMIT 300 }}
  ?person p:P39 ?st . ?st ps:P39 ?pos ; wikibase:rank ?rank .
  FILTER(?rank != wikibase:DeprecatedRank)
  FILTER NOT EXISTS {{ ?st pq:P582 ?end }}
  FILTER NOT EXISTS {{ ?person wdt:P570 ?died }}
  OPTIONAL {{ ?st pq:P580 ?start }}
  OPTIONAL {{ ?person wdt:P18 ?image }}
  OPTIONAL {{ ?person wdt:P102 ?party }}
  OPTIONAL {{ ?person wdt:P856 ?site }}
  OPTIONAL {{ ?person wdt:P968 ?email }}
  OPTIONAL {{ ?pos wdt:P856 ?posSite }}
  OPTIONAL {{ ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} LIMIT 600'''


def _official(url):
    try:
        u = urllib.parse.urlsplit(str(url).replace('mailto:', 'https://x@'))
    except ValueError:
        return False
    host = (u.hostname or '').lower()
    return any(host == d.lstrip('.') or host.endswith(d) for d in OFFICIAL_DOMAINS)


def photo(image_url):
    """Wikidata P18 (a Commons Special:FilePath URL) -> a small thumbnail plus its credit page."""
    if not image_url:
        return None
    name = urllib.parse.unquote(str(image_url).rsplit('/', 1)[-1]).replace(' ', '_')
    if not name or '/' in name:
        return None
    q = urllib.parse.quote(name)
    return {'src': f'https://commons.wikimedia.org/wiki/Special:FilePath/{q}?width=180',
            'credit': f'https://commons.wikimedia.org/wiki/File:{q}', 'credit_label': 'Photo: Wikimedia Commons'}


def _date(v):
    return str(v or '')[:10] or None


def parse(kind, payload):
    """SPARQL JSON -> one entry per office, keeping the most recent start when Wikidata lists
    several open-ended holders of the same office (a stale statement nobody closed)."""
    rows = (payload or {}).get('results', {}).get('bindings', [])
    best = {}
    for b in rows:
        v = {k: x.get('value') for k, x in b.items()}
        pos, name = v.get('posLabel') or '', v.get('personLabel') or ''
        if not pos or not name or re.fullmatch(r'Q\d+', name) or re.fullmatch(r'Q\d+', pos):
            continue
        if not ROLE_WORDS.search(pos) or SKIP_WORDS.search(pos):
            continue
        key = v.get('pos')
        prev = best.get(key)
        if prev and prev['wikidata'] == v.get('person'):
            _merge_contacts(prev, v)
            continue
        if prev and (prev['since'] or '') >= (_date(v.get('start')) or ''):
            continue
        entry = {'name': name, 'position': pos, 'since': _date(v.get('start')), 'party': v.get('partyLabel'),
                 'photo': photo(v.get('image')), 'wikidata': v.get('person'),
                 'wikipedia': v.get('article'), 'contacts': [], 'source': 'Wikidata', 'portfolios': []}
        _merge_contacts(entry, v)
        best[key] = entry
    return list(best.values())


def _merge_contacts(entry, v):
    seen = {c['url'] for c in entry['contacts']}
    for label, url in (('Office website', v.get('posSite')), ('Official website', v.get('site')), ('Official email', v.get('email'))):
        if not url or not _official(url):
            continue
        if label == 'Official email' and not url.startswith('mailto:'):
            url = 'mailto:' + url
        if url not in seen:
            entry['contacts'].append({'label': label, 'url': url}); seen.add(url)
    if not entry.get('photo') and v.get('image'):
        entry['photo'] = photo(v.get('image'))


# ------------------------------------------------------------------ Wikipedia (primary)
_page_lock = threading.Lock()
_pages = {}


def wp_page_url(title):
    return WP_API + '?' + urllib.parse.urlencode({'action': 'parse', 'page': title, 'prop': 'text', 'format': 'json',
                                                  'formatversion': '2', 'redirects': '1', 'disableeditsection': '1',
                                                  'disablelimitreport': '1'})


def wp_page(title, getter, cache_dir=None, force=False):
    """Article HTML, cached in memory and on disk for PAGE_TTL. A stale copy is used if Wikipedia is down."""
    now = time.time()
    with _page_lock:
        hit = _pages.get(title)
    if hit and not force and now - hit[0] < PAGE_TTL:
        return hit[1]
    disk = Path(cache_dir) / ('wp_' + hashlib.sha256(title.encode()).hexdigest()[:24] + '.json') if cache_dir else None
    if disk and not hit:
        try:
            saved = json.loads(disk.read_text(encoding='utf-8'))
            hit = (saved['t'], saved['html'])
            if not force and now - hit[0] < PAGE_TTL:
                with _page_lock:
                    _pages[title] = hit
                return hit[1]
        except (OSError, ValueError, KeyError):
            pass
    try:
        data = json.loads(getter(wp_page_url(title)).decode('utf-8'))
        if 'error' in data:
            raise LookupError(data['error'].get('info', 'missing page'))
        html = data['parse']['text']
        if isinstance(html, dict):
            html = html.get('*', '')
    except Exception:
        if hit:
            return hit[1]
        raise
    with _page_lock:
        _pages[title] = (now, html)
    if disk:
        try:
            disk.parent.mkdir(parents=True, exist_ok=True)
            disk.write_text(json.dumps({'t': now, 'html': html}), encoding='utf-8')
        except OSError:
            pass
    return html


def wp_search(query, getter, limit=5):
    url = WP_API + '?' + urllib.parse.urlencode({'action': 'query', 'list': 'search', 'srsearch': query, 'srlimit': str(limit),
                                                 'format': 'json', 'formatversion': '2'})
    data = json.loads(getter(url).decode('utf-8'))
    return [x['title'] for x in data.get('query', {}).get('search', [])]


def wp_images(titles, getter):
    """Free-licence lead images for Wikipedia articles, 50 at a time."""
    out = {}
    titles = [t for t in dict.fromkeys(titles) if t]
    for i in range(0, len(titles), 50):
        url = WP_API + '?' + urllib.parse.urlencode({'action': 'query', 'prop': 'pageimages', 'piprop': 'thumbnail|name',
                                                     'pithumbsize': '160', 'pilicense': 'free', 'redirects': '1',
                                                     'titles': '|'.join(titles[i:i + 50]), 'format': 'json', 'formatversion': '2'})
        data = json.loads(getter(url).decode('utf-8'))
        q = data.get('query', {})
        back = {}
        for r in q.get('redirects', []) + q.get('normalized', []):
            back[r['to']] = back.get(r['from'], r['from'])
        for p in q.get('pages', []):
            th = (p.get('thumbnail') or {}).get('source')
            if th and th.startswith('https://upload.wikimedia.org/'):
                credit = 'https://en.wikipedia.org/wiki/File:' + urllib.parse.quote(p.get('pageimage', '')) if p.get('pageimage') else None
                out[back.get(p['title'], p['title'])] = out[p['title']] = {'src': th, 'credit': credit, 'credit_label': 'Photo: Wikimedia'}
    return out


def _wp_link(title):
    return 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(title.replace(' ', '_')) if title else None


def _table_photo(rec):
    if not rec.get('img'):
        return None
    credit = 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(rec['file']) if rec.get('file') else None
    return {'src': rec['img'], 'credit': credit, 'credit_label': 'Photo: Wikimedia'}


def person(rec, position, group, source, order=0, portfolios=None):
    return {'name': rec['name'], 'position': position, 'group': group, 'order': order,
            'since': rec.get('since'), 'party': rec.get('party'), 'party_link': rec.get('party_link'),
            'photo': _table_photo(rec), 'wiki_title': rec.get('link'), 'wikipedia': _wp_link(rec.get('link')),
            'contacts': [], 'source': source, 'portfolios': list(portfolios if portfolios is not None else rec.get('portfolios') or [])}


def _group_from_heading(h, national):
    h = (h or '').lower()
    if 'independent' in h:
        return 'Ministers of State (Independent Charge)'
    if 'state' in h and 'minister' in h and 'cabinet' not in h:
        return 'Ministers of State'
    if 'deputy minister' in h:
        return 'Ministers of State'
    return 'Cabinet ministers'


def _current_rows(html):
    out = []
    for t in W.tables(html):
        if 'navbox' in t['class'] or 'infobox' in t['class']:
            continue
        for r in W.records(t):
            if r['current']:
                out.append(r)
    return out


def ministers_from(html, national, source):
    """Council of ministers tables -> one entry per person, portfolios gathered from every row."""
    people, order = {}, 0
    for r in _current_rows(html):
        if not r['portfolios'] and not re.search(r'minister', r['heading'] or '', re.I):
            continue
        g = _group_from_heading(r['heading'], national)
        ports = [p for p in r['portfolios'] if not re.fullmatch(r'(cabinet|minister|ministers?)', p, re.I)]
        if any(re.match(r'(Prime Minister|Chief Minister)\b', p) for p in ports):
            g = 'Head of government'
        elif any(re.match(r'Deputy Chief Minister', p) for p in ports):
            g = 'Head of government'
        key = norm_person(r['name'])
        if key in people:
            e = people[key]
            for p in ports:
                if p not in e['portfolios']:
                    e['portfolios'].append(p)
            if GROUPS.index(g) < GROUPS.index(e['group']):
                e['group'] = g
            continue
        order += 1
        people[key] = person(r, ports[0] if ports else ('Minister' if not national else 'Union Minister'), g, source, order, ports)
    for e in people.values():
        e['position'] = _primary(e, national)
        if e['position'] in e['portfolios']:
            e['portfolios'].remove(e['position'])
        if not re.search(r'minister|ministry|department|governor', e['position'], re.I):
            e['position'] = 'Minister of ' + e['position']      # state tables often give the bare portfolio
    return list(people.values())


def _primary(e, national):
    ports = e['portfolios']
    for want in NATIONAL_FIRST if national else []:
        for p in ports:
            if p.lower().startswith(want.lower()):
                return p
    for p in ports:
        if re.match(r'(Prime Minister|Chief Minister|Deputy Chief Minister)', p):
            return p
    return ports[0] if ports else e['position']


def national_people(getter, cache_dir, report, force=False):
    report('Union Council of Ministers (Wikipedia)', 'running')
    html = wp_page(LIST_PAGES['union'], getter, cache_dir, force)
    people = ministers_from(html, True, 'Wikipedia: Union Council of Ministers')
    for p in people:
        if p['group'] == 'Head of government' and re.match(r'Prime Minister', p['position']):
            p['position'] = 'Prime Minister of India'
            p['portfolios'] = [x for x in p['portfolios'] if not x.startswith('Prime Minister')]
        elif p['group'] == 'Cabinet ministers':
            for i, want in enumerate(NATIONAL_FIRST):
                if p['position'].lower().startswith(want.lower()):
                    p['order'] = -10 + i            # Home, Defence, Finance, External Affairs first
        if p['position'] in p['portfolios']:
            p['portfolios'].remove(p['position'])
    report('Union Council of Ministers (Wikipedia)', 'done', len(people))
    return people


def _rows_for_state(title, state, getter, cache_dir, force):
    html = wp_page(title, getter, cache_dir, force)
    return [r for r in _current_rows(html) if same_place(r.get('state'), state)]


def state_people(key, getter, cache_dir, report, force=False):
    name = place_name(key)
    people = []
    # head of state
    report('Governor (Wikipedia list)', 'running')
    gov = []
    for k, label in (('gov', 'Governor'), ('lg', 'Lieutenant Governor')):
        try:
            for r in _rows_for_state(LIST_PAGES[k], name, getter, cache_dir, force):
                if k == 'lg' and re.search(r'administrator', r.get('heading') or '', re.I):
                    label = 'Administrator'
                gov.append(person(r, f'{label} of {name}', 'Constitutional office', 'Wikipedia: ' + LIST_PAGES[k], 0, []))
        except Exception:
            continue
        if gov:
            break
    people += gov[:1]
    report('Governor (Wikipedia list)', 'done' if gov else 'empty', len(gov[:1]))
    # head of government
    report('Chief Minister (Wikipedia list)', 'running')
    cm_rows = _rows_for_state(LIST_PAGES['cm'], name, getter, cache_dir, force)
    ministry = None
    for r in cm_rows[:1]:
        people.append(person(r, f'Chief Minister of {name}', 'Head of government', 'Wikipedia: ' + LIST_PAGES['cm'], 0, []))
        ministry = r.get('ministry')
    report('Chief Minister (Wikipedia list)', 'done' if cm_rows else 'empty', len(cm_rows[:1]))
    report('Deputy Chief Ministers (Wikipedia list)', 'running')
    dcm = []
    try:
        for r in _rows_for_state(LIST_PAGES['dcm'], name, getter, cache_dir, force):
            dcm.append(person(r, f'Deputy Chief Minister of {name}', 'Head of government', 'Wikipedia: ' + LIST_PAGES['dcm'], 1 + len(dcm), []))
    except Exception:
        pass
    people += dcm
    report('Deputy Chief Ministers (Wikipedia list)', 'done' if dcm else 'empty', len(dcm))
    # council of ministers
    report('Council of Ministers', 'running')
    candidates = [ministry] if ministry else []
    try:
        candidates += [t for t in wp_search(f'"{name} Council of Ministers" OR "{name}" ministry council of ministers', getter)
                       if re.search(r'ministry|council of ministers', t, re.I) and not re.search(r'^list of', t, re.I)][:2]
    except Exception:
        pass
    found, used = [], None
    for title in dict.fromkeys(c for c in candidates if c):
        try:
            found = ministers_from(wp_page(title, getter, cache_dir, force), False, 'Wikipedia: ' + title)
        except Exception:
            continue
        if len(found) >= 3:
            used = title
            break
    for m in found:
        hit = next((p for p in people if same_person(p['name'], m['name'])), None)
        if hit:
            hit['portfolios'] = [x for x in m['portfolios'] if not re.match(r'(Chief Minister|Deputy Chief Minister)', x)]
            hit['party'] = hit.get('party') or m.get('party')
            hit['photo'] = hit.get('photo') or m.get('photo')
            continue
        if m['group'] == 'Head of government':
            m['group'] = 'Cabinet ministers'      # the lists above are the authority for who heads the government
        people.append(m)
    report('Council of Ministers', 'done' if used else 'empty', len(found), used)
    return people


# ------------------------------------------------------------------ assembly
def merge_wikidata(people, live, kind):
    """Wikidata adds contacts and photos to people Wikipedia already lists; where Wikipedia has nothing for
    an office (or nothing at all), Wikidata's holder is used."""
    covered = {p['position'].lower() for p in people}
    for w in live:
        hit = next((p for p in people if same_person(p['name'], w['name'])), None)
        if hit:
            hit['contacts'] = hit['contacts'] or w['contacts']
            hit['photo'] = hit.get('photo') or w.get('photo')
            hit['since'] = hit.get('since') or w.get('since')
            hit['wikidata'] = w.get('wikidata')
            hit['wikipedia'] = hit.get('wikipedia') or w.get('wikipedia')
            continue
        if w['position'].lower() in covered:
            continue                                    # Wikipedia names someone else: Wikidata is behind
        if people and re.search(r'\bMinister\b', w['position']) and not re.search(r'(Prime|Chief) Minister', w['position']):
            continue                                    # cabinet comes from the ministry page when we have one
        w['group'] = _group_for_position(w['position'], kind)
        w['order'] = 50
        people.append(w)
    return people


def _group_for_position(pos, kind):
    if pos.startswith(APOLITICAL):
        return 'Constitutional office'
    if re.match(r'(Prime Minister|Chief Minister|Deputy Chief Minister)', pos):
        return 'Head of government'
    if re.match(r'(Mayor|Deputy Mayor)', pos):
        return 'Elected by the corporation'
    if re.search(r'Minister of State', pos):
        return 'Ministers of State'
    if 'Minister' in pos:
        return 'Cabinet ministers'
    return 'Other offices'


def apply_overrides(kind, scope_id, people, overrides=None):
    o = (overrides or _load_overrides()).get('scopes', {}).get(scope_id, {})
    hide = {h.lower() for h in o.get('hide', [])}
    out = [p for p in people if p['name'].lower() not in hide and p['position'].lower() not in hide]
    edits = o.get('edit', {})
    for p in out:
        e = edits.get(p['name']) or edits.get(p['position'])
        if e:
            p.update({k: v for k, v in e.items() if k in ('name', 'position', 'since', 'party', 'contacts', 'note', 'group')})
    have = {p['position'].lower() for p in out}
    for raw in o.get('people', []):
        p = dict(raw)
        if p.get('fallback') and p.get('position', '').lower() in have:
            hit = next(x for x in out if x['position'].lower() == p['position'].lower())
            hit['contacts'] = hit.get('contacts') or [c for c in p.get('contacts', []) if c.get('url', '').startswith('https://')]
            continue        # the live sources already have this office; the shipped entry only adds contacts
        if not p.get('fallback'):
            out = [x for x in out if x['position'].lower() != p.get('position', '').lower()]
        p.setdefault('contacts', []); p.setdefault('photo', None); p.setdefault('portfolios', [])
        p['contacts'] = [c for c in p['contacts'] if c.get('url', '').startswith(('https://', 'mailto:', 'tel:'))]
        p['source'] = 'Sanjaya file' if not p.get('source_url') else 'Sanjaya file, from ' + urllib.parse.urlsplit(p['source_url']).hostname
        p.setdefault('group', _group_for_position(p.get('position', ''), kind))
        p.setdefault('order', 0)
        p.pop('fallback', None)
        out.append(p)
    for p in out:
        p.setdefault('group', _group_for_position(p['position'], kind))
        p.setdefault('order', 50)
        p['apolitical'] = p['position'].startswith(APOLITICAL)
        if p['apolitical']:
            p['party'] = None     # constitutional offices are shown without a party
            p['group'] = 'Constitutional office'
        if kind == 'national' and p['apolitical']:
            p['order'] = 0 if p['position'].startswith('President') else 1
    out.sort(key=lambda p: (GROUPS.index(p['group']) if p['group'] in GROUPS else 99, p.get('order', 50), p['name']))
    return out, o


def _colour(people):
    try:
        import elections
        table = elections.parties()
    except Exception:
        return
    by_name = {str(v.get('name', '')).lower(): k for k, v in table.items()}
    for p in people:
        party = (p.get('party') or '').strip()
        if not party:
            continue
        code = p.get('party_code') or (party if party in table else None) or by_name.get(party.lower()) \
            or by_name.get(str(p.get('party_link') or '').lower())
        if code:
            p['party_code'], p['party_color'] = code, elections.party_info(code)[1]
            p['party'] = table.get(code, {}).get('name') or party


def build(scope, getter, overrides=None, cache_dir=None, report=None, force=False):
    kind, scope_id, key = parse_scope(scope)
    o = (overrides or _load_overrides()).get('scopes', {}).get(scope_id, {})
    steps = []
    partial = {'people': []}

    def rep(label, state, count=None, detail=None):
        s = next((x for x in steps if x['label'] == label), None)
        if not s:
            s = {'label': label}; steps.append(s)
        s.update(state=state, count=count, detail=detail)
        if report:
            report(steps, partial['people'])

    people, errors = [], []
    if kind == 'national':
        try:
            people = national_people(getter, cache_dir, rep, force)
        except Exception as exc:
            rep('Union Council of Ministers (Wikipedia)', 'failed', detail=type(exc).__name__); errors.append('Wikipedia')
    elif kind == 'state':
        try:
            people = state_people(key, getter, cache_dir, rep, force)
        except Exception as exc:
            rep('Chief Minister (Wikipedia list)', 'failed', detail=type(exc).__name__); errors.append('Wikipedia')
    partial['people'] = list(people)
    if o.get('wikidata', True):
        rep('Wikidata (contacts and photos)', 'running')
        try:
            url = SPARQL + '?' + urllib.parse.urlencode({'format': 'json', 'query': query_for(kind, key)})
            live = parse(kind, json.loads(getter(url).decode('utf-8')))
            people = merge_wikidata(people, live, kind)
            rep('Wikidata (contacts and photos)', 'done', len(live))
        except Exception as exc:
            rep('Wikidata (contacts and photos)', 'failed', detail=type(exc).__name__); errors.append('Wikidata')
    partial['people'] = list(people)
    missing = [p['wiki_title'] for p in people if not p.get('photo') and p.get('wiki_title')]
    if missing:
        rep('Photos (Wikipedia)', 'running')
        try:
            imgs = wp_images(missing, getter)
            for p in people:
                if not p.get('photo') and p.get('wiki_title') in imgs:
                    p['photo'] = imgs[p['wiki_title']]
            rep('Photos (Wikipedia)', 'done', sum(1 for t in missing if t in imgs))
        except Exception as exc:
            rep('Photos (Wikipedia)', 'failed', detail=type(exc).__name__)
    people, o = apply_overrides(kind, scope_id, people, overrides)
    _colour(people)
    for p in people:
        p.pop('wiki_title', None); p.pop('party_link', None)
    live_error = None
    if errors and len(errors) == (2 if kind != 'city' else 1):
        live_error = 'Wikipedia and Wikidata could not be reached.' if kind != 'city' else 'Wikidata could not be reached.'
    return {'scope': scope_id, 'kind': kind, 'title': o.get('title') or _title(kind, key),
            'people': people, 'portal': o.get('portal'), 'note': o.get('note'), 'steps': steps,
            'as_of': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
            'live_error': live_error, 'partial_sources': errors,
            'method': 'Wikipedia\'s current office-holder lists and ministry articles, Wikidata (CC0) for official '
                      'contacts and photos, corrected by a reviewed file that ships with Sanjaya. Contacts are official '
                      'channels only. Photos: Wikimedia, credited per file.',
            'data_status': 'ok' if people else ('unavailable' if live_error else 'empty')}


def _title(kind, key):
    return 'Union of India' if kind == 'national' else place_name(key)


# ------------------------------------------------------------------ background job with progress
_lock = threading.Lock()
_jobs = {}


def _cache_file(cache_dir, scope_id):
    return Path(cache_dir) / ('officials_' + re.sub(r'[^A-Za-z0-9_]', '_', scope_id) + '.json')


def request(scope, getter, cache_dir, force=False, builder=None):
    """Serve what we have now; fetch in the background when it is missing, stale or a refresh was asked for.
    While a fetch runs, the answer carries its steps and whatever people are known so far.
    builder: an alternative build(scope_id, getter, cache_dir, report, force) for other countries."""
    if builder:
        kind, scope_id = 'other', scope
    else:
        kind, scope_id, _ = parse_scope(scope)
    now = time.time()
    with _lock:
        job = _jobs.get(scope_id)
        if job is None:
            job = {'data': None, 'checked': 0, 'running': False, 'steps': [], 'partial': [], 'error': None}
            try:
                saved = json.loads(_cache_file(cache_dir, scope_id).read_text(encoding='utf-8'))
                job.update(data=saved['data'], checked=saved['checked'])
            except (OSError, ValueError, KeyError):
                pass
            _jobs[scope_id] = job
        failed_recently = job['error'] and now - job['checked'] < 60
        due = force or not job['data'] or now - job['checked'] > TTL or (job['data'] or {}).get('live_error')
        if due and not job['running'] and not (failed_recently and not force):
            job.update(running=True, steps=[], partial=[], started=now)

            def report(steps, people):
                with _lock:
                    job['steps'] = [dict(s) for s in steps]; job['partial'] = list(people)

            def work():
                try:
                    d = builder(scope_id, getter, cache_dir, report, force) if builder else build(scope_id, getter, cache_dir=cache_dir, report=report, force=force)
                    with _lock:
                        if d['people'] or not job['data']:
                            job['data'] = d
                        job.update(checked=time.time(), error=d.get('live_error'))
                    try:
                        f = _cache_file(cache_dir, scope_id)
                        f.parent.mkdir(parents=True, exist_ok=True)
                        tmp = f.with_suffix('.tmp'); tmp.write_text(json.dumps({'data': job['data'], 'checked': job['checked']}), encoding='utf-8'); tmp.replace(f)
                    except OSError:
                        pass
                except Exception as exc:
                    with _lock:
                        job.update(error=f'{type(exc).__name__}: {exc}'[:200], checked=time.time())
                finally:
                    with _lock:
                        job['running'] = False
            threading.Thread(target=work, name='officials-' + scope_id, daemon=True).start()
        out = dict(job['data'] or {'scope': scope_id, 'kind': kind, 'people': [], 'title': _title(kind, scope_id.partition(':')[2])})
        out.update(pending=job['running'], steps=job['steps'] if job['running'] else out.get('steps', []),
                   last_checked=job['checked'], error=job['error'])
        if job['running'] and not (job['data'] or {}).get('people') and job['partial']:
            if builder:
                out['people'] = [dict(p) for p in job['partial']]
            else:
                partial, _ = apply_overrides(kind, scope_id, [dict(p) for p in job['partial']])
                _colour(partial)
                out['people'] = partial
        return out
