"""2025–26 US results read from Wikipedia at view time, until states certify and an archive covers them.

Reads the results tables of "<year> United States House of Representatives elections", "... Senate elections"
and "... gubernatorial elections". Wikipedia editors update those tables as races are called; a race is
treated as decided only when its status says so (hold, gain, elected, re-elected, defeated). Races still being
counted, or heading to a runoff, are kept and marked uncalled. Sanjaya never calls a race itself.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

import officials as O
import wikitables as W
from us_elections_data import STATES, OUT

TTL = 6 * 3600
PAGES = {'H': '{y} United States House of Representatives elections', 'S': '{y} United States Senate elections',
         'G': '{y} United States gubernatorial elections'}
NAMES = sorted(STATES.items(), key=lambda kv: -len(kv[1]))
PARTY = [(r'democratic|dfl|democratic–farmer–labor|democratic-npl', 'D'), (r'republican', 'R'), (r'independent', 'I')]
CALLED = re.compile(r'\b(hold|gain|elected|re-elected|reelected|defeated|won|lost re-?election|lost renomination|retired)\b', re.I)
OPEN = re.compile(r'\b(advanced|renominated|to be elected|undecided|too close|tbd|pending|runoff|running for|seeking|not yet)\b', re.I)
CAND = re.compile(r'^(?:[✓✔▌]\s*|Y\s+)*(?P<name>[^()]+?)\s*\((?P<party>[^)]{1,60})\)\s*(?P<pct>\d{1,3}(?:\.\d+)?)?\s*%?')
ROMAN = {'1': 'I', '2': 'II', '3': 'III', 'I': 'I', 'II': 'II', 'III': 'III'}


def party_code(text):
    t = (text or '').lower()
    for pat, code in PARTY:
        if re.search(pat, t):
            return code
    return 'O'


def place(text):
    """'California 40' -> ('CA', '40'); 'Alaska at-large' -> ('AK', '1'); 'Ohio (Class 3)' -> ('OH', 'III')."""
    t = re.sub(r'\[\w+\]', '', text or '').strip()
    for st, name in NAMES:
        if t.lower().startswith(name.lower()):
            rest = t[len(name):].strip()
            m = re.search(r'class\s*(I{1,3}|[123])\b', rest, re.I)
            if m:
                return st, ROMAN[m.group(1).upper()]
            m = re.match(r'(\d{1,2})\b', rest)
            if m:
                return st, str(int(m.group(1)))
            if re.match(r'at[- ]large', rest, re.I):
                return st, '1'
            return st, ''
    return None, None


def _col(header, *words, skip=()):
    for w in words:
        for j, h in enumerate(header):
            hl = h.lower()
            if w in hl and j not in skip:
                return j
    return None


def parse_page(office, cycle, html):
    out = []
    for t in W.tables(html):
        hdr = t['header']
        cj = _col(hdr, 'candidates')
        if cj is None:
            continue
        lj = _col(hdr, 'location', 'district', 'state')
        sj = _col(hdr, 'status', 'results', 'result')
        mj = _col(hdr, 'member', 'senator', 'governor', 'incumbent', skip={sj, lj})
        pj = _col(hdr, 'party', skip={cj})
        if lj is None:
            continue
        special_table = 'special' in (t['heading'] or '').lower()
        for row in t['rows']:
            cell = lambda j: row[j] if j is not None and j < len(row) else None
            loc = cell(lj)
            if not loc:
                continue
            st, seat = place(loc['text'])
            if not st:
                continue
            if office == 'H' and not seat:
                continue
            status = (cell(sj) or {}).get('text', '') if sj is not None else ''
            cands = []
            for line in (cell(cj) or {}).get('lines', []):
                m = CAND.match(line.strip())
                if m:
                    pct = float(m.group('pct')) if m.group('pct') else None
                    cands.append([m.group('name').strip(' ;,'), party_code(m.group('party')), None, pct, 0])
            if not cands:
                continue
            called = bool(CALLED.search(status)) and not OPEN.search(status)
            with_pct = [c for c in cands if c[3] is not None]
            win = None
            if with_pct:
                win = max(with_pct, key=lambda c: c[3])
            party_known = None
            if called:
                m = re.search(r'(democratic|republican|independent)\s+(hold|gain)', status, re.I)
                if m:
                    party_known = party_code(m.group(1))
                    if not with_pct:
                        hits = [c for c in cands if c[1] == party_known]
                        win = hits[0] if len(hits) == 1 else None
            if win:
                win[4] = 1 if called else 0
            ranked = sorted(cands, key=lambda c: -(c[3] or 0))
            run = next((c for c in ranked if c is not win), None)
            special = special_table or bool(re.search(r'special', loc['text'] + ' ' + status, re.I))
            if office == 'S' and not seat:
                seat = ''          # filled in later from the state's classes
            inc_party = party_code((cell(pj) or {}).get('text', '')) if pj is not None and cell(pj) and cell(pj)['text'] else None
            margin = round(win[3] - run[3], 2) if win and run and win[3] is not None and run[3] is not None else None
            wparty = win[1] if win else party_known     # same-party contests: the party is known before the name
            rid = {'H': f'H-{cycle}-{st}-{seat}', 'S': f'S-{cycle}-{st}-{seat}', 'G': f'G-{cycle}-{st}'}[office]
            if special:
                rid += '-special'
            out.append({'id': rid, 'office': office, 'cycle': cycle, 'state': st, 'seat': seat, 'special': int(special),
                        'stage': 'general', 'date': None, 'winner': win[0] if win else None, 'winner_party': wparty,
                        'runner': run[0] if run else None, 'runner_party': run[1] if run else None, 'winner_votes': None,
                        'runner_votes': None, 'total': None, 'margin_pct': margin, 'unopposed': int(len(cands) == 1 and called),
                        'incumbent_party': inc_party, 'cands': json.dumps(ranked[:8]), 'called': int(called and bool(wparty)),
                        'status_text': status[:160], 'incumbent': (cell(mj) or {}).get('text', '')[:80] if mj is not None else None,
                        'origin': 'wikipedia', 'source': 'https://en.wikipedia.org/wiki/' + PAGES[office].format(y=cycle).replace(' ', '_')})
    seen, uniq = set(), []
    for r in out:                 # the same race can appear in a summary table and a state section: keep the fullest
        if r['id'] in seen:
            prev = next(x for x in uniq if x['id'] == r['id'])
            if (r['called'], r['margin_pct'] is not None) > (prev['called'], prev['margin_pct'] is not None):
                uniq[uniq.index(prev)] = r
            continue
        seen.add(r['id']); uniq.append(r)
    return uniq


def assign_senate_classes(races, history):
    """Wikipedia's tables rarely print the Senate class. Regular seats in a cycle share one class; a special
    election fills whichever of the state's other seats was last elected longest ago."""
    regular = {2024: 'I', 2026: 'II', 2028: 'III', 2030: 'I', 2032: 'II'}
    for r in races:
        if r['office'] != 'S':
            continue
        if r['seat']:
            if r['seat'] != regular.get(r['cycle']) and not r['special']:
                r['special'] = 1          # a seat outside this year's class can only be a special election
                r['id'] += '-special'
            continue
        if not r['special']:
            r['seat'] = regular.get(r['cycle'], '')
        else:
            classes = sorted({h['seat'] for h in history if h['state'] == r['state'] and h['seat'] and h['seat'] != regular.get(r['cycle'])},
                             key=lambda c: max((h['cycle'] for h in history if h['state'] == r['state'] and h['seat'] == c), default=0))
            r['seat'] = classes[0] if classes else ''
        r['id'] = f"S-{r['cycle']}-{r['state']}-{r['seat']}" + ('-special' if r['special'] else '')
    return races


# ------------------------------------------------------------------ cache + background job with progress
_lock = threading.Lock()
_jobs = {}


def _file(office, cycle):
    return OUT / f'live_{office}_{cycle}.json'


def request(office, cycle, getter, history=(), force=False):
    key = (office, cycle)
    now = time.time()
    with _lock:
        job = _jobs.get(key)
        if job is None:
            job = {'data': None, 't': 0, 'running': False, 'step': '', 'error': None}
            try:
                saved = json.loads(_file(office, cycle).read_text(encoding='utf-8'))
                job.update(data=saved['races'], t=saved['t'])
            except (OSError, ValueError, KeyError):
                pass
            _jobs[key] = job
        due = force or job['data'] is None or now - job['t'] > TTL
        recent_fail = job['error'] and now - job['t'] < 120 and not force
        if due and not job['running'] and not recent_fail:
            job.update(running=True, step=f'Reading Wikipedia: {PAGES[office].format(y=cycle)}', error=None)

            def work():
                try:
                    html = O.wp_page(PAGES[office].format(y=cycle), getter, OUT / 'wp_cache', force=force)
                    with _lock:
                        job['step'] = 'Reading the results tables'
                    races = parse_page(office, cycle, html)
                    if office == 'S':
                        assign_senate_classes(races, list(history))
                    if not races:
                        raise LookupError('no results tables found on the page')
                    t = time.time()
                    try:
                        _file(office, cycle).parent.mkdir(parents=True, exist_ok=True)
                        _file(office, cycle).write_text(json.dumps({'t': t, 'races': races}), encoding='utf-8')
                    except OSError:
                        pass
                    with _lock:
                        job.update(data=races, t=t)
                except Exception as exc:
                    with _lock:
                        job.update(error=f'{type(exc).__name__}: {exc}'[:200], t=time.time() if job['data'] is None else job['t'])
                finally:
                    with _lock:
                        job['running'] = False
            threading.Thread(target=work, name=f'us-live-{office}-{cycle}', daemon=True).start()
        return {'races': job['data'] or [], 'fetched': job['t'] or None, 'pending': job['running'], 'step': job['step'] if job['running'] else '',
                'error': job['error'], 'page': PAGES[office].format(y=cycle)}
