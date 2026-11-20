"""Pulse: where today's signals point, for elections that are still far away.

When the next election is more than six months off, the seat model in forecast.py waits for more data.
The pulse fills that gap with a deliberately simple ensemble. Each member is one hypothesis about how
votes move between elections; each is fitted on past results, and each is shown separately so the
reader can see which assumption drives the answer.

  H1 National mood      Parties gain or lose everywhere at once. The swing seen in every election held
                        elsewhere since this state last voted (recent ones weigh more) is applied here,
                        scaled by a coefficient fitted on past elections.
  H2 Lok Sabha anchor   Voters move toward how they voted in the most recent Lok Sabha election held
                        here (state elections only; scaled by a fitted coefficient).
                        For the Lok Sabha pulse: each state's own assembly swing since 2024.
  H3 Time for change    Governing parties lose ground over a term and large parties regress toward the
                        mean. A ridge regression on incumbency and last share, scaled by how much of the
                        term has passed.
  H4 Seat patterns      The bagging + boosting tree ensemble from forecast.py, given the national mood as
                        its swing input. (State elections only.)
  H5 Coverage tone      H1 tilted by the tone of recent news coverage of each party in Sanjaya's own
                        archive, compared with its tone over the previous five months. Not backtested:
                        Sanjaya has not archived coverage of a full election cycle yet.

Seat ranges come from simulating each hypothesis with its own fitted error, plus drift for the months
left before the poll, then pooling. The law of total variance splits the spread of each party's seat
total into: which hypothesis holds (between), state-wide error, time until the poll, and seat-level noise.
This is a model, not a poll. It never calls a winner.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import sqlite3
import threading
import time
from pathlib import Path

import forecast as F

MODEL_VERSION = 'pulse-1'
DATA_DIR = F.DATA_DIR
SIMS = 1600
MOOD_WINDOW = 36            # months of other elections that feed the national mood
MOOD_HALFLIFE = 18
DRIFT_PER_YEAR = 0.025      # state-wide share drift per year until the poll (sd)
SENT_GAIN = 0.03            # share points per unit of tone change (prior, not fitted)
SENT_SD = 0.015
SENT_MIN_ARTICLES = 25
HYPOTHESES = {
    'H1': ('National mood', 'Parties gain or lose everywhere at once: the swing seen in elections held elsewhere since this place last voted.'),
    'H2': ('Lok Sabha anchor', 'Voters drift toward how they voted in the latest Lok Sabha election here.'),
    'H3': ('Time for change', 'Governments lose ground over a term; big parties regress toward the mean.'),
    'H4': ('Seat patterns', 'The tree ensemble: past seat-level patterns repeat, given the national mood.'),
    'H5': ('Coverage tone', 'National mood, tilted by how the tone of recent news coverage of each party has moved.'),
}
HYP_NATIONAL = {'H2': ('Assembly swing', 'Each state moves by its own assembly swing since 2024, where it has voted since.')}


def _key(y, m):
    return F._mkey(y, m)


# ------------------------------------------------------------------ signals
def events(ae, ge_shares, seats):
    """Every election with a predecessor: (key, state, kind, weight-size, swing dict)."""
    out = []
    for st, lst in ae.items():
        for i in range(1, len(lst)):
            a, b = lst[i - 1], lst[i]
            sa, sb = F.state_shares(seats[a['id']].values()), F.state_shares(seats[b['id']].values())
            out.append((_key(b['year'], b['month']), st, 'AE', b['seats'] or len(seats[b['id']]), _swing(sa, sb)))
    for st, lst in ge_shares.items():
        lst = sorted(lst)
        for i in range(1, len(lst)):
            (y, m), sb = lst[i]
            out.append((_key(y, m), st, 'GE', 10, _swing(lst[i - 1][1], sb)))
    return out


def _swing(a, b):
    return {p: b.get(p, 0) - a.get(p, 0) for p in set(a) | set(b)
            if p not in F.NOT_PARTIES and (a.get(p, 0) >= F.MIN_STATE_SHARE or b.get(p, 0) >= F.MIN_STATE_SHARE)}


def mood(evts, asof, exclude=None, since=None):
    """Recency-weighted average swing per party across elections held elsewhere."""
    num, den, n = {}, {}, 0
    lo = max(asof - MOOD_WINDOW, since if since is not None else -1)
    for k, st, kind, size, sw in evts:
        if st == exclude or not (lo < k <= asof):
            continue
        w = math.exp(-(asof - k) / MOOD_HALFLIFE * math.log(2)) * math.sqrt(size) * (0.5 if kind == 'GE' else 1.0)
        n += 1
        for p, v in sw.items():
            num[p] = num.get(p, 0) + w * v
            den[p] = den.get(p, 0) + w
    return {p: num[p] / den[p] for p in num if den[p] > 0.5}, n


# ------------------------------------------------------------------ sentiment from Sanjaya's archive
POS = set('win wins won victory sweep surge surges lead leads leading gain gains boost boosts popular praise praised welcome welcomed success successful landslide rally record support backing backs momentum strong strengthens unveils launches delivers'.split())
NEG = set('lose loses lost defeat defeated rout scam scandal corruption corrupt protest protests setback crisis rebel rebels rebellion quits quit resigns resigned arrested arrest raid raids row slammed slams criticism criticised criticized anger angry decline declines split splits defection defections exodus infighting rift jolt blow trouble probe fails failure'.split())


def aliases():
    try:
        import elections
        table = elections.parties()
    except Exception:
        table = {}
    out = {}
    extra = {'INC': ['Congress'], 'AAAP': ['AAP', 'Aam Aadmi'], 'AITC': ['Trinamool', 'TMC'], 'ADMK': ['AIADMK'],
             'SHS': ['Shiv Sena'], 'SHSUBT': ['Sena (UBT)', 'Shiv Sena (UBT)'], 'CPM': ['CPI(M)', 'CPM'], 'JD(U)': ['JD(U)', 'JDU'],
             'SAD': ['Akali Dal'], 'BRS': ['BRS', 'Bharat Rashtra Samithi'], 'YSRCP': ['YSRCP', 'YSR Congress'], 'RLD': ['RLD', 'Rashtriya Lok Dal']}
    for code, info in table.items():
        names = [code] if re.fullmatch(r'[A-Z][A-Z()\-]{1,8}', code) and code not in ('IND', 'OTH', 'NOTA') else []
        if info.get('name'):
            names.append(re.sub(r'\s*\(.*\)$', '', info['name']))
        out[code] = names + extra.get(code, [])
    for code, names in extra.items():
        out.setdefault(code, names)
    return out


def tone_lexicon(text):
    words = re.findall(r"[a-z]+", text.lower())
    pos = sum(w in POS for w in words); neg = sum(w in NEG for w in words)
    return (pos - neg) / (pos + neg + 1)


def coverage_tone(db_path, parties, place=None, now=None, recent_days=30, base_days=180):
    """Per party: tone of articles that mention it (and no other tracked party), last 30 days vs the 150
    days before. Article tone is a small news lexicon; when Sanjaya's language model has embedded the
    articles, it is averaged with a similarity score against positive and negative anchor sentences."""
    now = now or dt.datetime.now(dt.timezone.utc)
    al = aliases()
    pats = {p: re.compile(r'\b(' + '|'.join(re.escape(a) for a in al.get(p, [p]) if a) + r')\b')
            for p in parties if p != 'OTH' and al.get(p)}
    if not pats:
        return {}
    try:
        con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        since = (now - dt.timedelta(days=base_days)).strftime('%Y-%m-%d')
        rows = con.execute('SELECT id, title, summary, COALESCE(published, retrieved) FROM entries WHERE COALESCE(published, retrieved) >= ?', (since,)).fetchall()
        con.close()
    except sqlite3.Error:
        return {}
    place_re = re.compile(r'\b' + re.escape(place) + r'\b', re.I) if place else None
    cut = (now - dt.timedelta(days=recent_days)).strftime('%Y-%m-%d')
    hits = []
    for eid, title, summary, when in rows:
        text = f'{title}. {summary or ""}'
        if place_re and not place_re.search(text):
            continue
        found = [p for p, rx in pats.items() if rx.search(text)]
        if len(found) != 1:
            continue
        hits.append((eid, found[0], str(when or '') >= cut, tone_lexicon(text)))
    emb = _embedding_tone([h[0] for h in hits], db_path)
    out = {}
    for p in pats:
        rec = [(h[2], (h[3] + emb[h[0]]) / 2 if h[0] in emb else h[3]) for h in hits if h[1] == p]
        now_t = [t for r, t in rec if r]; base_t = [t for r, t in rec if not r]
        if len(now_t) >= 5 and len(base_t) >= 5:
            out[p] = {'recent': len(now_t), 'before': len(base_t), 'tone_recent': round(sum(now_t) / len(now_t), 3),
                      'tone_before': round(sum(base_t) / len(base_t), 3),
                      'delta': round(sum(now_t) / len(now_t) - sum(base_t) / len(base_t), 3)}
    return out


def _embedding_tone(ids, db_path):
    try:
        import numpy as np
        import semantic
        if not ids or not semantic.ready():
            return {}
        con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        q = ','.join('?' * min(len(ids), 900))
        rows = con.execute(f'SELECT id, vec FROM embeddings WHERE id IN ({q})', ids[:900]).fetchall()
        con.close()
        if not rows:
            return {}
        anchors = semantic.embed_texts(['The party wins support, gains ground and is praised.',
                                        'The party loses support, faces scandal and is criticised.'])
        a = np.asarray(anchors, dtype=np.float32)
        a /= np.linalg.norm(a, axis=1, keepdims=True)
        out = {}
        for eid, blob in rows:
            v = np.frombuffer(blob, dtype=np.float32)
            if v.shape[0] != a.shape[1]:
                continue
            v = v / (np.linalg.norm(v) or 1)
            out[eid] = float(np.clip((v @ a[0] - v @ a[1]) * 5, -1, 1))
        return out
    except Exception:
        return {}


# ------------------------------------------------------------------ fitting the statistical hypotheses
def training_rows(ae, ge_shares, seats, evts, lead=6, before=None):
    """Past state elections seen from `lead` months before the poll: the signals each hypothesis uses,
    and the swing that actually happened."""
    rows = []
    for st, lst in ae.items():
        for i in range(1, len(lst)):
            L, T = lst[i - 1], lst[i]
            tk = _key(T['year'], T['month'])
            if before is not None and tk >= before:
                continue
            asof = tk - lead
            sL = F.state_shares(seats[L['id']].values()); sT = F.state_shares(seats[T['id']].values())
            ge = F._ge_between(ge_shares.get(st), L, T['year'], T['month'])
            if ge and _key(*ge[0]) > asof:
                ge = None
            parties = F.party_set(sL, ge[1] if ge else None)
            m, _ = mood(evts, asof, exclude=st, since=_key(L['year'], L['month']))
            wins = F.seat_winners(seats[L['id']].values())
            inc = max(wins, key=wins.get) if wins else None
            for p in parties:
                rows.append({'state': st, 'key': tk, 'p': p, 'y': sT.get(p, 0) - sL.get(p, 0), 'mood': m.get(p, 0.0),
                             'ge': (ge[1].get(p, 0) - sL.get(p, 0)) if ge else None, 'inc': 1.0 if p == inc else 0.0,
                             'share': sL.get(p, 0)})
    return rows


def fit(rows):
    import numpy as np
    out = {}
    y = np.array([r['y'] for r in rows]); mo = np.array([r['mood'] for r in rows])
    k = float((mo @ y) / max(1e-9, mo @ mo)) if len(rows) else 0.0
    out['kappa'] = max(0.0, min(1.5, k))
    out['sd1'] = float(np.std(y - out['kappa'] * mo)) if len(rows) else 0.06
    g = [r for r in rows if r['ge'] is not None]
    if g:
        gy = np.array([r['y'] for r in g]); gx = np.array([r['ge'] for r in g])
        lam = float((gx @ gy) / max(1e-9, gx @ gx))
        out['lambda'] = max(0.0, min(1.5, lam)); out['sd2'] = float(np.std(gy - out['lambda'] * gx))
    else:
        out['lambda'], out['sd2'] = 0.5, 0.07
    X = np.array([[r['inc'], r['share'], 1.0] for r in rows]) if rows else np.zeros((0, 3))
    if len(rows) >= 10:
        beta = np.linalg.solve(X.T @ X + 0.5 * np.eye(3), X.T @ y)
        out['beta'] = [float(b) for b in beta]; out['sd3'] = float(np.std(y - X @ beta))
    else:
        out['beta'], out['sd3'] = [-0.03, -0.1, 0.01], 0.07
    out['n'] = len(rows)
    return out


def swings(params, parties, sL, m, ge_sw, inc, frac, tone=None):
    """Statewide swing per party under each statistical hypothesis."""
    k, lam, (bi, bs, b0) = params['kappa'], params['lambda'], params['beta']
    out = {'H1': {p: k * m.get(p, 0.0) for p in parties}}
    if ge_sw is not None:
        out['H2'] = {p: lam * ge_sw.get(p, 0.0) for p in parties}
    out['H3'] = {p: frac * (bi * (1.0 if p == inc else 0.0) + bs * sL.get(p, 0) + b0) for p in parties}
    if tone:
        mean = sum(t['delta'] for t in tone.values()) / len(tone)
        out['H5'] = {p: out['H1'][p] + (SENT_GAIN * (tone[p]['delta'] - mean) if p in tone else 0.0) for p in parties}
    return out


# ------------------------------------------------------------------ simulation + variance decomposition
def apply_swing(M0, cols, sw):
    import numpy as np
    d = np.array([sw.get(c, 0.0) for c in cols])
    if 'OTH' in cols:
        d[cols.index('OTH')] = -sum(v for c, v in sw.items() if c in cols and c != 'OTH')
    M = np.clip(M0 + d[None, :], 0.001, None)
    return M / M.sum(1, keepdims=True)


def sim(M, sd_state, sd_seat, n, rng, groups=None):
    """Seat totals for n simulated elections. groups: optional seat->state index for state-level noise
    (national pulse), so each state swings on its own."""
    import numpy as np
    S, P = M.shape
    tot = np.zeros((n, P))
    for k in range(0, n, 100):
        b = min(100, n - k)
        if groups is None:
            st = rng.normal(0, sd_state, (b, 1, P)) if sd_state > 0 else 0
        else:
            G = int(groups.max()) + 1
            st = (rng.normal(0, sd_state, (b, G, P))[:, groups, :]) if sd_state > 0 else 0
        se = rng.normal(0, sd_seat, (b, S, P)) if sd_seat > 0 else 0
        win = (M[None] + st + se).argmax(2)
        for j in range(P):
            tot[k:k + b, j] = (win == j).sum(1)
    return tot


def mixture(members, cols, sd_seat, drift, n=SIMS, seed=5, groups=None):
    """members: {h: (M, weight, sd_state)}. Returns pooled ranges, per-hypothesis medians and the variance split."""
    import numpy as np
    rng = np.random.default_rng(seed)
    wsum = sum(w for _, w, _ in members.values())
    pooled, stats = [], {}
    for h, (M, w, sd) in members.items():
        k = max(150, int(round(n * w / wsum)))
        full = sim(M, math.hypot(sd, drift), sd_seat, k, rng, groups)
        only_state = sim(M, sd, 0, 300, rng, groups)
        only_drift = sim(M, drift, 0, 300, rng, groups) if drift > 0 else np.zeros_like(only_state)
        only_seat = sim(M, 0, sd_seat, 300, rng, groups)
        point = sim(M, 0, 0, 1, rng, groups)[0]
        stats[h] = {'w': w / wsum, 'mean': full.mean(0), 'var': full.var(0), 'point': point,
                    'v_state': only_state.var(0), 'v_drift': only_drift.var(0), 'v_seat': only_seat.var(0),
                    'p10': np.percentile(full, 10, 0), 'p50': np.percentile(full, 50, 0), 'p90': np.percentile(full, 90, 0)}
        pooled.append((full, w / wsum))
    allsims = np.concatenate([x for x, _ in pooled])
    mu = sum(s['w'] * s['mean'] for s in stats.values())
    between = sum(s['w'] * (s['mean'] - mu) ** 2 for s in stats.values())
    within = sum(s['w'] * s['var'] for s in stats.values())
    comp = {'between': between, 'state': 0 * mu, 'drift': 0 * mu, 'seat': 0 * mu}
    for s in stats.values():
        parts = s['v_state'] + s['v_drift'] + s['v_seat']
        parts = np.where(parts > 0, parts, 1)
        for name, v in (('state', s['v_state']), ('drift', s['v_drift']), ('seat', s['v_seat'])):
            comp[name] = comp[name] + s['w'] * s['var'] * v / parts
    total = between + within
    ranges = []
    for j, c in enumerate(cols):
        v = allsims[:, j]
        r = {'code': c, 'lo': int(np.percentile(v, 10)), 'median': int(np.percentile(v, 50)), 'hi': int(np.percentile(v, 90)),
             'by_hypothesis': {h: {'median': int(s['p50'][j]), 'lo': int(s['p10'][j]), 'hi': int(s['p90'][j])} for h, s in stats.items()}}
        t = float(total[j])
        if t > 0:
            r['variance'] = {k: round(float(comp[k][j]) / t, 3) for k in comp}
            r['sd'] = round(math.sqrt(t), 1)
        ranges.append(r)
    return ranges, {h: round(s['w'], 3) for h, s in stats.items()}


def significance(ranges, majority):
    """Is the choice of hypothesis a material part of the uncertainty? F-like ratio on the leading parties."""
    lead = sorted([r for r in ranges if r['code'] != 'OTH' and r.get('variance')], key=lambda r: -r['median'])[:2]
    if not lead:
        return {'significant': False}
    top = max(r['variance']['between'] for r in lead)
    spread = max(abs(h['median'] - r['median']) for r in lead for h in r['by_hypothesis'].values())
    return {'between_share': round(top, 3), 'max_shift': int(spread), 'threshold': 0.10,
            'significant': top >= 0.10}


# ------------------------------------------------------------------ backtest (trust)
def backtest(ae, ge_shares, seats, evts, lead=12, sims=300):
    """Pulses taken twelve months before past state elections (2017 on), with H1-H3 fitted only on earlier
    elections. H4 (trees) and H5 (coverage) are not part of this test."""
    import numpy as np
    recs = []
    per_h = {'H1': [0, 0], 'H2': [0, 0], 'H3': [0, 0]}
    for st, lst in ae.items():
        for i in range(1, len(lst)):
            L, T = lst[i - 1], lst[i]
            if T['year'] < 2017:
                continue
            tk = _key(T['year'], T['month']); asof = tk - lead
            rows = training_rows(ae, ge_shares, seats, evts, lead=lead, before=asof)
            if len(rows) < 30:
                continue
            params = fit(rows)
            sL = F.state_shares(seats[L['id']].values())
            ge = F._ge_between(ge_shares.get(st), L, T['year'], T['month'])
            if ge and _key(*ge[0]) > asof:
                ge = None
            sl = F.seat_list_of(seats[T['id']], st)
            X, Y, meta, cols = F.features(st, L, lst[i - 2] if i >= 2 else None, ge, sl, seats, T['year'], seats[T['id']])
            if len(X) < 20:
                continue
            fi = F.FEATURES.index('share_1')
            _, M0 = F.shares_matrix([x[fi] for x in X], meta, cols)
            _, A = F.shares_matrix(Y, meta, cols)
            m, _ = mood(evts, asof, exclude=st, since=_key(L['year'], L['month']))
            wins = F.seat_winners(seats[L['id']].values()); inc = max(wins, key=wins.get) if wins else None
            sw = swings(params, [c for c in cols if c != 'OTH'], sL, m, ({p: ge[1].get(p, 0) - sL.get(p, 0) for p in cols} if ge else None), inc, 1.0)
            members = {}
            for h, d in sw.items():
                Mh = apply_swing(M0, cols, d)
                members[h] = (Mh, 1.0, params['sd' + h[1]])
                hit = float((Mh.argmax(1) == A.argmax(1)).mean())
                per_h[h][0] += hit * len(A); per_h[h][1] += len(A)
            Mbar = sum(x[0] for x in members.values()) / len(members)
            calls = float((Mbar.argmax(1) == A.argmax(1)).mean())
            rg, _ = mixture(members, cols, 0.09, DRIFT_PER_YEAR * math.sqrt(lead / 12), n=sims)
            actual = np.bincount(A.argmax(1), minlength=len(cols))
            named = [j for j, c in enumerate(cols) if c != 'OTH' and (actual[j] > 0 or rg[j]['hi'] > 0)]
            cov = [rg[j]['lo'] <= actual[j] <= rg[j]['hi'] for j in named]
            recs.append({'state': st, 'year': T['year'], 'seats': len(A), 'call_accuracy': round(calls, 3),
                         'coverage': round(float(np.mean(cov)), 3) if cov else None})
    def wavg(k):
        v = [(r[k], r['seats']) for r in recs if r.get(k) is not None]
        return round(sum(a * b for a, b in v) / sum(b for _, b in v), 3) if v else None
    out = {'elections': len(recs), 'call_accuracy': wavg('call_accuracy'), 'coverage': wavg('coverage'), 'lead_months': lead,
           'per_hypothesis': {h: round(a / b, 3) for h, (a, b) in per_h.items() if b}}
    out['label'] = F.trust_label(out['call_accuracy'], out['coverage'])
    return out, recs


# ------------------------------------------------------------------ the pulse for every far election
def run(db_path, news_db=None, now=None, progress=None, sims=SIMS, with_trees=True):
    import numpy as np
    t0 = time.time()
    now = now or dt.datetime.now(dt.timezone.utc)
    nowk = _key(now.year, now.month)
    say = progress or (lambda s: None)
    els, seats = F.load(db_path)
    ae, ge_shares = F.history(els, seats)
    evts = events(ae, ge_shares, seats)
    say('Fitting the statistical hypotheses')
    params = fit(training_rows(ae, ge_shares, seats, evts, lead=6))
    say('Backtesting pulses taken a year before past elections')
    bt, bt_rows = backtest(ae, ge_shares, seats, evts)
    model = None
    if with_trees:
        say('Training the tree ensemble')
        built = []
        for st, prev, prev2, cur, ge in F.tasks(ae, ge_shares, seats):
            X, Y, _, _ = F.features(st, prev, prev2, ge, F.seat_list_of(seats[cur['id']], st), seats, cur['year'], seats[cur['id']])
            if len(X) >= 20:
                built.append((X, Y))
        model = F.Ensemble().fit(np.concatenate([np.asarray(x, float) for x, _ in built]), np.concatenate([np.asarray(y, float) for _, y in built]))
    sd_seat = 0.09
    try:
        c = F.cached()
        if c and c.get('noise'):
            sd_seat = c['noise'].get('seat_sd', sd_seat)
    except Exception:
        pass
    states = {}
    for st, lst in ae.items():
        L = lst[-1]
        ey, em = L['year'] + F.TERM_YEARS, L['month'] or 1
        away = _key(ey, em) - nowk
        if away <= F.SHOW_WITHIN_MONTHS or away > 66:
            continue
        say(f'Pulse for {st.replace("_", " ")}')
        try:
            states[st] = state_pulse(st, lst, ae, ge_shares, seats, evts, params, model, nowk, (ey, em), sd_seat, news_db, now, sims)
        except Exception as exc:
            states[st] = {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'[:200]}
    say('Pulse for the Lok Sabha')
    try:
        national = national_pulse(ae, ge_shares, seats, evts, params, nowk, sd_seat, news_db, now, sims)
    except Exception as exc:
        national = {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'[:200]}
    return {'model': MODEL_VERSION, 'generated': now.strftime('%Y-%m-%dT%H:%MZ'), 'seconds': round(time.time() - t0, 1),
            'params': {k: (round(v, 4) if isinstance(v, float) else v) for k, v in params.items()},
            'backtest': bt, 'backtest_rows': bt_rows, 'states': states, 'national': national}


def _hyp_table(ranges, weights, names, bt):
    lead = [r for r in sorted(ranges, key=lambda r: -r['median']) if r['code'] != 'OTH'][:3]
    rows = []
    for h, w in weights.items():
        nm, desc = names.get(h, HYPOTHESES[h])
        rows.append({'id': h, 'name': nm, 'about': desc, 'weight': w,
                     'backtest_accuracy': (bt.get('per_hypothesis') or {}).get(h),
                     'medians': [{'code': r['code'], 'median': r['by_hypothesis'][h]['median']} for r in lead if h in r['by_hypothesis']]})
    return rows


def state_pulse(st, lst, ae, ge_shares, seats, evts, params, model, nowk, expected, sd_seat, news_db, now, sims):
    import numpy as np
    L = lst[-1]; prev2 = lst[-2] if len(lst) >= 2 else None
    Lk = _key(L['year'], L['month'])
    sL = F.state_shares(seats[L['id']].values())
    ge = F._ge_between(ge_shares.get(st), L, 9999, 1)
    m, n_events = mood(evts, nowk, exclude=st, since=Lk)
    wins = F.seat_winners(seats[L['id']].values()); inc = max(wins, key=wins.get) if wins else None
    sl = F.seat_list_of(seats[L['id']], st)
    X, _, meta, cols = F.features(st, L, prev2, ge, sl, seats, expected[0])
    if len(X) < 20:
        return {'status': 'no_history'}
    fi = F.FEATURES.index('share_1')
    _, M0 = F.shares_matrix([x[fi] for x in X], meta, cols)
    parties = [c for c in cols if c != 'OTH']
    term = max(12, _key(*expected) - Lk)
    frac = min(1.0, max(0.0, (nowk - Lk) / term))
    tone = coverage_tone(news_db, parties, st.replace('_', ' ').replace(' & ', ' and '), now) if news_db else {}
    tone_ok = {p: t for p, t in tone.items() if t['recent'] >= 5}
    use_tone = sum(t['recent'] for t in tone_ok.values()) >= SENT_MIN_ARTICLES and len(tone_ok) >= 2
    ge_sw = {p: ge[1].get(p, 0) - sL.get(p, 0) for p in parties} if ge else None
    sw = swings(params, parties, sL, m, ge_sw, inc, frac, tone_ok if use_tone else None)
    members = {}
    for h, d in sw.items():
        sd = params.get('sd' + h[1], 0.06) * (frac if h == 'H3' else 1.0) if h != 'H5' else math.hypot(params['sd1'], SENT_SD)
        members[h] = (apply_swing(M0, cols, d), 0.6 if h == 'H5' else 1.0, max(0.02, sd))
    if model is not None:
        trend = ge if ge else ((L['year'], L['month']), {p: sL.get(p, 0) + params['kappa'] * m.get(p, 0) for p in parties})
        X4, _, meta4, cols4 = F.features(st, L, prev2, trend, sl, seats, expected[0])
        if cols4 == cols and len(X4) == len(X):
            _, M4 = F.shares_matrix(model.predict(X4), meta4, cols4)
            c = F.cached() or {}
            members['H4'] = (M4, 1.0, max(0.02, (c.get('noise') or {}).get('state_sd', 0.06)))
    months_left = max(0, _key(*expected) - nowk)
    drift = DRIFT_PER_YEAR * math.sqrt(months_left / 12)
    ranges, weights = mixture(members, cols, sd_seat, drift, n=sims)
    try:
        import elections
        for r in ranges:
            r['name'], r['color'] = ('Others and independents', '#8A96A3') if r['code'] == 'OTH' else elections.party_info(r['code'])
    except Exception:
        pass
    ranges = [r for r in ranges if r['hi'] > 0 or r['code'] != 'OTH']
    ranges.sort(key=lambda r: (r['code'] == 'OTH', -r['median'], -r['hi']))
    total = L['seats'] or len(sl)
    return {'status': 'ready', 'state': st, 'expected': f'{expected[0]}-{expected[1]:02d}', 'months_left': months_left,
            'seats_total': total, 'majority': total // 2 + 1, 'ranges': ranges,
            'hypotheses': _hyp_table(ranges, weights, {}, {}),
            'significance': significance(ranges, total // 2 + 1),
            'signals': {'mood_elections': n_events, 'mood': {p: round(m.get(p, 0) * 100, 1) for p in parties if p in m},
                        'lok_sabha': f'{ge[0][0]}' if ge else None, 'term_elapsed': round(frac, 2), 'incumbent': inc,
                        'coverage': tone, 'coverage_used': use_tone},
            'drift_sd': round(drift, 4)}


def national_pulse(ae, ge_shares, seats, evts, params, nowk, sd_seat, news_db, now, sims):
    import numpy as np
    ges = sorted([e for e in seats if e.startswith('GE-')], key=lambda x: int(x[3:]))
    if not ges:
        return {'status': 'no_history'}
    gid = ges[-1]; gy = int(gid[3:])
    gk = _key(gy, 6)
    rows = sorted(seats[gid].items())
    nat = F.state_shares([s for _, s in rows])
    parties = [p for p in sorted(nat, key=lambda p: -nat[p]) if p not in F.NOT_PARTIES and nat[p] >= 0.01][:12]
    cols = parties + ['OTH']
    M0 = np.array([[s['shares'].get(p, 0.0) for p in parties] + [max(0.0, 1 - sum(s['shares'].get(p, 0.0) for p in parties))] for _, s in rows])
    states = sorted({st for (st, _), _ in rows}); si = {s: i for i, s in enumerate(states)}
    groups = np.array([si[st] for (st, _), _ in rows])
    m, n_events = mood(evts, nowk, since=gk)
    wins = F.seat_winners([s for _, s in rows]); inc = max(wins, key=wins.get)
    expected = (gy + 5, 5)
    frac = min(1.0, max(0.0, (nowk - gk) / 60))
    members = {}
    sw1 = {p: params['kappa'] * m.get(p, 0.0) for p in parties}
    members['H1'] = (apply_swing(M0, cols, sw1), 1.0, params['sd1'] * 0.7)
    # H2: each state's own assembly swing since the Lok Sabha election, where it has voted; national mood elsewhere
    M2 = M0.copy(); own = 0
    for st in states:
        lst = ae.get(st, [])
        after = [a for a in lst if _key(a['year'], a['month']) > gk]
        if not after:
            d = sw1
        else:
            b = after[-1]; a = [x for x in lst if _key(x['year'], x['month']) < _key(b['year'], b['month'])]
            if not a:
                d = sw1
            else:
                own += 1
                sa = F.state_shares(seats[a[-1]['id']].values()); sb = F.state_shares(seats[b['id']].values())
                d = {p: params['lambda'] * (sb.get(p, 0) - sa.get(p, 0)) for p in parties}
        idx = groups == si[st]
        M2[idx] = apply_swing(M0[idx], cols, d)
    members['H2'] = (M2, 1.0, params['sd2'] * 0.7)
    bi, bs, b0 = params['beta']
    members['H3'] = (apply_swing(M0, cols, {p: frac * (bi * (1.0 if p == inc else 0.0) + bs * nat.get(p, 0) + b0) for p in parties}), 1.0, max(0.02, params['sd3'] * 0.7 * max(frac, .3)))
    tone = coverage_tone(news_db, parties, None, now) if news_db else {}
    use_tone = sum(t['recent'] for t in tone.values()) >= SENT_MIN_ARTICLES and len(tone) >= 2
    if use_tone:
        mean = sum(t['delta'] for t in tone.values()) / len(tone)
        members['H5'] = (apply_swing(M0, cols, {p: sw1[p] + (SENT_GAIN * (tone[p]['delta'] - mean) if p in tone else 0) for p in parties}), 0.6, math.hypot(params['sd1'] * 0.7, SENT_SD))
    months_left = max(0, _key(*expected) - nowk)
    drift = DRIFT_PER_YEAR * math.sqrt(months_left / 12)
    ranges, weights = mixture(members, cols, sd_seat, drift, n=sims, groups=groups)
    try:
        import elections
        for r in ranges:
            r['name'], r['color'] = ('Others and independents', '#8A96A3') if r['code'] == 'OTH' else elections.party_info(r['code'])
    except Exception:
        pass
    ranges = [r for r in ranges if r['hi'] > 0 or r['code'] != 'OTH']
    ranges.sort(key=lambda r: (r['code'] == 'OTH', -r['median'], -r['hi']))
    total = max(len(rows), 543)        # Surat 2024 was decided unopposed, so it has no vote row
    return {'status': 'ready', 'state': '', 'expected': f'{expected[0]}-{expected[1]:02d}', 'months_left': months_left,
            'seats_total': total, 'majority': total // 2 + 1, 'ranges': ranges,
            'hypotheses': _hyp_table(ranges, weights, HYP_NATIONAL, {}),
            'significance': significance(ranges, total // 2 + 1),
            'signals': {'mood_elections': n_events, 'mood': {p: round(m.get(p, 0) * 100, 1) for p in parties if p in m},
                        'states_with_own_swing': own, 'term_elapsed': round(frac, 2), 'incumbent': inc,
                        'coverage': tone, 'coverage_used': use_tone, 'base': gid},
            'drift_sd': round(drift, 4)}


# ------------------------------------------------------------------ cache + job
_lock = threading.Lock()
_job = {'state': 'idle', 'step': '', 'error': None}
REFRESH_HOURS = 6


def _cache_path():
    return DATA_DIR / 'pulse.json'


def cached(max_age_h=REFRESH_HOURS):
    try:
        d = json.loads(_cache_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if d.get('model') != MODEL_VERSION or d.get('pack') != F._pack_stamp():
        return None
    d['_stale'] = time.time() - d.get('_t', 0) > max_age_h * 3600
    return d


def start(news_db=None, force=False):
    with _lock:
        if _job['state'] == 'running':
            return False
        _job.update(state='running', step='Starting', error=None)

    def work():
        try:
            d = run(DATA_DIR / 'elections.sqlite3', news_db=news_db, progress=lambda s: _job.update(step=s))
            d['pack'] = F._pack_stamp(); d['_t'] = time.time()
            tmp = _cache_path().with_suffix('.tmp'); tmp.write_text(json.dumps(d), encoding='utf-8'); tmp.replace(_cache_path())
            _job.update(state='done', step='')
        except Exception as exc:
            _job.update(state='error', error=f'{type(exc).__name__}: {exc}'[:300])
    threading.Thread(target=work, name='election-pulse', daemon=True).start()
    return True


METHOD = ('Pulse: an ensemble of simple hypotheses about how votes move between elections, each fitted on past '
          'results and simulated with its own error, plus drift for the months left; the simulations are pooled. '
          'The variance split uses the law of total variance.')
DISCLAIMER = 'A pulse of today\'s signals, not a poll and not a prediction of who will win. Far from an election, it mostly says how uncertain things are.'


def for_scope(state, news_db=None, hidden=(), force=False):
    base = {'state': state, 'method': METHOD, 'disclaimer': DISCLAIMER, 'model': MODEL_VERSION,
            'hypothesis_notes': {k: v[1] for k, v in HYPOTHESES.items()}}
    if 'projection' in hidden:
        return {**base, 'status': 'hidden', 'message': 'Projections are hidden during the Election Commission\'s silence period.'}
    if not F.numpy_ok():
        return {**base, 'status': 'needs_numpy', 'message': 'The pulse needs numpy, which comes with the language-model pack.'}
    if not (DATA_DIR / 'elections.sqlite3').exists():
        return {**base, 'status': 'needs_pack', 'message': 'Download the results pack first.'}
    d = cached()
    if force or not d or d.get('_stale'):
        start(news_db, force)
    if not d:
        return {**base, 'status': 'computing', 'step': _job.get('step') or 'Starting',
                'error': _job.get('error') if _job['state'] == 'error' else None,
                'message': 'Reading today\'s signals and fitting the pulse. This takes about a minute.'}
    rec = d['national'] if not state else d['states'].get(state)
    if not rec:
        return {**base, 'status': 'none', 'message': 'No pulse for this election: it is either close enough for the seat model or has no history.'}
    out = {**base, **rec, 'backtest': d['backtest'], 'params': d['params'], 'generated': d['generated'],
           'updating': _job['state'] == 'running', 'step': _job.get('step') if _job['state'] == 'running' else None}
    if out.get('status') == 'ready':
        out['trust'] = {'label': d['backtest']['label'], 'note': 'Backtest covers H1 to H3 a year before past state elections. '
                        'H4 is backtested in the seat model; H5 is not backtested.'}
    return out
