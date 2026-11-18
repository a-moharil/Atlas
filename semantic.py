"""ATLAS v5.1 · grouping by meaning with a small local multilingual model.

* Model: ``sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`` run through
  fastembed (ONNX Runtime, CPU only, no PyTorch). About 220 MB, 384 dimensions,
  50+ languages including Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, Urdu.
* Text embedded: the headline (without the trailing " - Publisher") plus the first
  part of the feed excerpt. Full articles are never fetched.
* Vectors are stored once per article in SQLite (``embeddings``), computed in the
  background after each collection with a capped thread count so the laptop stays
  responsive.
* Grouping: pairs above a cosine threshold inside a time window are merged strongest
  first, but two groups only merge when their centroids are also similar. This stops
  "chaining" (A≈B, B≈C, but A≠C) from gluing separate events together.
* If fastembed/numpy are not installed, the model is still downloading, or too few
  articles are embedded, every caller falls back to keyword matching and says so.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import threading
import time
from contextlib import closing

MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
DIM = 384
DEFAULTS = {'threshold': 0.72, 'window_hours': 72, 'coverage_min': 0.6}
LOCK = threading.RLock()
STATE = {'status': 'not_checked', 'detail': '', 'embedded': 0, 'last_run': None, 'last_batch': 0,
         'rate': None, 'model': MODEL, 'cache_dir': None}
_model = None
_np = None
_cache = {'key': None, 'value': None}
_matrix = {'key': None, 'ids': [], 'mat': None}


# ------------------------------------------------------------------ setup

def available() -> bool:
    global _np
    try:
        import numpy  # noqa: F401
        import fastembed  # noqa: F401
        _np = numpy
        return True
    except Exception:
        return False


def init(con):
    con.executescript('''CREATE TABLE IF NOT EXISTS embeddings(
        id TEXT PRIMARY KEY, model TEXT NOT NULL, vec BLOB NOT NULL, created TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS lm_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);''')
    con.commit()


def settings(con) -> dict:
    out = dict(DEFAULTS)
    try:
        for k, v in con.execute('SELECT key,value FROM lm_settings'):
            if k in ('threshold', 'coverage_min'):
                out[k] = min(0.95, max(0.5, float(v))) if k == 'threshold' else float(v)
            elif k == 'window_hours':
                out[k] = int(v)
            else:
                out[k] = v
    except Exception:
        pass
    return out


def set_setting(con, key, value):
    allowed = {'threshold', 'window_hours', 'labels_enabled', 'ollama_model', 'ollama_url'}
    if key not in allowed:
        raise ValueError('Unknown setting')
    if key == 'threshold':
        value = f'{min(0.95, max(0.5, float(value))):.3f}'
    if key == 'window_hours' and int(value) not in (24, 48, 72, 120, 168):
        raise ValueError('Window must be 24, 48, 72, 120 or 168 hours')
    if key == 'labels_enabled' and str(value) not in ('0', '1'):
        raise ValueError('labels_enabled must be 0 or 1')
    if key == 'ollama_model' and not re.fullmatch(r'[A-Za-z0-9._:\-/]{2,80}', str(value)):
        raise ValueError('Invalid model name')
    if key == 'ollama_url' and not re.fullmatch(r'http://(127\.0\.0\.1|localhost)(:\d{2,5})?', str(value)):
        raise ValueError('Ollama must run on this computer (http://127.0.0.1:11434)')
    con.execute('INSERT INTO lm_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))
    con.commit()
    with LOCK:
        _cache['key'] = None


def _load_model(cache_dir):
    """Load (downloading on first use) the ONNX model. Runs in a background thread."""
    global _model
    with LOCK:
        if _model is not None or STATE['status'] == 'loading':
            return
        STATE.update(status='loading', detail='Loading the multilingual model (first run downloads about 220 MB)…')
    try:
        from fastembed import TextEmbedding
        threads = max(1, min(4, (os.cpu_count() or 2) // 2))
        m = TextEmbedding(model_name=MODEL, cache_dir=str(cache_dir), threads=threads)
        list(m.embed(['warm-up']))
        with LOCK:
            _model = m
            STATE.update(status='ready', detail=f'Model ready on the processor ({threads} thread{"s" if threads != 1 else ""})')
    except Exception as exc:
        with LOCK:
            STATE.update(status='error', detail=f'{type(exc).__name__}: {str(exc)[:300]}')


def status() -> dict:
    with LOCK:
        return dict(STATE)


def ready() -> bool:
    return _model is not None and _np is not None


# ------------------------------------------------------------------ embedding

def clean(title: str, summary: str = '') -> str:
    t = re.sub(r'\s[-–|]\s[^-–|]{2,60}$', '', title or '').strip()
    s = re.sub(r'\s+', ' ', summary or '').strip()
    if s and s.lower() != t.lower():
        t = f'{t}. {s[:220]}'
    return t[:400]


def embed_pending(db_connect, cache_dir, limit=1500, batch=48) -> int:
    """Embed recent articles that have no vector yet. Safe to call repeatedly."""
    if not available():
        with LOCK:
            STATE.update(status='not_installed', detail='Install the optional language model pack (install_language_model.bat) to group by meaning.')
        return 0
    if _model is None:
        _load_model(cache_dir)
        if _model is None:
            return 0
    with closing(db_connect()) as con:
        init(con)
        rows = con.execute('''SELECT e.id,e.title,e.summary FROM entries e LEFT JOIN embeddings v ON v.id=e.id AND v.model=?
            WHERE e.medium='article' AND v.id IS NULL ORDER BY COALESCE(e.published,e.retrieved) DESC LIMIT ?''', (MODEL, limit)).fetchall()
    done, t0 = 0, time.time()
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        vecs = list(_model.embed([clean(r['title'], r['summary']) for r in chunk], batch_size=batch))
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        out = []
        for r, v in zip(chunk, vecs):
            v = _np.asarray(v, dtype=_np.float32)
            n = float(_np.linalg.norm(v)) or 1.0
            out.append((r['id'], MODEL, (v / n).astype(_np.float32).tobytes(), now))
        with closing(db_connect()) as con:
            con.executemany('INSERT OR REPLACE INTO embeddings VALUES(?,?,?,?)', out)
            con.commit()
        done += len(out)
        time.sleep(0.05)  # yield to the web server between batches
    with closing(db_connect()) as con:
        total = con.execute('SELECT COUNT(*) FROM embeddings WHERE model=?', (MODEL,)).fetchone()[0]
    with LOCK:
        STATE.update(embedded=total, last_run=dt.datetime.now(dt.timezone.utc).isoformat(), last_batch=done,
                     rate=round(done / max(0.001, time.time() - t0), 1) if done else STATE.get('rate'))
        _cache['key'] = None
    return done


_EMBED_LOCK = threading.Lock()


def embed_texts(texts, cache_dir=None):
    """Unit vectors (float32) for arbitrary texts, or None when the model pack is unavailable.
    Used by the research radar; news grouping does not go through here."""
    if not available():
        return None
    if _model is None and cache_dir is not None:
        _load_model(cache_dir)
    if _model is None:
        return None
    texts = [str(t or '')[:2000] for t in texts]
    if not texts:
        return []
    with _EMBED_LOCK:
        raw = list(_model.embed(texts, batch_size=32))
    out = []
    for v in raw:
        v = _np.asarray(v, dtype=_np.float32)
        out.append(v / (float(_np.linalg.norm(v)) or 1.0))
    return out


def vectors(db_connect, ids) -> dict:
    """id -> unit vector for the given ids (only those already embedded)."""
    if _np is None or not ids:
        return {}
    out = {}
    ids = list(ids)
    with closing(db_connect()) as con:
        for i in range(0, len(ids), 900):
            part = ids[i:i + 900]
            q = f"SELECT id,vec FROM embeddings WHERE model=? AND id IN ({','.join('?' for _ in part)})"
            for r in con.execute(q, (MODEL, *part)):
                out[r[0]] = _np.frombuffer(r[1], dtype=_np.float32)
    return out


def _ts(e):
    x = e.get('published') or e.get('retrieved') or ''
    try:
        return dt.datetime.fromisoformat(str(x).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return 0.0


# ------------------------------------------------------------------ grouping

def group(items, vecs, threshold, window_hours):
    """Centroid-guarded agglomeration. ``items`` are dicts with id + published.
    Returns list of groups (lists of indices) and per-group mean similarity."""
    np = _np
    idx = [i for i, e in enumerate(items) if e['id'] in vecs]
    if not idx:
        return [], {}
    M = np.stack([vecs[items[i]['id']] for i in idx])
    S = M @ M.T
    t = np.array([_ts(items[i]) for i in idx])
    near = np.abs(t[:, None] - t[None, :]) <= window_hours * 3600
    S = np.where(near, S, -1.0)
    np.fill_diagonal(S, -1.0)
    a, b = np.where(np.triu(S >= threshold, 1))
    order = np.argsort(-S[a, b])
    parent = list(range(len(idx)))
    sums = {i: M[i].copy() for i in range(len(idx))}
    size = {i: 1 for i in range(len(idx))}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    guard = threshold  # centroids must meet the same bar as single pairs
    for k in order:
        x, y = find(int(a[k])), find(int(b[k]))
        if x == y:
            continue
        sx, sy = sums[x], sums[y]
        c = float(sx @ sy) / ((float(np.linalg.norm(sx)) * float(np.linalg.norm(sy))) or 1.0)
        if c < guard:
            continue
        if size[x] < size[y]:
            x, y = y, x
        parent[y] = x
        sums[x] = sx + sy
        size[x] += size[y]
        del sums[y], size[y]
    groups = {}
    for j in range(len(idx)):
        groups.setdefault(find(j), []).append(j)
    out, cohesion = [], {}
    for root, members in groups.items():
        cen = sums[root] / (float(np.linalg.norm(sums[root])) or 1.0)
        sims = M[members] @ cen
        out.append([idx[m] for m in members])
        cohesion[len(out) - 1] = float(sims.mean())
    return out, cohesion


def story_groups(entries, db_connect, con_settings):
    """Map entry id -> {'group': key, 'similarity': float}. Empty dict = use keywords."""
    if not ready():
        st = STATE.get('status')
        why = ('Language model pack not installed' if not available() else
               'Language model is loading' if st in ('loading', 'not_checked') else f'Language model error: {STATE.get("detail", "")[:120]}')
        return {}, 'keywords', why + '; grouped by headline keywords.'
    arts = [e for e in entries if e.get('medium') == 'article']
    vecs = vectors(db_connect, [e['id'] for e in arts])
    cover = len(vecs) / max(1, len(arts))
    if cover < con_settings['coverage_min']:
        return {}, 'keywords', f'Only {cover:.0%} of articles embedded so far'
    key = (len(arts), len(vecs), arts[0]['id'] if arts else '', con_settings['threshold'], con_settings['window_hours'])
    with LOCK:
        if _cache['key'] == key:
            return _cache['value'], 'meaning', ''
    groups, coh = group(arts, vecs, con_settings['threshold'], con_settings['window_hours'])
    out = {}
    for gi, members in enumerate(groups):
        gid = arts[members[0]]['id']
        for m in members:
            out[arts[m]['id']] = {'group': gid, 'similarity': round(coh.get(gi, 1.0), 3)}
    with LOCK:
        _cache.update(key=key, value=out)
    return out, 'meaning', ''


class Matcher:
    """Incremental matcher for the emergency newsroom's lead-first grouping."""

    def __init__(self, vecs, threshold):
        self.vecs, self.thr, self.sums, self.used, self.fallback = vecs, threshold, {}, 0, 0

    def assign(self, row, groups):
        v = self.vecs.get(row['id'])
        if v is None:
            self.fallback += 1
            return None, False
        best, best_s = None, self.thr
        for g in groups:
            s = self.sums.get(g['id'])
            if s is None:
                continue
            sim = float(v @ s) / (float(_np.linalg.norm(s)) or 1.0)
            if sim >= best_s:
                best, best_s = g, sim
        self.used += 1
        return best, True

    def add(self, row, g):
        v = self.vecs.get(row['id'])
        if v is not None:
            self.sums[g['id']] = self.sums.get(g['id'], 0) + v


def related(entry_id, db_connect, entries, limit=8, floor=0.62, days=7):
    """Nearest articles by meaning to one article (for the story drawer)."""
    if not ready():
        return None
    pool = [e for e in entries if e.get('medium') == 'article' and e['id'] != entry_id]
    vecs = vectors(db_connect, [entry_id] + [e['id'] for e in pool])
    q = vecs.get(entry_id)
    if q is None:
        return None
    t0 = None
    for e in entries:
        if e['id'] == entry_id:
            t0 = _ts(e)
    scored = []
    for e in pool:
        v = vecs.get(e['id'])
        if v is None or (t0 and abs(_ts(e) - t0) > days * 86400):
            continue
        s = float(q @ v)
        if s >= floor:
            scored.append((s, e))
    scored.sort(key=lambda x: -x[0])
    return [(round(s, 3), e) for s, e in scored[:limit * 3]]


def borderline(db_connect, entries, threshold, window_hours, band=0.07, limit=24):
    """Article pairs just above and just below the threshold, for a human to review."""
    if not ready():
        return []
    arts = [e for e in entries if e.get('medium') == 'article'][:900]
    vecs = vectors(db_connect, [e['id'] for e in arts])
    idx = [i for i, e in enumerate(arts) if e['id'] in vecs]
    if len(idx) < 2:
        return []
    np = _np
    M = np.stack([vecs[arts[i]['id']] for i in idx])
    S = M @ M.T
    t = np.array([_ts(arts[i]) for i in idx])
    S = np.where(np.abs(t[:, None] - t[None, :]) <= window_hours * 3600, S, -1.0)
    a, b = np.where(np.triu((S >= threshold - band) & (S < threshold + band), 1))
    order = np.argsort(np.abs(S[a, b] - threshold))[: limit * 4]
    out, seen = [], set()
    for k in order:
        x, y = arts[idx[int(a[k])]], arts[idx[int(b[k])]]
        if x['id'] in seen or y['id'] in seen:
            continue
        seen.update((x['id'], y['id']))
        out.append({'similarity': round(float(S[a[k], b[k]]), 3), 'joined': bool(S[a[k], b[k]] >= threshold),
                    'a': {'title': x['title'], 'source': x.get('source', '')}, 'b': {'title': y['title'], 'source': y.get('source', '')}})
        if len(out) >= limit:
            break
    return sorted(out, key=lambda p: -p['similarity'])
