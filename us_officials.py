"""US office-holders for the Elections page.

  National: President and Vice President (unitedstates/congress-legislators executive file, CC0),
            then the Cabinet (Wikipedia, "Cabinet of the United States").
  State:    Governor (Wikipedia, "List of current United States governors"), the state's two senators and its
            House delegation (unitedstates/congress-legislators, CC0).
Contacts are official channels only: office websites, contact forms and Capitol office phone numbers.
Member photos: the public-domain congressional portraits in unitedstates/images; others from Wikipedia.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path

import officials as O
import wikitables as W
from us_elections_data import STATES

LEG = 'https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/legislators-current.json'
EXEC = 'https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/executive.json'
PHOTO = 'https://theunitedstates.io/images/congress/225x275/{}.jpg'
CABINET = 'Cabinet of the United States'
GOVERNORS = 'List of current United States governors'
PARTY = {'Democrat': 'Democratic', 'Republican': 'Republican', 'Independent': 'Independent'}
COLOR = {'Democratic': '#3A78D4', 'Republican': '#D5483F', 'Independent': '#9575CD'}
CAB_FIRST = ['Secretary of State', 'Secretary of the Treasury', 'Secretary of Defense', 'Secretary of War', 'Attorney General']


def parse_scope(scope):
    scope = str(scope or 'us')
    if scope == 'us':
        return 'national', 'us', None
    m = re.fullmatch(r'us-state:([A-Z]{2})', scope)
    if not m or m.group(1) not in STATES:
        raise ValueError('Unknown scope. Use us or us-state:<two-letter state>.')
    return 'state', scope, m.group(1)


def _json(url, getter, cache_dir, name, ttl=24 * 3600, force=False):
    p = Path(cache_dir) / name
    try:
        saved = json.loads(p.read_text(encoding='utf-8'))
        if not force and time.time() - saved['t'] < ttl:
            return saved['data']
    except (OSError, ValueError, KeyError):
        saved = None
    try:
        data = json.loads(getter(url).decode('utf-8'))
    except Exception:
        if saved:
            return saved['data']
        raise
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'t': time.time(), 'data': data}), encoding='utf-8')
    except OSError:
        pass
    return data


def _party(p):
    name = PARTY.get(p, p)
    return {'party': name, 'party_color': COLOR.get(name, '#8A96A3')}


def _contacts(term):
    out = []
    if term.get('url'):
        out.append({'label': 'Official website', 'url': term['url'].replace('http://', 'https://')})
    if term.get('contact_form'):
        out.append({'label': 'Contact form', 'url': term['contact_form'].replace('http://', 'https://')})
    if term.get('phone'):
        out.append({'label': 'Capitol office ' + term['phone'], 'url': 'tel:+1-' + term['phone']})
    return out


def _name(n):
    if isinstance(n, dict):
        return n.get('official_full') or ' '.join(x for x in (n.get('first'), n.get('middle'), n.get('last'), n.get('suffix')) if x)
    return str(n)


def _run_start(terms):
    """Start of the current unbroken run in the same office (a second, non-consecutive presidency starts again)."""
    t = terms[-1]
    start = t['start']
    for x in reversed(terms[:-1]):
        if x['type'] == t['type'] and x.get('end') == start and x.get('state') == t.get('state'):
            start = x['start']
        else:
            break
    return start


def member(p, group, order):
    t = p['terms'][-1]
    pos = (f"U.S. Senator for {STATES[t['state']]}" if t['type'] == 'sen' else
           f"U.S. Representative, {STATES[t['state']]} {'at-large' if t.get('district') in (0, None) else 'district ' + str(t['district'])}")
    first = _run_start(p['terms'])
    return {'name': _name(p['name']), 'position': pos, 'group': group, 'order': order, 'since': first, **_party(t.get('party')),
            'photo': {'src': PHOTO.format(p['id']['bioguide']), 'credit': 'https://github.com/unitedstates/images',
                      'credit_label': 'Photo: US Congress (public domain)'},
            'wikipedia': 'https://en.wikipedia.org/wiki/' + p['id']['wikipedia'].replace(' ', '_') if p['id'].get('wikipedia') else None,
            'contacts': _contacts(t), 'portfolios': [], 'source': 'unitedstates/congress-legislators'}


def build(scope, getter, cache_dir, report=None, force=False):
    kind, scope_id, st = parse_scope(scope)
    steps, people, errors = [], [], []

    def rep(label, state, count=None, detail=None):
        s = next((x for x in steps if x['label'] == label), None)
        if not s:
            s = {'label': label}; steps.append(s)
        s.update(state=state, count=count, detail=detail)
        if report:
            report(steps, people)

    today = dt.date.today().isoformat()
    if kind == 'national':
        rep('President and Vice President (congress-legislators)', 'running')
        try:
            ex = _json(EXEC, getter, cache_dir, 'us_executive.json', force=force)
            for p in ex:
                t = p['terms'][-1]
                if t['type'] in ('prez', 'viceprez') and t['start'] <= today < t['end']:
                    people.append({'name': _name(p['name']), 'position': 'President of the United States' if t['type'] == 'prez' else 'Vice President of the United States',
                                   'group': 'Head of state and government' if t['type'] == 'prez' else 'Vice President', 'order': 0,
                                   'since': _run_start(p['terms']),
                                   **_party(t.get('party')), 'photo': None, 'wiki_title': (p.get('id') or {}).get('wikipedia') or _name(p['name']),
                                   'contacts': [{'label': 'White House', 'url': 'https://www.whitehouse.gov/'}], 'portfolios': [],
                                   'source': 'unitedstates/congress-legislators'})
            rep('President and Vice President (congress-legislators)', 'done', len(people))
        except Exception as exc:
            rep('President and Vice President (congress-legislators)', 'failed', detail=type(exc).__name__); errors.append('congress-legislators')
        rep('Cabinet (Wikipedia)', 'running')
        try:
            html = O.wp_page(CABINET, getter, cache_dir, force)
            cab = []
            for t in W.tables(html):
                for r in W.records(t):
                    office = (r['portfolios'] or [''])[0]
                    if not r['current'] or not office or re.search(r'^(President|Vice President)\b', office):
                        continue
                    if any(O.same_person(r['name'], x['name']) for x in cab):
                        continue
                    level = 'Cabinet-level officials' if re.search(r'cabinet[- ]level', (r['heading'] or '') + ' ' + (t.get('section') or ''), re.I) else 'Cabinet'
                    order = next((i for i, w in enumerate(CAB_FIRST) if office.startswith(w)), 10 + len(cab))
                    e = O.person(r, office, level, 'Wikipedia: ' + CABINET, order, [])
                    e['party'] = None
                    cab.append(e)
            people += cab
            rep('Cabinet (Wikipedia)', 'done' if cab else 'empty', len(cab))
        except Exception as exc:
            rep('Cabinet (Wikipedia)', 'failed', detail=type(exc).__name__); errors.append('Wikipedia')
    else:
        rep('Governor (Wikipedia list)', 'running')
        try:
            html = O.wp_page(GOVERNORS, getter, cache_dir, force)
            gov = []
            for t in W.tables(html):
                for r in W.records(t):
                    if O.same_place(r.get('state'), STATES[st]) and r['current']:
                        e = O.person(r, f'Governor of {STATES[st]}', 'Governor', 'Wikipedia: ' + GOVERNORS, 0, [])
                        e.update(_party({'Democratic': 'Democrat'}.get(r.get('party') or '', r.get('party') or '')))
                        gov.append(e)
            people += gov[:1]
            rep('Governor (Wikipedia list)', 'done' if gov else 'empty', len(gov[:1]))
        except Exception as exc:
            rep('Governor (Wikipedia list)', 'failed', detail=type(exc).__name__); errors.append('Wikipedia')
        rep('Senators and representatives (congress-legislators)', 'running')
        try:
            leg = _json(LEG, getter, cache_dir, 'us_legislators.json', force=force)
            mine = [p for p in leg if p['terms'][-1].get('state') == st]
            sen = sorted([p for p in mine if p['terms'][-1]['type'] == 'sen'], key=lambda p: p['terms'][-1].get('state_rank') != 'senior')
            rep_ = sorted([p for p in mine if p['terms'][-1]['type'] == 'rep'], key=lambda p: p['terms'][-1].get('district') or 0)
            people += [member(p, 'U.S. Senators', i) for i, p in enumerate(sen)]
            people += [member(p, 'U.S. Representatives', i) for i, p in enumerate(rep_)]
            rep('Senators and representatives (congress-legislators)', 'done', len(sen) + len(rep_))
        except Exception as exc:
            rep('Senators and representatives (congress-legislators)', 'failed', detail=type(exc).__name__); errors.append('congress-legislators')
    missing = [p['wiki_title'] for p in people if not p.get('photo') and p.get('wiki_title')]
    if missing:
        rep('Photos (Wikipedia)', 'running')
        try:
            imgs = O.wp_images(missing, getter)
            for p in people:
                if not p.get('photo') and p.get('wiki_title') in imgs:
                    p['photo'] = imgs[p['wiki_title']]
            rep('Photos (Wikipedia)', 'done', sum(1 for t in missing if t in imgs))
        except Exception as exc:
            rep('Photos (Wikipedia)', 'failed', detail=type(exc).__name__)
    groups = ['Head of state and government', 'Vice President', 'Cabinet', 'Cabinet-level officials', 'Governor', 'U.S. Senators', 'U.S. Representatives']
    people.sort(key=lambda p: (groups.index(p['group']) if p['group'] in groups else 99, p.get('order', 50)))
    for p in people:
        p.pop('wiki_title', None); p.pop('party_link', None)
        p['apolitical'] = False
    return {'scope': scope_id, 'kind': kind, 'title': 'United States' if kind == 'national' else STATES[st], 'people': people,
            'steps': steps, 'note': None, 'portal': {'label': 'USA.gov: elected officials', 'url': 'https://www.usa.gov/elected-officials'},
            'as_of': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'partial_sources': errors,
            'live_error': 'The sources could not be reached.' if len(errors) >= 2 or (errors and not people) else None,
            'data_status': 'ok' if people else 'unavailable'}


def request(scope, getter, cache_dir, force=False):
    _, scope_id, _ = parse_scope(scope)
    return O.request(scope_id, getter, cache_dir, force, builder=build)
