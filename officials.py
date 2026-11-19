"""Who governs: the people in office for a level and region of the Elections page.

Live list from Wikidata (query.wikidata.org, CC0), corrected and filled in by
election_officials.json, which ships with Sanjaya:
  - national:  President, Vice President (both apolitical offices), Prime Minister, Union ministers
  - state:     Governor or Lieutenant Governor, Chief Minister, Deputy Chief Ministers, state ministers
  - municipal: Mayor and Deputy Mayor (Wikidata rarely has these, so the file carries them)

Contacts are official channels only: the office's own website, and an email address when it is on a
government domain. No personal numbers, no residences. Photos are Wikimedia Commons files loaded by the
browser at view time and credited to their file page; nothing is stored in the repository.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OVERRIDES_FILE = ROOT / 'election_officials.json'
SPARQL = 'https://query.wikidata.org/sparql'
TTL = 12 * 3600
OFFICIAL_DOMAINS = ('.gov.in', '.nic.in', 'sansad.in', '.gov')
ROLE_WORDS = re.compile(r'\b(President|Vice President|Prime Minister|Minister|Governor|Mayor|Speaker)\b', re.I)
SKIP_WORDS = re.compile(r'\b(Member of|Leader of the Opposition|Secretary|former|Shadow|Chief Justice|Judge)\b', re.I)

# National order: the two apolitical offices first, then the head of government, then the four
# ministries conventionally listed first (Home, Defence, Finance, External Affairs).
NATIONAL_FIRST = ['President of India', 'Vice President of India', 'Prime Minister of India',
                  'Minister of Home Affairs', 'Minister of Defence', 'Minister of Finance', 'Minister of External Affairs']
APOLITICAL = ('President of India', 'Vice President of India', 'Governor', 'Lieutenant Governor')


def _load_overrides():
    try:
        return json.loads(OVERRIDES_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'scopes': {}}


def place_name(state_key):
    """Elections state key (Jammu_&_Kashmir) -> English name Wikidata uses (Jammu and Kashmir)."""
    return str(state_key or '').replace('_', ' ').replace(' & ', ' and ').strip()


def parse_scope(scope):
    scope = str(scope or '').strip()
    if scope in ('', 'IN', 'national'):
        return 'national', 'IN', None
    kind, _, key = scope.partition(':')
    if kind not in ('state', 'city') or not re.fullmatch(r"[A-Za-z_&\- ]{2,60}", key or ''):
        raise ValueError('Unknown scope. Use IN, state:<State_key> or city:<City>.')
    return kind, f'{kind}:{key}', key


def _lit(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"@en'


def query_for(kind, key):
    """SPARQL for current holders of every office whose jurisdiction (P1001) is the place.

    The place is found through its head-of-government office label, so no Wikidata ids are baked in
    except India itself (Q668)."""
    if kind == 'national':
        where = 'VALUES ?jur { wd:Q668 }'
    elif kind == 'state':
        name = place_name(key)
        where = f'VALUES ?headLabel {{ {_lit("Chief Minister of " + name)} {_lit("Governor of " + name)} {_lit("Lieutenant Governor of " + name)} }} ?head rdfs:label ?headLabel ; wdt:P1001 ?jur .'
    else:
        name = place_name(key)
        where = f'VALUES ?headLabel {{ {_lit("Mayor of " + name)} }} ?head rdfs:label ?headLabel ; wdt:P1001 ?jur .'
    return f'''SELECT DISTINCT ?pos ?posLabel ?person ?personLabel ?start ?image ?partyLabel ?site ?email ?posSite ?article WHERE {{
  {where}
  ?pos wdt:P1001 ?jur .
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
}} LIMIT 400'''


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


def rank_of(kind, position):
    p = position or ''
    if kind == 'national':
        for i, name in enumerate(NATIONAL_FIRST):
            if p.lower() == name.lower():
                return i
        if re.search(r'Minister of State', p, re.I):
            return 300
        return 100 if 'Minister' in p else 400
    order = [r'^Lieutenant Governor', r'^Governor', r'^Chief Minister', r'^Deputy Chief Minister', r'^Speaker',
             r'^Mayor', r'^Deputy Mayor']
    for i, pat in enumerate(order):
        if re.search(pat, p, re.I):
            return i
    if re.search(r'Minister of State', p, re.I):
        return 300
    return 100 if 'Minister' in p else 400


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
        if prev and (prev['since'] or '') > (_date(v.get('start')) or ''):
            if prev['wikidata'] == v.get('person'):
                _merge_contacts(prev, v)
            continue
        if prev and prev['wikidata'] == v.get('person'):
            _merge_contacts(prev, v)
            continue
        entry = {'name': name, 'position': pos, 'since': _date(v.get('start')), 'party': v.get('partyLabel'),
                 'photo': photo(v.get('image')), 'wikidata': v.get('person'),
                 'wikipedia': v.get('article'), 'contacts': [], 'source': 'Wikidata'}
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


def apply_overrides(kind, scope_id, people, overrides=None):
    o = (overrides or _load_overrides()).get('scopes', {}).get(scope_id, {})
    hide = {h.lower() for h in o.get('hide', [])}
    out = [p for p in people if p['name'].lower() not in hide and p['position'].lower() not in hide]
    edits = o.get('edit', {})
    for p in out:
        e = edits.get(p['name']) or edits.get(p['position'])
        if e:
            p.update({k: v for k, v in e.items() if k in ('name', 'position', 'since', 'party', 'contacts', 'note')})
    have = {p['position'].lower() for p in out}
    for raw in o.get('people', []):
        p = dict(raw)
        if p.get('fallback') and p.get('position', '').lower() in have:
            continue        # Wikidata already has this office; the shipped entry is only a fallback
        if not p.get('fallback'):
            out = [x for x in out if x['position'].lower() != p.get('position', '').lower()]
        p.setdefault('contacts', []); p.setdefault('photo', None)
        p['contacts'] = [c for c in p['contacts'] if c.get('url', '').startswith(('https://', 'mailto:', 'tel:'))]
        p['source'] = 'Sanjaya file' if not p.get('source_url') else 'Sanjaya file, from ' + urllib.parse.urlsplit(p['source_url']).hostname
        p.pop('fallback', None)
        out.append(p)
    for p in out:
        p['apolitical'] = any(p['position'].startswith(a) for a in APOLITICAL)
        if p['apolitical']:
            p['party'] = None     # constitutional offices are shown without a party
        p['rank'] = rank_of(kind, p['position'])
    out.sort(key=lambda p: (p['rank'], p['position'], p['name']))
    return out, o


def build(scope, getter, overrides=None):
    kind, scope_id, key = parse_scope(scope)
    people, live_error = [], None
    if kind != 'city' or (overrides or _load_overrides()).get('scopes', {}).get(scope_id, {}).get('wikidata', True):
        url = SPARQL + '?' + urllib.parse.urlencode({'format': 'json', 'query': query_for(kind, key)})
        try:
            people = parse(kind, json.loads(getter(url).decode('utf-8')))
        except Exception as exc:          # offline, rate-limited or malformed: the shipped file still answers
            live_error = f'Wikidata could not be reached ({type(exc).__name__}).'
    people, o = apply_overrides(kind, scope_id, people, overrides)
    _colour(people)
    return {'scope': scope_id, 'kind': kind, 'title': o.get('title') or _title(kind, key),
            'people': people, 'portal': o.get('portal'), 'note': o.get('note'),
            'as_of': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
            'live_error': live_error,
            'method': 'Current officeholders from Wikidata (CC0), corrected by a reviewed file that ships with Sanjaya. '
                      'Contacts are official channels only. Photos: Wikimedia Commons, credited per file.',
            'data_status': 'ok' if people else ('unavailable' if live_error else 'empty')}


def _colour(people):
    try:
        import elections
        table = elections.parties()
    except Exception:
        return
    by_name = {str(v.get('name', '')).lower(): (k, v.get('color')) for k, v in table.items()}
    for p in people:
        party = p.get('party')
        if not party:
            continue
        code = p.get('party_code') or (by_name.get(party.lower()) or (None, None))[0]
        if code:
            p['party_code'], p['party_color'] = code, elections.party_info(code)[1]


def _title(kind, key):
    if kind == 'national':
        return 'Union of India'
    return place_name(key)
