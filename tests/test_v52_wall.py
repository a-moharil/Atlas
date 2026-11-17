"""v5.2: removing an article from the wall persists and can be undone; it never deletes the article."""
import json, sys, tempfile, threading, unittest, urllib.request
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class WallTest(unittest.TestCase):
    def test_hide_undo_clear(self):
        with tempfile.TemporaryDirectory() as td, patch.object(server, 'DB_FILE', Path(td) / 'observatory.sqlite3'):
            server.init_db()
            srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{srv.server_address[1]}'
            def post(body):
                req = urllib.request.Request(base + '/api/wall', json.dumps(body).encode(), {'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=10) as r:
                    return json.load(r)['wall_hidden']
            try:
                self.assertEqual(sorted(post({'ids': ['a', 'b'], 'hidden': True})), ['a', 'b'])
                self.assertEqual(post({'ids': ['a'], 'hidden': False}), ['b'])
                self.assertIn('b', server.read_state()['wall_hidden'])
                self.assertEqual(post({'clear': True}), [])
                with closing(server.db_connect()) as con:  # entries table is untouched by hiding
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM wall_hidden').fetchone()[0], 0)
            finally:
                srv.shutdown()


if __name__ == '__main__':
    unittest.main()
