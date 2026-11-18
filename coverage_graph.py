"""Atlas coverage graph: sources -> stories -> articles.

Overview: one node per source on the page. Two kinds of edges, both kept:
  * co-coverage: how many stories two sources both covered (Jaccard over their story sets);
  * topic overlap: how close their coverage is in meaning, measured article by article
    (for each article of A, its best match among B's articles; averaged both ways).
    This is robust to outlets that cover many topics, unlike one averaged vector per source.

Diffusion from a seed article: a random walk with restart (personalised PageRank) over
articles, their stories and their sources, plus each article's nearest neighbours by
meaning. It reaches the seed story's sources first, then related stories on any desk,
and flags sources that usually cover this kind of story but have not covered this one.

Uses the stored article embeddings when the language model pack is ready; otherwise
TF-IDF keyword vectors, and says so.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter, defaultdict

import semantic
from research_radar import Tfidf, key_terms, sparse_dot

MAX_PAGE = 600       # articles considered for the overview
MAX_SOURCES = 40     # nodes drawn in the overview
MAX_POOL = 2500      # articles considered for diffusion (meaning mode)
MAX_POOL_KW = 500    # articles considered for diffusion (keyword mode)
KNN = 8


def _story(e) -> str:
    return (e.get('story') or {}).get('id') or e['id']


def _text(e) -> str:
    return (e.get('title') or '') + '. ' + (e.get('summary') or '')[:300]


def _articles(entries):
    return [e for e in entries if e.get('medium') == 'article' and e.get('publisher')]


def _space(arts, db_connect):
    """('meaning', {id: unit vector}) when embeddings cover most articles, else ('keywords', tfidf)."""
    if semantic.ready():
        vecs = semantic.vectors(db_connect, [e['id'] for e in arts])
        if len(vecs) >= 0.6 * max(1, len(arts)):
            return 'meaning', vecs
    return 'keywords', Tfidf([_text(e) for e in arts])


def _sim_fn(mode, space, arts):
    if mode == 'meaning':
        return lambda i, j: float(space[arts[i]['id']] @ space[arts[j]['id']]) if arts[i]['id'] in space and arts[j]['id'] in space else 0.0
    return lambda i, j: sparse_dot(space.vecs[i], space.vecs[j])


def _sim_matrix(mode, space, arts):
    """Full similarity matrix as a list of rows (numpy when available)."""
    if mode == 'meaning':
        np = semantic._np
        ok = [i for i, e in enumerate(arts) if e['id'] in space]
        M = np.zeros((len(arts), len(arts)), dtype=np.float32)
        if ok:
            V = np.stack([space[arts[i]['id']] for i in ok])
            S = V @ V.T
            idx = np.array(ok)
            M[np.ix_(idx, idx)] = S
        return M
    n = len(arts)
    M = [[0.0] * n for _ in range(n)]
    for i in range(n):
        vi = space.vecs[i]
        M[i][i] = 1.0
        for j in range(i + 1, n):
            s = sparse_dot(vi, space.vecs[j])
            M[i][j] = M[j][i] = s
    return M


# ------------------------------------------------------------------ overview

def overview(entries, page_ids, db_connect, profile, pref_of=lambda h: '') -> dict:
    want = set(page_ids)
    arts = [e for e in _articles(entries) if e['id'] in want][:MAX_PAGE]
    if not arts:
        return {'mode': 'keywords', 'note': 'No articles on this page yet.', 'nodes': [], 'edges': [], 'stories': {}}
    by_src = defaultdict(list)
    for i, e in enumerate(arts):
        by_src[e['publisher']].append(i)
    hosts = sorted(by_src, key=lambda h: -len(by_src[h]))[:MAX_SOURCES]
    keep = set(hosts)
    story_srcs = defaultdict(set)
    story_arts = defaultdict(list)
    for i, e in enumerate(arts):
        story_arts[_story(e)].append(i)
        if e['publisher'] in keep:
            story_srcs[_story(e)].add(e['publisher'])
    src_stories = defaultdict(set)
    for s, hs in story_srcs.items():
        for h in hs:
            src_stories[h].add(s)
    # Co-coverage over shared stories.
    co = Counter()
    for s, hs in story_srcs.items():
        hs = sorted(hs)
        for a in range(len(hs)):
            for b in range(a + 1, len(hs)):
                co[(hs[a], hs[b])] += 1
    # Topic overlap: soft, article-level matching between sources.
    mode, space = _space(arts, db_connect)
    M = _sim_matrix(mode, space, arts)
    np = semantic._np if mode == 'meaning' else None
    topic = {}
    for a in range(len(hosts)):
        for b in range(a + 1, len(hosts)):
            A, B = by_src[hosts[a]], by_src[hosts[b]]
            if np is not None:
                sub = M[np.ix_(A, B)]
                ab, ba = float(sub.max(1).mean()), float(sub.max(0).mean())
            else:
                ab = sum(max(M[i][j] for j in B) for i in A) / len(A)
                ba = sum(max(M[i][j] for i in A) for j in B) / len(B)
            topic[tuple(sorted((hosts[a], hosts[b])))] = (ab + ba) / 2
    # Rescale topic overlap within this page so the strongest pairs read as strong.
    tv = sorted(topic.values())
    lo, hi = (tv[len(tv) // 10], tv[-1]) if tv else (0, 1)
    edges = []
    per_node = defaultdict(list)
    for pair, t in topic.items():
        c = co.get(pair, 0)
        union = len(src_stories[pair[0]] | src_stories[pair[1]]) or 1
        jac = c / union
        tn = max(0.0, (t - lo) / (hi - lo)) if hi > lo else 0.0
        e = {'a': pair[0], 'b': pair[1], 'shared': c, 'co': round(jac, 3), 'topic': round(tn, 3), 'topic_raw': round(t, 3)}
        per_node[pair[0]].append(e)
        per_node[pair[1]].append(e)
    chosen = set()
    for h, es in per_node.items():
        for e in sorted(es, key=lambda e: -max(e['co'], e['topic']))[:5]:
            if e['shared'] or e['topic'] >= 0.35:
                chosen.add((e['a'], e['b']))
    for (a, b), c in co.items():
        if c >= 2:
            chosen.add((a, b))
    for pair in chosen:
        e = next(x for x in per_node[pair[0]] if (x['a'], x['b']) == pair)
        edges.append(e)
    nodes = []
    for h in hosts:
        p = profile(h)
        nodes.append({'id': h, 'name': p.get('name') or h, 'lean': p.get('lean'), 'kind': p.get('kind'), 'country': p.get('country', ''),
                      'logo': p.get('logo', ''), 'masthead': p.get('masthead', 'grotesk'), 'articles': len(by_src[h]),
                      'stories': len(src_stories[h]), 'primary': pref_of(h) == 'primary'})
    stories = {}
    for s, idxs in story_arts.items():
        lead = max(idxs, key=lambda i: arts[i].get('published') or '')
        stories[s] = {'id': s, 'title': arts[lead].get('title', ''), 'articles': [arts[i]['id'] for i in idxs],
                      'sources': sorted(story_srcs.get(s, set()))}
    note = ('Topic overlap from the local language model.' if mode == 'meaning'
            else 'Topic overlap from shared keywords (language model pack not ready).')
    return {'mode': mode, 'note': note, 'nodes': nodes, 'edges': edges, 'stories': stories,
            'articles': len(arts), 'sources_total': len(by_src)}


# ------------------------------------------------------------------ diffusion

def _pool(entries, seed, days):
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    arts = [e for e in _articles(entries) if (e.get('published') or '') >= cut or e['id'] == seed['id']]
    arts.sort(key=lambda e: e.get('published') or '', reverse=True)
    return arts


def diffuse(entries, seed_id, db_connect, profile, days=7, alpha=0.2, steps=30) -> dict:
    allarts = _articles(entries)
    seed = next((e for e in allarts if e['id'] == seed_id), None)
    if seed is None:
        raise LookupError('That article is no longer held. Refresh the page and try again.')
    arts = _pool(entries, seed, days)
    seed_story = _story(seed)
    head = [e for e in arts if _story(e) == seed_story]
    rest = [e for e in arts if _story(e) != seed_story]
    arts = head + rest[:MAX_POOL - len(head)]  # the seed's story always takes part
    mode, space = _space(arts, db_connect)
    if mode == 'keywords':
        arts = arts[:max(len(head), MAX_POOL_KW)]
        space = Tfidf([_text(e) for e in arts])
    n = len(arts)
    idx = {e['id']: i for i, e in enumerate(arts)}
    # Nodes: articles 0..n-1, then stories, then sources.
    stories = sorted({_story(e) for e in arts})
    hosts = sorted({e['publisher'] for e in arts})
    sidx = {s: n + k for k, s in enumerate(stories)}
    hidx = {h: n + len(stories) + k for k, h in enumerate(hosts)}
    N = n + len(stories) + len(hosts)
    adj = [defaultdict(float) for _ in range(N)]

    def link(a, b, w):
        if a != b and w > 0:
            adj[a][b] += w
            adj[b][a] += w
    for i, e in enumerate(arts):
        link(i, sidx[_story(e)], 1.0)
        link(i, hidx[e['publisher']], 0.5)
    # Nearest neighbours by meaning (or keywords): bridges between stories and desks.
    seed_sims = [0.0] * n
    if mode == 'meaning':
        np = semantic._np
        have = [i for i, e in enumerate(arts) if e['id'] in space]
        if have:
            V = np.stack([space[arts[i]['id']] for i in have])
            for start in range(0, len(have), 512):
                S = V[start:start + 512] @ V.T
                for r in range(S.shape[0]):
                    i = have[start + r]
                    row = S[r]
                    row[start + r] = -1
                    top = np.argpartition(-row, min(KNN, len(have) - 1))[:KNN]
                    for t in top:
                        if row[t] >= 0.45:
                            link(i, have[int(t)], float(row[t]))
            if seed['id'] in space:
                sv = space[seed['id']]
                for i in have:
                    seed_sims[i] = float(space[arts[i]['id']] @ sv)
    else:
        for i in range(n):
            vi = space.vecs[i]
            sims = sorted(((sparse_dot(vi, space.vecs[j]), j) for j in range(n) if j != i), reverse=True)[:KNN]
            for s, j in sims:
                if s >= 0.12:
                    link(i, j, s * 2)
        si = idx[seed['id']]
        seed_sims = [sparse_dot(space.vecs[si], space.vecs[i]) for i in range(n)]
    # Personalised PageRank from the seed article.
    deg = [sum(a.values()) or 1.0 for a in adj]
    p0 = [0.0] * N
    p0[idx[seed['id']]] = 1.0
    p = p0[:]
    for _ in range(steps):
        nxt = [alpha * x for x in p0]
        for u in range(N):
            if p[u]:
                share = (1 - alpha) * p[u] / deg[u]
                for v, w in adj[u].items():
                    nxt[v] += share * w
        p = nxt
    # Stories: the seed's own story, then related ones by walk score.
    by_story = defaultdict(list)
    for i, e in enumerate(arts):
        by_story[_story(e)].append(i)

    def story_card(s, score=None):
        members = by_story[s]
        lead = max(members, key=lambda i: arts[i].get('published') or '')
        return {'id': s, 'title': arts[lead].get('title', ''), 'articles': [arts[i]['id'] for i in members],
                'sources': sorted({arts[i]['publisher'] for i in members}),
                'score': round(score if score is not None else p[sidx[s]], 6),
                'similarity': round(max(seed_sims[i] for i in members), 3)}
    ranked = sorted((s for s in stories if s != seed_story), key=lambda s: -p[sidx[s]])
    close = 0.35 if mode == 'meaning' else 0.08
    cards = [story_card(s) for s in ranked[:40]]
    # Related = close in meaning; the rest were reached only through the same outlets.
    related = [c for c in cards if c['similarity'] >= close][:10]
    via = [c for c in cards if c['similarity'] < close][:6]
    same = story_card(seed_story)
    covered = set(same['sources'])
    reached = sorted(hosts, key=lambda h: -p[hidx[h]])[:16]
    # Coverage gaps: sources whose recent articles are close to this story but did not cover it.
    src_arts = defaultdict(list)
    for i, e in enumerate(arts):
        src_arts[e['publisher']].append(i)
    gaps = []
    for h, members in src_arts.items():
        if h in covered or len(members) < 3:
            continue
        top3 = sorted((seed_sims[i] for i in members), reverse=True)[:3]
        aff = sum(top3) / len(top3)
        gaps.append((aff, h))
    gaps.sort(reverse=True)
    floor = 0.45 if mode == 'meaning' else 0.05
    gaps = [(a, h) for a, h in gaps if a >= floor][:6]

    def src(h, extra=None):
        pr = profile(h)
        d = {'id': h, 'name': pr.get('name') or h, 'lean': pr.get('lean'), 'logo': pr.get('logo', ''),
             'masthead': pr.get('masthead', 'grotesk'), 'score': round(p[hidx[h]], 6) if h in hidx else 0,
             'covered': h in covered, 'articles': len(src_arts.get(h, []))}
        if extra:
            d.update(extra)
        return d
    background = Tfidf([e.get('title', '') for e in arts[:800]])  # rare-in-the-pool words make better queries
    terms = key_terms(' '.join(arts[i].get('title', '') for i in by_story[seed_story]), 5, background)
    return {'mode': mode, 'seed': seed['id'], 'seed_story': same, 'related': related, 'via_sources': via,
            'sources': [src(h) for h in reached], 'gaps': [src(h, {'affinity': round(a, 3)}) for a, h in gaps],
            'pool': n, 'days': days, 'terms': terms,
            'note': ('Spread over articles by meaning with the local language model.' if mode == 'meaning'
                     else 'Spread over shared keywords (language model pack not ready); results are rougher.')}


def search_queries(terms, gap_hosts, max_sites=3) -> list:
    """Google News queries for 'Search further': one open query, then one per gap outlet."""
    words = ' '.join(f'"{t}"' if ' ' in t else t for t in terms[:4])
    qs = [f'{words} when:3d']
    for h in [h for h in gap_hosts if h and not h.startswith('feed:')][:max_sites]:
        qs.append(f'site:{h} {" ".join(t for t in terms[:3])} when:7d')
    return qs
