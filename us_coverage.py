"""Third source for 2026 counts: numbers reported in the news coverage Sanjaya already holds.

Some states publish no machine-readable count, or refuse automated reading (see us_official). Their counts still
appear in reporting, which usually quotes the state's own figures ("with 92% of the expected vote counted, X has 51.3%
to Y's 47.9%, according to the Secretary of State"). For each race that has no state count, this module:

1. Builds a description of the race (state, office, district, the candidates Wikipedia lists).
2. Ranks the articles in Sanjaya's database (title and summary) against it with the language model's embeddings,
   the same multilingual MiniLM vectors the news desk uses. Without the language-model pack it falls back to word
   matching on the state and candidate names.
3. Reads the numbers next to each candidate's surname: a vote count ("123,456 votes") or a share ("51.3%"), and
   "N% to M%" pairs that follow both names. At least two candidates must have numbers of the same kind, and shares
   must add up to no more than 100.
4. Keeps the most recent article that yields numbers, preferring ones that cite an official source (secretary of
   state, board of elections, official or unofficial results).

These numbers are labelled as reported in news coverage, with the article and its date. They never call a race, and
they never override a state count or a Wikipedia call: where Wikipedia has called a race and the coverage shows
someone else ahead, the coverage is set aside. It runs only when asked (the "Search news coverage" button), and the
answer is kept until asked again.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
import time

from us_elections_data import OUT, STATES

OFFICIAL = re.compile(r'secretary of state|board of elections|election(s)? (commission|division|board|office)|'
                      r'(un)?official (results|count|returns|tally)|certified|state results', re.I)
PCT = r'(\d{1,2}(?:\.\d{1,2})?)\s*(?:%|percent\b|per cent\b)'
VOTES = r'(\d{1,3}(?:,\d{3})+|\d{4,7})\s*(?:votes?\b)'
COUNTED = re.compile(r'(\d{1,3}(?:\.\d)?)\s*(?:%|percent)\s*of\s*(?:the\s*)?(?:estimated\s*|expected\s*)?(?:votes?|ballots|precincts)\s*'
                     r'(?:counted|in|reporting|tallied)', re.I)
OFFICE_WORDS = {'H': 'U.S. House', 'S': 'U.S. Senate', 'G': 'governor'}
WINDOW_DAYS = 30
_lock = threading.Lock()
_state = {'running': False, 'step': '', 'error': None}


def _file(cycle):
    return OUT / f'coverage_{cycle}.json'


def load(cycle):
    try:
        return json.loads(_file(cycle).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'t': None, 'races': {}, 'searched': 0, 'method': None}


def surname(name):
    parts = [p for p in re.split(r'\s+', re.sub(r'\(.*?\)|["“”]', ' ', str(name or ''))) if p]
    parts = [p for p in parts if not re.fullmatch(r'(jr|sr|ii|iii|iv)\.?,?', p, re.I)]
    return parts[-1].strip(',.') if parts else ''


def describe(race):
    st = STATES.get(race['state'], race['state'])
    office = OFFICE_WORDS[race['office']]
    where = f"{st}'s {race['seat']} congressional district" if race['office'] == 'H' else st
    names = ', '.join(c[0] for c in race.get('cands_list', [])[:4])
    return f'{where} {office} election results 2026: {names} vote count and percentage'


def extract(text, cands):
    """{name: (votes or None, pct or None)} for the candidates whose numbers the text reports, plus the counted share."""
    found = {}
    counted = COUNTED.search(text)
    low = COUNTED.sub(lambda m: ' ' * len(m.group(0)), text)     # "97% of the vote counted" is nobody's share
    # "Smith leads Jones 52% to 46%"
    names = [(n, surname(n)) for n, _ in cands if len(surname(n)) >= 3]
    for (a, sa) in names:
        for (b, sb) in names:
            if a == b:
                continue
            m = re.search(r'\b' + re.escape(sa) + r'\b[^.%]{0,80}?\b' + re.escape(sb) + r'\b[^.%]{0,30}?' + PCT + r'\s*(?:to|-|–)\s*' + PCT,
                          low, re.I)
            if m:
                found[a] = (None, float(m.group(1)))
                found[b] = (None, float(m.group(2)))
                low = low[:m.start()] + ' ' * (m.end() - m.start()) + low[m.end():]
    for name, _party in cands:
        sn = surname(name)
        if len(sn) < 3:
            continue
        others = [re.escape(surname(n)) for n, _ in cands if len(surname(n)) >= 3 and surname(n).lower() != sn.lower()]
        for m in re.finditer(r'\b' + re.escape(sn) + r'\b', low, re.I):
            tail = low[m.end():m.end() + 70]
            if others:                                      # stop at the next candidate's name
                tail = re.split(r'\b(?:' + '|'.join(others) + r')\b', tail, maxsplit=1, flags=re.I)[0]
            v = re.search(VOTES, tail, re.I)
            p = re.search(PCT, tail, re.I)
            if (v or p) and name not in found:
                found[name] = (float(v.group(1).replace(',', '')) if v else None, float(p.group(1)) if p else None)
    return found, (float(counted.group(1)) if counted else None)


def _usable(found):
    pcts = [p for v, p in found.values() if p is not None]
    votes = [v for v, p in found.values() if v is not None]
    if len(votes) >= 2:
        return 'votes'
    if len(pcts) >= 2 and sum(pcts) <= 100.5 and max(pcts) < 100:
        return 'pct'
    return None


def _articles(news_db, since):
    con = sqlite3.connect(f'file:{news_db}?mode=ro', uri=True)
    try:
        rows = con.execute('SELECT id, title, summary, url, source, COALESCE(published, retrieved) FROM entries '
                           'WHERE COALESCE(published, retrieved) >= ?', (since,)).fetchall()
    finally:
        con.close()
    return [r for r in rows if re.search(r'\d', f'{r[1]} {r[2]}') and re.search(r'%|percent|votes?\b', f'{r[1]} {r[2]}', re.I)]


def _vectors(news_db, ids, texts_for_missing, cache_dir):
    """Stored article vectors from the language-model pack, embedding the few that are missing. None without the pack."""
    try:
        import numpy as np
        import semantic
        if not semantic.available():
            return None, None
        con = sqlite3.connect(f'file:{news_db}?mode=ro', uri=True)
        try:
            out = {}
            for i in range(0, len(ids), 900):
                part = ids[i:i + 900]
                q = f"SELECT id, vec FROM embeddings WHERE model=? AND id IN ({','.join('?' * len(part))})"
                for eid, blob in con.execute(q, (semantic.MODEL, *part)):
                    out[eid] = np.frombuffer(blob, dtype=np.float32)
        except sqlite3.Error:
            out = {}
        finally:
            con.close()
        todo = [i for i in ids if i not in out][:400]
        if todo:
            for i, v in zip(todo, semantic.embed_texts([texts_for_missing[i] for i in todo], cache_dir) or []):
                out[i] = v
        return out, semantic
    except Exception:
        return None, None


def search(cycle, races, news_db, cache_dir=None, election_day='2026-11-03', progress=None):
    """Numbers from news coverage for each race (rows with cands from Wikipedia). Returns {race_id: race-like dict}."""
    day = dt.date.fromisoformat(election_day)
    arts = _articles(news_db, (day - dt.timedelta(days=1)).isoformat())
    text = {a[0]: f'{a[1]}. {a[2] or ""}' for a in arts}
    meta = {a[0]: {'title': a[1], 'url': a[3], 'publisher': a[4], 'when': a[5]} for a in arts}
    todo = []
    for r in races:
        try:
            cands = [(c[0], c[1]) for c in json.loads(r.get('cands') or '[]') if c and c[0]]
        except ValueError:
            cands = []
        if len(cands) >= 2:
            todo.append({**r, 'cands_list': cands})
    vecs, semantic = _vectors(news_db, [a[0] for a in arts], text, cache_dir) if arts and todo else (None, None)
    qv = None
    if vecs is not None and todo:
        qv = semantic.embed_texts([describe(r) for r in todo], cache_dir)
    method = 'embeddings' if qv else 'words'
    out = {}
    for n, r in enumerate(todo):
        if progress and n % 10 == 0:
            progress(f'Searching coverage: {n} of {len(todo)} races')
        st = STATES.get(r['state'], r['state'])
        sns = [surname(c[0]) for c in r['cands_list'] if len(surname(c[0])) >= 3]
        pool = [a for a in text if re.search(r'\b' + re.escape(st) + r'\b', text[a], re.I) or
                sum(1 for s in sns if re.search(r'\b' + re.escape(s) + r'\b', text[a], re.I)) >= 2]
        pool = [a for a in pool if sum(1 for s in sns if re.search(r'\b' + re.escape(s) + r'\b', text[a], re.I)) >= 1]
        if not pool:
            continue
        if qv:
            import numpy as np
            q = np.asarray(qv[n], dtype=np.float32)
            scored = []
            for a in pool:
                v = vecs.get(a)
                if v is None or v.shape[0] != q.shape[0]:
                    continue
                scored.append((float(v @ q / ((np.linalg.norm(v) or 1) * (np.linalg.norm(q) or 1))), a))
        else:
            scored = [(sum(1 for s in sns if re.search(r'\b' + re.escape(s) + r'\b', text[a], re.I)) / max(1, len(sns)), a) for a in pool]
        scored.sort(reverse=True)
        best = None
        for score, a in scored[:12]:
            if qv and score < 0.30:
                break
            found, counted = extract(text[a], r['cands_list'])
            kind = _usable(found)
            if not kind:
                continue
            cand = (bool(OFFICIAL.search(text[a])), str(meta[a]['when'] or ''), score, a, found, counted, kind)
            if best is None or cand[:3] > best[:3]:
                best = cand
        if best:
            official, when, score, a, found, counted, kind = best
            out[r['id']] = _race(r, found, counted, kind, meta[a], official, score, method)
    return out, method, len(todo)


def _race(r, found, counted, kind, art, official, score, method):
    party = dict(r['cands_list'])
    rows = []
    for name, (v, p) in found.items():
        rows.append([name, party.get(name, 'O'), int(v) if v is not None and kind == 'votes' else None,
                     p if p is not None else None, 0])
    if kind == 'votes':
        total = sum(x[2] or 0 for x in rows)
        for x in rows:
            x[3] = round(100 * (x[2] or 0) / total, 2) if total else x[3]
    rows.sort(key=lambda x: -(x[3] or 0))
    lead, run = rows[0], rows[1] if len(rows) > 1 else None
    when = str(art.get('when') or '')[:10]
    return {'id': r['id'], 'office': r['office'], 'cycle': r['cycle'], 'state': r['state'], 'seat': r['seat'],
            'special': r.get('special', 0), 'leader': lead[0], 'leader_party': lead[1],
            'runner': run[0] if run else None, 'runner_party': run[1] if run else None,
            'winner_votes': lead[2], 'runner_votes': run[2] if run else None,
            'total': sum(x[2] or 0 for x in rows) if kind == 'votes' else None,
            'margin_pct': round(lead[3] - run[3], 2) if run and lead[3] is not None and run[3] is not None else None,
            'cands': json.dumps(rows[:8]), 'counted_pct': counted, 'counted_basis': 'reported' if counted is not None else None,
            'origin': 'coverage', 'source': art.get('url'), 'unopposed': 0, 'certified': 0,
            'coverage': {'title': art.get('title'), 'publisher': art.get('publisher'), 'date': when, 'cites_official': official,
                         'match': round(score, 3), 'method': method},
            'status_text': f"Reported by {art.get('publisher') or 'news coverage'}{', ' + when if when else ''}"}


def request(cycle, office, races, news_db, cache_dir=None, force=False):
    """Cached coverage numbers; a new search only when forced (it runs on request, never on its own)."""
    saved = load(cycle)
    with _lock:
        running = _state['running']
        if force and not running and news_db:
            _state.update(running=True, step='Searching news coverage', error=None)

            def work():
                try:
                    res, method, n = search(cycle, races, news_db, cache_dir, progress=lambda s: _state.update(step=s))
                    old = load(cycle).get('races', {})
                    keep = {k: v for k, v in old.items() if not k.startswith(f'{office}-')}
                    data = {'t': time.time(), 'races': {**keep, **res}, 'searched': n, 'method': method, 'office': office}
                    try:
                        _file(cycle).parent.mkdir(parents=True, exist_ok=True)
                        _file(cycle).write_text(json.dumps(data), encoding='utf-8')
                    except OSError:
                        pass
                except Exception as exc:
                    _state['error'] = f'{type(exc).__name__}: {exc}'[:200]
                finally:
                    _state['running'] = False
            threading.Thread(target=work, name=f'us-coverage-{cycle}', daemon=True).start()
            running = True
    return {**saved, 'pending': running, 'step': _state['step'] if running else '', 'error': _state['error']}


def apply(rows, coverage):
    """Fill numbers from coverage for races that have no state count. Never calls a race; never contradicts a call."""
    out = []
    for r in rows:
        c = coverage.get(r['id'])
        if not c or 'state' in str(r.get('origin') or ''):
            out.append(r)
            continue
        if r.get('called') and r.get('winner_party') and c.get('leader_party') != r['winner_party']:
            out.append({**r, 'coverage_note': f"News coverage ({c['coverage'].get('publisher')}) shows {c['leader']} ahead; set aside "
                                              "because Wikipedia lists this race as decided"})
            continue
        m = dict(r)
        for k in ('leader', 'leader_party', 'runner', 'runner_party', 'winner_votes', 'runner_votes', 'total', 'margin_pct',
                  'counted_pct', 'counted_basis'):
            if c.get(k) is not None or k in ('total', 'counted_pct', 'counted_basis'):
                m[k] = c.get(k)
        cands = json.loads(c['cands'])
        if r.get('called'):
            for x in cands:
                x[4] = int(x[1] == r.get('winner_party') and x[0] == c['leader'])
        m.update(cands=json.dumps(cands), origin=(r.get('origin') or 'wikipedia') + '+coverage', coverage=c['coverage'],
                 coverage_source=c['source'], wiki_status=r.get('status_text'))
        out.append(m)
    return out
