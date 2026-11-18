"""Ask drawer: answers from articles Sanjaya holds and the open Wikipedia page, written by
the local Ollama model, with every sentence cited.

Retrieval
  - Sanjaya articles: the panel-search ranking (find.py) over the panel the question was
    asked from, or over everything held. Questions are long, so keyword matching is
    loosened: any query word counts and BM25 does the ranking. With the language model
    on, meaning and keywords are blended.
  - Wikipedia: the open article's plain text, split into ~110-word passages, ranked
    the same way; the lead passage is always offered.

Generation
  - Sources are numbered [A1]... (Sanjaya) and [W1]... (Wikipedia). The model is told to
    use only those sources and to cite each sentence. Sanjaya then checks the citations:
    unknown ones are removed and uncited sentences are marked, so a reader can see what
    is supported.
  - Runs in a background job and streams into the drawer. If Ollama isn't running, the
    sources are still returned so the question isn't wasted.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
import urllib.request

import find

JOBS = {}
LOCK = threading.Lock()
MAX_JOBS = 30
SYSTEM = """You answer questions for a news and research dashboard.
Use ONLY the numbered sources below. Do not use outside knowledge.
Cite every sentence with the source ids it relies on, in square brackets, for example [A2] or [W1][A4].
If the sources don't answer the question, say so in one sentence and stop.
Be concise: at most {words} words, in plain English, no headings. Mention when sources disagree.
Sanjaya articles are news reports; say "reports" or "according to" rather than stating claims as settled fact."""


def loosen(groups):
    """Long questions: one group of all terms, any of which may match."""
    terms = [t for g in groups for t in g]
    return [list(dict.fromkeys(terms))[:14]] if terms else []


def rank_loose(question, docs, mode, sims):
    groups = loosen(find.parse(question))
    if not groups:
        return []
    kw = {}
    if mode in ('keywords', 'both'):
        # Any single term qualifies; BM25 sums the evidence.
        kw = find.keyword_scores(groups, docs, need_fn=lambda n: 1)
    top = max((v[0] for v in kw.values()), default=0) or 1
    out = []
    for d in docs:
        k, s = kw.get(d[0]), sims.get(d[0])
        if mode == 'keywords':
            if not k:
                continue
            score = k[0] / top
        else:
            if not k and (s is None or s < find.BLEND_FLOOR):
                continue
            score = find.W_MEANING * max(0.0, s or 0) + find.W_KEYWORD * (k[0] / top if k else 0)
        out.append({'id': d[0], 'score': score, 'terms': k[1] if k else [], 'meaning': s})
    out.sort(key=lambda r: -r['score'])
    return out


def build_prompt(question, articles, passages, words=220):
    lines = []
    for i, a in enumerate(articles, 1):
        ex = re.sub(r'\s+', ' ', a.get('summary') or '')[:420]
        when = (a.get('published') or '')[:10]
        lines.append(f"[A{i}] {a.get('outlet') or a.get('source', '')} ({when}): {a.get('title', '')}" + (f" — {ex}" if ex and ex != a.get('title') else ''))
    for i, p in enumerate(passages, 1):
        lines.append(f"[W{i}] Wikipedia, \"{p['page']}\", section \"{p['section']}\": {p['text']}")
    return [{'role': 'system', 'content': SYSTEM.format(words=words)},
            {'role': 'user', 'content': 'Sources:\n' + '\n'.join(lines) + f'\n\nQuestion: {question}\nAnswer with citations:'}]


CITE = re.compile(r'\[((?:[AW]\d{1,2})(?:\s*[,;]\s*[AW]\d{1,2})*)\]')


def check_citations(text, n_a, n_w):
    """Drop citations to sources that don't exist; split into sentences with their citations."""
    def keep(m):
        ids = [x.strip() for x in re.split(r'[,;]', m.group(1))]
        ok = [x for x in ids if (x[0] == 'A' and 1 <= int(x[1:]) <= n_a) or (x[0] == 'W' and 1 <= int(x[1:]) <= n_w)]
        return ''.join(f'[{x}]' for x in ok)
    text = CITE.sub(keep, text or '')
    sentences = []
    for s in re.split(r'(?<=[.!?])\s+(?=[A-Z"(\[])', text.strip()):
        if not s.strip():
            continue
        cites = re.findall(r'\[([AW]\d{1,2})\]', s)
        sentences.append({'text': s.strip(), 'cites': list(dict.fromkeys(cites))})
    # A citation-only fragment belongs to the sentence before it.
    merged = []
    for s in sentences:
        if merged and not re.sub(r'\[[AW]\d{1,2}\]', '', s['text']).strip():
            merged[-1]['text'] += ' ' + s['text']
            merged[-1]['cites'] = list(dict.fromkeys(merged[-1]['cites'] + s['cites']))
        else:
            merged.append(s)
    return text, merged


def _stream(url, model, messages, on_text, timeout=180):
    body = {'model': model, 'messages': messages, 'stream': True, 'options': {'temperature': 0.2, 'num_ctx': 6144, 'num_predict': 700}}
    req = urllib.request.Request(url + '/api/chat', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # local only
    with opener.open(req, timeout=timeout) as r:
        for line in r:
            if not line.strip():
                continue
            d = json.loads(line.decode('utf-8'))
            if d.get('error'):
                raise RuntimeError(d['error'])
            on_text(d.get('message', {}).get('content', ''))
            if d.get('done'):
                break


def start(question, articles, passages, url, model, stream=None):
    jid = uuid.uuid4().hex[:12]
    job = {'id': jid, 'status': 'writing', 'text': '', 'sentences': [], 'error': '', 'model': model, 'started': time.time(),
           'sources': {'atlas': articles, 'wikipedia': passages}}
    with LOCK:
        JOBS[jid] = job
        for k in sorted(JOBS, key=lambda k: JOBS[k]['started'])[:-MAX_JOBS]:
            JOBS.pop(k, None)
    messages = build_prompt(question, articles, passages)

    def run():
        def add(t):
            with LOCK:
                job['text'] += t
        try:
            (stream or _stream)(url, model, messages, add)
            with LOCK:
                job['text'], job['sentences'] = check_citations(job['text'], len(articles), len(passages))
                job['status'] = 'done'
        except Exception as exc:
            with LOCK:
                job['status'] = 'error'
                job['error'] = f'{type(exc).__name__}: {str(exc)[:200]}'
    threading.Thread(target=run, daemon=True, name='ask').start()
    return job


def get(jid):
    with LOCK:
        j = JOBS.get(jid)
        return json.loads(json.dumps(j)) if j else None
