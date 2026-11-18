"""Panel search: find held articles by keywords, by meaning, or both.

Query syntax (kept deliberately small):
  - words:                 iran nuclear talks      (most of the words must appear)
  - "quoted phrases":      "south china sea"       (the exact phrase)
  - commas for "or":       iran, north korea       (either topic; articles covering both rank higher)

Keyword ranking is BM25 over title (counted twice), summary and outlet name, with light
plural/suffix matching. Meaning ranking is cosine similarity between the query and each
article in the local multilingual model's space. "Both" keeps either kind of match and
blends the two scores.
"""
from __future__ import annotations

import math
import re

STOP = set('''a an and are as at be by for from has have in into is it its of on or that the this to was were will with
about after before over under than then them they their there these those what when where which who why how new news
latest today live update updates says said video watch'''.split())
MEANING_FLOOR = 0.40   # meaning-only: cosine needed to count as a match
BLEND_FLOOR = 0.46     # "both": cosine needed for a match without any keyword
W_MEANING, W_KEYWORD = 0.6, 0.4


def parse(q: str) -> list:
    """Split a query into groups (comma = or); each group is a list of terms (phrases kept whole)."""
    groups = []
    for part in re.split(r'[,;|]|\bOR\b', str(q or '')[:300]):
        terms = [p.lower() for p in re.findall(r'"([^"]{2,80})"', part)]
        rest = re.sub(r'"[^"]*"', ' ', part)
        for w in re.findall(r"[\w][\w'\-.]*", rest.lower()):
            w = w.strip(".'-")
            if len(w) > 1 and w not in STOP:
                terms.append(w)
        if terms:
            groups.append(list(dict.fromkeys(terms))[:8])
    return groups[:5]


def _pattern(term: str):
    if ' ' in term:
        return re.compile(r'\b' + r'\s+'.join(re.escape(t) for t in term.split()) + r'\b', re.I)
    # light stemming: "sanction" finds "sanctions", "talk" finds "talks/talking"
    stem = term[:-1] if len(term) > 4 and term.endswith('s') else term
    return re.compile(r'\b' + re.escape(stem) + r"[\w']{0,3}\b", re.I)


def need(n: int) -> int:
    """Terms of a group that must match: all of 1–2, two of 3, three of 4, and so on."""
    return n if n <= 2 else math.ceil(n * 0.6)


def keyword_scores(groups, docs, need_fn=None) -> dict:
    """docs: list of (id, title, text, source). Returns id -> (score, matched_terms, groups_hit)."""
    terms = sorted({t for g in groups for t in g})
    if not terms or not docs:
        return {}
    pats = {t: _pattern(t) for t in terms}
    N = len(docs)
    lens = [len((d[1] or '') + ' ' + (d[2] or '')) / 6 + 1 for d in docs]
    avg = sum(lens) / N
    tf = {}
    df = dict.fromkeys(terms, 0)
    for i, (_, title, text, source) in enumerate(docs):
        for t, p in pats.items():
            n = 2 * len(p.findall(title or '')) + len(p.findall(text or '')) + len(p.findall(source or ''))
            if n:
                tf[(i, t)] = n
                df[t] += 1
    idf = {t: math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5)) for t in terms}
    out = {}
    k1, b = 1.2, 0.6
    for i, d in enumerate(docs):
        hit = {t for t in terms if (i, t) in tf}
        if not hit:
            continue
        groups_hit = [g for g in groups if len(hit & set(g)) >= (need_fn or need)(len(g))]
        if not groups_hit:
            continue
        s = 0.0
        for t in hit:
            f = tf[(i, t)]
            s += idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * lens[i] / avg))
        s *= 1 + 0.5 * (len(groups_hit) - 1)  # covers more than one comma-separated topic
        out[d[0]] = (s, sorted(hit), len(groups_hit))
    return out


def rank(groups, docs, mode, sims=None, limit=60):
    """Combine keyword and meaning scores.

    mode: 'keywords' | 'meaning' | 'both'. sims: id -> cosine (best over groups) or None.
    Returns a list of dicts sorted best first.
    """
    kw = keyword_scores(groups, docs) if mode in ('keywords', 'both') else {}
    sims = sims or {}
    top = max((v[0] for v in kw.values()), default=0) or 1
    out = []
    for d in docs:
        i = d[0]
        k = kw.get(i)
        s = sims.get(i)
        if mode == 'keywords':
            if not k:
                continue
            score = k[0] / top
        elif mode == 'meaning':
            if s is None or s < MEANING_FLOOR:
                continue
            score = s
        else:
            if not k and (s is None or s < BLEND_FLOOR):
                continue
            score = W_MEANING * max(0.0, s or 0) + W_KEYWORD * (k[0] / top if k else 0)
        out.append({'id': i, 'score': round(score, 4), 'meaning': None if s is None else round(float(s), 3),
                    'keyword': round(k[0] / top, 3) if k else 0, 'terms': k[1] if k else []})
    out.sort(key=lambda r: -r['score'])
    return out[:limit]


def web_queries(groups, days=7) -> list:
    """Google News queries: one per comma-separated topic (up to three)."""
    qs = []
    for g in groups[:3]:
        words = ' '.join(f'"{t}"' if ' ' in t else t for t in g[:6])
        qs.append(f'{words} when:{days}d')
    return qs
