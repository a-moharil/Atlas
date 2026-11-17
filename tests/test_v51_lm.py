"""v5.1: grouping by meaning (embeddings) and optional local-model labels."""
import json, sys, threading, unittest, http.server
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import numpy as np
import semantic, publishers, lm_labels, emergency

def unit(v):
    v = np.asarray(v, dtype=np.float32); return v / np.linalg.norm(v)

def art(i, t='2026-11-16T10:00:00Z', src='a', title='x'):
    return {'id': f'id{i}', 'medium': 'article', 'published': t, 'retrieved': t, 'source_id': src, 'title': title, 'url': f'https://x/{i}'}


class GroupingTests(unittest.TestCase):
    def setUp(self):
        semantic._np = np

    def test_same_meaning_grouped_and_chaining_blocked(self):
        base = np.zeros(8)
        A = unit([1, 0, 0, 0, 0, 0, 0, 0]); A2 = unit([0.97, 0.24, 0, 0, 0, 0, 0, 0])
        B = unit([0.70, 0.71, 0, 0, 0, 0, 0, 0])  # close to A2 (0.85) but not to A (0.70)
        C = unit([0, 1, 0, 0, 0, 0, 0, 0])
        items = [art(i) for i in range(4)]
        vecs = {'id0': A, 'id1': A2, 'id2': B, 'id3': C}
        groups, _ = semantic.group(items, vecs, 0.8, 72)
        sets = sorted(sorted(g) for g in groups)
        self.assertIn([0, 1], sets)           # paraphrases joined
        self.assertNotIn([0, 1, 2, 3], sets)  # no chain through B to C

    def test_time_window_separates_events(self):
        v = unit([1, 0, 0])
        items = [art(0, '2026-11-01T00:00:00Z'), art(1, '2026-11-16T00:00:00Z')]
        groups, _ = semantic.group(items, {'id0': v, 'id1': v}, 0.8, 72)
        self.assertEqual(len(groups), 2)

    def test_story_spread_uses_meaning_and_marks_method(self):
        publishers.set_feeds([{'id': 'a', 'url': 'https://www.thehindu.com/f', 'site': 'https://thehindu.com'},
                              {'id': 'b', 'url': 'https://swarajyamag.com/f', 'site': 'https://swarajyamag.com'}])
        rows = [art(0, src='a', title='RBI holds repo rate steady'), art(1, src='b', title='Reserve Bank keeps policy unchanged'),
                art(2, src='a', title='Monsoon deficit widens across Maharashtra districts')]
        meaning = {'id0': {'group': 'g', 'similarity': .88}, 'id1': {'group': 'g', 'similarity': .88}}
        s = publishers.stories(rows, meaning)
        self.assertEqual(s['id0']['sources'], 2)
        self.assertEqual(s['id0']['method'], 'meaning')
        self.assertEqual(s['id2']['method'], 'keywords')

    def test_newsroom_matcher(self):
        v1, v2 = unit([1, .1, 0]), unit([.95, .2, 0])
        m = semantic.Matcher({'r1': v1, 'r2': v2}, 0.8)
        g = {'id': 'g1'}
        best, used = m.assign({'id': 'r1'}, []); self.assertTrue(used); self.assertIsNone(best)
        m.add({'id': 'r1'}, g)
        best, used = m.assign({'id': 'r2'}, [g]); self.assertIs(best, g)
        best, used = m.assign({'id': 'r3'}, [g]); self.assertFalse(used)  # no vector -> keyword fallback

    def test_settings_validation(self):
        import sqlite3
        con = sqlite3.connect(':memory:'); semantic.init(con)
        semantic.set_setting(con, 'threshold', '0.99'); self.assertEqual(semantic.settings(con)['threshold'], 0.95)
        with self.assertRaises(ValueError): semantic.set_setting(con, 'ollama_url', 'http://evil.example:11434')
        with self.assertRaises(ValueError): semantic.set_setting(con, 'window_hours', '5')

    def test_not_ready_means_keywords(self):
        semantic._model = None
        out, mode, note = semantic.story_groups([art(0)], None, dict(semantic.DEFAULTS))
        self.assertEqual((out, mode), ({}, 'keywords'))


class LabelTests(unittest.TestCase):
    def test_parse_and_prompt(self):
        out = lm_labels.parse('noise {"label":"RBI policy decision","summary":"Outlets report the RBI held rates.","differences":"No clear difference."}')
        self.assertEqual(out['label'], 'RBI policy decision')
        with self.assertRaises(ValueError): lm_labels.parse('{"label":""}')
        p = lm_labels.build_prompt([{'source': 'The Hindu', 'title': 'आरबीआई ने दरें स्थिर रखीं', 'summary': ''}])
        self.assertIn('Use ONLY the headlines', p); self.assertIn('आरबीआई', p)

    def test_run_against_fake_ollama(self):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _send(self, obj):
                b = json.dumps(obj).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
            def do_GET(self): self._send({'models': [{'name': 'qwen2.5:1.5b'}]})
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self._send({'response': json.dumps({'label': 'Border talks', 'summary': 'Both outlets report talks.', 'differences': 'No clear difference.'})})
        srv = http.server.HTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        import sqlite3, tempfile, os
        path = os.path.join(tempfile.mkdtemp(), 'l.db')
        def db():
            c = sqlite3.connect(path); c.row_factory = sqlite3.Row; return c
        groups = [[{'id': 'a', 'source': 'The Hindu', 'title': 'India China talks'}, {'id': 'b', 'source': 'Swarajya', 'title': 'India, China hold talks'}],
                  [{'id': 'c', 'source': 'One outlet', 'title': 'Solo story'}]]
        n = lm_labels.run(groups, db, f'http://127.0.0.1:{srv.server_port}', 'qwen2.5:1.5b')
        self.assertEqual(n, 1)  # single-outlet group skipped
        with db() as c: self.assertEqual(lm_labels.cached(c, [lm_labels.group_key(groups[0])])[lm_labels.group_key(groups[0])]['label'], 'Border talks')
        srv.shutdown()


if __name__ == '__main__':
    unittest.main()
