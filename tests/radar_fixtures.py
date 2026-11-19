"""Offline fixtures for the research radar, shaped like the real API responses.

Papers here are invented for testing; deadline files in fixtures/radar/ are real
copies of the ccfddl dataset. ``fake_fetch`` routes URLs the way the network would.
"""
import datetime as dt
import json
import re
import urllib.parse
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent / 'fixtures' / 'radar'

LANE_PAPERS = [
    ('AutoML pipeline synthesis with pre-trained transformers for tabular and multimodal data',
     'We synthesise machine learning pipelines with a pre-trained transformer that ranks candidate pipelines, reducing AutoML search cost on OpenML benchmark tasks.'),
    ('Meta-learning warm starts for hyperparameter optimization across OpenML tasks',
     'We learn warm-start configurations for hyperparameter optimization from thousands of OpenML experiments and evaluate on an AutoML benchmark.'),
    ('Neural architecture search under a compute budget for tabular AutoML',
     'A budget-aware neural architecture search method for tabular AutoML that matches gradient boosting on standard benchmarks.'),
    ('Hyperbolic embeddings of weight trajectories reveal training dynamics of deep networks',
     'We embed snapshots of network weights during training in hyperbolic space and show that training dynamics self-organise, giving intrinsic explainability of deep networks.'),
    ('Scale invariance in the loss landscape of deep neural networks',
     'We study scale-invariant diagnostics of training dynamics and the geometry of the loss landscape of deep neural networks across optimisers.'),
    ('Permutation-equivariant meta-networks over neural network weights',
     'Meta-networks that read the parameters of trained networks, equivariant to neuron permutations, predict generalisation from weights alone.'),
    ('Contextual embeddings from transformer language models for code understanding',
     'We probe contextual embeddings of transformer language models and propose a contextualization toolkit for source code representation learning.'),
    ('Scaling multimodal foundation models with sparse mixtures of experts',
     'A sparse mixture-of-experts multimodal foundation model trained on image and text pairs improves transfer learning.'),
    ('Bots in issue trackers: how automation changes developer comments on GitHub and JIRA',
     'Mining software repositories, we study bots in issue trackers and their influence on human comments in GitHub and JIRA projects.'),
    ('MLOps debt: an empirical study of machine learning systems in production',
     'We mine repositories of ML systems in production to characterise MLOps technical debt and testing practices for deep learning code.'),
    ('Data quality checks for tabular benchmarks and dataset documentation',
     'A data-centric study of dataset curation, documentation and data quality issues in popular tabular benchmarks and datasets.'),
    ('Diffusion models for protein backbone generation',
     'We train a diffusion model to generate protein backbones and evaluate designability.'),
    ('Reinforcement learning from human feedback for dialogue agents',
     'A study of reward modelling and preference optimisation for large language model dialogue agents.'),
    ('Efficient attention kernels for long-context transformers',
     'Memory-efficient attention kernels enabling long-context transformer language models on commodity hardware.'),
]
CATS = ['cs.LG', 'cs.AI', 'stat.ML', 'cs.SE', 'cs.CL', 'cs.NE']
LAB = [
    ('Occam-style transferability estimation for model selection', ['Prabhant Singh', 'Joaquin Vanschoren']),
    ('Automated machine learning for unsupervised tabular tasks', ['Diana-Alexandra Onuțu', 'Joaquin Vanschoren']),
    ('Self-regulated neurogenesis for online data-incremental learning', ['Anna Vettoruzzo', 'Joaquin Vanschoren']),
]


def _entry(aid, title, abstract, authors, when, cats, journal=''):
    a = ''.join(f'<author><name>{escape(n)}</name></author>' for n in authors)
    c = ''.join(f'<category term="{t}" scheme="http://arxiv.org/schemas/atom"/>' for t in cats)
    j = f'<arxiv:journal_ref xmlns:arxiv="http://arxiv.org/schemas/atom">{escape(journal)}</arxiv:journal_ref>' if journal else ''
    ts = when.strftime('%Y-%m-%dT%H:%M:%SZ')
    return f'''<entry><id>http://arxiv.org/abs/{aid}v1</id><updated>{ts}</updated><published>{ts}</published>
<title>{escape(title)}</title><summary>  {escape(abstract)}
  </summary>{a}{j}<link href="http://arxiv.org/abs/{aid}v1" rel="alternate" type="text/html"/>
<link title="pdf" href="http://arxiv.org/pdf/{aid}v1" rel="related" type="application/pdf"/>
<arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="{cats[0]}" scheme="http://arxiv.org/schemas/atom"/>{c}</entry>'''


def _feed(entries):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
            '<title type="html">ArXiv Query</title><id>http://arxiv.org/api/x</id>'
            + ''.join(entries) + '</feed>').encode()


def arxiv_bulk(now=None, copies=4):
    now = now or dt.datetime.now(dt.timezone.utc)
    out, n = [], 0
    for k in range(copies):
        for i, (t, a) in enumerate(LANE_PAPERS):
            n += 1
            title = t if k == 0 else f'{t} (variant {k + 1})'
            out.append(_entry(f'2611.{10000 + n}', title, a, [f'Author {n} One', f'Author {n} Two'],
                              now - dt.timedelta(hours=3 + n * 2), [CATS[i % len(CATS)], 'cs.LG']))
    return _feed(out)


def arxiv_lab(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    return _feed([_entry(f'2610.{20000 + i}', t, f'{t}. An AutoML and meta-learning study.', au,
                         now - dt.timedelta(days=5 + i * 9), ['cs.LG'], 'ICLR 2026' if i == 0 else '')
                  for i, (t, au) in enumerate(LAB)])


def arxiv_one(aid):
    now = dt.datetime(2026, 10, 2, tzinfo=dt.timezone.utc)
    known = {
        '2407.09585': ('A Scale-Invariant Diagnostic Approach Towards Understanding Dynamics of Deep Neural Networks',
                       'Scale-invariant diagnostics of training dynamics in deep neural networks.'),
        '2610.03000': ('Temporal Geometry of Deep Networks: Hyperbolic Representations of Training Dynamics for Intrinsic Explainability',
                       'Temporal parameter graphs from training snapshots embedded in the Poincare ball give intrinsic explainability of training dynamics.'),
    }
    if aid not in known:
        return _feed([])
    t, a = known[aid]
    return _feed([_entry(aid, t, a, ['Ambarish Moharil'], now, ['cs.LG'])])


BROAD = [
    ('Diffusion transformers for video generation at scale', 'We scale diffusion transformers for video generation.', ['cs.CV', 'cs.LG']),
    ('Offline reinforcement learning with conservative critics', 'Conservative critics for offline reinforcement learning.', ['cs.LG']),
    ('Graph neural networks for molecular property prediction', 'Message passing networks predict molecular properties.', ['cs.LG', 'q-bio.QM']),
    ('Neural architecture search for tabular AutoML under budgets', 'Budget-aware AutoML search over pipelines for tabular data on OpenML.', ['cs.LG', 'stat.ML']),
    ('Loss landscape geometry and training dynamics of transformers', 'We study training dynamics and the loss landscape of transformers.', ['cs.LG']),
]


def arxiv_rss(cat='cs.LG', now=None):
    """arXiv's 2024 RSS format: announce type in description and arxiv:announce_type, dc:creator list."""
    now = now or dt.datetime.now(dt.timezone.utc)
    day = now.strftime('%a, %d %b %Y 00:00:00 -0500')
    items = []
    base = sum(map(ord, cat)) % 900
    for i, (t, a, cats) in enumerate(BROAD):
        aid = f'2611.{30000 + base * 10 + i}'
        typ = 'cross' if i == 2 else 'new'
        items.append(f'''<item><title>{escape(t)}</title><link>https://arxiv.org/abs/{aid}</link>
<description>arXiv:{aid}v1 Announce Type: {typ} 
Abstract: {escape(a)}</description><guid isPermaLink="false">oai:arXiv.org:{aid}v1</guid>
{''.join(f'<category>{c}</category>' for c in cats)}<pubDate>{day}</pubDate>
<arxiv:announce_type>{typ}</arxiv:announce_type><dc:rights>http://creativecommons.org/licenses/by/4.0/</dc:rights>
<dc:creator>Ada Lovelace, Alan Turing, Grace Hopper</dc:creator></item>''')
    items.append(f'''<item><title>A replaced older paper</title><link>https://arxiv.org/abs/2401.00001</link>
<description>arXiv:2401.00001v3 Announce Type: replace 
Abstract: Old.</description><guid isPermaLink="false">oai:arXiv.org:2401.00001v3</guid><category>{cat}</category>
<pubDate>{day}</pubDate><arxiv:announce_type>replace</arxiv:announce_type><dc:creator>Old Author</dc:creator></item>''')
    return (f'''<?xml version='1.0' encoding='UTF-8'?>
<rss xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/" version="2.0">
<channel><title>{cat} updates on arXiv.org</title><link>http://rss.arxiv.org/rss/{cat}</link>
<description>{cat} updates on the arXiv.org e-print archive.</description>{''.join(items)}</channel></rss>''').encode()


def arxiv_keyword(phrases, now=None):
    """Keyword query: entries whose title or abstract contains one of the phrases."""
    now = now or dt.datetime.now(dt.timezone.utc)
    out, n = [], 0
    for k in range(2):
        for i, (t, a) in enumerate(LANE_PAPERS):
            n += 1
            text = (t + ' ' + a).lower()
            if any(p in text for p in phrases):
                title = t if k == 0 else f'{t} (variant {k + 1})'
                out.append(_entry(f'2611.{10000 + n}', title, a, [f'Author {n} One', f'Author {n} Two'],
                                  now - dt.timedelta(hours=3 + n * 2), [CATS[i % len(CATS)], 'cs.LG']))
    return _feed(out)


def openalex_work(wid, title, abstract='', authors=('A. Author',), date='2024-06-01', venue='Machine Learning', doi=''):
    words = abstract.split()
    inv = {}
    for i, w in enumerate(words):
        inv.setdefault(w, []).append(i)
    return {'id': f'https://openalex.org/{wid}', 'display_name': title, 'publication_date': date,
            'doi': f'https://doi.org/{doi}' if doi else None, 'ids': {},
            'primary_location': {'landing_page_url': f'https://example.org/{wid}', 'pdf_url': None,
                                 'source': {'display_name': venue}},
            'authorships': [{'author': {'display_name': n}} for n in authors],
            'abstract_inverted_index': inv or None}


def fake_fetch(url, max_bytes=None):
    u = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(u.query)
    if u.netloc == 'export.arxiv.org':
        if 'id_list' in q:
            return arxiv_one(q['id_list'][0])
        sq = q.get('search_query', [''])[0]
        if sq.startswith('au:'):
            return arxiv_lab()
        if 'submittedDate' in sq:
            return arxiv_keyword([x.lower() for x in re.findall(r'"([^"]+)"', sq)])
        return arxiv_bulk() if q.get('start', ['0'])[0] == '0' else _feed([])
    if u.netloc == 'rss.arxiv.org':
        return arxiv_rss(u.path.rsplit('/', 1)[-1])
    if u.netloc == 'api.openalex.org':
        if u.path == '/authors':
            return json.dumps({'results': [{'id': 'https://openalex.org/A500', 'display_name': 'Joaquin Vanschoren', 'works_count': 300},
                                           {'id': 'https://openalex.org/A501', 'display_name': 'J. Someone', 'works_count': 900}]}).encode()
        if u.path == '/works' and 'filter' in q and 'author.id' in q['filter'][0]:
            return json.dumps({'results': [openalex_work('W9001', 'OpenML: insights from ten years and a thousand papers',
                                                         'OpenML benchmark meta analysis', ['Joaquin Vanschoren'], '2025-09-01', 'Discovery Science')]}).encode()
        if u.path == '/works' and 'from_publication_date' in q.get('filter', [''])[0]:
            today = dt.date.today().isoformat()
            return json.dumps({'results': [
                openalex_work('W500', 'Pipeline synthesis for AutoML in clinical prediction', 'AutoML pipeline synthesis applied to clinical tabular data on OpenML benchmarks',
                              ['C. Researcher'], today, 'Machine Learning', '10.1007/fixture-1'),
                dict(openalex_work('W501', 'Hyperbolic training dynamics revisited', 'Training dynamics of deep networks in hyperbolic space',
                                   ['D. Researcher'], today, 'Transactions on Machine Learning Research'), ids={'arxiv': 'https://arxiv.org/abs/2611.10004'}),
            ]}).encode()
        if u.path == '/works':
            s = q.get('search', [''])[0].lower()
            if s.startswith('towards efficient automl'):
                return json.dumps({'results': [openalex_work('W1', 'Towards efficient AutoML: a pipeline synthesis approach leveraging pre-trained transformers for multimodal data',
                                                             'AutoML pipeline synthesis with pre-trained transformers for multimodal data on OpenML tasks')]}).encode()
            if s.startswith('tabasco'):
                return json.dumps({'results': [openalex_work('W2', 'TABASCO: A transformer based contextualization toolkit',
                                                             'A transformer based contextualization toolkit for contextual embeddings', date='2023-05-01', venue='Science of Computer Programming')]}).encode()
            if s.startswith('between jira'):
                return json.dumps({'results': [openalex_work('W3', 'Between JIRA and GitHub: ASFBot and its Influence on Human Comments in Issue Trackers',
                                                             'Bots in issue trackers and human comments on GitHub and JIRA', date='2022-05-01', venue='MSR')]}).encode()
            return json.dumps({'results': [openalex_work('W77', 'An older survey of AutoML and meta-learning',
                                                         'Survey of automated machine learning hyperparameter optimization and meta-learning', date='2019-01-01'),
                                           openalex_work('W78', 'Unrelated work on crop yields', 'Crop yield prediction from weather', date='2020-01-01')]}).encode()
    if u.netloc == 'api.crossref.org':
        return json.dumps({'status': 'ok', 'message': {
            'title': ['Fixture preprint on hyperbolic training dynamics'],
            'abstract': '<jats:title>Abstract</jats:title><jats:p>Hyperbolic representations of training dynamics in deep networks.</jats:p>',
            'author': [{'given': 'Ambarish', 'family': 'Moharil'}], 'posted': {'date-parts': [[2026, 3, 1]]},
            'URL': 'https://doi.org/10.21203/rs.3.rs-11721788/v1', 'DOI': '10.21203/rs.3.rs-11721788/v1',
            'institution': [{'name': 'Research Square'}]}}).encode()
    if u.netloc == 'huggingface.co':
        if u.path == '/api/models':
            return json.dumps([{'id': 'org/model-a', 'likes': 1200, 'downloads': 50000, 'pipeline_tag': 'text-generation', 'library_name': 'transformers'},
                               {'id': 'org/model-b', 'likes': 300, 'downloads': 9000, 'pipeline_tag': 'tabular-classification'}]).encode()
        if u.path == '/api/daily_papers':
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            return json.dumps([{'paper': {'id': '2611.10001', 'title': 'AutoML pipeline synthesis with pre-trained transformers for tabular and multimodal data',
                                          'summary': LANE_PAPERS[0][1], 'authors': [{'name': 'Author 1 One'}], 'publishedAt': now, 'upvotes': 42}},
                                {'paper': {'id': '2611.40001', 'title': 'Agents that write their own evaluation suites', 'summary': 'LLM agents generate evaluation suites.',
                                           'authors': [{'name': 'E. Example'}], 'publishedAt': now, 'upvotes': 120}}]).encode()
        if u.path == '/api/papers/search':
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            return json.dumps([{'paper': {'id': '2611.40002', 'title': 'Meta-learned optimisers and training dynamics',
                                          'summary': 'We meta-learn optimisers and analyse training dynamics of deep networks.',
                                          'authors': [{'name': 'F. Example'}], 'publishedAt': now, 'upvotes': 7}},
                               {'paper': {'id': '1706.03762', 'title': 'Attention is all you need', 'summary': 'Transformers.',
                                          'authors': [{'name': 'A. Vaswani'}], 'publishedAt': '2017-06-12T00:00:00.000Z', 'upvotes': 99}}]).encode()
    if u.netloc == 'www.openml.org':
        m = re.search(r'/(data|task)/list/limit/(\d+)/offset/(\d+)', u.path)
        kind, limit, off = m.group(1), int(m.group(2)), int(m.group(3))
        total = 4567 if kind == 'data' else 3000
        ids = list(range(off, min(total, off + limit)))
        if not ids:
            raise OSError('412 No results')
        if kind == 'data':
            return json.dumps({'data': {'dataset': [{'did': i + 1, 'name': f'dataset_{i + 1}', 'version': 1, 'status': 'active',
                                                     'quality': [{'name': 'NumberOfInstances', 'value': '1000.0'},
                                                                 {'name': 'NumberOfFeatures', 'value': '12.0'}]} for i in ids]}}).encode()
        return json.dumps({'tasks': {'task': [{'task_id': i + 1, 'task_type': 'Supervised Classification', 'did': i + 1,
                                               'name': f'dataset_{i + 1}', 'quality': []} for i in ids]}}).encode()
    if u.netloc == 'raw.githubusercontent.com':
        name = u.path.rsplit('/', 1)[-1]
        name = {'nips.yml': 'nips.yml'}.get(name, name)
        return (HERE / name).read_bytes()
    raise OSError(f'fixture has no route for {url}')
