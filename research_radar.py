"""Sanjaya research radar: new ML research ranked against your own papers.

Everything is local. Papers come from open APIs (arXiv, OpenAlex, Crossref, OpenML,
Hugging Face, and the ccfddl deadlines dataset on GitHub). They are stored in the
Sanjaya database, embedded with the same local multilingual model that groups news
(when the optional pack is installed) and compared with a "fingerprint": the
user's own papers. Without the model pack, the radar falls back to TF-IDF keyword
similarity and says so.
"""
from __future__ import annotations

import datetime as dt
import difflib
import email.utils
import hashlib
import html
import json
import math
import re
import threading
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from contextlib import closing
from pathlib import Path

import semantic

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / 'radar_config.json'
ARXIV_API = 'https://export.arxiv.org/api/query'
OPENALEX = 'https://api.openalex.org'
CROSSREF = 'https://api.crossref.org/works/'
OPENML = 'https://www.openml.org/api/v1/json'
HF = 'https://huggingface.co/api'
ARXIV_RSS = 'https://rss.arxiv.org/rss/'
DDL = 'https://raw.githubusercontent.com/ccfddl/ccf-deadlines/main/conference/'
NS = {'a': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
BIG = 8_000_000
_config = None
_lock = threading.RLock()
_mem = {'anchors': None, 'themes': {}}
DIGEST = {'status': 'idle', 'detail': ''}


def config() -> dict:
    global _config
    if _config is None:
        _config = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    return _config


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


# arXiv asks for one request every three seconds over a single connection (API and RSS).
_arxiv_lock = threading.Lock()
_arxiv_last = [0.0]


def arxiv_get(fetch, url, max_bytes=None):
    with _arxiv_lock:
        wait = 3.2 - (time.time() - _arxiv_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            return fetch(url, max_bytes or BIG)
        finally:
            _arxiv_last[0] = time.time()


def oa_key(db_connect) -> str:
    with closing(db_connect()) as con:
        init(con)
        return str(meta(con, 'openalex_key', '') or '')


def oa_url(path, params, key='') -> str:
    """OpenAlex works without a key on a small daily budget; a free key raises it tenfold."""
    p = dict(params)
    if key:
        p['api_key'] = key
    return f'{OPENALEX}{path}?{urllib.parse.urlencode(p)}'


# ------------------------------------------------------------------ storage

def init(con):
    con.executescript('''
        CREATE TABLE IF NOT EXISTS radar_papers (
            id TEXT PRIMARY KEY, source TEXT, title TEXT NOT NULL, abstract TEXT, authors TEXT,
            published TEXT, url TEXT, pdf TEXT, categories TEXT, venue TEXT, doi TEXT,
            lab INTEGER DEFAULT 0, added TEXT
        );
        CREATE INDEX IF NOT EXISTS radar_papers_pub ON radar_papers(published);
        CREATE TABLE IF NOT EXISTS radar_vecs (id TEXT, model TEXT, vec BLOB, PRIMARY KEY(id, model));
        CREATE TABLE IF NOT EXISTS radar_fingerprint (
            id TEXT PRIMARY KEY, kind TEXT, ref TEXT, title TEXT, abstract TEXT, authors TEXT,
            year TEXT, url TEXT, status TEXT, detail TEXT, added TEXT
        );
        CREATE TABLE IF NOT EXISTS radar_queue (
            id TEXT PRIMARY KEY, paper TEXT NOT NULL, status TEXT NOT NULL, note TEXT, added TEXT, updated TEXT
        );
        CREATE TABLE IF NOT EXISTS radar_meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS radar_digest (week TEXT PRIMARY KEY, model TEXT, text TEXT, papers TEXT, created TEXT);
    ''')
    if not con.execute("SELECT 1 FROM radar_meta WHERE key='seeded'").fetchone():
        for s in config().get('fingerprint_seed', []):
            _fp_insert(con, s['kind'], s['ref'])
        con.execute("INSERT OR REPLACE INTO radar_meta VALUES('seeded','1')")
    con.commit()


def meta(con, key, default=None):
    r = con.execute('SELECT value FROM radar_meta WHERE key=?', (key,)).fetchone()
    if not r:
        return default
    try:
        return json.loads(r[0])
    except ValueError:
        return default


def set_meta(con, key, value):
    con.execute('INSERT OR REPLACE INTO radar_meta VALUES(?,?)', (key, json.dumps(value)))


def norm_title(t: str) -> str:
    t = unicodedata.normalize('NFKD', t or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', t).strip()


def _ws(t) -> str:
    return re.sub(r'\s+', ' ', html.unescape(str(t or ''))).strip()


def _row_paper(r) -> dict:
    d = dict(r)
    for k in ('authors', 'categories'):
        try:
            d[k] = json.loads(d.get(k) or '[]')
        except ValueError:
            d[k] = []
    return d


def store_papers(con, papers, lab=False) -> int:
    added = 0
    for p in papers:
        if not p.get('id') or not p.get('title'):
            continue
        ex = con.execute('SELECT id, lab FROM radar_papers WHERE id=?', (p['id'],)).fetchone()
        if ex:
            if lab and not ex['lab']:
                con.execute('UPDATE radar_papers SET lab=1 WHERE id=?', (p['id'],))
            continue
        con.execute('''INSERT INTO radar_papers(id,source,title,abstract,authors,published,url,pdf,categories,venue,doi,lab,added)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (p['id'], p.get('source', ''), p['title'], p.get('abstract', ''), json.dumps(p.get('authors', [])),
                     p.get('published', ''), p.get('url', ''), p.get('pdf', ''), json.dumps(p.get('categories', [])),
                     p.get('venue', ''), p.get('doi', ''), 1 if lab else 0, now_iso()))
        added += 1
    return added


def prune(con, keep_days):
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=keep_days)).isoformat()
    lab_cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=730)).isoformat()
    queued = [r[0] for r in con.execute('SELECT id FROM radar_queue')]
    q = ','.join('?' * len(queued)) or "''"
    con.execute(f'''DELETE FROM radar_papers WHERE id NOT IN ({q}) AND
                    ((lab=0 AND published < ?) OR (lab=1 AND published < ?))''', (*queued, cut, lab_cut))
    con.execute("DELETE FROM radar_vecs WHERE id NOT LIKE 'fp:%' AND id NOT IN (SELECT id FROM radar_papers)")


# ------------------------------------------------------------------ parsing

def _safe_xml(data: bytes):
    if b'<!ENTITY' in data[:4000] or b'<!DOCTYPE' in data[:4000]:
        raise ValueError('Refusing XML with entity declarations')
    return ET.fromstring(data)


def parse_arxiv(data: bytes) -> list:
    root = _safe_xml(data)
    out = []
    for e in root.findall('a:entry', NS):
        raw = e.findtext('a:id', default='', namespaces=NS)
        m = re.search(r'arxiv\.org/abs/(.+?)(v\d+)?$', raw)
        if not m:
            continue
        aid = m.group(1)
        pdf = ''
        for ln in e.findall('a:link', NS):
            if ln.get('title') == 'pdf':
                pdf = ln.get('href', '')
        pc = e.find('arxiv:primary_category', NS)
        cats = list(dict.fromkeys(c.get('term') for c in e.findall('a:category', NS) if c.get('term')))
        if pc is not None and pc.get('term') in cats:
            cats.remove(pc.get('term'))
            cats.insert(0, pc.get('term'))
        out.append({
            'id': 'arxiv:' + aid, 'source': 'arxiv', 'arxiv': aid,
            'title': _ws(e.findtext('a:title', default='', namespaces=NS)),
            'abstract': _ws(e.findtext('a:summary', default='', namespaces=NS)),
            'authors': [_ws(a.findtext('a:name', default='', namespaces=NS)) for a in e.findall('a:author', NS)],
            'published': e.findtext('a:published', default='', namespaces=NS),
            'url': f'https://arxiv.org/abs/{aid}', 'pdf': pdf, 'categories': cats,
            'venue': _ws(e.findtext('arxiv:journal_ref', default='', namespaces=NS)),
            'doi': _ws(e.findtext('arxiv:doi', default='', namespaces=NS)),
        })
    return out


def openalex_abstract(inv) -> str:
    if not isinstance(inv, dict):
        return ''
    pos = {}
    for word, places in inv.items():
        for p in places or []:
            pos[p] = word
    return ' '.join(pos[k] for k in sorted(pos))


def parse_openalex_work(w: dict) -> dict:
    loc = w.get('primary_location') or {}
    src = (loc.get('source') or {}).get('display_name') or ''
    doi = (w.get('doi') or '').replace('https://doi.org/', '')
    ids = w.get('ids') or {}
    arx = ''
    for v in (ids.get('arxiv') or '', loc.get('landing_page_url') or ''):
        m = re.search(r'arxiv\.org/abs/([^v\s/]+(?:/\d+)?)', v or '')
        if m:
            arx = m.group(1)
    oid = (w.get('id') or '').rsplit('/', 1)[-1]
    return {
        'id': ('arxiv:' + arx) if arx else ('oa:' + oid), 'source': 'openalex', 'arxiv': arx,
        'title': _ws(w.get('display_name') or w.get('title')),
        'abstract': _ws(openalex_abstract(w.get('abstract_inverted_index'))),
        'authors': [_ws((a.get('author') or {}).get('display_name')) for a in (w.get('authorships') or [])],
        'published': (w.get('publication_date') or '') + ('T00:00:00Z' if w.get('publication_date') else ''),
        'url': loc.get('landing_page_url') or (('https://doi.org/' + doi) if doi else w.get('id', '')),
        'pdf': loc.get('pdf_url') or '', 'categories': [], 'venue': src, 'doi': doi,
    }


def parse_crossref(msg: dict) -> dict:
    title = _ws((msg.get('title') or [''])[0])
    abstract = _ws(re.sub(r'<[^>]+>', ' ', msg.get('abstract') or ''))
    abstract = re.sub(r'^Abstract\s*', '', abstract)
    authors = [_ws(f"{a.get('given', '')} {a.get('family', '')}") for a in msg.get('author') or []]
    parts = None
    for k in ('published', 'posted', 'issued', 'created'):
        dp = (msg.get(k) or {}).get('date-parts')
        if dp and dp[0]:
            parts = dp[0]
            break
    year = str(parts[0]) if parts else ''
    venue = _ws(((msg.get('container-title') or ['']) or [''])[0]) or _ws((msg.get('institution') or [{}])[0].get('name', ''))
    return {'title': title, 'abstract': abstract, 'authors': authors, 'year': year,
            'url': msg.get('URL') or '', 'venue': venue, 'doi': msg.get('DOI') or ''}


# ------------------------------------------------------------------ fingerprint

def _fp_id(kind, ref):
    return hashlib.sha1(f'{kind}:{ref.strip().lower()}'.encode()).hexdigest()[:16]


def _fp_insert(con, kind, ref):
    kind = kind if kind in ('arxiv', 'doi', 'title') else 'title'
    ref = ref.strip()
    con.execute('INSERT OR IGNORE INTO radar_fingerprint(id,kind,ref,status,added) VALUES(?,?,?,?,?)',
                (_fp_id(kind, ref), kind, ref, 'pending', now_iso()))
    return _fp_id(kind, ref)


def classify_ref(text: str):
    t = text.strip()
    m = re.search(r'arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})', t) or re.fullmatch(r'(?:arXiv:)?([0-9]{4}\.[0-9]{4,5})(v\d+)?', t, re.I)
    if m:
        return 'arxiv', m.group(1)
    m = re.search(r'(10\.\d{4,9}/\S+)', t)
    if m:
        return 'doi', m.group(1).rstrip('.')
    return 'title', t[:400]


def fp_add(con, text):
    if not text or not text.strip():
        raise ValueError('Paste an arXiv link or ID, a DOI, or a paper title.')
    kind, ref = classify_ref(text)
    return _fp_insert(con, kind, ref)


def resolve_one(kind, ref, fetch, key='') -> dict:
    if kind == 'arxiv':
        q = urllib.parse.urlencode({'id_list': ref, 'max_results': 1})
        got = parse_arxiv(arxiv_get(fetch, f'{ARXIV_API}?{q}'))
        if not got:
            raise LookupError('arXiv has no paper with that ID')
        p = got[0]
        return {'title': p['title'], 'abstract': p['abstract'], 'authors': p['authors'],
                'year': p['published'][:4], 'url': p['url']}
    if kind == 'doi':
        try:
            msg = json.loads(fetch(CROSSREF + urllib.parse.quote(ref, safe='/'), BIG)).get('message') or {}
            c = parse_crossref(msg)
            if c['title']:
                return c
        except Exception:
            pass
        w = json.loads(fetch(oa_url('/works/doi:' + urllib.parse.quote(ref, safe='/'), {}, key), BIG))
        p = parse_openalex_work(w)
        return {'title': p['title'], 'abstract': p['abstract'], 'authors': p['authors'],
                'year': p['published'][:4], 'url': p['url']}
    res = json.loads(fetch(oa_url('/works', {'search': ref, 'per_page': 5}, key), BIG)).get('results') or []
    best, score = None, 0.0
    for w in res:
        s = difflib.SequenceMatcher(None, norm_title(ref), norm_title(w.get('display_name') or '')).ratio()
        if s > score:
            best, score = w, s
    if not best or score < 0.85:
        raise LookupError('No paper with a matching title was found in OpenAlex')
    p = parse_openalex_work(best)
    return {'title': p['title'], 'abstract': p['abstract'], 'authors': p['authors'],
            'year': p['published'][:4], 'url': p['url']}


def resolve_fingerprint(db_connect, fetch, cache_dir) -> dict:
    key = oa_key(db_connect)
    with closing(db_connect()) as con:
        init(con)
        rows = [dict(r) for r in con.execute("SELECT * FROM radar_fingerprint WHERE status IN ('pending','error')")]
    for r in rows:
        try:
            info = resolve_one(r['kind'], r['ref'], fetch, key)
            vals = ('resolved', '', info['title'], info.get('abstract', ''), json.dumps(info.get('authors', [])),
                    info.get('year', ''), info.get('url', ''))
        except LookupError as exc:
            vals = ('not_found', str(exc), r.get('title'), r.get('abstract'), r.get('authors') or '[]', r.get('year'), r.get('url'))
        except Exception as exc:
            vals = ('error', f'{type(exc).__name__}: {str(exc)[:160]}', r.get('title'), r.get('abstract'),
                    r.get('authors') or '[]', r.get('year'), r.get('url'))
        with closing(db_connect()) as con:
            con.execute('UPDATE radar_fingerprint SET status=?,detail=?,title=?,abstract=?,authors=?,year=?,url=? WHERE id=?',
                        (*vals, r['id']))
            con.execute("DELETE FROM radar_vecs WHERE id=?", ('fp:' + r['id'],))
            con.commit()
        time.sleep(0.3)
    embed_missing(db_connect, cache_dir)
    with closing(db_connect()) as con:
        refresh_watch(con)
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM radar_fingerprint WHERE status='resolved'").fetchone()[0]
        pending = con.execute("SELECT COUNT(*) FROM radar_fingerprint WHERE status='pending'").fetchone()[0]
    return {'data_status': 'partial' if pending else 'ok', 'resolved': n, 'pending': pending}


def fingerprint(con) -> list:
    out = []
    for r in con.execute('SELECT * FROM radar_fingerprint ORDER BY added'):
        d = dict(r)
        try:
            d['authors'] = json.loads(d.get('authors') or '[]')
        except ValueError:
            d['authors'] = []
        out.append(d)
    return out


# ------------------------------------------------------------------ watch phrases

GENERIC = {'neural networks', 'neural network', 'deep learning', 'machine learning', 'deep neural', 'deep networks',
           'language models', 'large language', 'experimental results', 'results show', 'proposed method',
           'real-world', 'state-of-the-art', 'paper', 'approach', 'data', 'model', 'models', 'networks', 'learning'}


def watch(con) -> dict:
    w = meta(con, 'watch', None) or {'auto': [], 'added': [], 'removed': []}
    active = [x for x in w['auto'] if x not in w['removed']] + [x for x in w['added'] if x not in w['auto']]
    return {**w, 'active': active[:40]}


COMMON_ML = set("""deep training trained train transformer transformers network networks neural model models learning
data dataset datasets diagnostic diagnostics influence multimodal performance optimization optimisation representation
representations embedding embeddings language task tasks method methods system systems analysis approach framework
efficient understanding dynamics human comments graph graphs image images text agent agents benchmark benchmarks""".split())
WEAK_PART = {'understanding', 'towards', 'embedded', 'leveraging', 'based', 'using', 'via', 'new', 'novel', 'human',
             'influence', 'approach', 'study', 'results', 'show', 'propose', 'fixture'}


def _good_phrase(t, corpus, background_n) -> bool:
    words = t.split()
    if t in GENERIC or len(t) < 4 or any(w in WEAK_PART for w in words):
        return False
    if len(words) == 1:
        # A single word must be distinctive: rare in recent arXiv papers, or not a common ML word.
        if t in COMMON_ML:
            return False
        if background_n >= 200:
            return corpus.df.get(t, 0) / max(1, background_n) < 0.01
        return True
    return True


def refresh_watch(con) -> list:
    """Re-extract phrases from your papers; your additions and removals are kept."""
    fps = [f for f in fingerprint(con) if f['status'] == 'resolved' and f.get('title')]
    if not fps:
        return []
    background = [r['title'] + '. ' + (r['abstract'] or '')[:400] for r in
                  con.execute('SELECT title, abstract FROM radar_papers ORDER BY published DESC LIMIT 1500')]
    corpus = Tfidf([_text(f) for f in fps] + background)
    picked = []
    for f in fps:
        terms = [t for t in key_terms(_text(f), 12, corpus) if _good_phrase(t, corpus, len(background))]
        terms.sort(key=lambda t: (' ' not in t,))  # phrases before single words
        for t in terms[:4]:
            if t not in picked:
                picked.append(t)
    w = meta(con, 'watch', None) or {'auto': [], 'added': [], 'removed': []}
    w['auto'] = picked[:24]
    set_meta(con, 'watch', w)
    return picked


def watch_action(con, data) -> dict:
    w = meta(con, 'watch', None) or {'auto': [], 'added': [], 'removed': []}
    phrase = re.sub(r'\s+', ' ', str(data.get('phrase') or '').replace('"', '')).strip().lower()[:60]
    act = data.get('action')
    if act == 'add':
        if len(phrase) < 3:
            raise ValueError('Type a word or phrase of at least three letters.')
        if phrase in w['removed']:
            w['removed'].remove(phrase)
        if phrase not in w['auto'] and phrase not in w['added']:
            w['added'].append(phrase)
    elif act == 'remove':
        if phrase in w['added']:
            w['added'].remove(phrase)
        elif phrase in w['auto'] and phrase not in w['removed']:
            w['removed'].append(phrase)
    elif act == 'reset':
        set_meta(con, 'watch', {'auto': w['auto'], 'added': [], 'removed': []})
        refresh_watch(con)
        w = meta(con, 'watch', w)
    else:
        raise ValueError('Unknown action.')
    set_meta(con, 'watch', w)
    set_meta(con, 'kw_since', None)  # new phrases: look back the full window again
    con.commit()
    return watch(con)


def groups_of(items, n):
    return [items[i:i + n] for i in range(0, len(items), n)]


# ------------------------------------------------------------------ embedding

def _text(p) -> str:
    if not isinstance(p, dict):
        p = dict(p)
    return (p.get('title') or '') + '. ' + (p.get('abstract') or '')[:900]


def embed_missing(db_connect, cache_dir, limit=3000) -> int:
    if not semantic.available():
        return 0
    with closing(db_connect()) as con:
        rows = con.execute('''SELECT p.id,p.title,p.abstract FROM radar_papers p LEFT JOIN radar_vecs v
                              ON v.id=p.id AND v.model=? WHERE v.id IS NULL ORDER BY p.published DESC LIMIT ?''',
                           (semantic.MODEL, limit)).fetchall()
        fps = con.execute('''SELECT f.id,f.title,f.abstract FROM radar_fingerprint f LEFT JOIN radar_vecs v
                             ON v.id='fp:'||f.id AND v.model=? WHERE v.id IS NULL AND f.status='resolved' ''',
                          (semantic.MODEL,)).fetchall()
    jobs = [(r['id'], _text(r)) for r in rows] + [('fp:' + r['id'], _text(r)) for r in fps]
    done = 0
    for i in range(0, len(jobs), 64):
        chunk = jobs[i:i + 64]
        vecs = semantic.embed_texts([t for _, t in chunk], cache_dir)
        if vecs is None:
            return done
        with closing(db_connect()) as con:
            con.executemany('INSERT OR REPLACE INTO radar_vecs VALUES(?,?,?)',
                            [(k, semantic.MODEL, v.tobytes()) for (k, _), v in zip(chunk, vecs)])
            con.commit()
        done += len(chunk)
        time.sleep(0.05)
    return done


def _vecs(con, ids):
    np = semantic._np
    if np is None or not ids:
        return {}
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 900):
        part = ids[i:i + 900]
        q = ','.join('?' * len(part))
        for r in con.execute(f'SELECT id, vec FROM radar_vecs WHERE model=? AND id IN ({q})', (semantic.MODEL, *part)):
            out[r[0]] = np.frombuffer(r[1], dtype=np.float32)
    return out


# ------------------------------------------------------------------ keyword fallback

STOP = set('''a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having he her here
hers him his how i if in into is it its itself just me more most my no nor not now of off on once only or other our out
over own same she should so some such than that the their them then there these they this those through to too under
until up very was we were what when where which while who whom why will with you your via using based new show shows
propose proposed approach approaches method methods paper results result model models data learning task tasks work
existing however also across well different two one first can our these used use study introduce present demonstrate
significantly performance state art novel framework analyse analyze analysing analyzing aim aims aiming investigate
investigates explore explores exploring focus focuses consider considers provide provides allow allows enable enables
achieve achieves obtain obtained typically often many several various within without towards toward thus hence while
including include includes given make makes made well-known able'''.split())


def tokens(text: str) -> list:
    # Bigrams only from words that are truly adjacent in the text (no stop word between them).
    raw = re.findall(r'[a-z][a-z0-9\-]*', (text or '').lower())
    words, grams, prev = [], [], None
    for w in raw:
        keep = len(w) > 2 and w not in STOP
        if keep:
            words.append(w)
            if prev:
                grams.append(prev + ' ' + w)
        prev = w if keep else None
    return words + grams


class Tfidf:
    def __init__(self, docs):
        self.df = Counter()
        toks = [Counter(tokens(d)) for d in docs]
        for t in toks:
            self.df.update(t.keys())
        self.n = max(1, len(docs))
        self.vecs = [self.vec_from(t) for t in toks]

    def vec_from(self, counts):
        v = {w: (1 + math.log(c)) * math.log((1 + self.n) / (1 + self.df.get(w, 0)) + 1) for w, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    def vec(self, text):
        return self.vec_from(Counter(tokens(text)))


def sparse_dot(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


def key_terms(text, k=8, corpus=None):
    """Search phrases for a text: phrases first, no term that repeats a chosen one."""
    c = Counter(tokens(text))
    def idf(w):
        return math.log((1 + corpus.n) / (1 + corpus.df.get(w, 0)) + 1) if corpus is not None else 1.0
    scored = sorted(((1 + math.log(n)) * idf(w) * (1.8 if ' ' in w else 1.0), w) for w, n in c.items())
    out = []
    for _, w in reversed(scored):
        parts = set(w.split())
        if any(w == o or parts & set(o.split()) for o in out):
            continue
        out.append(w)
        if len(out) >= k:
            break
    return out


# ------------------------------------------------------------------ scoring

def mode_for(con, ids) -> tuple:
    """('meaning'|'keywords', note)."""
    if not semantic.available():
        return 'keywords', 'Language model pack not installed; matched by keywords.'
    if not semantic.ready():
        return 'keywords', 'Language model is loading; matched by keywords for now.'
    have = con.execute('SELECT COUNT(*) FROM radar_vecs WHERE model=?', (semantic.MODEL,)).fetchone()[0]
    if have < max(1, int(0.6 * len(ids))):
        return 'keywords', 'Papers are still being processed by the language model; matched by keywords for now.'
    return 'meaning', 'Matched by meaning with the local multilingual model.'


def _anchor_vecs(cache_dir):
    lanes = config()['lanes']
    if _mem['anchors'] is None:
        v = semantic.embed_texts([l['label'] + ': ' + l['anchor'] for l in lanes], cache_dir)
        if v is not None:
            _mem['anchors'] = v
    return _mem['anchors']


def score(con, papers, cache_dir) -> tuple:
    """Adds match (0..1), nearest (fingerprint title) and lane to each paper."""
    lanes = config()['lanes']
    fps = [f for f in fingerprint(con) if f['status'] == 'resolved']
    mode, note = mode_for(con, [p['id'] for p in papers])
    if mode == 'meaning':
        np = semantic._np
        vec = _vecs(con, [p['id'] for p in papers] + ['fp:' + f['id'] for f in fps])
        anchors = _anchor_vecs(cache_dir)
        fpv = [(f, vec['fp:' + f['id']]) for f in fps if 'fp:' + f['id'] in vec]
        if anchors is None or not fpv:
            mode, note = 'keywords', 'Fingerprint papers are not embedded yet; matched by keywords for now.'
        else:
            A = np.stack(anchors)
            F = np.stack([v for _, v in fpv])
            have = [p for p in papers if p['id'] in vec]
            for p in papers:
                p.update(match=0.0, nearest='', lane=lanes[0]['key'])
            if have:
                P = np.stack([vec[p['id']] for p in have])
                S, L = P @ F.T, P @ A.T
                best, lane = S.argmax(1), L.argmax(1)
                for i, p in enumerate(have):
                    p.update(match=round(float(S[i, best[i]]), 3), nearest=fpv[int(best[i])][0]['title'],
                             lane=lanes[int(lane[i])]['key'])
            return mode, note
    docs = [_text(p) for p in papers] + [_text(f) for f in fps] + [l['anchor'] for l in lanes]
    tf = Tfidf(docs)
    n = len(papers)
    fpv = tf.vecs[n:n + len(fps)]
    av = tf.vecs[n + len(fps):]
    for i, p in enumerate(papers):
        v = tf.vecs[i]
        sims = [sparse_dot(v, f) for f in fpv] or [0.0]
        j = max(range(len(sims)), key=lambda k: sims[k])
        lane = max(range(len(av)), key=lambda k: sparse_dot(v, av[k]))
        p.update(match=round(sims[j], 3), nearest=fps[j]['title'] if fps else '', lane=lanes[lane]['key'])
    return mode, note


def recent(con, days, source=None, lab=None, limit=6000) -> list:
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    q = 'SELECT * FROM radar_papers WHERE published >= ?'
    args = [cut]
    if source:
        q += ' AND source=?'
        args.append(source)
    if lab is not None:
        q += ' AND lab=?'
        args.append(1 if lab else 0)
    return [_row_paper(r) for r in con.execute(q + ' ORDER BY published DESC LIMIT ?', (*args, limit))]


def overview(db_connect, cache_dir, days=7, per_lane=40) -> dict:
    with closing(db_connect()) as con:
        init(con)
        papers = recent(con, days)
        mode, note = score(con, papers, cache_dir)
        lab = [_row_paper(r) for r in con.execute('SELECT * FROM radar_papers WHERE lab=1 ORDER BY published DESC LIMIT 60')]
        if lab:
            score(con, lab, cache_dir)
        hf = meta(con, 'hf_daily', {}) or {}
        queue = {r[0]: r[1] for r in con.execute('SELECT id, status FROM radar_queue')}
        fps = fingerprint(con)
        w = watch(con)
        has_key = bool(meta(con, 'openalex_key', ''))
    lanes = []
    for l in config()['lanes']:
        mine = sorted([p for p in papers if p.get('lane') == l['key']], key=lambda p: -p['match'])
        lanes.append({'key': l['key'], 'label': l['label'], 'total': len(mine), 'papers': [_slim(p, hf) for p in mine[:per_lane]]})
    return {'mode': mode, 'note': note, 'days': days, 'held': len(papers), 'lanes': lanes,
            'lab': [_slim(p, hf) for p in lab], 'trace': {k: v for k, v in config()['trace'].items()},
            'fingerprint': [{k: f.get(k) for k in ('id', 'kind', 'ref', 'title', 'year', 'url', 'status', 'detail')} for f in fps],
            'queue': queue, 'watch': w, 'openalex_key': has_key, 'categories': config()['arxiv_categories'],
            'by_source': dict(Counter(p.get('source') or 'arxiv' for p in papers))}


def _slim(p, hf) -> dict:
    aid = p['id'][6:] if p['id'].startswith('arxiv:') else ''
    return {'id': p['id'], 'title': p['title'], 'abstract': (p.get('abstract') or '')[:1200],
            'authors': p.get('authors', [])[:12], 'more_authors': max(0, len(p.get('authors', [])) - 12),
            'published': p.get('published', ''), 'url': p.get('url', ''), 'pdf': p.get('pdf', ''),
            'categories': p.get('categories', [])[:4], 'venue': p.get('venue', ''), 'doi': p.get('doi', ''),
            'match': p.get('match', 0.0), 'nearest': p.get('nearest', ''), 'lane': p.get('lane', ''),
            'lab': bool(p.get('lab')), 'hf_upvotes': hf.get(aid) if aid else None, 'source': p.get('source') or 'arxiv'}


# ------------------------------------------------------------------ intake jobs

def _local(tag) -> str:
    return tag.rsplit('}', 1)[-1].split(':')[-1]


def _split_authors(text) -> list:
    parts = re.split(r',\s*|\s+and\s+', _ws(text))
    return [a.strip() for a in parts if a.strip() and a.strip().lower() != 'and']


def parse_arxiv_rss(data: bytes) -> list:
    """arXiv's daily RSS (2024 format). Keeps new listings and cross-lists, skips replacements."""
    root = _safe_xml(data)
    out = []
    for it in root.iter():
        if _local(it.tag) != 'item':
            continue
        f, cats = {}, []
        for ch in it:
            n = _local(ch.tag)
            if n == 'category':
                if ch.text:
                    cats.append(ch.text.strip())
            else:
                f[n] = ch.text or ''
        desc = f.get('description', '')
        m = re.search(r'Announce Type:\s*([\w-]+)', desc)
        typ = (f.get('announce_type') or (m.group(1) if m else 'new')).strip().lower()
        if typ.startswith('replace'):
            continue
        link = (f.get('link') or f.get('guid') or '').strip()
        m = re.search(r'arxiv\.org/abs/(.+?)(v\d+)?$', link) or re.search(r'arXiv:(\S+?)(v\d+)?\s', desc + ' ')
        if not m:
            continue
        aid = m.group(1).replace('oai:arXiv.org:', '')
        abstract = desc.split('Abstract:', 1)[1] if 'Abstract:' in desc else re.sub(r'^arXiv:\S+\s+Announce Type:\s*\S+', '', desc)
        try:
            published = email.utils.parsedate_to_datetime(f.get('pubDate', '')).astimezone(dt.timezone.utc).isoformat()
        except (TypeError, ValueError):
            published = now_iso()
        out.append({'id': 'arxiv:' + aid, 'source': 'arxiv', 'arxiv': aid, 'title': _ws(f.get('title')),
                    'abstract': _ws(abstract), 'authors': _split_authors(f.get('creator', '')), 'published': published,
                    'url': f'https://arxiv.org/abs/{aid}', 'pdf': f'https://arxiv.org/pdf/{aid}',
                    'categories': list(dict.fromkeys(cats)), 'venue': _ws(f.get('journal_reference')), 'doi': _ws(f.get('DOI'))})
    return out


def _save(db_connect, cache_dir, papers, lab=False) -> int:
    """Store one batch, then embed just that batch, so the page fills in progressively."""
    if not papers:
        return 0
    with closing(db_connect()) as con:
        init(con)
        added = store_papers(con, papers, lab=lab)
        con.commit()
    if added:
        embed_missing(db_connect, cache_dir, limit=max(64, added))
        _mem['themes'].clear()
    return added


def intake_rss(fetch, db_connect, cache_dir) -> dict:
    """Broad feed: each category's daily announcement in one small request (updated once a day)."""
    cfg = config()
    got, added, notes = 0, 0, []
    for cat in cfg['arxiv_categories']:
        try:
            ps = parse_arxiv_rss(arxiv_get(fetch, ARXIV_RSS + cat))
            got += len(ps)
            added += _save(db_connect, cache_dir, ps)
        except Exception as exc:
            notes.append(f'{cat}: {type(exc).__name__}')
    if notes and not got:
        raise RuntimeError('arXiv RSS unavailable (' + '; '.join(notes) + ')')
    with closing(db_connect()) as con:
        prune(con, cfg.get('keep_days', 30))
        con.commit()
    return {'data_status': 'ok', 'fetched': got, 'added': added, 'notes': notes}


def _arxiv_window(con, key, first_days):
    """Incremental: from the last successful run (with overlap), or the full window the first time."""
    now = dt.datetime.now(dt.timezone.utc)
    last = meta(con, key, None)
    try:
        start = dt.datetime.fromisoformat(last) - dt.timedelta(hours=36) if last else now - dt.timedelta(days=first_days)
    except ValueError:
        start = now - dt.timedelta(days=first_days)
    return start, now


def intake_keywords(fetch, db_connect, cache_dir) -> dict:
    """Targeted arXiv queries built from your watch phrases (a few small requests, newest first)."""
    cfg = config()
    with closing(db_connect()) as con:
        init(con)
        phrases = watch(con)['active']
        start, end = _arxiv_window(con, 'kw_since', cfg.get('first_lookback_days', 14))
    if not phrases:
        return {'data_status': 'partial', 'note': 'Waiting for your papers to be looked up before searching.'}
    cats = ' OR '.join(f'cat:{c}' for c in cfg['arxiv_categories'])
    span = f"submittedDate:[{start.strftime('%Y%m%d%H%M')} TO {end.strftime('%Y%m%d%H%M')}]"
    got, added, notes = 0, 0, []
    for grp in groups_of(phrases, cfg.get('phrases_per_query', 4)):
        terms = ' OR '.join(f'ti:"{p}" OR abs:"{p}"' for p in grp)
        q = urllib.parse.urlencode({'search_query': f'({terms}) AND ({cats}) AND {span}', 'sortBy': 'submittedDate',
                                    'sortOrder': 'descending', 'max_results': cfg.get('per_query', 100)})
        try:
            ps = parse_arxiv(arxiv_get(fetch, f'{ARXIV_API}?{q}'))
            got += len(ps)
            added += _save(db_connect, cache_dir, ps)
        except Exception as exc:
            notes.append(f'{grp[0]}…: {type(exc).__name__}')
    if notes and not got and len(notes) == len(groups_of(phrases, cfg.get('phrases_per_query', 4))):
        raise RuntimeError('arXiv search unavailable (' + '; '.join(notes[:3]) + ')')
    with closing(db_connect()) as con:
        set_meta(con, 'kw_since', end.isoformat())
        con.commit()
    return {'data_status': 'ok', 'fetched': got, 'added': added, 'queries': len(groups_of(phrases, cfg.get('phrases_per_query', 4))), 'notes': notes}


def _hf_paper(item) -> dict:
    p = item.get('paper') if isinstance(item.get('paper'), dict) else item
    pid = str(p.get('id') or '')
    if not re.fullmatch(r'\d{4}\.\d{4,5}', pid):
        return {}
    return {'id': 'arxiv:' + pid, 'source': 'hf', 'arxiv': pid, 'title': _ws(p.get('title') or item.get('title')),
            'abstract': _ws(p.get('summary') or item.get('summary')),
            'authors': [_ws(a.get('name')) for a in p.get('authors') or [] if isinstance(a, dict) and a.get('name')],
            'published': p.get('publishedAt') or item.get('publishedAt') or '', 'url': f'https://arxiv.org/abs/{pid}',
            'pdf': f'https://arxiv.org/pdf/{pid}', 'categories': [], 'venue': '', 'doi': '',
            'upvotes': p.get('upvotes', item.get('upvotes', 0)) or 0}


def huggingface(fetch, db_connect, cache_dir=None) -> dict:
    """Hugging Face: daily papers (stored as papers), paper search for your phrases, trending models."""
    cfg = config()
    models, daily, notes, papers = [], {}, [], []
    try:
        raw = json.loads(fetch(f'{HF}/models?sort=trendingScore&direction=-1&limit=24', BIG))
        for m in raw if isinstance(raw, list) else []:
            mid = m.get('id') or m.get('modelId')
            if mid:
                models.append({'id': mid, 'likes': m.get('likes'), 'downloads': m.get('downloads'),
                               'task': m.get('pipeline_tag') or '', 'library': m.get('library_name') or '',
                               'url': f'https://huggingface.co/{mid}'})
    except Exception as exc:
        notes.append(f'models: {type(exc).__name__}')
    try:
        raw = json.loads(fetch(f'{HF}/daily_papers?limit=100', BIG))
        for it in raw if isinstance(raw, list) else []:
            p = _hf_paper(it)
            if p:
                daily[p['arxiv']] = p['upvotes']
                papers.append(p)
    except Exception as exc:
        notes.append(f'daily papers: {type(exc).__name__}')
    with closing(db_connect()) as con:
        init(con)
        phrases = watch(con)['active'][:cfg.get('hf_search_phrases', 8)]
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=cfg.get('keep_days', 30))).isoformat()
    searched = 0
    for ph in phrases:
        try:
            raw = json.loads(fetch(f'{HF}/papers/search?' + urllib.parse.urlencode({'q': ph, 'limit': 20}), BIG))
            for it in raw if isinstance(raw, list) else []:
                p = _hf_paper(it)
                if p and p['published'] >= cut:
                    papers.append(p)
            searched += 1
        except Exception as exc:
            notes.append(f'search "{ph}": {type(exc).__name__}')
    if not models and not daily and not searched:
        raise RuntimeError('Hugging Face unavailable (' + '; '.join(notes[:3]) + ')')
    with closing(db_connect()) as con:
        init(con)
        set_meta(con, 'hf_daily', daily)
        con.commit()
    added = _save(db_connect, cache_dir, papers) if cache_dir else 0
    return {'data_status': 'ok', 'models': models, 'daily_count': len(daily), 'fetched': len(papers), 'added': added, 'notes': notes}


def intake_openalex(fetch, db_connect, cache_dir) -> dict:
    """Journals and proceedings for your phrases, last 30 days. Short queries keep within the keyless budget."""
    cfg = config()
    key = oa_key(db_connect)
    with closing(db_connect()) as con:
        init(con)
        phrases = watch(con)['active']
    if not phrases:
        return {'data_status': 'partial', 'note': 'Waiting for your papers to be looked up before searching.'}
    since = (dt.date.today() - dt.timedelta(days=cfg.get('keep_days', 30))).isoformat()
    got, added, notes = 0, 0, []
    for grp in groups_of(phrases, cfg.get('phrases_per_query', 4))[:cfg.get('openalex_queries', 6)]:
        url = oa_url('/works', {'search': ' OR '.join(f'"{p}"' for p in grp), 'filter': f'from_publication_date:{since}',
                                'sort': 'publication_date:desc', 'per_page': 25}, key)
        try:
            ps = [parse_openalex_work(w) for w in json.loads(fetch(url, BIG)).get('results') or []]
            ps = [dict(p, source='openalex') for p in ps if p['title']]
            got += len(ps)
            added += _save(db_connect, cache_dir, ps)
        except Exception as exc:
            msg = str(exc)
            notes.append('daily budget used up; add a free OpenAlex key' if '429' in msg else f'{type(exc).__name__}')
    if notes and not got:
        raise RuntimeError('OpenAlex unavailable (' + '; '.join(dict.fromkeys(notes)) + ')')
    return {'data_status': 'ok', 'fetched': got, 'added': added, 'keyed': bool(key), 'notes': list(dict.fromkeys(notes))}


def trace_lab(fetch, db_connect, cache_dir) -> dict:
    tr = config()['trace']
    key = oa_key(db_connect)
    papers, notes = [], []
    try:
        q = urllib.parse.urlencode({'search_query': f'au:{tr["arxiv_author"]}', 'sortBy': 'submittedDate',
                                    'sortOrder': 'descending', 'max_results': 40})
        papers += parse_arxiv(arxiv_get(fetch, f'{ARXIV_API}?{q}'))
    except Exception as exc:
        notes.append(f'arXiv: {type(exc).__name__}')
    try:
        cands = json.loads(fetch(oa_url('/authors', {'search': tr['openalex_author'], 'per_page': 5}, key), BIG)).get('results') or []
        last = tr['openalex_author'].split()[-1].lower()
        cands = [c for c in cands if last in (c.get('display_name') or '').lower()]
        if cands:
            best = max(cands, key=lambda c: c.get('works_count') or 0)
            aid = best['id'].rsplit('/', 1)[-1]
            works = json.loads(fetch(oa_url('/works', {'filter': f'author.id:{aid}', 'sort': 'publication_date:desc', 'per_page': 25}, key), BIG)).get('results') or []
            seen = {norm_title(p['title']) for p in papers}
            for w in works:
                p = parse_openalex_work(w)
                if p['title'] and norm_title(p['title']) not in seen:
                    seen.add(norm_title(p['title']))
                    papers.append(p)
    except Exception as exc:
        notes.append(f'OpenAlex: {type(exc).__name__}')
    if not papers:
        raise RuntimeError('No source returned papers (' + '; '.join(notes) + ')')
    with closing(db_connect()) as con:
        init(con)
        added = store_papers(con, papers, lab=True)
        con.commit()
    embed_missing(db_connect, cache_dir)
    return {'data_status': 'ok', 'found': len(papers), 'added': added, 'notes': notes}


def _openml_count(fetch, kind) -> int:
    """OpenML lists are ordered oldest first with no sort option, so find the end by probing."""
    def exists(off):
        try:
            d = json.loads(fetch(f'{OPENML}/{kind}/list/limit/1/offset/{off}', 200_000))
            return bool(d.get('data' if kind == 'data' else 'tasks'))
        except Exception:
            return False
    if not exists(0):
        return 0
    hi = 1
    while exists(hi) and hi < 2 ** 20:
        hi *= 2
    lo = hi // 2
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if exists(mid):
            lo = mid
        else:
            hi = mid
    return lo + 1


def _quality(item, name):
    for q in item.get('quality') or []:
        if q.get('name') == name:
            try:
                return int(float(q.get('value')))
            except (TypeError, ValueError):
                return None
    return None


def openml(fetch, n=24) -> dict:
    out, notes = {'datasets': [], 'tasks': []}, []
    for kind in ('data', 'task'):
        try:
            total = _openml_count(fetch, kind)
            if not total:
                raise RuntimeError('empty list')
            off = max(0, total - n)
            d = json.loads(fetch(f'{OPENML}/{kind}/list/limit/{n}/offset/{off}', BIG))
            if kind == 'data':
                for x in reversed((d.get('data') or {}).get('dataset') or []):
                    out['datasets'].append({'id': x.get('did'), 'name': x.get('name'), 'version': x.get('version'),
                                            'instances': _quality(x, 'NumberOfInstances'), 'features': _quality(x, 'NumberOfFeatures'),
                                            'classes': _quality(x, 'NumberOfClasses'),
                                            'url': f"https://www.openml.org/search?type=data&id={x.get('did')}"})
            else:
                for x in reversed((d.get('tasks') or {}).get('task') or []):
                    out['tasks'].append({'id': x.get('task_id'), 'type': x.get('task_type'), 'dataset': x.get('name'),
                                         'did': x.get('did'), 'instances': _quality(x, 'NumberOfInstances'),
                                         'url': f"https://www.openml.org/search?type=task&id={x.get('task_id')}"})
        except Exception as exc:
            notes.append(f'{kind}: {type(exc).__name__}: {str(exc)[:80]}')
    if not out['datasets'] and not out['tasks']:
        raise RuntimeError('OpenML unavailable (' + '; '.join(notes) + ')')
    return {'data_status': 'ok', **out, 'notes': notes}


# ------------------------------------------------------------------ deadlines

def mini_yaml(text: str):
    """Parse the small YAML subset used by ccfddl files (block maps, lists, scalars)."""
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        lines.append((len(raw) - len(raw.lstrip(' ')), raw.strip()))

    def scalar(s):
        s = s.strip()
        if ' #' in s and not s.startswith(("'", '"')):
            s = s.split(' #', 1)[0].strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in '"\'':
            return s[1:-1]
        if s in ('null', '~', ''):
            return None
        if re.fullmatch(r'-?\d+', s):
            return int(s)
        return s

    def split_kv(s):
        m = re.match(r'^([^:\'"]+?):(?:\s+(.*))?$', s)
        return (m.group(1).strip(), m.group(2)) if m else (None, None)

    def block(i, indent):
        if i >= len(lines):
            return None, i
        if lines[i][1].startswith('- ') or lines[i][1] == '-':
            out = []
            while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith('-'):
                rest = lines[i][1][1:].strip()
                if not rest:
                    val, i = block(i + 1, lines[i + 1][0] if i + 1 < len(lines) else indent + 2)
                    out.append(val)
                    continue
                k, v = split_kv(rest)
                if k is None:
                    out.append(scalar(rest))
                    i += 1
                    continue
                item_indent = indent + 2
                lines[i] = (item_indent, rest)
                val, i = block(i, item_indent)
                out.append(val)
            return out, i
        out = {}
        while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith('- '):
            k, v = split_kv(lines[i][1])
            if k is None:
                i += 1
                continue
            if v is None or v == '':
                if i + 1 < len(lines) and lines[i + 1][0] > indent:
                    out[k], i = block(i + 1, lines[i + 1][0])
                elif i + 1 < len(lines) and lines[i + 1][0] == indent and lines[i + 1][1].startswith('- '):
                    out[k], i = block(i + 1, indent)
                else:
                    out[k] = None
                    i += 1
            else:
                out[k] = scalar(v)
                i += 1
        return out, i

    val, _ = block(0, lines[0][0]) if lines else (None, 0)
    return val


def _tz_offset(tz: str) -> int:
    tz = (tz or '').strip()
    if tz.upper() == 'AOE':
        return -12
    m = re.fullmatch(r'UTC([+-]\d{1,2})?', tz, re.I)
    return int(m.group(1)) if m and m.group(1) else 0


def conference_dates(doc, name, now=None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    conf = (doc or [{}])[0] if isinstance(doc, list) else (doc or {})
    editions = conf.get('confs') or []
    milestones, latest = [], None
    for ed in editions:
        latest = ed if not latest or (ed.get('year') or 0) >= (latest.get('year') or 0) else latest
        off = _tz_offset(str(ed.get('timezone') or 'UTC+0'))
        for tl in ed.get('timeline') or []:
            for k, v in (tl or {}).items():
                if not isinstance(v, str) or not re.match(r'\d{4}-\d{2}-\d{2}', v):
                    continue
                try:
                    local = dt.datetime.strptime(v[:19], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    continue
                at = (local - dt.timedelta(hours=off)).replace(tzinfo=dt.timezone.utc)
                if at < now - dt.timedelta(days=2):
                    continue
                milestones.append({'conference': name, 'year': ed.get('year'), 'kind': k.replace('_', ' '),
                                   'at': at.isoformat(), 'local': v[:16], 'timezone': ed.get('timezone') or 'UTC',
                                   'days': math.floor((at - now).total_seconds() / 86400),
                                   'link': ed.get('link') or '', 'date': ed.get('date') or '', 'place': ed.get('place') or ''})
    milestones.sort(key=lambda m: m['at'])
    return {'name': name, 'description': conf.get('description') or '', 'milestones': milestones,
            'latest': {k: (latest or {}).get(k) for k in ('year', 'link', 'date', 'place')}}


def deadlines(fetch) -> dict:
    confs, notes = [], []
    for c in config()['conferences']:
        if not c.get('file'):
            confs.append({'name': c['name'], 'description': '', 'milestones': [], 'note': c.get('note', ''),
                          'latest': {'link': c.get('link', '')}})
            continue
        try:
            doc = mini_yaml(fetch(DDL + c['file'], 1_000_000).decode('utf-8'))
            confs.append(conference_dates(doc, c['name']))
        except Exception as exc:
            notes.append(f"{c['name']}: {type(exc).__name__}")
            confs.append({'name': c['name'], 'milestones': [], 'note': 'Could not load dates right now.', 'latest': {}})
    if notes and len(notes) >= len([c for c in config()['conferences'] if c.get('file')]):
        raise RuntimeError('Deadlines dataset unavailable')
    upcoming = sorted([m for c in confs for m in c['milestones']], key=lambda m: m['at'])
    return {'data_status': 'ok', 'conferences': confs, 'upcoming': upcoming[:40],
            'source': 'ccfddl/ccf-deadlines on GitHub', 'notes': notes}


# ------------------------------------------------------------------ themes

def theme_terms(members, corpus, k=4) -> list:
    """Distinctive terms shared by several papers in a theme, phrases first."""
    docs = [set(tokens(_text(p))) for p in members]
    need = max(2, math.ceil(len(members) / 3))
    share = Counter(t for d in docs for t in d)
    scored = []
    for t, n in share.items():
        if n < need:
            continue
        idf = math.log((1 + corpus.n) / (1 + corpus.df.get(t, 0)) + 1)
        scored.append(((n / len(members)) * idf * (1.6 if ' ' in t else 1.0), t))
    out = []
    for _, t in sorted(scored, reverse=True):
        if any(t in o or o in t for o in out):
            continue
        out.append(t)
        if len(out) >= k:
            break
    return out

def themes(db_connect, cache_dir, days=7, threshold=0.6, limit=12) -> dict:
    key = (days, threshold)
    hit = _mem['themes'].get(key)
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    with closing(db_connect()) as con:
        init(con)
        papers = recent(con, days, limit=2500)
        mode, note = score(con, papers, cache_dir)
        groups = []
        if mode == 'meaning':
            vec = _vecs(con, [p['id'] for p in papers])
            idx_groups, cohesion = semantic.group(papers, vec, threshold, days * 24 + 24)
            groups = [(g, cohesion.get(i, 0.0)) for i, g in enumerate(idx_groups)]
    if mode != 'meaning':
        sample = sorted(papers, key=lambda p: -p.get('match', 0))[:500]
        papers = sample
        tf = Tfidf([_text(p) for p in papers])
        parent = list(range(len(papers)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        pairs = []
        for i in range(len(papers)):
            for j in range(i + 1, len(papers)):
                s = sparse_dot(tf.vecs[i], tf.vecs[j])
                if s >= 0.28:
                    pairs.append((s, i, j))
        for s, i, j in sorted(pairs, reverse=True):
            parent[find(j)] = find(i)
        bucket = {}
        for i in range(len(papers)):
            bucket.setdefault(find(i), []).append(i)
        groups = [(g, 0.0) for g in bucket.values()]
    corpus = Tfidf([_text(p) for p in papers]) if papers else None
    cut48 = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)).isoformat()
    out = []
    for g, coh in sorted(groups, key=lambda x: -len(x[0])):
        if len(g) < 3:
            continue
        members = [papers[i] for i in g]
        terms = theme_terms(members, corpus)
        members.sort(key=lambda p: -p.get('match', 0))
        out.append({'label': ' · '.join(terms[:3]), 'terms': terms, 'size': len(members),
                    'fresh': sum(1 for p in members if p.get('published', '') >= cut48),
                    'match': round(sum(p.get('match', 0) for p in members) / len(members), 3),
                    'cohesion': round(coh, 3), 'papers': [_slim(p, {}) for p in members[:5]]})
        if len(out) >= limit:
            break
    res = {'mode': mode, 'note': note, 'days': days, 'papers': len(papers), 'themes': out}
    _mem['themes'][key] = (time.time(), res)
    return res


# ------------------------------------------------------------------ related-work check

def related_work(text, db_connect, fetch, cache_dir, k=12) -> dict:
    text = (text or '').strip()
    if len(text) < 40:
        raise ValueError('Paste at least a few sentences: an abstract or a paragraph from your draft.')
    with closing(db_connect()) as con:
        init(con)
        held = [_row_paper(r) for r in con.execute('SELECT * FROM radar_papers')]
        mode, note = mode_for(con, [p['id'] for p in held])
        vec = _vecs(con, [p['id'] for p in held]) if mode == 'meaning' else {}
    wider, notes = [], []
    corpus = Tfidf([_text(p) for p in held] or [text])
    terms = key_terms(text, 6, corpus)
    try:
        res = json.loads(fetch(oa_url('/works', {'search': ' '.join(terms[:5]), 'per_page': 25}, oa_key(db_connect)), BIG)).get('results') or []
        wider = [parse_openalex_work(w) for w in res]
        wider = [w for w in wider if w['title']]
    except Exception as exc:
        notes.append(f'OpenAlex search failed: {type(exc).__name__}')
    if mode == 'meaning':
        np = semantic._np
        qv = semantic.embed_texts([text], cache_dir)[0]
        for p in held:
            v = vec.get(p['id'])
            p['sim'] = float(v @ qv) if v is not None else 0.0
        wv = semantic.embed_texts([_text(w) for w in wider], cache_dir) if wider else []
        for w, v in zip(wider, wv):
            w['sim'] = float(np.asarray(v) @ qv)
    else:
        tf = Tfidf([_text(p) for p in held] + [_text(w) for w in wider] + [text])
        qv = tf.vecs[-1]
        for i, p in enumerate(held + wider):
            p['sim'] = sparse_dot(tf.vecs[i], qv)
    floor = 0.3 if mode == 'meaning' else 0.04  # below this, papers are not meaningfully related
    local = [p for p in sorted(held, key=lambda p: -p['sim']) if p['sim'] >= floor][:k]
    seen = {norm_title(p['title']) for p in local}
    wider = [w for w in sorted(wider, key=lambda w: -w['sim']) if norm_title(w['title']) not in seen and w['sim'] >= floor][:k]

    def slim(p):
        d = _slim(p, {})
        d['match'] = round(p['sim'], 3)
        return d
    return {'mode': mode, 'note': note, 'terms': terms, 'recent': [slim(p) for p in local],
            'wider': [slim(w) for w in wider], 'notes': notes}


# ------------------------------------------------------------------ reading queue and BibTeX

QUEUE_STATES = ('to read', 'reading', 'read')


def queue_list(con) -> list:
    out = []
    for r in con.execute('SELECT * FROM radar_queue ORDER BY added DESC'):
        d = dict(r)
        d['paper'] = json.loads(d['paper'])
        out.append(d)
    return out


def queue_action(con, data) -> list:
    act = data.get('action')
    if act == 'add':
        p = data.get('paper') or {}
        pid = str(p.get('id') or '')[:200]
        if not pid or not p.get('title'):
            raise ValueError('A paper with an id and a title is required.')
        keep = {k: p.get(k) for k in ('id', 'title', 'authors', 'published', 'url', 'pdf', 'venue', 'doi', 'categories')}
        keep['abstract'] = str(p.get('abstract') or '')[:3000]
        keep['authors'] = [str(a)[:120] for a in (p.get('authors') or [])][:60]
        con.execute('INSERT OR IGNORE INTO radar_queue VALUES(?,?,?,?,?,?)',
                    (pid, json.dumps(keep), 'to read', '', now_iso(), now_iso()))
    elif act == 'update':
        pid = str(data.get('id') or '')
        st = data.get('status')
        if st is not None and st not in QUEUE_STATES:
            raise ValueError('Unknown reading status.')
        row = con.execute('SELECT status, note FROM radar_queue WHERE id=?', (pid,)).fetchone()
        if not row:
            raise ValueError('That paper is not in the reading queue.')
        note = data.get('note')
        con.execute('UPDATE radar_queue SET status=?, note=?, updated=? WHERE id=?',
                    (st or row['status'], str(note)[:4000] if note is not None else row['note'], now_iso(), pid))
    elif act == 'remove':
        con.execute('DELETE FROM radar_queue WHERE id=?', (str(data.get('id') or ''),))
    else:
        raise ValueError('Unknown queue action.')
    con.commit()
    return queue_list(con)


def _bib_escape(s) -> str:
    s = str(s or '')
    for a, b in (('\\', '\\textbackslash{}'), ('{', '\\{'), ('}', '\\}'), ('&', '\\&'), ('%', '\\%'), ('$', '\\$'), ('#', '\\#'), ('_', '\\_')):
        s = s.replace(a, b)
    return s


def bibtex_entry(p, used=None) -> str:
    used = used if used is not None else set()
    authors = p.get('authors') or []
    last = norm_title((authors[0].split() or ['anon'])[-1] if authors else 'anon').replace(' ', '') or 'anon'
    year = (p.get('published') or '')[:4] or 'nd'
    first = next((w for w in norm_title(p.get('title')).split() if w not in STOP and len(w) > 2), 'paper')
    key = f'{last}{year}{first}'
    base, n = key, 1
    while key in used:
        n += 1
        key = f'{base}{chr(96 + n)}'
    used.add(key)
    pid = p.get('id') or ''
    fields = [('title', '{' + _bib_escape(p.get('title')) + '}'),
              ('author', ' and '.join(_bib_escape(a) for a in authors) or 'Unknown'),
              ('year', year)]
    if pid.startswith('arxiv:') and not p.get('venue'):
        kind = 'misc'
        fields += [('eprint', pid[6:]), ('archivePrefix', 'arXiv'),
                   ('primaryClass', (p.get('categories') or [''])[0])]
    else:
        kind = 'article'
        if p.get('venue'):
            fields.append(('journal', _bib_escape(p['venue'])))
    if p.get('doi'):
        fields.append(('doi', p['doi']))
    if p.get('url'):
        fields.append(('url', p['url']))
    body = ',\n'.join(f'  {k} = {{{v}}}' for k, v in fields if v)
    return f'@{kind}{{{key},\n{body}\n}}'


def bibtex(con, ids=None) -> str:
    items = queue_list(con)
    if ids:
        want = set(ids)
        items = [q for q in items if q['id'] in want]
    used = set()
    return '\n\n'.join(bibtex_entry(q['paper'], used) for q in items) + ('\n' if items else '')


# ------------------------------------------------------------------ weekly digest (Ollama)

def week_key(d=None) -> str:
    y, w, _ = (d or dt.date.today()).isocalendar()
    return f'{y}-W{w:02d}'


DIGEST_PROMPT = '''You write a short weekly research digest for one researcher.
Their own papers are:
{fingerprint}

Below are this week's new papers that are closest to their work (title and abstract excerpt).
Use ONLY this information. Do not invent results or claims.
Answer in English as JSON with keys:
"summary": 3 to 5 sentences on what moved this week in the researcher's areas,
"highlights": a list of up to 5 objects {{"title": exact paper title, "why": one sentence on why it is relevant to their work}}.

Papers:
{papers}
'''


def digest_get(con) -> dict:
    r = con.execute('SELECT * FROM radar_digest ORDER BY week DESC LIMIT 1').fetchone()
    d = dict(r) if r else None
    if d:
        try:
            d['text'] = json.loads(d['text'])
        except ValueError:
            pass
        d['papers'] = json.loads(d.get('papers') or '[]')
    return {'latest': d, 'week': week_key(), **DIGEST}


def digest_run(db_connect, cache_dir, url, model, call):
    """Run in a background thread. ``call`` is lm_labels._call."""
    DIGEST.update(status='running', detail=f'Writing with {model}…')
    try:
        data = overview(db_connect, cache_dir, days=7, per_lane=40)
        pool = sorted([p for l in data['lanes'] for p in l['papers']], key=lambda p: -p['match'])[:10]
        if not pool:
            raise RuntimeError('No papers this week yet. Let the radar collect first.')
        fps = '\n'.join(f"- {f['title']}" for f in data['fingerprint'] if f.get('title'))
        papers = '\n'.join(f"[{i + 1}] {p['title']}\n{p['abstract'][:450]}" for i, p in enumerate(pool))
        body = {'model': model, 'prompt': DIGEST_PROMPT.format(fingerprint=fps, papers=papers), 'stream': False,
                'format': 'json', 'options': {'temperature': 0.2, 'num_predict': 600, 'num_ctx': 4096}}
        res = call(url, '/api/generate', body, timeout=300)
        out = json.loads(res.get('response') or '{}')
        if not isinstance(out, dict) or not out.get('summary'):
            raise RuntimeError('The model did not return a summary')
        titles = {norm_title(p['title']): p for p in pool}
        hl = []
        for h in out.get('highlights') or []:
            if isinstance(h, dict) and norm_title(h.get('title', '')) in titles:
                p = titles[norm_title(h['title'])]
                hl.append({'title': p['title'], 'url': p['url'], 'why': str(h.get('why', ''))[:400]})
        text = {'summary': str(out['summary'])[:2000], 'highlights': hl}
        with closing(db_connect()) as con:
            con.execute('INSERT OR REPLACE INTO radar_digest VALUES(?,?,?,?,?)',
                        (week_key(), model, json.dumps(text), json.dumps([{'title': p['title'], 'url': p['url']} for p in pool]), now_iso()))
            con.commit()
        DIGEST.update(status='done', detail='')
    except Exception as exc:
        DIGEST.update(status='error', detail=f'{type(exc).__name__}: {str(exc)[:240]}')


# ------------------------------------------------------------------ jobs

def job_specs(fetch, db_connect, cache_dir) -> dict:
    """name -> (cache key, loader, seconds between refreshes). arXiv publishes once a day; the
    keyword search is incremental, so checking hourly costs one small request per phrase group."""
    return {
        'fingerprint': ('radar-fingerprint', lambda: resolve_fingerprint(db_connect, fetch, cache_dir), 7 * 86400),
        'keywords': ('radar-keywords', lambda: intake_keywords(fetch, db_connect, cache_dir), 3600),
        'rss': ('radar-rss', lambda: intake_rss(fetch, db_connect, cache_dir), 3 * 3600),
        'huggingface': ('radar-hf', lambda: huggingface(fetch, db_connect, cache_dir), 3 * 3600),
        'openalex': ('radar-openalex', lambda: intake_openalex(fetch, db_connect, cache_dir), 12 * 3600),
        'lab': ('radar-lab', lambda: trace_lab(fetch, db_connect, cache_dir), 12 * 3600),
        'openml': ('radar-openml', lambda: openml(fetch), 24 * 3600),
        'deadlines': ('radar-deadlines', lambda: deadlines(fetch), 24 * 3600),
    }


def run_jobs(request, fetch, db_connect, cache_dir, cache, force=False, only=None) -> dict:
    """Start (or read) every source job through retrieval_jobs.request; returns their states."""
    out = {}
    for name, (key, loader, ttl) in job_specs(fetch, db_connect, cache_dir).items():
        if only and name not in only:
            continue
        out[name] = request(key, loader, cache, force, ttl=ttl)
    return out


# ------------------------------------------------------------------ source check

def probe(fetch, db_connect=None) -> list:
    """One tiny request per source, to confirm fetching works on this computer."""
    key = oa_key(db_connect) if db_connect else ''
    checks = [
        ('arXiv API', lambda: len(parse_arxiv(arxiv_get(fetch, f'{ARXIV_API}?id_list=2407.09585&max_results=1'))), 'paper'),
        ('arXiv RSS', lambda: len(parse_arxiv_rss(arxiv_get(fetch, ARXIV_RSS + 'cs.LG'))), "of today's cs.LG listings"),
        ('Hugging Face papers', lambda: len(json.loads(fetch(f'{HF}/daily_papers?limit=5', BIG))), 'daily papers'),
        ('Hugging Face search', lambda: len(json.loads(fetch(f'{HF}/papers/search?q=automl&limit=5', BIG))), 'search results'),
        ('OpenAlex', lambda: len(json.loads(fetch(oa_url('/works', {'search': 'automl', 'per_page': 3}, key), BIG)).get('results') or []),
         'works' + (' (with your key)' if key else ' (no key)')),
        ('Crossref', lambda: 1 if json.loads(fetch(CROSSREF + '10.21203/rs.3.rs-11721788/v1', BIG)).get('message') else 0, 'record'),
        ('OpenML', lambda: len((json.loads(fetch(f'{OPENML}/data/list/limit/2/offset/0', 200_000)).get('data') or {}).get('dataset') or []), 'datasets'),
        ('Deadlines (GitHub)', lambda: len((mini_yaml(fetch(DDL + 'AI/iclr.yml', 1_000_000).decode('utf-8')) or [{}])[0].get('confs') or []), 'ICLR editions'),
    ]
    out = []
    for name, fn, unit in checks:
        t0 = time.time()
        try:
            n = fn()
            out.append({'source': name, 'ok': n > 0, 'ms': int((time.time() - t0) * 1000),
                        'detail': f'{n} {unit}' if n else 'reachable, but returned nothing'})
        except Exception as exc:
            msg = str(exc)
            hint = ' (daily budget used up: add a free OpenAlex key)' if name == 'OpenAlex' and '429' in msg else ''
            out.append({'source': name, 'ok': False, 'ms': int((time.time() - t0) * 1000),
                        'detail': f'{type(exc).__name__}: {msg[:160]}{hint}'})
    return out


# ------------------------------------------------------------------ search and filters

FIELD = re.compile(r'^(author|au|cat|category|title|ti):(.+)$', re.I)


def parse_query(q: str) -> dict:
    q = q or ''
    phrases = [x.strip().lower() for x in re.findall(r'"([^"]+)"', q) if x.strip()]
    rest = re.sub(r'"[^"]*"', ' ', q)
    out = {'phrases': phrases, 'authors': [], 'cats': [], 'title': [], 'neg': [], 'words': []}
    for tok in rest.split():
        m = FIELD.match(tok)
        if m:
            k, v = m.group(1).lower(), m.group(2).strip().lower()
            out['authors' if k in ('author', 'au') else 'cats' if k in ('cat', 'category') else 'title'].append(v)
        elif tok.startswith('-') and len(tok) > 1:
            out['neg'].append(tok[1:].lower())
        else:
            out['words'].append(tok.lower())
    return out


def auto_mode(q: str, parsed=None) -> tuple:
    """Keyword for precise queries (quotes, fields, exclusions, a few words); semantic for descriptions."""
    p = parsed or parse_query(q)
    if p['phrases'] or p['authors'] or p['cats'] or p['title'] or p['neg']:
        return 'keyword', 'uses quotes, a field or an exclusion'
    words = [w for w in p['words'] if w not in STOP]
    if len(p['words']) <= 3:
        return 'keyword', 'is a few words'
    if len(words) >= 4:
        return 'semantic', 'reads like a description'
    return 'keyword', 'is short'


def _passes(p, f, queue, hf) -> bool:
    if f.get('lane') and p.get('lane') != f['lane']:
        return False
    if f.get('cat') and not any(c.lower().startswith(f['cat'].lower()) for c in p.get('categories') or []):
        return False
    if f.get('min') and (p.get('match') or 0) < f['min']:
        return False
    src = f.get('source')
    if src == 'lab' and not p.get('lab'):
        return False
    if src == 'arxiv' and (p.get('source') or 'arxiv') != 'arxiv':
        return False
    if src in ('hf', 'openalex') and p.get('source') != src:
        return False
    if f.get('saved') == 'saved' and p['id'] not in queue:
        return False
    if f.get('saved') == 'unsaved' and p['id'] in queue:
        return False
    aid = p['id'][6:] if p['id'].startswith('arxiv:') else ''
    if f.get('hf') and not (aid and aid in hf):
        return False
    return True


def search(db_connect, cache_dir, q='', mode='auto', filters=None, days=7, limit=60) -> dict:
    f = filters or {}
    parsed = parse_query(q)
    reason = ''
    if q.strip() and mode == 'auto':
        mode, reason = auto_mode(q, parsed)
    with closing(db_connect()) as con:
        init(con)
        papers = recent(con, days)
        papers += [p for p in [_row_paper(r) for r in con.execute('SELECT * FROM radar_papers WHERE lab=1')]
                   if p['id'] not in {x['id'] for x in papers}] if f.get('source') == 'lab' else []
        rank_mode, note = score(con, papers, cache_dir)
        queue = {r[0] for r in con.execute('SELECT id FROM radar_queue')}
        hf = meta(con, 'hf_daily', {}) or {}
        pool = [p for p in papers if _passes(p, f, queue, hf)]
        fallback = ''
        if q.strip() and mode == 'semantic' and rank_mode != 'meaning':
            mode, fallback = 'keyword', 'Semantic search needs the language model pack; searched by keywords instead.'
        if q.strip() and mode == 'semantic':
            vec = _vecs(con, [p['id'] for p in pool])
    if not q.strip():
        res = sorted(pool, key=lambda p: -(p.get('match') or 0))
        for p in res:
            p['score'] = p.get('match') or 0
        used = 'filters'
    elif mode == 'semantic':
        qv = semantic.embed_texts([q], cache_dir)[0]
        res = []
        for p in pool:
            v = vec.get(p['id'])
            if v is not None:
                p['score'] = float(v @ qv)
                if p['score'] >= 0.2:
                    res.append(p)
        res.sort(key=lambda p: -p['score'])
        used = 'semantic'
    else:
        def hay(p):
            return (p['title'] + ' ' + (p.get('abstract') or '')).lower()

        def ok(p, words_all=True):
            h, a, t = hay(p), [plain_name(x) for x in p.get('authors') or []], p['title'].lower()
            if any(x not in h for x in parsed['phrases']) or any(x in h for x in parsed['neg']):
                return False
            if any(not any(au in x for x in a) for au in map(plain_name, parsed['authors'])):
                return False
            if any(not any(c.lower().startswith(x) for c in p.get('categories') or []) for x in parsed['cats']):
                return False
            if any(x not in t for x in parsed['title']):
                return False
            ws = parsed['words']
            return (all(w in h for w in ws) if words_all else any(w in h for w in ws)) if ws else True
        res = [p for p in pool if ok(p)]
        if not res and parsed['words']:
            res = [p for p in pool if ok(p, words_all=False)]
            fallback = fallback or 'No paper has all the words; showing papers with any of them.'
        terms = ' '.join(parsed['phrases'] + parsed['words'] + parsed['title'])
        tf = Tfidf([_text(p) for p in res] + [terms or q])
        qv = tf.vecs[-1]
        for i, p in enumerate(res):
            title_hit = any(w in p['title'].lower() for w in parsed['phrases'] + parsed['words'] + parsed['title'])
            p['score'] = sparse_dot(tf.vecs[i], qv) + (0.15 if title_hit else 0) + 0.05 * (p.get('match') or 0)
        res.sort(key=lambda p: -p['score'])
        used = 'keyword'
    out = []
    for p in res[:limit]:
        d = _slim(p, hf)
        d['score'] = round(p['score'], 3)
        out.append(d)
    return {'mode': used, 'reason': reason, 'note': fallback, 'rank_mode': rank_mode, 'total': len(res),
            'pool': len(pool), 'results': out, 'query': q, 'filters': f, 'days': days}


def plain_name(s) -> str:
    return unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
