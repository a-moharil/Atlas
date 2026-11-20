"""v5.5 coverage graph: co-coverage and topic edges, story zoom, diffusion, gaps, search queries, endpoints."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coverage_graph as G  # noqa: E402
import semantic  # noqa: E402
import server  # noqa: E402
from tests.tmpdir import TempDir


def art(i, host, story, title, when='2099-01-01T00:00:00Z'):
    return {'id': f'a{i}', 'medium': 'article', 'publisher': host, 'story': {'id': story}, 'title': title,
            'summary': title, 'published': when, 'url': f'https://{host}/{i}'}


ENTRIES = [
    art(1, 'a.com', 's1', 'RBI holds repo rate steady as inflation cools'),
    art(2, 'b.com', 's1', 'Reserve Bank keeps repo rate unchanged amid inflation'),
    art(3, 'c.com', 's1', 'RBI repo rate pause as inflation eases'),
    art(4, 'a.com', 's2', 'Rupee hits record low against dollar on inflation worries'),
    art(5, 'd.com', 's2', 'Rupee slides to record low as dollar strengthens'),
    art(6, 'b.com', 's3', 'Monsoon rains flood Kerala districts'),
    art(7, 'd.com', 's4', 'Rupee weakness and inflation pressure the RBI'),
    art(8, 'd.com', 's5', 'Inflation data and RBI policy outlook for markets'),
    art(9, 'd.com', 's6', 'Bond yields rise as RBI signals inflation caution'),
    art(10, 'e.com', 's7', 'Cricket: India beat Australia in Perth'),
]
profile = lambda h: {'name': h.upper(), 'lean': 0, 'kind': 'news', 'logo': ''}


class Graph(unittest.TestCase):
    def setUp(self):
        self.p = patch.object(semantic, 'ready', lambda: False)  # keyword mode, no model needed
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_overview_nodes_edges_and_stories(self):
        g = G.overview(ENTRIES, [e['id'] for e in ENTRIES], None, profile, lambda h: 'primary' if h == 'a.com' else '')
        self.assertEqual(g['mode'], 'keywords')
        nodes = {n['id']: n for n in g['nodes']}
        self.assertEqual(nodes['d.com']['articles'], 4)
        self.assertTrue(nodes['a.com']['primary'])
        edge = {(e['a'], e['b']): e for e in g['edges']}
        self.assertEqual(edge[('a.com', 'b.com')]['shared'], 1)       # both covered s1
        self.assertEqual(edge[('a.com', 'c.com')]['shared'], 1)
        self.assertIn(('a.com', 'd.com'), edge)                           # shared s2
        self.assertTrue(all(0 <= e['topic'] <= 1 and 0 <= e['co'] <= 1 for e in g['edges']))
        self.assertEqual(set(g['stories']['s1']['articles']), {'a1', 'a2', 'a3'})
        self.assertEqual(g['stories']['s1']['sources'], ['a.com', 'b.com', 'c.com'])

    def test_overview_only_uses_page_ids(self):
        g = G.overview(ENTRIES, ['a1', 'a2'], None, profile)
        self.assertEqual({n['id'] for n in g['nodes']}, {'a.com', 'b.com'})

    def test_diffusion_rings_and_gaps(self):
        d = G.diffuse(ENTRIES, 'a1', None, profile, days=36500)
        self.assertEqual(d['seed_story']['id'], 's1')
        self.assertEqual(d['seed_story']['sources'], ['a.com', 'b.com', 'c.com'])
        rel = [s['id'] for s in d['related']]
        self.assertIn('s2', rel + [s['id'] for s in d['via_sources']])
        self.assertNotIn('s7', rel)                                       # cricket is not related to the RBI
        self.assertTrue(all(s['similarity'] >= 0.08 for s in d['related']))
        self.assertEqual([g['id'] for g in d['gaps']], ['d.com'])         # writes about RBI and inflation, missed this one
        self.assertTrue(d['terms'])
        self.assertTrue(any(s['covered'] for s in d['sources']))

    def test_unknown_seed(self):
        with self.assertRaises(LookupError):
            G.diffuse(ENTRIES, 'nope', None, profile)

    def test_search_queries(self):
        qs = G.search_queries(['repo rate', 'rbi', 'inflation'], ['d.com', 'feed:x', 'e.com', 'f.com', 'g.com'])
        self.assertEqual(qs[0], '"repo rate" rbi inflation when:3d')
        self.assertEqual([q.split()[0] for q in qs[1:]], ['site:d.com', 'site:e.com', 'site:f.com'])


class Endpoints(unittest.TestCase):
    def test_http(self):
        with TempDir() as td, patch.object(server, 'DB_FILE', Path(td) / 'o.sqlite3'), \
                patch.object(semantic, 'ready', lambda: False), patch.object(server, 'graph_entries', lambda: ENTRIES):
            server.init_db()
            srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{srv.server_address[1]}'
            post = lambda u, b: json.load(urllib.request.urlopen(urllib.request.Request(base + u, json.dumps(b).encode(), {'Content-Type': 'application/json'}), timeout=20))
            try:
                g = post('/api/graph', {'ids': [e['id'] for e in ENTRIES]})
                self.assertEqual(len(g['nodes']), 5)
                d = post('/api/graph/diffuse', {'seed': 'a4', 'days': 14})
                self.assertEqual(d['seed_story']['id'], 's2')
                with self.assertRaises(urllib.error.HTTPError) as e:
                    post('/api/graph/diffuse', {'seed': 'missing'})
                self.assertEqual(e.exception.code, 404)
                with patch.object(server, 'fetch_bytes', side_effect=OSError('offline')):
                    r = post('/api/graph/search-further', {'terms': ['repo rate', 'rbi'], 'gaps': ['d.com', 'bad host!'], 'desk': 'Finance'})
                self.assertEqual((r['added'], r['fetched'], r['queries']), (0, 0, 2))
                self.assertEqual(len(r['notes']), 2)
                with self.assertRaises(urllib.error.HTTPError):
                    post('/api/graph/search-further', {'terms': [], 'gaps': []})
            finally:
                srv.shutdown()


if __name__ == '__main__':
    unittest.main()
