"""Associated Press election results, for readers who hold an AP Elections API key.

AP's results and race calls are licensed: the API needs a key from AP (https://developer.ap.org/ap-elections-api).
With a key saved in Sanjaya (stored on this computer only, never sent back to the page), US races are read
from AP first and Wikipedia fills any race AP has not returned. A race is called only when AP marks a winner
("X"); "R" means AP has advanced it to a runoff. AP asks clients not to poll too often, so answers are kept
for two minutes.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse

from us_elections_data import OUT, STATES

API = 'https://api.ap.org/v3/elections/{date}'
DATES = {2026: '2026-11-03', 2028: '2028-11-07'}
TTL = 120
PARTY = {'Dem': 'D', 'GOP': 'R', 'Ind': 'I', 'DFL': 'D', 'NPA': 'I', 'Una': 'I', 'NP': 'I'}
OFFICE = {'H': 'H', 'S': 'S', 'G': 'G'}


def url_for(cycle, key):
    q = {'format': 'json', 'level': 'state', 'officeID': 'H,S,G', 'raceTypeID': 'G', 'resultsType': 'l', 'apiKey': key}
    return API.format(date=DATES[cycle]) + '?' + urllib.parse.urlencode(q)


def _name(c):
    return ' '.join(x for x in (c.get('first'), c.get('last')) if x).strip() or c.get('ballotName') or 'Candidate'


def parse(payload, cycle):
    out = []
    for race in (payload or {}).get('races', []):
        office = OFFICE.get(race.get('officeID'))
        if not office:
            continue
        ru = next((u for u in race.get('reportingUnits', []) if u.get('level') in ('state', 'district', None)), None) \
            or (race.get('reportingUnits') or [None])[0]
        if not ru:
            continue
        st = ru.get('statePostal') or race.get('statePostal')
        if st not in STATES:
            continue
        seat = ''
        if office == 'H':
            seat = str(int(race['seatNum'])) if str(race.get('seatNum', '')).isdigit() and int(race['seatNum']) > 0 else '1'
        desc = ' '.join(str(race.get(k) or '') for k in ('description', 'seatName', 'raceType')).lower()
        special = 'special' in desc
        cands = ru.get('candidates', [])
        total = sum(c.get('voteCount') or 0 for c in cands)
        rows = sorted(([_name(c), PARTY.get(c.get('party'), 'O'), c.get('voteCount') or 0,
                        round(100 * (c.get('voteCount') or 0) / total, 2) if total else None, 1 if c.get('winner') == 'X' else 0,
                        c.get('winner')] for c in cands), key=lambda c: -c[2])
        if not rows:
            continue
        won = next((c for c in rows if c[4]), None)
        runoff = any(c[5] == 'R' for c in rows)
        lead, second = rows[0], (rows[1] if len(rows) > 1 else None)
        win = won or lead
        run = next((c for c in rows if c is not win), None)
        margin = round(win[3] - run[3], 2) if run and win[3] is not None and run[3] is not None else None
        counted = ru.get('eevp') if ru.get('eevp') is not None else ru.get('precinctsReportingPct')
        rid = {'H': f'H-{cycle}-{st}-{seat}', 'S': f'S-{cycle}-{st}-{seat}', 'G': f'G-{cycle}-{st}'}[office]
        if special:
            rid += '-special'
        status = ('AP called the race' if won else 'Heading to a runoff (AP)' if runoff else
                  f'Not called by AP{f", about {counted:.0f}% of the expected vote counted" if isinstance(counted, (int, float)) else ""}')
        out.append({'id': rid, 'office': office, 'cycle': cycle, 'state': st, 'seat': seat, 'special': int(special), 'stage': 'general',
                    'date': DATES.get(cycle), 'winner': win[0] if won else None, 'winner_party': win[1] if won else None,
                    'leader': lead[0], 'leader_party': lead[1] if lead[2] > 0 else None,
                    'runner': run[0] if run else None, 'runner_party': run[1] if run else None, 'winner_votes': win[2] or None,
                    'runner_votes': run[2] if run else None, 'total': total or None, 'margin_pct': margin,
                    'unopposed': int(len(rows) == 1), 'incumbent_party': None,
                    'cands': json.dumps([c[:5] for c in rows[:8]]), 'called': int(bool(won)), 'status_text': status,
                    'counted_pct': counted, 'origin': 'ap', 'source': 'https://apnews.com/projects/election-results-2026/'})
    return out


_lock = threading.Lock()
_cache = {}


def request(cycle, key, getter, force=False):
    """AP races for a cycle, at most one request per two minutes. Errors are reported, never raised."""
    if not key or cycle not in DATES:
        return {'races': [], 'enabled': bool(key), 'error': None, 'fetched': None}
    now = time.time()
    with _lock:
        hit = _cache.get(cycle)
        if hit and not force and now - hit['t'] < TTL:
            return {**hit['out'], 'enabled': True}
    try:
        payload = json.loads(getter(url_for(cycle, key)).decode('utf-8'))
        races = parse(payload, cycle)
        out = {'races': races, 'error': None if races else 'AP returned no races for this election', 'fetched': now}
        try:
            (OUT / f'ap_{cycle}.json').write_text(json.dumps({'t': now, 'races': races}), encoding='utf-8')
        except OSError:
            pass
    except Exception as exc:
        msg = str(exc)
        if '401' in msg or '403' in msg:
            msg = 'AP refused the key (check that it is active and covers this election)'
        saved = None
        try:
            saved = json.loads((OUT / f'ap_{cycle}.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        out = {'races': saved['races'] if saved else [], 'fetched': saved['t'] if saved else None,
               'error': f'{type(exc).__name__}: {msg}'[:200]}
    with _lock:
        _cache[cycle] = {'t': now, 'out': out}
    return {**out, 'enabled': True}
