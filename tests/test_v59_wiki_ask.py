"""v5.9 Wikipedia page and Ask drawer: HTML cleaning, caching, passages, citations, endpoints."""
import datetime as dt
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ask  # noqa: E402
import lm_labels  # noqa: E402
import semantic  # noqa: E402
import server  # noqa: E402
import wiki  # noqa: E402

PAGE = '''<html><head><title>Red Sea</title><style>p{}</style></head><body>
<section><p id="intro" onclick="steal()">The <b>Red Sea</b> is a <a rel="mw:WikiLink" href="./Seawater" title="Seawater">seawater</a> inlet<sup class="reference"><a href="#cite_note-1">[1]</a></sup>.</p>
<span class="mw-editsection">[edit]</span><script>alert(1)</script><div style="display: none">hidden</div>
<table class="infobox vcard"><tr><th scope="row">Area</th><td colspan="2">438,000 km²</td></tr></table>
<figure class="mw-default-size"><img src="//upload.wikimedia.org/x.jpg" width="220" onerror="x()"><figcaption>Map</figcaption></figure>
<img src="https://evil.example/x.png"><a href="javascript:alert(1)">bad</a><a href="./Category:Seas">cat</a>
<div class="navbox"><a href="./Other">navbox link</a></div><p>After <a href="https://example.org/x">site</a></p></section></body></html>'''


class Clean(unittest.TestCase):
    def test_allowlist(self):
        h = wiki.clean_html(PAGE)
        for bad in ('script', 'onclick', 'onerror', 'alert', 'hidden', '[edit]', 'navbox link', 'evil.example', '<style', 'javascript'):
            self.assertNotIn(bad, h)
        self.assertIn('id="wk-intro"', h)
        self.assertIn('data-wiki="Seawater"', h)
        self.assertIn('data-wikijump="wk-cite_note-1"', h)
        self.assertIn('src="https://upload.wikimedia.org/x.jpg"', h)
        self.assertIn('colspan="2"', h)
        self.assertIn('class="wk-infobox"', h)
        self.assertIn('href="https://en.wikipedia.org/wiki/Category%3ASeas" target="_blank"', h)
        self.assertIn('href="https://example.org/x" target="_blank" rel="noopener noreferrer"', h)
        self.assertIn('After', h)  # content after dropped blocks survives

    def test_titles(self):
        self.assertEqual(wiki.norm_title('red  sea'), 'Red_sea')
        with self.assertRaises(ValueError):
            wiki.norm_title('a|b')

    def test_passages_skip_reference_sections(self):
        text = 'Lead text ' * 30 + '\n== History ==\n' + 'Old times. ' * 10 + '\n== References ==\nRef one'
        ps = wiki.passages(text, words=40)
        self.assertEqual(ps[0]['section'], 'Introduction')
        self.assertIn('History', {p['section'] for p in ps})
        self.assertNotIn('References', {p['section'] for p in ps})


class Cache(unittest.TestCase):
    def test_fresh_then_stale(self):
        with tempfile.TemporaryDirectory() as td:
            db = lambda: __import__('sqlite3').connect(Path(td) / 'w.db')
            calls = []
            get = lambda url, *a: calls.append(url) or json.dumps({'query': {'search': [{'title': 'Red Sea', 'snippet': '<span>Red</span> Sea', 'wordcount': 5000}]}}).encode()
            r = wiki.search('red sea', get, db)
            self.assertEqual(r['results'][0]['snippet'], 'Red Sea')
            wiki.search('Red Sea', get, db)
            self.assertEqual(len(calls), 1)  # cached
            later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)
            body, info = wiki._cached(db, 'search:red sea', 'search', lambda: (_ for _ in ()).throw(OSError('offline')), now=later)
            self.assertTrue(info['stale'])
            with self.assertRaises(OSError):
                wiki._cached(db, 'never', 'search', lambda: (_ for _ in ()).throw(OSError('offline')))


class Citations(unittest.TestCase):
    def test_check(self):
        text, s = ask.check_citations('Ships were attacked [A1][A9]. Insurers raised rates [A2, W1]. The sea is salty. [W1]', 2, 1)
        self.assertNotIn('A9', text)
        self.assertEqual(s[0]['cites'], ['A1'])
        self.assertEqual(s[1]['cites'], ['A2', 'W1'])
        self.assertEqual(s[2]['cites'], ['W1'])  # trailing citation joins its sentence
        _, s = ask.check_citations('Unsupported claim. Supported one [A1].', 1, 0)
        self.assertEqual([x['cites'] for x in s], [[], ['A1']])

    def test_prompt_and_job(self):
        arts = [{'title': 'Houthis attack ship', 'summary': 'Reuters reports', 'outlet': 'Reuters', 'published': '2026-11-18T00:00:00Z'}]
        ps = [{'page': 'Red Sea', 'section': 'Introduction', 'text': 'The Red Sea is an inlet.'}]
        msgs = ask.build_prompt('What happened?', arts, ps)
        self.assertIn('[A1] Reuters (2026-11-18): Houthis attack ship', msgs[1]['content'])
        self.assertIn('[W1] Wikipedia, "Red Sea"', msgs[1]['content'])
        job = ask.start('q', arts, ps, 'http://127.0.0.1:1', 'm', stream=lambda u, m, msg, add: [add(t) for t in ['Ships were ', 'attacked [A1]. ', 'It is an inlet [W1].']])
        for _ in range(50):
            if ask.get(job['id'])['status'] != 'writing':
                break
            time.sleep(0.02)
        j = ask.get(job['id'])
        self.assertEqual(j['status'], 'done')
        self.assertEqual([x['cites'] for x in j['sentences']], [['A1'], ['W1']])

    def test_loose_ranking(self):
        docs = [('a', 'Houthi attack on ship in Red Sea', '', ''), ('b', 'Cricket final', '', ''), ('c', 'Shipping insurers react', '', '')]
        r = ask.rank_loose('What did the Houthis do to shipping in the Red Sea?', docs, 'keywords', {})
        self.assertEqual(r[0]['id'], 'a')
        self.assertNotIn('b', [x['id'] for x in r])


ENTRIES = [{'id': 'n0', 'source_id': 'x', 'source': 'Reuters', 'publisher': 'reuters.com', 'title': 'Houthis attack ship in Red Sea', 'summary': '',
            'medium': 'article', 'published': '2026-11-18T00:00:00Z', 'url': 'https://reuters.com/a'},
           {'id': 'n1', 'source_id': 'x', 'source': 'BBC', 'publisher': 'bbc.co.uk', 'title': 'Cricket final tonight', 'summary': '',
            'medium': 'article', 'published': '2026-11-18T00:00:00Z', 'url': 'https://bbc.co.uk/b'}]


class Endpoints(unittest.TestCase):
    def test_wiki_and_ask(self):
        def fake_get(url, *a):
            if 'list=search' in url:
                return json.dumps({'query': {'search': [{'title': 'Red Sea', 'snippet': 'Red Sea', 'wordcount': 9}]}}).encode()
            if '/page/html/' in url:
                if 'Nope' in url:
                    raise urllib.error.HTTPError(url, 404, 'nf', {}, None)
                return PAGE.encode()
            if '/page/summary/' in url:
                return json.dumps({'title': 'Red Sea', 'description': 'Sea between Africa and Asia'}).encode()
            if 'prop=extracts' in url:
                return json.dumps({'query': {'pages': [{'extract': 'The Red Sea is a seawater inlet of the Indian Ocean.\n== Shipping ==\nThe Red Sea carries shipping through the Suez Canal.'}]}}).encode()
            raise AssertionError(url)
        with tempfile.TemporaryDirectory() as td, patch.object(server, 'DB_FILE', Path(td) / 'o.sqlite3'), \
                patch.object(semantic, 'ready', lambda: False), patch.object(server, 'graph_entries', lambda: ENTRIES), \
                patch.object(server, 'wiki_get', fake_get):
            server.init_db()
            srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{srv.server_address[1]}'
            get = lambda u: json.load(urllib.request.urlopen(base + u, timeout=20))
            post = lambda u, b: json.load(urllib.request.urlopen(urllib.request.Request(base + u, json.dumps(b).encode(), {'Content-Type': 'application/json'}), timeout=20))
            try:
                self.assertEqual(get('/api/wiki/search?q=red+sea')['results'][0]['title'], 'Red Sea')
                p = get('/api/wiki/page?title=Red_Sea')
                self.assertEqual(p['description'], 'Sea between Africa and Asia')
                self.assertNotIn('<script', p['html'])
                with self.assertRaises(urllib.error.HTTPError) as e:
                    get('/api/wiki/page?title=Nope')
                self.assertEqual(e.exception.code, 404)
                # Ollama not running: sources still come back.
                with patch.object(lm_labels, 'check', lambda u, m: {'status': 'offline', 'detail': 'not running', 'models': []}):
                    d = post('/api/ask', {'question': 'What is happening to shipping in the Red Sea?', 'wiki': 'Red Sea'})
                self.assertEqual(d['status'], 'no_model')
                self.assertEqual([a['id'] for a in d['sources']['atlas']], ['n0'])
                self.assertIn('Introduction', [w['section'] for w in d['sources']['wikipedia']])
                self.assertIn('Shipping', [w['section'] for w in d['sources']['wikipedia']])
                # Panel scope: only the ids sent are searched.
                with patch.object(lm_labels, 'check', lambda u, m: {'status': 'ready', 'detail': '', 'models': [m]}), \
                        patch.object(ask, '_stream', lambda u, m, msg, add: add('Reuters reports an attack [A1]. Suez [W2].')):
                    d = post('/api/ask', {'question': 'Red Sea attack', 'ids': ['n0', 'n1'], 'wiki': 'Red Sea'})
                    self.assertEqual(d['status'], 'writing')
                    for _ in range(50):
                        j = get('/api/ask/job/' + d['job'])
                        if j['status'] != 'writing':
                            break
                        time.sleep(0.02)
                self.assertEqual(j['status'], 'done')
                self.assertEqual(j['sentences'][0]['cites'], ['A1'])
                d = post('/api/ask', {'question': 'zebra migration', 'ids': ['n1']})
                self.assertEqual(d['status'], 'no_sources')
                with self.assertRaises(urllib.error.HTTPError):
                    post('/api/ask', {'question': ''})
                self.assertTrue(post('/api/ask/settings', {'model': 'llama3.2:3b'})['ok'])
                with self.assertRaises(urllib.error.HTTPError):
                    post('/api/ask/settings', {'model': 'bad model!'})
            finally:
                srv.shutdown()


if __name__ == '__main__':
    unittest.main()
