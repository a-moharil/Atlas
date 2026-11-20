"""US elections for the Elections page: House, Senate, governors and president.

Results only: who won each race as recorded (FiveThirtyEight through 2024, a reviewed file for off-year
governor races; for 2026, each state's own count from its results site and Wikipedia's results tables).
Sanjaya never calls a race: a race is decided only when Wikipedia lists it as decided and the state's count
has the same party ahead.
"""
from __future__ import annotations

import json
import sqlite3

import us_elections_data as UD
import us_coverage
import us_live
import us_official

LIVE = {'H': [2026], 'S': [2026], 'G': [2026]}
OFFICES = {'H': 'House of Representatives', 'S': 'Senate', 'G': 'Governors', 'P': 'President'}
PARTIES = {'D': ('Democratic', '#3A78D4'), 'R': ('Republican', '#D5483F'), 'I': ('Independent', '#9575CD'),
           'O': ('Other', '#8A96A3'), 'U': ('Not yet called', '#4B5560')}
CAUCUS_D = {'Bernie Sanders', 'Angus King', 'Joe Lieberman', 'Angus S. King Jr.'}
ORDER = ['D', 'I', 'O', 'U', 'R']          # left to right in the chamber chart


def _con():
    con = sqlite3.connect(f'file:{UD.DB}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def ready():
    return UD.status()['ready']


def _rows(office, cycles=None, upto=None):
    con = _con()
    q, a = 'SELECT * FROM races WHERE office=?', [office]
    if cycles:
        q += f' AND cycle IN ({",".join("?" * len(cycles))})'; a += list(cycles)
    if upto is not None:
        q += ' AND cycle <= ?'; a.append(upto)
    rows = [dict(r) for r in con.execute(q, a)]
    con.close()
    return rows


def catalog():
    st = UD.status()
    out = {'pack': st, 'offices': []}
    if not st['ready']:
        return out
    con = _con()
    for o in 'HSGP':
        cyc = [r[0] for r in con.execute('SELECT cycle, COUNT(*) n FROM races WHERE office=? AND special=0 GROUP BY cycle', (o,))
               if r[0] % 2 == 0 and (o != 'H' or r[1] >= 400) and (o != 'S' or r[1] >= 25) and (o != 'G' or r[1] >= 9) and (o != 'P' or r[1] >= 50)]
        cyc = sorted(set(cyc) | set(LIVE.get(o, [])), reverse=True)
        if o in 'SG':
            cyc = [c for c in cyc if c >= 2000]
        out['offices'].append({'office': o, 'label': OFFICES[o], 'cycles': cyc, 'live': LIVE.get(o, [])})
    con.close()
    return out


def live_races(office, cycle, getter, force=False):
    hist = _rows('S', upto=cycle - 1) if office == 'S' else []
    return us_live.request(office, cycle, getter, history=[h for h in hist if h['cycle'] >= cycle - 8], force=force)


def _cand(r):
    try:
        return json.loads(r.get('cands') or '[]')
    except ValueError:
        return []


def _seat_of(r):
    return {'state': r['state'], 'seat': r['seat'], 'winner': r['winner'], 'party': r['winner_party'] if r.get('called', 1) and r['winner_party'] else 'U',
            'leader_party': r.get('leader_party') or r['winner_party'], 'leader': r.get('leader') or r['winner'],
            'counted': r.get('counted_pct'), 'runner': r.get('runner'), 'runner_party': r.get('runner_party'),
            'margin': r.get('margin_pct'), 'called': bool(r.get('called', 1) and r['winner_party']), 'special': bool(r.get('special')),
            'unopposed': bool(r.get('unopposed')), 'cycle': r['cycle'], 'cands': _cand(r), 'origin': r.get('origin'),
            'status': r.get('status_text'), 'source': r.get('source'), 'counted_basis': r.get('counted_basis'),
            'wiki_status': r.get('wiki_status'), 'certified': bool(r.get('certified')), 'coverage': r.get('coverage'),
            'coverage_source': r.get('coverage_source'), 'coverage_note': r.get('coverage_note')}


def _latest(rows):
    """For each seat, the most recent race (a special election replaces the regular one it followed)."""
    best = {}
    for r in sorted(rows, key=lambda r: (r['cycle'], r.get('date') or '', r['special'])):
        best[(r['state'], r['seat'])] = r
    return best


def result(office, cycle, getter=None, force=False, state_getter=None, force_states=False, news_db=None, model_cache=None,
           search_coverage=False):
    if office not in OFFICES:
        raise ValueError('Unknown office')
    cycle = int(cycle)
    live = None
    rows = _rows(office, [cycle])
    if cycle in LIVE.get(office, []) and getter is not None:
        live = live_races(office, cycle, getter, force)
        st = us_official.request(cycle, state_getter, force_states) if state_getter else {'races': [], 'states': {}, 'enabled': False}
        st_races = [dict(r) for r in st['races'] if r['office'] == office]
        if office == 'S':
            hist = [h for h in _rows('S', upto=cycle - 1) if h['cycle'] >= cycle - 8]
            us_live.assign_senate_classes(st_races, hist)
        merged = us_official.merge(live['races'], st_races)
        # Third source: numbers reported in Sanjaya's own news coverage, for races no state count covers. On request only.
        missing = [r for r in merged if 'state' not in str(r.get('origin') or '')]
        cov = us_coverage.request(cycle, office, missing, news_db, model_cache, force=search_coverage) if news_db else \
            {'races': {}, 'pending': False, 't': None}
        merged = us_coverage.apply(merged, cov.get('races') or {})
        have = {r['id'] for r in rows}
        rows += [r for r in merged if r['id'] not in have]
        live = {**live, 'wiki_pending': live.get('pending', False),
                'pending': live.get('pending') or st.get('pending', False) or cov.get('pending', False),
                'coverage': {'pending': cov.get('pending', False), 'step': cov.get('step', ''), 'fetched': cov.get('t'),
                             'error': cov.get('error'), 'method': cov.get('method'), 'searched': cov.get('searched', 0),
                             'missing': len(missing), 'enabled': bool(news_db),
                             'races': sum(1 for r in merged if 'coverage' in str(r.get('origin') or '') and r['office'] == office)},
                'states': {'enabled': st.get('enabled', False), 'pending': st.get('pending', False), 'step': st.get('step', ''),
                           'fetched': st.get('fetched'), 'list': st.get('states', {}),
                           'races': len(st_races), 'read': sum(1 for v in st.get('states', {}).values() if v.get('status') in ('read', 'partial')),
                           'certified': sum(1 for v in st.get('states', {}).values() if v.get('certified'))},
                'wikipedia_races': len(live['races'])}
    f = {'H': house, 'S': senate, 'G': governors, 'P': president}[office]
    out = f(cycle, rows)
    if live and out.get('missing'):
        # Races the live source has not listed yet still occupy seats: show them as not yet called.
        u = next((p for p in out['parties'] if p['code'] == 'U'), None)
        if not u:
            u = {'code': 'U', 'seats': 0}
            out['parties'].insert(len([p for p in out['parties'] if ORDER.index(p['code']) < ORDER.index('U')]), u)
        u['seats'] += out['missing']
        out['uncalled'] += out['missing']
        out['notes'] = [f"{out['missing']} race{'s' if out['missing'] != 1 else ''} not found on Wikipedia or the state results sites yet."] + out.get('notes', [])
    # Net change against the previous election of the same kind, so a new year visibly differs from the last.
    step = 4 if office == 'P' else 2
    prev_rows = _rows(office, [cycle - step])
    if prev_rows:
        try:
            prev = f(cycle - step, prev_rows)
            before = {p['code']: p['seats'] for p in prev['parties'] if p['code'] != 'U'}
            now = {p['code']: p['seats'] for p in out['parties'] if p['code'] != 'U'}
            out['change'] = {k: now.get(k, 0) - before.get(k, 0) for k in set(before) | set(now) if now.get(k, 0) != before.get(k, 0)}
            out['previous'] = {'cycle': cycle - step, 'parties': before}
            if out.get('uncalled') and office != 'P':
                # While races are still uncalled, "seats now minus seats last time" counts every uncalled seat as a loss.
                # Count only seats that were called for a different party than last time.
                net = {}
                for fl in out.get('flips', []):
                    if fl.get('from') and fl.get('party') and fl['from'] != fl['party']:
                        net[fl['party']] = net.get(fl['party'], 0) + 1
                        net[fl['from']] = net.get(fl['from'], 0) - 1
                out['change'] = {k: v for k, v in net.items() if v}
                out['change_basis'] = 'called'
        except Exception:
            pass
    # Lean of races not yet called: who is ahead in the count, never a call.
    lean = {}
    for st in out.get('seats', []):
        if not st['called'] and st.get('up', True):
            k = st.get('leader_party') or '?'
            lean[k] = lean.get(k, 0) + 1
    if out.get('missing') and live:
        lean['?'] = lean.get('?', 0) + out['missing']
    out['lean'] = lean
    out.update(office=office, cycle=cycle, label=f'{OFFICES[office]} {cycle}', attribution=UD.ATTRIBUTION,
               live={k: v for k, v in live.items() if k != 'races'} if live else None)
    for p in out['parties']:
        p['name'], p['color'] = PARTIES[p['code']]
    return out


def _parties(seats, key='party'):
    counts = {}
    for s in seats:
        counts[s[key]] = counts.get(s[key], 0) + 1
    return [{'code': c, 'seats': counts[c]} for c in ORDER if counts.get(c)]


def _closest(seats, n=12):
    return sorted([s for s in seats if s['called'] and s['margin'] is not None and not s['unopposed']], key=lambda s: s['margin'])[:n]


def house(cycle, rows):
    regular = [r for r in rows if not r['special']]
    by = _latest(regular)
    seats = [_seat_of(r) for r in by.values()]
    seats.sort(key=lambda s: (s['state'], int(s['seat']) if str(s['seat']).isdigit() else 0))
    prev = _latest([r for r in _rows('H', [cycle - 2]) if not r['special']])
    flips = []
    same_era = UD.era_of(cycle) == UD.era_of(cycle - 2)
    for s in seats:
        p = prev.get((s['state'], s['seat']))
        s['previous'] = p['winner_party'] if p else None
        if same_era and p and s['called'] and p['winner_party'] != s['party']:
            flips.append({**s, 'from': p['winner_party']})
    votes = {}
    for r in regular:
        for c in _cand(r):
            if c[2]:
                votes[c[1]] = votes.get(c[1], 0) + c[2]
    tv = sum(votes.values())
    counted = sum(1 for r in regular if any(c[2] for c in _cand(r)))
    parties = _parties(seats)
    for p in parties:
        p['share'] = round(100 * votes.get(p['code'], 0) / tv, 1) if tv else None
    era = UD.era_of(cycle)
    return {'seats_total': 435, 'majority': 218, 'parties': parties, 'seats': seats, 'flips': flips, 'closest': _closest(seats),
            'uncalled': sum(1 for s in seats if not s['called']), 'missing': max(0, 435 - len(seats)),
            'popular_vote': {k: round(100 * v / tv, 1) for k, v in votes.items()} if tv else None, 'popular_vote_races': counted,
            'map': {'kind': 'tiles', 'era': str(era), 'values': {f"{s['state']}-{s['seat']}": _mapval(s) for s in seats}},
            'notes': ['Flips compare the same district number with the previous election. Where a state redrew its map in between, '
                      'the same number can cover different places.'] if same_era else
                     ['Districts were redrawn after the census, so seats are not compared with the previous election.']}


def _mapval(s):
    return {'p': s['party'], 'l': s['leader_party'], 'm': s['margin'], 'w': s['winner'] or s.get('leader'), 'r': s['runner'], 'up': s.get('up', True),
            'c': s['called'], 'sp': s['special'], 'src': s.get('origin'), 'n': s.get('counted')}


def senate(cycle, rows):
    hist = _rows('S', upto=cycle - 1)
    hist = [h for h in hist if h['cycle'] >= cycle - 12]
    by = _latest(hist + rows)
    seats = []
    for r in by.values():
        s = _seat_of(r)
        s['up'] = r['cycle'] == cycle
        if not s['up']:
            s['called'] = True; s['party'] = r['winner_party']
        s['caucus'] = 'D' if s['party'] == 'I' and s['winner'] in CAUCUS_D else None
        seats.append(s)
    seats.sort(key=lambda s: (s['state'], s['seat']))
    parties = _parties(seats)
    for p in parties:
        p['up'] = sum(1 for s in seats if s['up'] and s['party'] == p['code'])
    flips = []
    prevs = _latest(hist)
    for s in seats:
        if s['up'] and s['called']:
            p = prevs.get((s['state'], s['seat']))
            if p and p['winner_party'] != s['party']:
                flips.append({**s, 'from': p['winner_party']})
    by_state = {}
    for s in seats:
        by_state.setdefault(s['state'], []).append(s)
    values = {}
    for st, ss in by_state.items():
        up = [s for s in ss if s['up']]
        main = up[0] if up else ss[0]
        v = _mapval(main)
        v['up'] = bool(up); v['both'] = [x['party'] for x in ss]
        values[st] = v
    caucus = sum(1 for s in seats if s.get('caucus') == 'D')
    return {'seats_total': 100, 'majority': 51, 'parties': parties, 'seats': seats, 'flips': flips,
            'closest': _closest([s for s in seats if s['up']]), 'uncalled': sum(1 for s in seats if not s['called']),
            'up': sum(1 for s in seats if s['up']), 'missing': max(0, 100 - len(seats)),
            'map': {'kind': 'states', 'values': values},
            'notes': ([f'{caucus} independent senator{"s" if caucus > 1 else ""} caucus with the Democrats.'] if caucus else []) +
                     ['Seats not up this year are shown faded. The vice president breaks a 50–50 tie.']}


def governors(cycle, rows):
    hist = _rows('G', upto=cycle - 1)
    by = {}
    for r in sorted(hist + rows, key=lambda r: (r['cycle'], r.get('date') or '', r['special'])):
        by[r['state']] = r
    seats = []
    for r in by.values():
        s = _seat_of(r)
        s['up'] = r['cycle'] == cycle or (r['cycle'] == cycle - 1)   # odd-year races just before count as this round
        if r['cycle'] != cycle:
            s['called'] = True; s['party'] = r['winner_party']
        seats.append(s)
    seats.sort(key=lambda s: s['state'])
    seats = [s for s in seats if s['state'] != 'DC']
    flips, prevs = [], {}
    for r in sorted(hist, key=lambda r: (r['cycle'], r.get('date') or '')):
        if r['cycle'] < cycle - 1:
            prevs[r['state']] = r
    for s in seats:
        p = prevs.get(s['state'])
        if s['up'] and s['called'] and p and p['winner_party'] != s['party']:
            flips.append({**s, 'from': p['winner_party']})
    parties = _parties(seats)
    for p in parties:
        p['up'] = sum(1 for s in seats if s['up'] and s['party'] == p['code'])
    return {'seats_total': len(seats), 'majority': len(seats) // 2 + 1, 'parties': parties, 'seats': seats, 'flips': flips,
            'closest': _closest([s for s in seats if s['up']]), 'uncalled': sum(1 for s in seats if not s['called']),
            'up': sum(1 for s in seats if s['up']), 'missing': max(0, 50 - len(seats)),
            'map': {'kind': 'states', 'values': {s['state']: _mapval(s) for s in seats}},
            'notes': ['Governorships after this election: states not voting keep the governor elected earlier. '
                      'Changes between elections (resignations, deaths) are not shown here; see In office now.']}


def president(cycle, rows):
    con = _con()
    allh = [dict(r) for r in con.execute("SELECT office, cycle, state, seat FROM races WHERE office='H'")]
    con.close()
    ev = UD.electoral_votes(UD.apportionment(allh), cycle)
    split = {r['state'] for r in rows if r['seat']}
    states, totals, votes = [], {}, {}
    for r in rows:
        st = r['state']
        if r['seat']:
            n = 1
        elif st in split:
            n = 2
        else:
            n = ev.get(st, 0)
        s = _seat_of(r); s['ev'] = n
        states.append(s)
        totals[s['party']] = totals.get(s['party'], 0) + n
        if not r['seat']:
            for c in _cand(r):
                if c[2]:
                    votes[c[1]] = votes.get(c[1], 0) + c[2]
    tv = sum(votes.values())
    parties = [{'code': c, 'seats': totals[c], 'share': round(100 * votes.get(c, 0) / tv, 1) if tv else None} for c in ORDER if totals.get(c)]
    names = {}
    for s in states:
        if not s['seat']:
            names.setdefault(s['party'], s['winner'])
    for p in parties:
        p['candidate'] = names.get(p['code'])
    prev = {(r['state'], r['seat']): r for r in _rows('P', [cycle - 4])}
    flips = [{**s, 'from': prev[(s['state'], s['seat'])]['winner_party']} for s in states
             if (s['state'], s['seat']) in prev and prev[(s['state'], s['seat'])]['winner_party'] != s['party']]
    statewide = [s for s in states if not s['seat']]
    values = {s['state']: _mapval(s) for s in statewide}
    for s in states:
        if s['seat']:
            values.setdefault(s['state'], {}).setdefault('districts', []).append({'d': s['seat'], 'p': s['party']})
    return {'seats_total': sum(ev.values()), 'majority': sum(ev.values()) // 2 + 1, 'parties': parties, 'seats': states,
            'flips': flips, 'closest': _closest(statewide), 'uncalled': 0, 'missing': 0,
            'popular_vote': {k: round(100 * v / tv, 1) for k, v in votes.items()} if tv else None, 'popular_vote_races': counted,
            'map': {'kind': 'states', 'values': values},
            'notes': ['Electoral votes as pledged by each state\'s result; Maine and Nebraska also award one vote per congressional district. '
                      'Faithless electors (2016: seven) are not reflected.']}


def geo():
    return json.loads((UD.OUT / 'geo.json').read_text(encoding='utf-8'))
