"""Elections page API: results, alliances, comparisons and maps.

Sanjaya presents results; it never calls a winner. A seat counts as won only when
the source records it as declared. Projections and polls (with the Election
Commission's blackout windows) are a later phase; the blackout check already lives
here so every future poll or projection passes through it.
"""
import difflib
import json
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import elections_data as D

ROOT = Path(__file__).resolve().parent
PARTIES_FILE = ROOT / 'election_parties.json'
ALLIANCES_FILE = ROOT / 'election_alliances.json'
MUNICIPAL_FILE = ROOT / 'election_municipal.json'
BLACKOUT_FILE = ROOT / 'election_blackout.json'
MAP_MIN_MATCH = 0.85       # share of seats whose names match the map before we draw it
# The ECI / TCPD code for the same party sometimes changes between elections. Comparisons
# across years use these canonical codes; tables still show each election's own code.
CANON = {'ADS': 'ADAL', 'AAP': 'AAAP', 'AIADMK': 'ADMK', 'TRS': 'BRS', 'JKNC': 'JKN', 'RLTP': 'RaLtP', 'NPP': 'NPEP'}


def canon(code):
    return CANON.get(code, code)

_cache = {}


def _load(path):
    key = (str(path), path.stat().st_mtime if path.exists() else 0)
    if key not in _cache:
        _cache[key] = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return _cache[key]


def parties():
    p = dict(_load(PARTIES_FILE).get('parties', {}))
    for k, v in _load(MUNICIPAL_FILE).get('extra_parties', {}).items():
        p.setdefault(k, v)
    return p


def party_info(code):
    p = parties().get(code)
    if p:
        return p['name'], p['color']
    # Stable neutral colour for parties without a curated one.
    h = sum(ord(c) * (i + 7) for i, c in enumerate(code)) % 360
    return code, f'hsl({h} 22% 52%)'


def _db():
    con = sqlite3.connect(f'file:{D.DB}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def label_for(e):
    if e['kind'] == 'GE':
        return f"Lok Sabha {e['year']}"
    return f"{D.label(e['state'])} Vidhan Sabha {e['year']}"


# ---------------------------------------------------------------- blackout windows
def blackout(now=None, state=None):
    """Active Election Commission windows (Sections 126 and 126A, RP Act 1951).

    election_blackout.json lists windows the ECI has notified:
      {"state": "Uttar_Pradesh", "kind": "exit_poll", "start": "...", "end": "...", "source": "..."}
      {"state": "Uttar_Pradesh", "kind": "silence", "start": "...", "end": "...", "phase": 1, "source": "..."}
    exit_poll: no exit poll results may be shown. silence: the 48 hours before polling
    closes, when no opinion poll or projection may be shown for that area.
    Times are ISO 8601 with offset (IST is +05:30)."""
    now = now or datetime.now(timezone.utc)
    out = []
    for w in _load(BLACKOUT_FILE).get('windows', []):
        try:
            a = datetime.fromisoformat(w['start'])
            b = datetime.fromisoformat(w['end'])
        except (KeyError, ValueError):
            continue
        if a <= now <= b and (state is None or w.get('state') in (state, 'IN', '*')):
            out.append({**w, 'hides': ['exit polls'] if w.get('kind') == 'exit_poll' else ['opinion polls', 'projections']})
    return out


def hidden_kinds(state, now=None):
    """What must not be shown for a state right now: a subset of {'exit_poll', 'opinion_poll', 'projection'}."""
    kinds = set()
    for w in blackout(now, state):
        if w.get('kind') == 'exit_poll':
            kinds.add('exit_poll')
        elif w.get('kind') == 'silence':
            kinds.update({'opinion_poll', 'projection'})
    return kinds


# ---------------------------------------------------------------- catalogue
def catalog():
    st = D.status()
    out = {'pack': st, 'national': [], 'states': [], 'municipal': [], 'blackout': blackout(),
           'attribution': D.ATTRIBUTION}
    for m in _load(MUNICIPAL_FILE).get('corporations', []):
        out['municipal'].append({'id': m['id'], 'name': m['name'], 'short': m.get('short'), 'city': m['city'],
                                 'state': m['state'], 'year': int(m['polled'][:4]), 'seats': m['seats'],
                                 'status': m.get('status', '')})
    if not st['ready']:
        return out
    man = st['manifest'] or {}
    with closing(_db()) as con:
        rows = [dict(r) for r in con.execute('SELECT * FROM elections ORDER BY year DESC')]
    for e in rows:
        if e['kind'] == 'GE':
            out['national'].append({'id': e['id'], 'year': e['year'], 'seats': e['seats'], 'label': label_for(e)})
    states = {}
    for e in rows:
        if e['kind'] != 'AE':
            continue
        s = states.setdefault(e['state'], {'state': e['state'], 'label': D.label(e['state']), 'elections': []})
        s['elections'].append({'id': e['id'], 'year': e['year'], 'seats': e['seats'], 'label': label_for(e)})
    for s in states.values():
        g = (man.get('ac_states') or {}).get(s['state'])
        s['map'] = bool(g and (g.get('name_match_latest') or 0) >= MAP_MIN_MATCH)
    out['states'] = sorted(states.values(), key=lambda s: s['label'])
    return out


# ---------------------------------------------------------------- one election
def _alliances(eid):
    return _load(ALLIANCES_FILE).get(eid) or {}


def _tally(seats, extra=()):
    agg = {}
    total_valid = 0
    for s in seats:
        total_valid += s['valid'] or 0
        for code, v in json.loads(s['party_votes'] or '{}').items():
            a = agg.setdefault(code, {'seats': 0, 'votes': 0, 'contested': 0})
            a['votes'] += v
            a['contested'] += 1
        agg.setdefault(s['party'], {'seats': 0, 'votes': 0, 'contested': 0})['seats'] += 1
    for u in extra:
        agg.setdefault(u['party'], {'seats': 0, 'votes': 0, 'contested': 0})['seats'] += 1
    return agg, total_valid


def result(eid):
    if eid.startswith('MC-'):
        return municipal(eid)
    if not D.status()['ready']:
        raise LookupError('The elections data pack is not downloaded yet.')
    with closing(_db()) as con:
        e = con.execute('SELECT * FROM elections WHERE id=?', (eid,)).fetchone()
        if not e:
            raise LookupError(f'No election {eid}')
        e = dict(e)
        seats = [dict(r) for r in con.execute('SELECT * FROM seats WHERE election=? ORDER BY state, no', (eid,))]
        prev = con.execute('SELECT * FROM elections WHERE kind=? AND state=? AND year<? ORDER BY year DESC LIMIT 1',
                           (e['kind'], e['state'], e['year'])).fetchone()
        prev = dict(prev) if prev else None
        prev_seats = [dict(r) for r in con.execute('SELECT * FROM seats WHERE election=?', (prev['id'],))] if prev else []
    cfg = _alliances(eid)
    unopposed = cfg.get('unopposed', [])
    agg, valid = _tally(seats, unopposed)
    pagg_raw, pvalid = _tally(prev_seats, _alliances(prev['id']).get('unopposed', []) if prev else ())
    pagg = {}
    for code, a in pagg_raw.items():
        t = pagg.setdefault(canon(code), {'seats': 0, 'votes': 0, 'contested': 0})
        for k in t:
            t[k] += a[k]
    total = len(seats) + len(unopposed)
    electors = sum(s['electors'] or 0 for s in seats)
    polled_est = sum((s['electors'] or 0) * (s['turnout'] or 0) / 100 for s in seats)
    rows = []
    for code, a in agg.items():
        if code == 'NOTA' and not a['seats']:
            continue
        name, color = party_info(code)
        p = pagg.get(canon(code), {})
        share = 100 * a['votes'] / valid if valid else 0
        pshare = 100 * p.get('votes', 0) / pvalid if pvalid and p else None
        rows.append({'code': code, 'name': name, 'color': color, 'seats': a['seats'], 'votes': a['votes'],
                     'share': round(share, 2), 'contested': a['contested'],
                     'seat_change': (a['seats'] - p.get('seats', 0)) if prev else None,
                     'share_change': round(share - pshare, 2) if pshare is not None else None})
    rows.sort(key=lambda r: (-r['seats'], -r['votes']))
    nota = agg.get('NOTA', {}).get('votes', 0)
    alliances = []
    for name, al in (cfg.get('alliances') or {}).items():
        members = [r for r in rows if r['code'] in al['parties']]
        alliances.append({'name': name, 'color': al.get('color') or '#888', 'parties': al['parties'],
                          'seats': sum(r['seats'] for r in members), 'votes': sum(r['votes'] for r in members),
                          'share': round(sum(r['share'] for r in members), 2)})
    closest = sorted([s for s in seats if s['margin']], key=lambda s: s['margin'])[:12]
    gkey = _geo_keys(e, seats)
    out_seats = [{'state': s['state'], 'no': s['no'], 'geo': gkey.get((s['state'], s['no'])), 'name': s['name'], 'type': s['type'], 'party': s['party'],
                  'winner': s['winner'], 'votes': s['votes'], 'runner': s['runner'], 'runner_party': s['runner_party'],
                  'margin': s['margin'], 'margin_pct': s['margin_pct'], 'turnout': s['turnout'],
                  'share': round(100 * s['votes'] / s['valid'], 1) if s['valid'] else None} for s in seats]
    for u in unopposed:
        out_seats.append({'state': u['state'], 'no': u['no'], 'geo': f"{u['state']}|{u['no']}" if e['kind'] == 'GE' else str(u['no']),
                          'name': u['name'].title(), 'type': '', 'party': u['party'],
                          'winner': '', 'votes': 0, 'runner': '', 'runner_party': '', 'margin': None, 'margin_pct': None,
                          'turnout': None, 'share': None, 'unopposed': True})
    map_info = _map_info(e)
    off_map = [s for s in out_seats if not s.get('geo')]
    if map_info.get('available') and off_map and e['kind'] == 'GE':
        map_info['note'] += (f" {len(off_map)} seat{'s' if len(off_map) > 1 else ''} whose boundaries were redrawn after this map was made "
                             f"({', '.join(sorted({D.label(x['state']) for x in off_map}))}) appear only in the tables.")
    # Seats that changed hands, where the constituency existed last time.
    flips = []
    if prev:
        before = {(s['state'], s['no']): s for s in prev_seats}
        for s in seats:
            b = before.get((s['state'], s['no']))
            if b and canon(b['party']) != canon(s['party']) and D._same_place(b['name'], s['name']):
                flips.append([s['state'], s['no'], b['party'], s['party'], gkey.get((s['state'], s['no']))])
    return {
        'id': eid, 'kind': e['kind'], 'state': e['state'], 'year': e['year'], 'label': label_for(e),
        'seats_total': total, 'majority': total // 2 + 1, 'valid_votes': valid, 'nota_votes': nota,
        'turnout': round(100 * polled_est / electors, 2) if electors else None, 'electors': electors,
        'parties': rows, 'alliances': alliances, 'alliance_source': cfg.get('source', ''),
        'previous': {'id': prev['id'], 'year': prev['year'], 'label': label_for(prev)} if prev else None,
        'flips': flips, 'closest': [{'state': s['state'], 'no': s['no'], 'geo': gkey.get((s['state'], s['no'])), 'name': s['name'], 'party': s['party'],
                                     'runner_party': s['runner_party'], 'margin': s['margin'], 'margin_pct': s['margin_pct']}
                                    for s in closest],
        'seats': out_seats, 'map': map_info, 'hidden': sorted(hidden_kinds(e['state'] if e['kind'] == 'AE' else 'IN')),
        'attribution': D.ATTRIBUTION, 'unopposed': unopposed,
    }


def _geo_keys(e, seats):
    """Key of each seat's shape on the map, matching by number and falling back to name.

    Names change less than numbering: Ladakh became its own Union Territory, Dadra-Nagar
    Haveli merged with Daman-Diu, and Andhra Pradesh was renumbered after 2014."""
    out = {}
    try:
        g = geo('pc') if e['kind'] == 'GE' else geo('ac', e['state'])
    except (LookupError, ValueError):
        return out
    if e['kind'] == 'GE':
        items = {f"{i['state']}|{i['no']}": i for i in g['items']}
        names = {k: D.norm_name(i['name']) for k, i in items.items()}
        taken = set()
        pending = []
        for s in seats:
            k = f"{s['state']}|{s['no']}"
            if k in items and D._same_place(items[k]['name'], s['name']):
                out[(s['state'], s['no'])] = k
                taken.add(k)
            else:
                pending.append(s)
        for s in pending:      # renumbered or renamed: the closest unused name, if it is close enough
            n = D.norm_name(s['name'])
            best, score = None, 0.0
            for k, kn in names.items():
                if k in taken or not kn or not n:
                    continue
                r = 1.0 if kn == n else difflib.SequenceMatcher(None, n, kn).ratio()
                if r > score:
                    best, score = k, r
            if best and score >= 0.8:
                out[(s['state'], s['no'])] = best
                taken.add(best)
    else:
        nos = {i['no'] for i in g['items']}
        for s in seats:
            if s['no'] in nos:
                out[(s['state'], s['no'])] = str(s['no'])
    return out


def _map_info(e):
    if e['kind'] == 'GE':
        return {'layer': 'pc', 'available': (D.GEO / 'pc.json').exists(),
                'note': 'Lok Sabha constituencies (2008 delimitation). Survey of India boundary.'}
    man = (D.manifest() or {}).get('ac_states', {}).get(e['state'])
    path = D.GEO / f"ac_{e['state']}.json"
    if not man or not path.exists():
        return {'layer': 'ac', 'state': e['state'], 'available': False, 'note': 'No constituency map for this state.'}
    # Check this election (not just the latest) against the map's names.
    g = geo('ac', e['state'])
    names = {i['no']: i['name'] for i in g['items']}
    with closing(_db()) as con:
        rows = con.execute('SELECT no, name FROM seats WHERE election=?', (e['id'],)).fetchall()
    ok = sum(1 for r in rows if names.get(r['no']) and D._same_place(r['name'], names[r['no']]))
    match = ok / max(1, len(rows))
    missing = sorted(r['no'] for r in rows if r['no'] not in names)
    if match < MAP_MIN_MATCH:
        return {'layer': 'ac', 'state': e['state'], 'available': False, 'match': round(match, 3),
                'note': 'The constituency map in the data pack predates the boundaries used in this election '
                        '(re-delimitation), so seats cannot be placed on it. The chart and tables are complete.'}
    note = 'Assembly constituencies. Survey of India boundary.'
    if missing:
        note += f' {len(missing)} constituencies are missing from the map source and appear only in the tables.'
    return {'layer': 'ac', 'state': e['state'], 'available': True, 'match': round(match, 3), 'missing': missing, 'note': note}


def geo(layer, state=None):
    if layer == 'pc':
        path = D.GEO / 'pc.json'
    else:
        st = D.norm_state(state or '')
        if not st or '/' in st or '\\' in st or '..' in st:
            raise ValueError('Unknown state')
        path = D.GEO / f'ac_{st}.json'
    if not path.exists():
        raise LookupError('No map for that layer')
    key = ('geo', str(path), path.stat().st_mtime)
    if key not in _cache:
        _cache[key] = json.loads(path.read_text(encoding='utf-8'))
    return _cache[key]


# ---------------------------------------------------------------- municipal
def municipal(mid):
    m = next((c for c in _load(MUNICIPAL_FILE).get('corporations', []) if c['id'] == mid), None)
    if not m:
        raise LookupError(f'No municipal corporation {mid}')
    rows = []
    for code, n in m['parties']:
        name, color = party_info(code)
        rows.append({'code': code, 'name': name, 'color': color, 'seats': n, 'votes': None, 'share': None,
                     'contested': None, 'seat_change': None, 'share_change': None})
    alliances = []
    for name, al in (m.get('alliances') or {}).items():
        alliances.append({'name': name, 'color': al.get('color', '#888'), 'parties': al['parties'],
                          'seats': sum(n for c, n in m['parties'] if c in al['parties']), 'votes': None, 'share': None})
    return {'id': mid, 'kind': 'MC', 'state': m['state'], 'year': int(m['polled'][:4]),
            'label': f"{m['name']} {m['polled'][:4]}", 'city': m['city'], 'short': m.get('short'),
            'seats_total': m['seats'], 'majority': m['majority'], 'turnout': m.get('turnout'),
            'polled': m['polled'], 'counted': m.get('counted'), 'authority': m.get('authority'),
            'parties': rows, 'alliances': alliances, 'previous_note': (m.get('previous') or {}).get('note'),
            'previous_year': (m.get('previous') or {}).get('year'), 'note': m.get('note', ''), 'status': m.get('status', ''),
            'sources': m.get('sources', []), 'seats': [], 'closest': [], 'flips': [],
            'map': {'available': False, 'note': 'Ward-level results and ward maps are not available for this corporation yet.'},
            'hidden': [], 'attribution': f"Seat totals: {m.get('authority', 'State Election Commission')}, as reported."}
