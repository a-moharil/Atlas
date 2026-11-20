"""v6.0 Sanjaya: your own lean calibration, the rename and the motivation page."""
import json
import sqlite3
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import publishers as P  # noqa: E402
import semantic  # noqa: E402
import server  # noqa: E402
from tests.tmpdir import TempDir


class Calibration(unittest.TestCase):
    def setUp(self):
        self.td = TempDir()
        self.con = sqlite3.connect(Path(self.td.name) / 'p.db')
        P.init(self.con)

    def tearDown(self):
        self.con.close()
        self.td.cleanup()
        P.OVERRIDES = {}
        P._OVERRIDE_VERSION[0] += 1

    def test_override_applies_and_resets(self):
        self.assertEqual(P.profile('theguardian.com')['lean'], -2)
        P.set_lean(self.con, 'www.theguardian.com', 1, 'my reading of the opinion pages', 'now')
        p = P.profile('theguardian.com')
        self.assertEqual((p['lean'], p['lean_label'], p['lean_user'], p['lean_original']), (1, 'Lean Right', True, -2))
        self.assertEqual(p['lean_note'], 'my reading of the opinion pages')
        P.set_lean(self.con, 'theguardian.com', None, '', 'now')
        self.assertIsNone(P.profile('theguardian.com')['lean'])
        self.assertEqual(P.profile('theguardian.com')['lean_label'], 'Not rated')
        P.set_lean(self.con, 'theguardian.com', 'reset', '', 'now')
        p = P.profile('theguardian.com')
        self.assertEqual((p['lean'], p['lean_user']), (-2, False))

    def test_unrated_outlet_can_be_rated(self):
        P.set_lean(self.con, 'smallpaper.example', -1, '', 'now')
        self.assertEqual(P.profile('smallpaper.example')['lean'], -1)

    def test_validation(self):
        for bad in (3, -3, 'left', 1.5):
            with self.assertRaises(ValueError):
                P.set_lean(self.con, 'reuters.com', bad, '', 'now')
        with self.assertRaises(ValueError):
            P.set_lean(self.con, 'bad host!', 0, '', 'now')

    def test_persists_and_reloads(self):
        P.set_lean(self.con, 'foxnews.com', 0, '', 'now')
        P.OVERRIDES = {}
        P.load_overrides(self.con)
        self.assertEqual(P.profile('foxnews.com')['lean'], 0)

    def test_story_spread_follows_override(self):
        es = [{'id': 'a', 'medium': 'article', 'title': 'Budget vote passes parliament tonight', 'url': 'https://www.theguardian.com/a', 'source': 'Guardian'},
              {'id': 'b', 'medium': 'article', 'title': 'Budget vote passes parliament tonight', 'url': 'https://www.foxnews.com/b', 'source': 'Fox'}]
        P.enrich(es)
        self.assertEqual(es[0]['story']['dist'], {'left': 1, 'center': 0, 'right': 1, 'unrated': 0})
        P.set_lean(self.con, 'theguardian.com', 2, '', 'now')
        es = [dict(e) for e in es]
        P.enrich(es)  # same articles: the cache must not hide the change
        self.assertEqual(es[0]['story']['dist'], {'left': 0, 'center': 0, 'right': 2, 'unrated': 0})


class Endpoint(unittest.TestCase):
    def test_http(self):
        with TempDir() as td, patch.object(server, 'DB_FILE', Path(td) / 'o.sqlite3'), patch.object(semantic, 'ready', lambda: False):
            server.init_db()
            srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{srv.server_address[1]}'
            post = lambda b: json.load(urllib.request.urlopen(urllib.request.Request(base + '/api/lean', json.dumps(b).encode(), {'Content-Type': 'application/json'}), timeout=20))
            try:
                r = post({'host': 'reuters.com', 'lean': -1, 'note': 'test'})
                self.assertEqual(r['lean_overrides']['reuters.com']['lean'], -1)
                st = server.read_state()
                self.assertIn('reuters.com', st['lean_overrides'])
                self.assertTrue(st['publishers']['reuters.com']['lean_user'])
                self.assertEqual(post({'host': 'reuters.com', 'lean': 'none'})['lean_overrides']['reuters.com']['lean'], None)
                self.assertNotIn('reuters.com', post({'host': 'reuters.com', 'lean': 'reset'})['lean_overrides'])
                with self.assertRaises(urllib.error.HTTPError) as e:
                    post({'host': 'reuters.com', 'lean': 7})
                self.assertEqual(e.exception.code, 400)
            finally:
                srv.shutdown()
                P.OVERRIDES = {}


class Name(unittest.TestCase):
    def test_visible_name_and_page(self):
        html = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<title>Sanjaya', html)
        self.assertIn('data-page="about"', html)
        self.assertIn('/about.js', html)
        self.assertIn('/calibrate.js', html)
        about = (ROOT / 'static' / 'about.js').read_text(encoding='utf-8')
        self.assertIn('Ambarish Moharil', about)
        self.assertIn('kim akurvata sañjaya', about)


if __name__ == '__main__':
    unittest.main()
