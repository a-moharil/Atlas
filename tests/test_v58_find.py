"""v5.8 panel search: query parsing, keyword and meaning ranking, endpoints, fetching from the web."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import find as F  # noqa: E402
import semantic  # noqa: E402
import server  # noqa: E402

DOCS = [('a', 'Iran agrees to IAEA nuclear inspections', 'Talks in Vienna ended late on Monday.', 'Reuters'),
        ('b', 'Nuclear power plant opens in France', 'A new reactor joins the grid.', 'France 24'),
        ('c', 'North Korea fires missiles into the sea', 'Seoul and Tokyo condemned the launch.', 'NHK'),
        ('d', 'Iran and North Korea talks: what we know', 'Diplomats met in Beijing.', 'BBC'),
        ('e', 'Monsoon arrives early in Kerala', 'Heavy rain in the south.', 'The Hindu'),
        ('f', 'Sanctions on Iran tightened', 'The EU agreed new measures against Tehran.', 'DW')]


class Parse(unittest.TestCase):
    def test_groups_phrases_and_stopwords(self):
        self.assertEqual(F.parse('"South China Sea" the drills, Taiwan'), [['south china sea', 'drills'], ['taiwan']])
        self.assertEqual(F.parse('iran OR israel; gaza'), [['iran'], ['israel'], ['gaza']])
        self.assertEqual(F.parse('   , the of '), [])

    def test_need(self):
        self.assertEqual([F.need(n) for n in range(1, 6)], [1, 2, 2, 3, 3])


class Keywords(unittest.TestCase):
    def test_all_words_needed_for_two(self):
        r = F.keyword_scores(F.parse('iran nuclear'), DOCS)
        self.assertEqual(set(r), {'a'})

    def test_stemming_and_phrase(self):
        self.assertIn('f', F.keyword_scores(F.parse('sanction'), DOCS))
        r = F.keyword_scores(F.parse('"north korea"'), DOCS)
        self.assertEqual(set(r), {'c', 'd'})

    def test_commas_rank_both_topics_first(self):
        r = F.rank(F.parse('iran, north korea'), DOCS, 'keywords')
        self.assertEqual(r[0]['id'], 'd')  # covers both topics
        self.assertEqual({x['id'] for x in r}, {'a', 'c', 'd', 'f'})
        self.assertNotIn('e', [x['id'] for x in r])


class Meaning(unittest.TestCase):
    sims = {'a': 0.72, 'b': 0.41, 'c': 0.2, 'd': 0.5, 'e': 0.05, 'f': 0.44}

    def test_meaning_only(self):
        r = F.rank(F.parse('atomic energy watchdog'), DOCS, 'meaning', self.sims)
        self.assertEqual([x['id'] for x in r], ['a', 'd', 'f', 'b'])

    def test_both_keeps_keyword_hits_and_strong_meaning(self):
        r = F.rank(F.parse('iran'), DOCS, 'both', self.sims)
        ids = [x['id'] for x in r]
        self.assertEqual(ids[0], 'a')
        self.assertIn('d', ids)
        self.assertNotIn('b', ids)  # 0.41 is below the blend floor and has no keyword
        self.assertTrue(all(x['terms'] for x in r if x['id'] in ('a', 'd', 'f')))

    def test_web_queries(self):
        self.assertEqual(F.web_queries(F.parse('"red sea" shipping, houthis')), ['"red sea" shipping when:7d', 'houthis when:7d'])


RSS = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Houthis target ship in Red Sea - Reuters</title><link>https://example.com/a1</link><pubDate>Wed, 18 Nov 2026 08:00:00 GMT</pubDate></item>
<item><title>Shipping insurers raise Red Sea premiums - FT</title><link>https://example.com/a2</link><pubDate>Wed, 18 Nov 2026 09:00:00 GMT</pubDate></item>
</channel></rss>'''

ENTRIES = [{'id': f'n{i}', 'source_id': 'x', 'source': src, 'title': t, 'summary': '', 'medium': 'article', 'published': '2026-11-18T00:00:00Z'}
           for i, (src, t) in enumerate([('Reuters', 'Iran nuclear talks resume'), ('BBC', 'Cricket: India win series'), ('DW', 'EU sanctions on Iran')])]


class Endpoints(unittest.TestCase):
    def test_find_and_fetch(self):
        with tempfile.TemporaryDirectory() as td, patch.object(server, 'DB_FILE', Path(td) / 'o.sqlite3'), \
                patch.object(semantic, 'ready', lambda: False), patch.object(server, 'graph_entries', lambda: ENTRIES):
            server.init_db()
            srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{srv.server_address[1]}'
            post = lambda u, b: json.load(urllib.request.urlopen(urllib.request.Request(base + u, json.dumps(b).encode(), {'Content-Type': 'application/json'}), timeout=20))
            try:
                d = post('/api/find', {'q': 'iran', 'mode': 'auto', 'ids': ['n0', 'n1']})
                self.assertEqual(d['mode'], 'keywords')  # no language model here
                self.assertEqual([r['id'] for r in d['results']], ['n0'])  # n2 is outside this panel
                self.assertEqual(d['pool'], 2)
                d = post('/api/find', {'q': 'iran', 'mode': 'meaning'})
                self.assertEqual(d['mode'], 'keywords')
                self.assertTrue(d['note'])
                with self.assertRaises(urllib.error.HTTPError) as e:
                    post('/api/find', {'q': ' the '})
                self.assertEqual(e.exception.code, 400)
                # Nothing held: fetch from Google News into the desk, then search with the fetched ids.
                self.assertEqual(post('/api/find', {'q': 'red sea', 'ids': ['n0', 'n1', 'n2']})['results'], [])
                with patch.object(server, 'fetch_bytes', return_value=RSS) as fb:
                    f = post('/api/find/fetch', {'q': '"red sea", houthis', 'desk': 'India'})
                self.assertEqual(fb.call_count, 2)
                self.assertEqual((f['fetched'], f['added']), (4, 2))  # same two articles from both queries
                self.assertEqual(len(f['ids']), 2)
                with closing(server.db_connect()) as con:
                    self.assertEqual({r[0] for r in con.execute('SELECT source_id FROM entries')}, {'expand:India'})
                d = post('/api/find', {'q': 'red sea', 'ids': ['n0'], 'extra': f['ids']})
                self.assertEqual(len(d['results']), 2)
                self.assertEqual(len(d['entries']), 2)  # sent in full: the page state doesn't hold them
                self.assertTrue(all(e['story']['sources'] == 1 for e in d['entries']))
                with patch.object(server, 'fetch_bytes', side_effect=OSError('offline')):
                    f = post('/api/find/fetch', {'q': 'anything', 'desk': 'Nowhere'})
                self.assertEqual((f['fetched'], len(f['notes'])), (0, 1))
            finally:
                srv.shutdown()


class MeaningEndpoint(unittest.TestCase):
    def test_meaning_path_embeds_missing_articles(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('numpy not installed')
        axis = {'iran': 0, 'nuclear': 0, 'sanctions': 0, 'cricket': 1}

        def embed(texts, cache_dir=None):
            out = []
            for t in texts:
                v = np.zeros(3, dtype=np.float32)
                for w, k in axis.items():
                    if w in t.lower():
                        v[k] += 1
                v[2] += 0.2
                out.append(v / np.linalg.norm(v))
            return out
        with patch.object(semantic, 'ready', lambda: True), patch.object(semantic, 'embed_texts', embed), \
                patch.object(semantic, 'vectors', lambda db, ids: {}), patch.object(server, 'graph_entries', lambda: ENTRIES):
            d = server.find_articles({'q': 'atomic programme of iran', 'mode': 'auto'})
            self.assertEqual(d['mode'], 'both')
            ids = [r['id'] for r in d['results']]
            self.assertEqual(ids[0], 'n0')
            self.assertNotIn('n1', ids)  # cricket: no keyword, far in meaning
            self.assertIsNotNone(d['results'][0]['meaning'])


if __name__ == '__main__':
    unittest.main()
