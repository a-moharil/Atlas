"""Seat ranges for upcoming assembly elections: a small bagging + boosting ensemble.

What it learns from: past assembly results only (TCPD / in-rolls, 2008 onward). For every seat and every
significant party it predicts that party's vote share at the next election from what happened last time:
the seat's own shares one and two elections back, the state-wide shares, the swing seen in the Lok Sabha
election held in between, who governed, how close the seat was, turnout, the number of candidates, and
reserved-seat status. News-coverage embeddings are deliberately not used yet: they join the feature set
once Sanjaya has archived coverage for a full election cycle.

Two tree ensembles are averaged: bagging (deep trees on bootstrap samples, feature subsampling) and
gradient boosting (shallow trees, shrinkage, row subsampling). Both are written with numpy only.

Ranges come from simulation: state-wide and seat-level errors are drawn from the model's own
rolling-origin backtest residuals, and the 10th-90th percentile of simulated seat totals is shown.
The trust label comes from that same backtest. This is a model, not a poll; it never calls a winner.
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import sqlite3
import threading
import time
from pathlib import Path

MODEL_VERSION = 'ens-1'
TERM_YEARS = 5
SHOW_WITHIN_MONTHS = 6          # closer than this: show ranges. Further: "wait for more data".
COMPUTE_WITHIN_MONTHS = 14      # precompute a little ahead so the cache stays useful
MIN_STATE_SHARE = 0.02
MIN_GE_SHARE = 0.03
MAX_PARTIES = 8
NOT_PARTIES = {'IND', 'NOTA', 'OTH'}
CANON = {'ADS': 'ADAL', 'AAP': 'AAAP', 'AIADMK': 'ADMK', 'TRS': 'BRS', 'JKNC': 'JKN', 'RLTP': 'RaLtP', 'NPP': 'NPEP'}
BAG = dict(trees=60, depth=6, min_leaf=30, feat_frac=0.7)
BOOST = dict(rounds=150, depth=3, min_leaf=30, lr=0.08, subsample=0.8)
SIMS = 1000
FEATURES = ['share_1', 'share_2', 'has_2', 'state_1', 'state_2', 'trend_ls', 'has_ls', 'incumbent', 'rank_1',
            'lead_1', 'n_cand', 'turnout', 'reserved_sc', 'reserved_st', 'enp', 'is_others', 'gap_years']

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'election_data'


def canon(c):
    return CANON.get(c, c)


def numpy_ok():
    try:
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


# ------------------------------------------------------------------ data
def _norm(n):
    return ''.join(ch for ch in str(n or '').lower().replace('(sc)', '').replace('(st)', '') if ch.isalnum())


def same_seat(a, b):
    a, b = _norm(a), _norm(b)
    return bool(a) and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.6)


def load(db_path):
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    els = [dict(r) for r in con.execute('select * from elections order by year, month')]
    seats = {}
    for r in con.execute('select election, state, no, name, type, turnout, n_cand, party_votes from seats'):
        try:
            pv = json.loads(r['party_votes'] or '{}')
        except ValueError:
            pv = {}
        votes = {}
        for k, v in pv.items():
            if k == 'NOTA':
                continue
            c = canon(k) if len(k) <= 12 else 'OTH'
            votes[c] = votes.get(c, 0) + (v or 0)
        tot = sum(votes.values())
        if tot <= 0:
            continue
        seats.setdefault(r['election'], {})[(r['state'], r['no'])] = {
            'name': r['name'], 'type': r['type'] or '', 'turnout': r['turnout'], 'n_cand': r['n_cand'] or 0,
            'shares': {k: v / tot for k, v in votes.items()}, 'votes': votes, 'total': tot}
    con.close()
    return els, seats


def state_shares(seat_rows):
    votes, tot = {}, 0
    for s in seat_rows:
        for k, v in s['votes'].items():
            votes[k] = votes.get(k, 0) + v
        tot += s['total']
    return {k: v / tot for k, v in votes.items()} if tot else {}


def seat_winners(seat_rows):
    out = {}
    for s in seat_rows:
        w = max(s['shares'], key=s['shares'].get)
        out[w] = out.get(w, 0) + 1
    return out


def history(els, seats):
    """Per state: assembly elections in order, and Lok Sabha state shares by (year, month)."""
    ae, ge = {}, []
    for e in els:
        if e['kind'] == 'AE' and e['id'] in seats:
            ae.setdefault(e['state'], []).append(e)
        elif e['kind'] == 'GE' and e['id'] in seats:
            ge.append(e)
    ge_shares = {}
    for g in ge:
        by_state = {}
        for (st, _), s in seats[g['id']].items():
            by_state.setdefault(st, []).append(s)
        for st, rows in by_state.items():
            ge_shares.setdefault(st, []).append(((g['year'], g['month'] or 5), state_shares(rows)))
    return ae, ge_shares


def _mkey(y, m):
    return y * 12 + (m or 1) - 1


def party_set(st1, ge):
    cand = {p: max(st1.get(p, 0), ge.get(p, 0) if ge else 0) for p in set(st1) | set(ge or {})
            if p not in NOT_PARTIES and (st1.get(p, 0) >= MIN_STATE_SHARE or (ge or {}).get(p, 0) >= MIN_GE_SHARE)}
    return sorted(cand, key=lambda p: -cand[p])[:MAX_PARTIES]


def features(state, prev, prev2, ge, seat_list, seats, target_year, target_seats=None):
    """Rows of (seat, party) features. seat_list: [(no, name, type)] of the election being predicted.
    target_seats: the actual results (training/backtest) or None (forecast)."""
    p1 = seats[prev['id']]
    p2 = seats.get(prev2['id']) if prev2 else None
    s1 = state_shares(p1.values())
    s2 = state_shares(p2.values()) if p2 else {}
    ge_sh = ge[1] if ge else None
    parties = party_set(s1, ge_sh)
    wins = seat_winners(p1.values())
    incumbent = max(wins, key=wins.get) if wins else None
    cols = parties + ['OTH']
    X, Y, meta = [], [], []
    for no, name, typ in seat_list:
        a = p1.get((state, no))
        if not a or not same_seat(a['name'], name):
            continue
        b = p2.get((state, no)) if p2 else None
        if b and not same_seat(b['name'], name):
            b = None
        t = None
        if target_seats is not None:
            t = target_seats.get((state, no))
            if not t:
                continue
        sh1 = {p: a['shares'].get(p, 0.0) for p in parties}
        sh1['OTH'] = max(0.0, 1 - sum(sh1.values()))
        sh2 = None
        if b:
            sh2 = {p: b['shares'].get(p, 0.0) for p in parties}
            sh2['OTH'] = max(0.0, 1 - sum(sh2.values()))
        order = sorted(cols, key=lambda p: -sh1[p])
        enp = 1.0 / max(1e-9, sum(v * v for v in a['shares'].values()))
        st1o = max(0.0, 1 - sum(s1.get(p, 0) for p in parties))
        st2o = max(0.0, 1 - sum(s2.get(p, 0) for p in parties)) if s2 else 0.0
        for p in cols:
            o = p == 'OTH'
            st1v = st1o if o else s1.get(p, 0.0)
            st2v = (st2o if o else s2.get(p, 0.0)) if s2 else st1v
            gev = (max(0.0, 1 - sum(ge_sh.get(q, 0) for q in parties)) if o else ge_sh.get(p, 0.0)) if ge_sh else None
            best_other = max(sh1[q] for q in cols if q != p)
            X.append([sh1[p], sh2[p] if sh2 else st2v, 1.0 if sh2 else 0.0, st1v, st2v,
                      (gev - st1v) if gev is not None else 0.0, 1.0 if gev is not None else 0.0,
                      1.0 if p == incumbent else 0.0, float(order.index(p) + 1), sh1[p] - best_other,
                      float(a['n_cand']), (a['turnout'] or 0) / 100.0, 1.0 if typ == 'SC' else 0.0,
                      1.0 if typ == 'ST' else 0.0, enp, 1.0 if o else 0.0, float(target_year - prev['year'])])
            if t is not None:
                Y.append(max(0.0, 1 - sum(t['shares'].get(q, 0) for q in parties)) if o else t['shares'].get(p, 0.0))
            meta.append((no, p))
    return X, Y, meta, cols


def tasks(ae, ge_shares, seats):
    """Every past assembly election that has a previous one to learn from."""
    out = []
    for st, lst in ae.items():
        for i in range(1, len(lst)):
            prev, cur = lst[i - 1], lst[i]
            prev2 = lst[i - 2] if i >= 2 else None
            out.append((st, prev, prev2, cur, _ge_between(ge_shares.get(st), prev, cur['year'], cur['month'])))
    return out


def _ge_between(lst, prev, year, month):
    lo, hi = _mkey(prev['year'], prev['month']), _mkey(year, month)
    best = None
    for (gy, gm), sh in lst or []:
        if lo < _mkey(gy, gm) < hi:
            best = ((gy, gm), sh)
    return best


def seat_list_of(seats_by_key, state):
    return sorted(((no, s['name'], s['type']) for (st, no), s in seats_by_key.items() if st == state))


# ------------------------------------------------------------------ trees (numpy)
class Binner:
    def __init__(self, X, bins=32):
        import numpy as np
        self.edges = [np.unique(np.quantile(X[:, j], np.linspace(0, 1, bins + 1)[1:-1])) for j in range(X.shape[1])]

    def __call__(self, X):
        import numpy as np
        return np.stack([np.searchsorted(e, X[:, j], side='right') for j, e in enumerate(self.edges)], 1).astype(np.int32)


def fit_tree(Xb, y, idx, depth, min_leaf, feat_frac, rng, nbins=33):
    import numpy as np
    nf = Xb.shape[1]
    feat, thr, left, right, val = [], [], [], [], []

    def node(ix, d):
        k = len(feat)
        feat.append(-1); thr.append(0); left.append(-1); right.append(-1); val.append(float(y[ix].mean()))
        if d >= depth or len(ix) < 2 * min_leaf:
            return k
        fs = rng.choice(nf, max(1, int(round(nf * feat_frac))), replace=False) if feat_frac < 1 else range(nf)
        yy, S, N = y[ix], y[ix].sum(), len(ix)
        best = (1e-12, None, None)
        for f in fs:
            col = Xb[ix, f]
            cnt = np.bincount(col, minlength=nbins).astype(float)
            sm = np.bincount(col, weights=yy, minlength=nbins)
            nl, sl = np.cumsum(cnt)[:-1], np.cumsum(sm)[:-1]
            nr, sr = N - nl, S - sl
            ok = (nl >= min_leaf) & (nr >= min_leaf)
            if not ok.any():
                continue
            gain = np.where(ok, sl * sl / np.maximum(nl, 1) + sr * sr / np.maximum(nr, 1) - S * S / N, -1)
            b = int(gain.argmax())
            if gain[b] > best[0]:
                best = (gain[b], f, b)
        if best[1] is None:
            return k
        f, b = best[1], best[2]
        m = Xb[ix, f] <= b
        feat[k], thr[k] = int(f), int(b)
        left[k] = node(ix[m], d + 1)
        right[k] = node(ix[~m], d + 1)
        return k

    node(idx, 0)
    return (np.array(feat), np.array(thr), np.array(left), np.array(right), np.array(val))


def predict_tree(t, Xb):
    import numpy as np
    feat, thr, left, right, val = t
    n = np.zeros(len(Xb), dtype=np.int64)
    for _ in range(64):
        f = feat[n]
        leaf = f < 0
        if leaf.all():
            break
        go_left = Xb[np.arange(len(Xb)), np.where(leaf, 0, f)] <= thr[n]
        n = np.where(leaf, n, np.where(go_left, left[n], right[n]))
    return val[n]


class Ensemble:
    def __init__(self, seed=7, bag=None, boost=None):
        self.seed, self.bag_cfg, self.boost_cfg = seed, dict(bag or BAG), dict(boost or BOOST)

    def fit(self, X, y):
        import numpy as np
        rng = np.random.default_rng(self.seed)
        X, y = np.asarray(X, float), np.asarray(y, float)
        self.binner = Binner(X)
        Xb = self.binner(X)
        n = len(y)
        c = self.bag_cfg
        self.bag = [fit_tree(Xb, y, rng.integers(0, n, n), c['depth'], c['min_leaf'], c['feat_frac'], rng) for _ in range(c['trees'])]
        c = self.boost_cfg
        self.base = float(y.mean())
        pred = np.full(n, self.base)
        self.boost = []
        for _ in range(c['rounds']):
            r = y - pred
            ix = rng.choice(n, int(n * c['subsample']), replace=False)
            t = fit_tree(Xb, r, ix, c['depth'], c['min_leaf'], 1.0, rng)
            self.boost.append(t)
            pred += c['lr'] * predict_tree(t, Xb)
        return self

    def predict(self, X):
        import numpy as np
        Xb = self.binner(np.asarray(X, float))
        bag = np.mean([predict_tree(t, Xb) for t in self.bag], 0)
        boost = self.base + self.boost_cfg['lr'] * np.sum([predict_tree(t, Xb) for t in self.boost], 0)
        return 0.5 * bag + 0.5 * boost


# ------------------------------------------------------------------ seats from shares
def shares_matrix(pred, meta, cols):
    import numpy as np
    seats_no = sorted({m[0] for m in meta})
    si = {s: i for i, s in enumerate(seats_no)}
    ci = {c: j for j, c in enumerate(cols)}
    M = np.zeros((len(seats_no), len(cols)))
    for v, (s, p) in zip(pred, meta):
        M[si[s], ci[p]] = v
    M = np.clip(M, 0, None)
    M /= np.maximum(M.sum(1, keepdims=True), 1e-9)
    return seats_no, M


def simulate(M, sd_state, sd_seat, sims=SIMS, seed=11):
    """Monte Carlo seat totals. OTH is a residual bloc: its seats are reported, never as a party."""
    import numpy as np
    rng = np.random.default_rng(seed)
    S, P = M.shape
    tot = np.zeros((sims, P), dtype=np.int32)
    for k in range(0, sims, 100):
        b = min(100, sims - k)
        noise = rng.normal(0, sd_state, (b, 1, P)) + rng.normal(0, sd_seat, (b, S, P))
        win = (M[None] + noise).argmax(2)
        for j in range(P):
            tot[k:k + b, j] = (win == j).sum(1)
    return tot


def ranges(tot, cols, lo=10, hi=90):
    import numpy as np
    out = []
    for j, c in enumerate(cols):
        v = tot[:, j]
        out.append({'code': c, 'lo': int(np.percentile(v, lo)), 'median': int(np.percentile(v, 50)), 'hi': int(np.percentile(v, hi))})
    return out


# ------------------------------------------------------------------ backtest + trust
def trust_label(acc, cov):
    if acc is None:
        return 'Low'
    if acc < 0.65 or (cov is not None and cov < 0.5):
        return 'Low'
    if acc >= 0.8 and (cov is None or cov >= 0.7):
        return 'High'
    return 'Medium'


def _residuals(pred, Y, meta, cols):
    """Split errors into a state-wide part (per party) and what is left at seat level."""
    import numpy as np
    seats_no, P = shares_matrix(pred, meta, cols)
    _, A = shares_matrix(Y, meta, cols)
    E = A - P
    state_err = E.mean(0)
    return state_err, (E - state_err).ravel(), seats_no, P, A


def run(db_path, now=None, progress=None, bag=None, boost=None, sims=SIMS):
    import numpy as np
    t0 = time.time()
    els, seats = load(db_path)
    ae, ge_shares = history(els, seats)
    all_tasks = tasks(ae, ge_shares, seats)

    def rows(task):
        st, prev, prev2, cur, ge = task
        sl = seat_list_of(seats[cur['id']], st)
        return features(st, prev, prev2, ge, sl, seats, cur['year'], seats[cur['id']])

    built = []
    for task in all_tasks:
        X, Y, meta, cols = rows(task)
        if len(X) >= 20:
            built.append((task, X, Y, meta, cols))
    years = sorted({t[0][3]['year'] for t in built})
    test_years = [y for y in years if y >= 2017]
    pool_state, pool_seat = [], []
    bt, per_state = [], {}
    for k, Yr in enumerate(test_years):
        if progress:
            progress(f'Backtest {k + 1} of {len(test_years)}: training on results before {Yr}')
        train = [b for b in built if b[0][3]['year'] < Yr]
        test = [b for b in built if b[0][3]['year'] == Yr]
        if not train or not test:
            continue
        Xtr = np.concatenate([np.asarray(b[1], float) for b in train])
        Ytr = np.concatenate([np.asarray(b[2], float) for b in train])
        model = Ensemble(bag=bag, boost=boost).fit(Xtr, Ytr)
        if pool_seat:
            sd_state, sd_seat = float(np.std(pool_state)), float(np.std(pool_seat))
        else:      # no earlier out-of-sample errors yet: inflate in-sample error
            ins = model.predict(Xtr) - Ytr
            sd_state, sd_seat = 0.03, float(np.std(ins) * 1.5)
        new_state, new_seat = [], []
        for (task, X, Y, meta, cols) in test:
            pred = model.predict(X)
            state_err, seat_err, seats_no, P, A = _residuals(pred, Y, meta, cols)
            new_state.extend(state_err[:-1].tolist()); new_seat.extend(seat_err.tolist())
            calls = float((P.argmax(1) == A.argmax(1)).mean())
            _, H = shares_matrix(np.asarray(X, float)[:, FEATURES.index('share_1')], meta, cols)
            held = float((H.argmax(1) == A.argmax(1)).mean())      # baseline: every seat stays with last winner
            actual = np.bincount(A.argmax(1), minlength=len(cols))
            tot = simulate(P, sd_state, sd_seat, sims=400)
            rg = ranges(tot, cols)
            named = [j for j, c in enumerate(cols) if c != 'OTH' and (actual[j] > 0 or rg[j]['hi'] > 0)]
            covered = [rg[j]['lo'] <= actual[j] <= rg[j]['hi'] for j in named]
            point = np.bincount(P.argmax(1), minlength=len(cols))
            seat_err_total = float(np.abs(point - actual).sum() / 2 / max(1, len(seats_no)))
            rec = {'state': task[0], 'year': Yr, 'seats': len(seats_no), 'call_accuracy': round(calls, 3),
                   'coverage': round(float(np.mean(covered)), 3) if covered else None,
                   'seat_total_error': round(seat_err_total, 3), 'baseline_accuracy': round(held, 3)}
            bt.append(rec)
            per_state.setdefault(task[0], []).append(rec)
        pool_state.extend(new_state); pool_seat.extend(new_seat)

    def wavg(key):
        vals = [(r[key], r['seats']) for r in bt if r.get(key) is not None]
        return round(sum(v * w for v, w in vals) / sum(w for _, w in vals), 3) if vals else None

    summary = {'elections': len(bt), 'call_accuracy': wavg('call_accuracy'), 'coverage': wavg('coverage'),
               'seat_total_error': wavg('seat_total_error'), 'baseline_accuracy': wavg('baseline_accuracy'), 'years': f'{test_years[0]}–{test_years[-1]}' if test_years else ''}
    summary['label'] = trust_label(summary['call_accuracy'], summary['coverage'])

    # production model: everything we have
    if progress:
        progress('Training on all results')
    Xall = np.concatenate([np.asarray(b[1], float) for b in built])
    Yall = np.concatenate([np.asarray(b[2], float) for b in built])
    model = Ensemble(bag=bag, boost=boost).fit(Xall, Yall)
    sd_state = float(np.std(pool_state)) if pool_state else 0.04
    sd_seat = float(np.std(pool_seat)) if pool_seat else 0.08

    now = now or dt.datetime.now(dt.timezone.utc)
    nowk = _mkey(now.year, now.month)
    states = {}
    for st, lst in ae.items():
        last = lst[-1]
        exp_y, exp_m = last['year'] + TERM_YEARS, last['month'] or 1
        away = _mkey(exp_y, exp_m) - nowk
        rec = {'state': st, 'last': last['id'], 'expected': f'{exp_y}-{exp_m:02d}', 'months_away': away,
               'seats_total': last['seats'], 'majority': last['seats'] // 2 + 1}
        if away <= COMPUTE_WITHIN_MONTHS and away > -6:
            prev2 = lst[-2] if len(lst) >= 2 else None
            ge = _ge_between(ge_shares.get(st), last, exp_y, exp_m)
            sl = seat_list_of(seats[last['id']], st)
            X, _, meta, cols = features(st, last, prev2, ge, sl, seats, exp_y)
            if len(X) >= 20:
                pred = model.predict(X)
                seats_no, M = shares_matrix(pred, meta, cols)
                tot = simulate(M, sd_state, sd_seat, sims=sims)
                rg = [r for r in ranges(tot, cols) if r['hi'] > 0 or r['code'] != 'OTH']
                rg.sort(key=lambda r: (r['code'] == 'OTH', -r['median'], -r['hi']))
                share = dict(zip(cols, (M.mean(0) * 100).round(1).tolist()))
                for r in rg:
                    r['seat_avg_share'] = share.get(r['code'])
                own = per_state.get(st, [])
                own_acc = round(sum(r['call_accuracy'] for r in own) / len(own), 3) if own else None
                own_cov = [r['coverage'] for r in own if r['coverage'] is not None]
                own_cov = round(sum(own_cov) / len(own_cov), 3) if own_cov else None
                label = summary['label']
                if own:
                    tiers = ['Low', 'Medium', 'High']
                    label = tiers[min(tiers.index(label), tiers.index(trust_label(own_acc, own_cov)))]
                rec.update(ranges=rg, seats_modelled=len(seats_no), lok_sabha_trend=f'{ge[0][0]}' if ge else None,
                           previous_two=[x['id'] for x in ([prev2] if prev2 else []) + [last]],
                           trust={'label': label, 'state_backtest': own, 'state_call_accuracy': own_acc, 'state_coverage': own_cov})
        states[st] = rec
    return {'model': MODEL_VERSION, 'generated': now.strftime('%Y-%m-%dT%H:%MZ'), 'seconds': round(time.time() - t0, 1),
            'backtest': summary, 'backtest_rows': bt, 'noise': {'state_sd': round(sd_state, 4), 'seat_sd': round(sd_seat, 4)},
            'training_rows': int(len(Yall)), 'states': states,
            'config': {'bagging': dict(bag or BAG), 'boosting': dict(boost or BOOST), 'simulations': sims,
                       'features': FEATURES}}


# ------------------------------------------------------------------ cache + background job
_lock = threading.Lock()
_job = {'state': 'idle', 'step': '', 'error': None}


def _cache_path():
    return DATA_DIR / 'forecast.json'


def _pack_stamp():
    try:
        m = json.loads((DATA_DIR / 'manifest.json').read_text(encoding='utf-8'))
        return str(m.get('built') or m.get('built_at') or m.get('version') or '') + '|' + str((DATA_DIR / 'elections.sqlite3').stat().st_mtime_ns)
    except (OSError, ValueError):
        return ''


def cached():
    try:
        d = json.loads(_cache_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if d.get('model') != MODEL_VERSION or d.get('pack') != _pack_stamp():
        return None
    return d


def start():
    with _lock:
        if _job['state'] == 'running':
            return False
        _job.update(state='running', step='Starting', error=None)

    def work():
        try:
            d = run(DATA_DIR / 'elections.sqlite3', progress=lambda s: _job.update(step=s))
            d['pack'] = _pack_stamp()
            tmp = _cache_path().with_suffix('.tmp')
            tmp.write_text(json.dumps(d), encoding='utf-8')
            tmp.replace(_cache_path())
            _job.update(state='done', step='')
        except Exception as exc:
            _job.update(state='error', error=f'{type(exc).__name__}: {exc}'[:300])
    threading.Thread(target=work, name='election-forecast', daemon=True).start()
    return True


METHOD = ('Bagging (60 trees, depth 6) and gradient boosting (150 shallow trees) averaged, trained on every '
          'assembly result since 2008. Features: each seat\'s party shares one and two elections back, state-wide '
          'shares, the swing in the Lok Sabha election held in between, incumbency, margin, turnout, candidates and '
          'reserved-seat status. Ranges: 10th to 90th percentile of 1,000 simulations whose errors are drawn from the '
          'model\'s own backtest. News coverage is not used yet.')
DISCLAIMER = ('A statistical model, not a poll and not a prediction of who will win. It knows nothing about '
              'candidates, alliances or campaigns that are not in past results.')


def for_state(state, now=None, hidden=(), force=False):
    """What the Elections page shows for one state's next election."""
    now = now or dt.datetime.now(dt.timezone.utc)
    base = {'state': state, 'method': METHOD, 'disclaimer': DISCLAIMER, 'model': MODEL_VERSION}
    if 'projection' in hidden:
        return {**base, 'status': 'hidden',
                'message': 'Projections are hidden during the Election Commission\'s silence period for this state.'}
    if not numpy_ok():
        return {**base, 'status': 'needs_numpy',
                'message': 'Forecasts need numpy, which comes with the language-model pack. Install it with install_language_model.bat (Windows) or pip install numpy.'}
    if not (DATA_DIR / 'elections.sqlite3').exists():
        return {**base, 'status': 'needs_pack', 'message': 'Download the results pack first.'}
    d = cached()
    if force:
        start()
    if not d:
        start()
        return {**base, 'status': 'computing', 'step': _job.get('step') or 'Starting',
                'error': _job.get('error') if _job['state'] == 'error' else None,
                'message': 'Training the forecast model on past results. This takes a minute or two, once per results pack.'}
    rec = d['states'].get(state)
    if not rec:
        return {**base, 'status': 'no_history', 'message': 'Sanjaya needs at least two past assembly elections for this state.'}
    nowk = _mkey(now.year, now.month)
    ey, em = (int(x) for x in rec['expected'].split('-'))
    away = _mkey(ey, em) - nowk
    out = {**base, **{k: v for k, v in rec.items() if k not in ('ranges', 'trust')}, 'months_away': away,
           'updating': _job['state'] == 'running', 'step': _job.get('step') if _job['state'] == 'running' else None,
           'backtest': d['backtest'], 'generated': d['generated'], 'noise': d['noise']}
    if away > SHOW_WITHIN_MONTHS:
        out.update(status='waiting', message='Wait for more data. Ranges appear about six months before the expected poll, '
                                             'once the most recent results and Lok Sabha swing are as close as they will get.')
        return out
    if away < -3 or 'ranges' not in rec:
        out.update(status='stale', message='The expected poll date has passed. Download the results pack again to add the new results.')
        return out
    try:
        import elections
        for r in rec['ranges']:
            r['name'], r['color'] = ('Others and independents', '#8A96A3') if r['code'] == 'OTH' else elections.party_info(r['code'])
    except Exception:
        pass
    out.update(status='ready', ranges=rec['ranges'], trust=rec['trust'], seats_modelled=rec.get('seats_modelled'),
               lok_sabha_trend=rec.get('lok_sabha_trend'), previous_two=rec.get('previous_two'))
    return out


def national(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    return {'status': 'waiting', 'expected': '2029-05', 'months_away': _mkey(2029, 5) - _mkey(now.year, now.month),
            'method': METHOD, 'disclaimer': DISCLAIMER,
            'message': 'Wait for more data. Sanjaya models assembly elections first; a Lok Sabha model needs the 2027–29 '
                       'assembly round and archived coverage before it is worth showing.'}
