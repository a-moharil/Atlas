"""v5.7 geopolitics reel and player errors: classification, selection, endpoints, isolation from the desks."""
import datetime as dt
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import geo_video as G  # noqa: E402
import semantic  # noqa: E402
import server  # noqa: E402
import video_check  # noqa: E402
from tests.tmpdir import TempDir

NOW = dt.datetime(2026, 11, 18, 12, tzinfo=dt.timezone.utc)
iso = lambda h: (NOW - dt.timedelta(hours=h)).strftime('%Y-%m-%dT%H:%M:%SZ')
CH = {'geo_aje': {'name': 'Al Jazeera English', 'region': 'World'}, 'geo_sky': {'name': 'Sky News', 'region': 'UK'}}


def row(i, src, title, hours, vid=None):
    return {'id': f'v{i}', 'source_id': src, 'source': src, 'title': title, 'summary': '', 'video_id': vid or f'vid{i:08d}',
            'published': iso(hours)}


class Classify(unittest.TestCase):
    def test_news_and_geo(self):
        c = G.classify('Russia launches missile strikes on Kyiv as peace talks stall')
        self.assertTrue(c['news'])
        self.assertGreaterEqual(c['geo'], G.GEO_MIN)
        self.assertIn('missile', ' '.join(c['terms']))

    def test_not_news(self):
        for t in ['Champions League highlights: Arsenal v PSV', 'Behind the scenes at the Oscars', 'Best pasta recipe #shorts']:
            self.assertFalse(G.classify(t)['news'], t)

    def test_domestic_news_is_not_geopolitics(self):
        self.assertLess(G.classify('Local council approves new bus routes')['geo'], G.GEO_MIN)
        self.assertLess(G.classify('Government announces school holidays')['geo'], G.GEO_MIN)


class Select(unittest.TestCase):
    def rows(self):
        return [row(1, 'geo_aje', 'Iran and IAEA agree on inspections', 1), row(2, 'geo_aje', 'Gaza ceasefire talks resume in Cairo', 2),
                row(3, 'geo_aje', 'Israel and Hezbollah exchange fire on border', 3), row(4, 'geo_sky', 'NATO summit opens in The Hague', 4),
                row(5, 'geo_sky', 'Premier League: match highlights', 1), row(6, 'geo_sky', 'Weather: rain for the weekend', 2),
                row(7, 'geo_sky', 'Ukraine war: drone attack on Odesa', 30), row(8, 'other', 'China Taiwan military drills', 1),
                row(9, 'geo_sky', 'Sanctions on Russia extended by EU', 5)]

    def test_window_filters_and_interleave(self):
        states = {r['video_id']: {'state': 'playable'} for r in self.rows()}
        states['vid00000009'] = {'state': 'blocked'}
        vids, counts = G.select(self.rows(), states, CH, 24, True, now=NOW)
        self.assertEqual([v['id'] for v in vids], ['v1', 'v4', 'v2', 'v3'])  # channels alternate, newest first
        self.assertEqual(counts['recent'], 7)          # v7 too old, v8 not a reel channel
        self.assertEqual(counts['not_news'], 1)        # sport
        self.assertEqual(counts['not_geopolitics'], 1)  # weather
        self.assertEqual(counts['not_playable'], 1)

    def test_all_news_hidden_and_pending(self):
        states = {r['video_id']: {'state': 'playable'} for r in self.rows()[:4]}
        vids, counts = G.select(self.rows(), states, CH, 24, False, now=NOW, hidden={'v2'})
        self.assertNotIn('v2', [v['id'] for v in vids])
        self.assertEqual(counts['removed'], 1)
        self.assertEqual(counts['awaiting_check'], 2)  # weather and sanctions have no check yet

    def test_duplicates_once(self):
        r = [row(1, 'geo_aje', 'Iran nuclear talks resume', 1, 'samevideo01'), row(2, 'geo_aje', 'Iran nuclear talks resume', 1, 'samevideo01')]
        vids, _ = G.select(r, {'samevideo01': {'state': 'playable'}}, CH, 24, True, now=NOW)
        self.assertEqual(len(vids), 1)


class PlayerErrors(unittest.TestCase):
    def test_report_and_recheck_window(self):
        with TempDir() as td, closing(__import__('sqlite3').connect(Path(td) / 'x.db')) as con:
            con.row_factory = __import__('sqlite3').Row
            self.assertFalse(video_check.report_player_error(con, 'bad id', 150, iso(0)))
            self.assertTrue(video_check.report_player_error(con, 'abcdefghijk', 150, iso(0)))
            st = video_check.states(con)['abcdefghijk']
            self.assertEqual(st['state'], 'blocked')
            row_ = dict(st, checked=iso(24))
            self.assertFalse(video_check._due(row_, NOW))  # oEmbed would say "playable"; keep the browser's answer
            self.assertTrue(video_check._due(dict(st, checked=iso(24 * 8)), NOW))
            video_check.report_player_error(con, 'abcdefghij2', 100, iso(0))
            self.assertEqual(video_check.states(con)['abcdefghij2']['state'], 'unavailable')


class Endpoints(unittest.TestCase):
    def test_reel_and_isolation(self):
        with TempDir() as td, patch.object(server, 'DB_FILE', Path(td) / 'o.sqlite3'), \
                patch.object(semantic, 'ready', lambda: False):
            server.init_db()
            now = dt.datetime.now(dt.timezone.utc)
            recent = (now - dt.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
            with closing(server.db_connect()) as con:
                video_check.init(con)
                for i, (src, title) in enumerate([('geo_aje', 'Iran and Israel trade strikes as UN calls for ceasefire'),
                                                  ('bbc_yt', 'Ukraine war: Russia hits power grid with missiles'),
                                                  ('geo_sky', 'Football: cup final highlights')]):
                    vid = f'reelvid{i:04d}'
                    con.execute('''INSERT INTO entries(id,source_id,source,tier,region,medium,title,url,summary,published,retrieved,video_id)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (f'e{i}', src, src, 'video', 'World', 'video', title, 'https://youtube.com', '', recent, recent, vid))
                    con.execute("INSERT INTO video_status(video_id,state,checked) VALUES(?,?,?)", (vid, 'playable', recent))
                con.commit()
            srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{srv.server_address[1]}'
            get = lambda u: json.load(urllib.request.urlopen(base + u, timeout=20))
            post = lambda u, b: json.load(urllib.request.urlopen(urllib.request.Request(base + u, json.dumps(b).encode(), {'Content-Type': 'application/json'}), timeout=20))
            try:
                r = get('/api/geo-reel')
                self.assertEqual({v['source_id'] for v in r['videos']}, {'geo_aje', 'bbc_yt'})
                self.assertEqual(r['counts']['not_news'], 1)
                self.assertTrue(any(c['id'] == 'geo_aje' for c in r['channels']))
                self.assertTrue(post('/api/video/player-error', {'video_id': 'reelvid0000', 'code': 150})['ok'])
                r = get('/api/geo-reel')
                self.assertEqual([v['source_id'] for v in r['videos']], ['bbc_yt'])
                # Reel-only uploads never reach the desks; included channels (bbc_yt) still do.
                ids = {e['id'] for e in server.read_state()['entries']}
                self.assertIn('e1', ids)
                self.assertNotIn('e0', ids)
                self.assertNotIn('e2', ids)
            finally:
                srv.shutdown()


if __name__ == '__main__':
    unittest.main()
