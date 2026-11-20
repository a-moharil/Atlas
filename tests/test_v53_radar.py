"""v5.3/v5.4 research radar: parsing, fingerprint, watch phrases, sources, ranking, search, deadlines, queue, BibTeX, endpoints.
Runs offline: network calls go to tests/radar_fixtures.py, which mirrors the real API shapes."""
import datetime as dt
import json
import re
import urllib.parse
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import radar_fixtures as F  # noqa: E402
from tmpdir import TempDir  # noqa: E402
import research_radar as R  # noqa: E402
import semantic  # noqa: E402
import server  # noqa: E402


def _no_wait(fetch, url, max_bytes=None):
    return fetch(url, max_bytes or R.BIG)


class Base(unittest.TestCase):
    def setUp(self):
        self.t = patch.object(R, 'arxiv_get', _no_wait)  # skip arXiv's 3 s pacing in tests
        self.t.start()
        self.td = TempDir()
        self.p = patch.object(server, 'DB_FILE', Path(self.td.name) / 'observatory.sqlite3')
        self.p.start()
        server.init_db()
        R._mem['themes'].clear()
        self.mc = Path(self.td.name) / 'model_cache'
        # Keyword mode: these tests must not depend on the optional model pack.
        self.m = patch.object(semantic, 'available', lambda: False)
        self.m.start()

    def tearDown(self):
        self.t.stop()
        self.m.stop()
        self.p.stop()
        self.td.cleanup()


class Parsing(unittest.TestCase):
    def test_arxiv_atom(self):
        ps = R.parse_arxiv(F.arxiv_bulk(copies=1))
        self.assertEqual(len(ps), len(F.LANE_PAPERS))
        p = ps[0]
        self.assertTrue(p['id'].startswith('arxiv:2611.'))
        self.assertTrue(p['url'].startswith('https://arxiv.org/abs/'))
        self.assertTrue(p['pdf'].startswith('http://arxiv.org/pdf/'))
        self.assertEqual(len(p['categories']), len(set(p['categories'])))  # primary category not repeated
        self.assertNotIn('\n', p['abstract'])

    def test_rejects_entity_xml(self):
        with self.assertRaises(ValueError):
            R.parse_arxiv(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><feed/>')

    def test_openalex_abstract_rebuilt_in_order(self):
        self.assertEqual(R.openalex_abstract({'world': [1], 'hello': [0], 'again': [2]}), 'hello world again')

    def test_classify_refs(self):
        self.assertEqual(R.classify_ref('https://arxiv.org/abs/2610.03000'), ('arxiv', '2610.03000'))
        self.assertEqual(R.classify_ref('arXiv:2407.09585v2'), ('arxiv', '2407.09585'))
        self.assertEqual(R.classify_ref('https://doi.org/10.21203/rs.3.rs-11721788/v1'), ('doi', '10.21203/rs.3.rs-11721788/v1'))
        self.assertEqual(R.classify_ref('TABASCO: A transformer based contextualization toolkit')[0], 'title')

    def test_key_terms_prefer_phrases_without_repeats(self):
        t = R.key_terms('We analyse the training dynamics of deep neural networks by embedding weight snapshots in hyperbolic space.', 5)
        self.assertIn('training dynamics', t)
        words = [w for x in t for w in x.split()]
        self.assertEqual(len(words), len(set(words)))


class Deadlines(unittest.TestCase):
    NOW = dt.datetime(2026, 11, 18, tzinfo=dt.timezone.utc)

    def test_real_ccfddl_files_parse(self):
        for f in ('nips', 'icml', 'iclr', 'icse', 'msr', 'sigkdd'):
            doc = R.mini_yaml((HERE / 'fixtures' / 'radar' / f'{f}.yml').read_text())
            self.assertIsInstance(doc, list)
            self.assertTrue(doc[0]['confs'], f)
            self.assertIn('timeline', doc[0]['confs'][-1])

    def test_aoe_conversion_and_past_dates_dropped(self):
        doc = R.mini_yaml((HERE / 'fixtures' / 'radar' / 'iclr.yml').read_text())
        c = R.conference_dates(doc, 'ICLR', now=self.NOW)
        kinds = [m['kind'] for m in c['milestones']]
        self.assertNotIn('deadline', kinds)  # the 2026-09-25 paper deadline has passed
        dec = next(m for m in c['milestones'] if m['kind'] == 'decision deadline')
        self.assertEqual(dec['at'][:16], '2026-12-17T11:59')  # 2026-12-16 23:59 AoE = UTC-12

    def test_unannounced_conference_has_no_milestones(self):
        doc = R.mini_yaml((HERE / 'fixtures' / 'radar' / 'nips.yml').read_text())
        c = R.conference_dates(doc, 'NeurIPS', now=self.NOW)
        self.assertEqual(c['milestones'], [])
        self.assertEqual(c['latest']['year'], 2026)

    def test_deadlines_job_includes_automl_note(self):
        d = R.deadlines(F.fake_fetch)
        names = [c['name'] for c in d['conferences']]
        self.assertIn('AutoML Conference', names)
        self.assertTrue(next(c for c in d['conferences'] if c['name'] == 'AutoML Conference')['note'])


class Pipeline(Base):
    def collect(self):
        R.resolve_fingerprint(server.db_connect, F.fake_fetch, self.mc)
        R.intake_keywords(F.fake_fetch, server.db_connect, self.mc)
        R.intake_rss(F.fake_fetch, server.db_connect, self.mc)

    def test_fingerprint_seeds_resolve(self):
        out = R.resolve_fingerprint(server.db_connect, F.fake_fetch, self.mc)
        self.assertEqual(out['resolved'], 6)
        with closing(server.db_connect()) as con:
            titles = [f['title'] for f in R.fingerprint(con)]
        self.assertIn('TABASCO: A transformer based contextualization toolkit', titles)
        self.assertTrue(any(t.startswith('Temporal Geometry of Deep Networks') for t in titles))

    def test_unknown_title_is_not_found_not_guessed(self):
        with closing(server.db_connect()) as con:
            R.fp_add(con, 'A paper title that does not exist in any index')
            con.commit()
        R.resolve_fingerprint(server.db_connect, F.fake_fetch, self.mc)
        with closing(server.db_connect()) as con:
            row = [f for f in R.fingerprint(con) if f['ref'].startswith('A paper title')][0]
        self.assertEqual(row['status'], 'not_found')

    def test_ranking_lanes_and_keyword_mode(self):
        R.resolve_fingerprint(server.db_connect, F.fake_fetch, self.mc)
        self.collect()
        ov = R.overview(server.db_connect, self.mc, days=7)
        self.assertEqual(ov['mode'], 'keywords')
        lanes = {l['key']: l for l in ov['lanes']}
        top = lambda k: lanes[k]['papers'][0]['title'].lower()
        self.assertIn('automl', top('automl'))
        self.assertIn('bots', top('se4ml'))
        self.assertTrue(all(0 <= p['match'] <= 1 for l in ov['lanes'] for p in l['papers']))
        ms = [p['match'] for p in lanes['automl']['papers']]
        self.assertEqual(ms, sorted(ms, reverse=True))

    def test_lab_trace_marks_lab_and_dedupes(self):
        out = R.trace_lab(F.fake_fetch, server.db_connect, self.mc)
        self.assertEqual(out['found'], 4)
        R.trace_lab(F.fake_fetch, server.db_connect, self.mc)
        with closing(server.db_connect()) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM radar_papers WHERE lab=1').fetchone()[0], 4)

    def test_openml_finds_newest_by_probing(self):
        o = R.openml(F.fake_fetch, n=5)
        self.assertEqual([d['id'] for d in o['datasets']], [4567, 4566, 4565, 4564, 4563])
        self.assertEqual(o['tasks'][0]['id'], 3000)

    def test_themes_and_related_work(self):
        R.resolve_fingerprint(server.db_connect, F.fake_fetch, self.mc)
        self.collect()
        th = R.themes(server.db_connect, self.mc, days=7)
        self.assertTrue(th['themes'])
        self.assertTrue(all(t['size'] >= 3 for t in th['themes']))
        rw = R.related_work('Bots in issue trackers change how developers comment on GitHub and JIRA; we mine software repositories.',
                            server.db_connect, F.fake_fetch, self.mc)
        self.assertIn('bots', rw['recent'][0]['title'].lower())
        with self.assertRaises(ValueError):
            R.related_work('too short', server.db_connect, F.fake_fetch, self.mc)

    def test_queue_and_bibtex(self):
        self.collect()
        ov = R.overview(server.db_connect, self.mc, days=7)
        p = ov['lanes'][0]['papers'][0]
        with closing(server.db_connect()) as con:
            R.queue_action(con, {'action': 'add', 'paper': p})
            R.queue_action(con, {'action': 'add', 'paper': p})  # idempotent
            q = R.queue_action(con, {'action': 'update', 'id': p['id'], 'status': 'read', 'note': 'Sec 3'})
            self.assertEqual([(x['status'], x['note']) for x in q], [('read', 'Sec 3')])
            with self.assertRaises(ValueError):
                R.queue_action(con, {'action': 'update', 'id': p['id'], 'status': 'shelved'})
            bib = R.bibtex(con)
        self.assertTrue(bib.startswith('@misc{'))
        self.assertIn('archivePrefix = {arXiv}', bib)
        self.assertIn('eprint = {' + p['id'][6:] + '}', bib)

    def test_bibtex_escapes_and_unique_keys(self):
        used = set()
        a = R.bibtex_entry({'id': 'oa:W1', 'title': 'Costs & {braces} 50% of $x$', 'authors': ['Ada Lovelace'],
                            'published': '2025-01-01', 'venue': 'J. Test', 'doi': '10.1/x'}, used)
        b = R.bibtex_entry({'id': 'oa:W2', 'title': 'Costs again', 'authors': ['Ada Lovelace'], 'published': '2025-02-01'}, used)
        self.assertIn('\\&', a)
        self.assertIn('\\{braces\\}', a)
        self.assertIn('@article{lovelace2025costs,', a)
        self.assertIn('@article{lovelace2025costsb,', b)

    def test_prune_keeps_queued_and_lab_papers(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)).isoformat()
        with closing(server.db_connect()) as con:
            R.init(con)
            R.store_papers(con, [{'id': 'arxiv:old.1', 'title': 'Old', 'published': old},
                                 {'id': 'arxiv:old.2', 'title': 'Old queued', 'published': old}])
            R.store_papers(con, [{'id': 'arxiv:old.3', 'title': 'Old lab', 'published': old}], lab=True)
            R.queue_action(con, {'action': 'add', 'paper': {'id': 'arxiv:old.2', 'title': 'Old queued'}})
            R.prune(con, 30)
            left = {r[0] for r in con.execute('SELECT id FROM radar_papers')}
        self.assertEqual(left, {'arxiv:old.2', 'arxiv:old.3'})


class Endpoints(Base):
    def test_http_endpoints(self):
        srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{srv.server_address[1]}'
        get = lambda u: urllib.request.urlopen(base + u, timeout=20)
        post = lambda u, b: json.load(urllib.request.urlopen(urllib.request.Request(base + u, json.dumps(b).encode(), {'Content-Type': 'application/json'}), timeout=20))
        try:
            with patch.object(server, 'research_fetch', F.fake_fetch):
                d = json.load(get('/api/radar?days=7'))
                for k in ('lanes', 'lab', 'fingerprint', 'sources', 'openml', 'deadlines', 'digest', 'mode'):
                    self.assertIn(k, d)
                fp = post('/api/radar/fingerprint', {'action': 'add', 'ref': 'https://arxiv.org/abs/2610.03000'})['fingerprint']
                self.assertEqual(len(fp), 6)  # already a seed: no duplicate
                q = post('/api/radar/queue', {'action': 'add', 'paper': {'id': 'arxiv:1', 'title': 'T', 'authors': ['A B']}})['queue']
                self.assertEqual(len(q), 1)
                r = get('/api/radar/bibtex')
                self.assertIn('attachment', r.headers['Content-Disposition'])
                self.assertIn('@misc{', r.read().decode())
                with self.assertRaises(urllib.error.HTTPError) as e:
                    post('/api/radar/related', {'text': 'short'})
                self.assertEqual(e.exception.code, 400)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == '__main__':
    unittest.main()


class Sources(Base):
    def test_rss_skips_replacements_and_splits_authors(self):
        ps = R.parse_arxiv_rss(F.arxiv_rss('cs.LG'))
        self.assertEqual(len(ps), len(F.BROAD))
        self.assertTrue(all(p['id'].startswith('arxiv:2611.') for p in ps))
        self.assertEqual(ps[0]['authors'], ['Ada Lovelace', 'Alan Turing', 'Grace Hopper'])
        self.assertTrue(ps[0]['published'].startswith(dt.date.today().isoformat()[:4]))
        self.assertNotIn('Announce Type', ps[0]['abstract'])

    def test_watch_phrases_extracted_editable_and_focused(self):
        R.resolve_fingerprint(server.db_connect, F.fake_fetch, self.mc)
        with closing(server.db_connect()) as con:
            w = R.watch(con)
            self.assertIn('pipeline synthesis', w['active'])
            self.assertIn('training dynamics', w['active'])
            for broad in ('deep', 'training', 'transformer', 'neural networks'):
                self.assertNotIn(broad, w['active'])
            w = R.watch_action(con, {'action': 'remove', 'phrase': 'pipeline synthesis'})
            self.assertNotIn('pipeline synthesis', w['active'])
            w = R.watch_action(con, {'action': 'add', 'phrase': 'Loss  Landscape'})
            self.assertIn('loss landscape', w['active'])
            with self.assertRaises(ValueError):
                R.watch_action(con, {'action': 'add', 'phrase': 'x'})
            w = R.watch_action(con, {'action': 'reset'})
            self.assertIn('pipeline synthesis', w['active'])
            self.assertNotIn('loss landscape', w['active'])

    def test_keyword_queries_are_small_dated_and_incremental(self):
        seen = []
        def spy(url, max_bytes=None):
            seen.append(urllib.parse.unquote_plus(url))
            return F.fake_fetch(url, max_bytes)
        R.resolve_fingerprint(server.db_connect, F.fake_fetch, self.mc)
        out = R.intake_keywords(spy, server.db_connect, self.mc)
        qs = [u for u in seen if 'submittedDate' in u]
        self.assertEqual(len(qs), out['queries'])
        self.assertTrue(all('max_results=100' in u and 'sortBy=submittedDate' in u for u in qs))
        self.assertTrue(any('abs:"pipeline synthesis"' in u for u in qs))
        self.assertGreater(out['added'], 0)
        first = re.search(r'submittedDate:\[(\d{12})', qs[0]).group(1)
        seen.clear()
        R.intake_keywords(spy, server.db_connect, self.mc)
        again = re.search(r'submittedDate:\[(\d{12})', [u for u in seen if 'submittedDate' in u][0]).group(1)
        self.assertGreater(again, first)  # second run only looks back from the last run

    def test_keywords_wait_for_fingerprint(self):
        out = R.intake_keywords(F.fake_fetch, server.db_connect, self.mc)
        self.assertEqual(out['data_status'], 'partial')

    def test_huggingface_and_openalex_add_papers(self):
        R.resolve_fingerprint(server.db_connect, F.fake_fetch, self.mc)
        hf = R.huggingface(F.fake_fetch, server.db_connect, self.mc)
        self.assertEqual(hf['daily_count'], 2)
        oa = R.intake_openalex(F.fake_fetch, server.db_connect, self.mc)
        self.assertFalse(oa['keyed'])
        with closing(server.db_connect()) as con:
            ids = {r[0]: r[1] for r in con.execute('SELECT id, source FROM radar_papers')}
        self.assertEqual(ids.get('arxiv:2611.40002'), 'hf')       # recent search hit kept
        self.assertNotIn('arxiv:1706.03762', ids)                  # old search hit dropped
        self.assertEqual(ids.get('oa:W500'), 'openalex')
        self.assertIn('arxiv:2611.10004', ids)                     # OpenAlex work with an arXiv id joins the arXiv record

    def test_openalex_key_is_sent_when_saved(self):
        urls = []
        with closing(server.db_connect()) as con:
            R.init(con)
            R.set_meta(con, 'openalex_key', 'abc12345key')
            con.commit()
        R.resolve_fingerprint(server.db_connect, lambda u, m=None: (urls.append(u), F.fake_fetch(u, m))[1], self.mc)
        oa = [u for u in urls if 'api.openalex.org' in u]
        self.assertTrue(oa and all('api_key=abc12345key' in u for u in oa))

    def test_probe_reports_every_source(self):
        checks = R.probe(F.fake_fetch, server.db_connect)
        self.assertEqual(len(checks), 8)
        self.assertTrue(all(c['ok'] for c in checks), checks)
        def broken(url, max_bytes=None):
            if 'openalex' in url:
                raise OSError('HTTP Error 429: Too Many Requests')
            return F.fake_fetch(url, max_bytes)
        bad = [c for c in R.probe(broken, server.db_connect) if not c['ok']]
        self.assertEqual([c['source'] for c in bad], ['OpenAlex'])
        self.assertIn('free OpenAlex key', bad[0]['detail'])


class Search(Base):
    def setUp(self):
        super().setUp()
        R.resolve_fingerprint(server.db_connect, F.fake_fetch, self.mc)
        R.intake_keywords(F.fake_fetch, server.db_connect, self.mc)
        R.intake_rss(F.fake_fetch, server.db_connect, self.mc)
        R.huggingface(F.fake_fetch, server.db_connect, self.mc)

    def test_auto_mode_choice(self):
        self.assertEqual(R.auto_mode('"training dynamics"')[0], 'keyword')
        self.assertEqual(R.auto_mode('author:vanschoren')[0], 'keyword')
        self.assertEqual(R.auto_mode('automl -tabular')[0], 'keyword')
        self.assertEqual(R.auto_mode('hyperbolic geometry')[0], 'keyword')
        self.assertEqual(R.auto_mode('papers on how networks organise their weights while being trained')[0], 'semantic')

    def test_keyword_syntax(self):
        r = R.search(server.db_connect, self.mc, '"training dynamics"', 'auto')
        self.assertEqual(r['mode'], 'keyword')
        self.assertTrue(r['results'])
        self.assertTrue(all('training dynamics' in (p['title'] + ' ' + p['abstract']).lower() for p in r['results']))
        r = R.search(server.db_connect, self.mc, 'author:lovelace', 'auto')
        self.assertTrue(r['results'] and all('Ada Lovelace' in p['authors'] for p in r['results']))
        r = R.search(server.db_connect, self.mc, 'automl -tabular', 'keyword')
        self.assertTrue(all('tabular' not in (p['title'] + p['abstract']).lower() for p in r['results']))
        r = R.search(server.db_connect, self.mc, 'cat:cs.SE', 'keyword')
        self.assertTrue(r['results'] and all(any(c.startswith('cs.SE') for c in p['categories']) for p in r['results']))

    def test_semantic_falls_back_to_keywords_without_model(self):
        r = R.search(server.db_connect, self.mc, 'papers on how networks organise their weights while being trained', 'semantic')
        self.assertEqual(r['mode'], 'keyword')
        self.assertIn('language model pack', r['note'])

    def test_filters(self):
        all_ = R.search(server.db_connect, self.mc, '', 'auto', {})
        self.assertEqual(all_['mode'], 'filters')
        hf = R.search(server.db_connect, self.mc, '', 'auto', {'hf': True})
        self.assertTrue(hf['results'] and all(p['id'] in ('arxiv:2611.10001', 'arxiv:2611.40001') for p in hf['results']))
        src = R.search(server.db_connect, self.mc, '', 'auto', {'source': 'hf'})
        self.assertTrue(all(p['source'] == 'hf' for p in src['results']))
        lane = R.search(server.db_connect, self.mc, '', 'auto', {'lane': 'se4ml'})
        self.assertTrue(lane['results'] and all(p['lane'] == 'se4ml' for p in lane['results']))
        hi = R.search(server.db_connect, self.mc, '', 'auto', {'min': 0.3})
        self.assertTrue(all(p['match'] >= 0.3 for p in hi['results']))
        self.assertLess(hi['total'], all_['total'])
