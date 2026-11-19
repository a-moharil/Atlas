"""ATLAS v5.1 · optional model-written story labels and summaries (local Ollama).

Off by default. When switched on in Language model settings, Sanjaya asks a small
local model (default ``qwen2.5:1.5b``, multilingual and fast on a laptop processor)
to describe each top story group using only the supplied headlines and excerpts.
Output is cached per group membership, always shown with a "Generated" tag, and
never replaces publisher text. Ollama must listen on this computer only.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
import urllib.request
from contextlib import closing

DEFAULT_URL = 'http://127.0.0.1:11434'
DEFAULT_MODEL = 'qwen2.5:1.5b'
LOCK = threading.Lock()
STATE = {'status': 'not_checked', 'detail': '', 'models': [], 'last_run': None, 'written': 0}
PROMPT = """You label groups of news headlines for a research dashboard.
Use ONLY the headlines and excerpts below. Do not add facts, numbers, names or causes that are not in them.
Headlines may be in different languages; always answer in English.

{items}

Reply with JSON only:
{{"label": "<neutral topic label, at most 8 words>",
  "summary": "<one or two neutral sentences on what the outlets report>",
  "differences": "<one sentence on how the outlets' framing or details differ, or 'No clear difference.'>"}}"""


def init(con):
    con.executescript('''CREATE TABLE IF NOT EXISTS story_labels(
        key TEXT PRIMARY KEY, model TEXT NOT NULL, label TEXT NOT NULL, summary TEXT NOT NULL,
        differences TEXT NOT NULL, sources INTEGER NOT NULL, created TEXT NOT NULL)''')
    con.commit()


def _call(url, path, body=None, timeout=8):
    req = urllib.request.Request(url + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'}, method='POST' if body is not None else 'GET')
    # Direct local connection: never through a proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read(2_000_000).decode('utf-8'))


def check(url=DEFAULT_URL, model=DEFAULT_MODEL) -> dict:
    try:
        tags = _call(url, '/api/tags', timeout=3)
        names = [m.get('name', '') for m in tags.get('models', [])]
        have = any(n == model or n.split(':')[0] == model.split(':')[0] and n.endswith(model.split(':')[-1]) for n in names)
        STATE.update(status='ready' if have else 'model_missing', models=names,
                     detail='Ollama is running' + ('' if have else f'; run "ollama pull {model}" to install the model'))
    except Exception as exc:
        STATE.update(status='offline', models=[], detail=f'Ollama not reachable at {url} ({type(exc).__name__}). Install it from ollama.com and keep it running.')
    return dict(STATE)


def group_key(records) -> str:
    ids = sorted(r['id'] for r in records)[:12]
    return hashlib.sha256('|'.join(ids).encode()).hexdigest()[:24]


def build_prompt(records) -> str:
    lines = []
    for r in records[:8]:
        ex = (r.get('summary') or '').strip().replace('\n', ' ')[:240]
        lines.append(f"- [{r.get('source', '')}] {r.get('title', '')}" + (f" — {ex}" if ex and ex != r.get('title') else ''))
    return PROMPT.format(items='\n'.join(lines))


def parse(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find('{'), text.rfind('}')
        data = json.loads(text[start:end + 1]) if start >= 0 and end > start else {}
    out = {k: str(data.get(k, '')).strip()[:limit] for k, limit in (('label', 90), ('summary', 420), ('differences', 300))}
    if not out['label'] or not out['summary']:
        raise ValueError('Model reply missing label or summary')
    return out


def write(records, url, model) -> dict:
    reply = _call(url, '/api/generate', {'model': model, 'prompt': build_prompt(records), 'stream': False, 'format': 'json',
                                         'options': {'temperature': 0.2, 'num_predict': 220, 'num_ctx': 2048}}, timeout=120)
    return parse(reply.get('response', ''))


def cached(con, keys) -> dict:
    init(con)
    if not keys:
        return {}
    q = f"SELECT * FROM story_labels WHERE key IN ({','.join('?' for _ in keys)})"
    return {r['key']: dict(r) for r in con.execute(q, tuple(keys))}


def run(groups, db_connect, url, model, limit=12) -> int:
    """Label up to ``limit`` multi-outlet groups lacking a cached label."""
    if not LOCK.acquire(blocking=False):
        return 0
    try:
        if check(url, model)['status'] != 'ready':
            return 0
        todo = []
        with closing(db_connect()) as con:
            have = cached(con, [group_key(g) for g in groups])
        for g in groups:
            if len({r.get('source') for r in g}) < 2:
                continue
            k = group_key(g)
            if k not in have:
                todo.append((k, g))
        n = 0
        for k, g in todo[:limit]:
            try:
                out = write(g, url, model)
            except Exception as exc:
                STATE['detail'] = f'Last label failed: {type(exc).__name__}: {str(exc)[:160]}'
                continue
            with closing(db_connect()) as con:
                init(con)
                con.execute('INSERT OR REPLACE INTO story_labels VALUES(?,?,?,?,?,?,?)',
                            (k, model, out['label'], out['summary'], out['differences'], len({r.get('source') for r in g}),
                             dt.datetime.now(dt.timezone.utc).isoformat()))
                con.commit()
            n += 1
        STATE.update(last_run=dt.datetime.now(dt.timezone.utc).isoformat(), written=STATE.get('written', 0) + n)
        return n
    finally:
        LOCK.release()
