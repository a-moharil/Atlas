"""v6.4.1: office-holders from Wikipedia's current lists (with progress and refresh), and the pulse model.

Wikipedia pages are replaced by fixtures shaped like the real articles (rowspans, split headers, hidden sort
keys, footnotes, former ministers), so these tests run offline.
"""
import datetime as dt
import json
import sqlite3
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path

import forecast as F
import officials as O
import pulse as P
import wikitables as W
from test_v64_officials_forecast import synthetic_db

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests' / 'fixtures'
PAGES = {'List of current Indian chief ministers': 'wp_cm_list.html', 'List of current Indian deputy chief ministers': 'wp_dcm_list.html',
         'List of current Indian governors': 'wp_gov_list.html', 'Second Yogi Adityanath ministry': 'wp_up_ministry.html',
         'Union Council of Ministers': 'wp_union_council.html'}


def fake_getter(calls=None):
    def get(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        if calls is not None:
            calls.append(q.get('page') or q.get('list') or q.get('prop') or 'sparql')
        if q.get('action') == 'parse':
            f = PAGES.get(q['page'])
            if not f:
                return json.dumps({'error': {'info': 'missing'}}).encode()
            return json.dumps({'parse': {'text': (FIX / f).read_text(encoding='utf-8')}}).encode()
        if q.get('list') == 'search':
            return json.dumps({'query': {'search': []}}).encode()
        if q.get('prop') == 'pageimages':
            return json.dumps({'query': {'pages': [{'title': 'Suresh Kumar Khanna', 'pageimage': 'SKK.jpg',
                                                    'thumbnail': {'source': 'https://upload.wikimedia.org/x/SKK.jpg'}}]}}).encode()
        raise OSError('Wikidata offline in tests')
    return get


class Tables(unittest.TestCase):
    def setUp(self):
        self.t = W.tables((FIX / 'wp_union_council.html').read_text(encoding='utf-8'))

    def test_sections_rowspans_and_split_headers(self):
        self.assertEqual([t['heading'] for t in self.t], ['Cabinet Ministers', 'Ministers of State (Independent Charge)', 'Ministers of State'])
        rec = W.records(self.t[0])
        shah = [r for r in rec if r['name'] == 'Amit Shah']
        self.assertEqual([r['portfolios'][0] for r in shah], ['Minister of Home Affairs', 'Minister of Co-operation'])   # rowspan
        self.assertTrue(all(r['party'] == 'BJP' for r in shah))                                  # Party | Party split header
        modi = rec[0]
        self.assertEqual(modi['name'], 'Narendra Modi')                                          # hidden sort key and footnote gone
        self.assertEqual(modi['since'], '2024-06-09')
        self.assertTrue(modi['img'].startswith('https://upload.wikimedia.org/'))
        self.assertFalse(next(r for r in rec if r['name'] == 'Old Minister')['current'])
        mos = W.records(self.t[2])
        self.assertEqual(mos[1]['portfolios'], mos[0]['portfolios'])                            # shared portfolio cell

    def test_list_page_columns(self):
        t = W.tables((FIX / 'wp_cm_list.html').read_text(encoding='utf-8'))[0]
        r = {x['state']: x for x in W.records(t)}
        self.assertEqual(r['Uttar Pradesh']['name'], 'Yogi Adityanath')
        self.assertEqual(r['Uttar Pradesh']['ministry'], 'Second Yogi Adityanath ministry')
        self.assertEqual(r['Punjab']['party'], 'AAP')
        d = W.tables((FIX / 'wp_dcm_list.html').read_text(encoding='utf-8'))[0]
        self.assertEqual([x['name'] for x in W.records(d)], ['Keshav Prasad Maurya', 'Brajesh Pathak'])   # Officeholder, not "Chief Minister"

    def test_dates(self):
        self.assertEqual(W.iso_date('19 March 2017 (9 years)'), '2017-03-19')
        self.assertEqual(W.iso_date('March 19, 2017'), '2017-03-19')
        self.assertIsNone(W.iso_date('Incumbent'))


class Pipeline(unittest.TestCase):
    def test_state_cabinet(self):
        steps = []
        d = O.build('state:Uttar_Pradesh', fake_getter(), overrides={'scopes': {}}, report=lambda s, p: steps.append(len(s)))
        names = [p['name'] for p in d['people']]
        self.assertEqual(names[:4], ['Anandiben Patel', 'Yogi Adityanath', 'Keshav Prasad Maurya', 'Brajesh Pathak'])
        self.assertIn('Suresh Kumar Khanna', names); self.assertIn('Anoop Pradhan', names)
        self.assertNotIn('Dropped MoS', names)                                           # left office
        groups = {p['name']: p['group'] for p in d['people']}
        self.assertEqual(groups['Girish Chandra Yadav'], 'Ministers of State (Independent Charge)')
        self.assertEqual(groups['Anoop Pradhan'], 'Ministers of State')
        cm = d['people'][1]
        self.assertEqual(cm['portfolios'], ['Home', 'Housing'])                          # merged from the ministry page
        self.assertEqual(next(p for p in d['people'] if p['name'] == 'Suresh Kumar Khanna')['position'], 'Minister of Finance')
        self.assertTrue(next(p for p in d['people'] if p['name'] == 'Suresh Kumar Khanna')['photo'])   # page image step
        self.assertIsNone(d['live_error']); self.assertEqual(d['partial_sources'], ['Wikidata'])
        self.assertGreater(len(steps), 4)                                                # progress was reported as it went
        self.assertEqual({s['label'] for s in d['steps'] if s['state'] == 'failed'}, {'Wikidata (contacts and photos)'})

    def test_national_order(self):
        d = O.build('IN', fake_getter())
        pos = [p['position'] for p in d['people']]
        self.assertEqual(pos[:4], ['President of India', 'Vice President of India', 'Prime Minister of India', 'Minister of Home Affairs'])
        self.assertEqual(pos[4:7], ['Minister of Defence', 'Minister of Finance', 'Minister of External Affairs'])
        modi = d['people'][2]
        self.assertEqual(modi['party_code'], 'BJP')
        self.assertIn('Department of Space', modi['portfolios'])

    def test_background_job_reports_progress_and_refreshes(self):
        with tempfile.TemporaryDirectory() as tmp:
            O._jobs.clear()
            calls = []
            first = O.request('state:Uttar_Pradesh', fake_getter(calls), tmp)
            self.assertTrue(first['pending'])
            for _ in range(100):
                time.sleep(0.05)
                d = O.request('state:Uttar_Pradesh', fake_getter(calls), tmp)
                if not d['pending']:
                    break
            self.assertFalse(d['pending']); self.assertGreater(len(d['people']), 5)
            n = len(calls)
            O.request('state:Uttar_Pradesh', fake_getter(calls), tmp)
            time.sleep(0.2)
            self.assertEqual(len(calls), n)                                   # fresh cache: no refetch
            again = O.request('state:Uttar_Pradesh', fake_getter(calls), tmp, force=True)
            self.assertTrue(again['pending']); self.assertTrue(again['people'])   # refresh keeps showing the list
            for _ in range(100):
                time.sleep(0.05)
                if not O.request('state:Uttar_Pradesh', fake_getter(calls), tmp)['pending']:
                    break
            self.assertGreater(len(calls), n)
            O._jobs.clear()

    def test_offline_falls_back_to_the_file(self):
        def down(url):
            raise OSError('offline')
        O._pages.clear()
        d = O.build('IN', down)
        self.assertTrue(d['live_error'])
        self.assertEqual([p['position'] for p in d['people']][:3], ['President of India', 'Vice President of India', 'Prime Minister of India'])


@unittest.skipUnless(F.numpy_ok(), 'numpy not installed')
class Pulse(unittest.TestCase):
    def test_mood_weights_recent_elections_more(self):
        ev = [(100, 'A', 'AE', 100, {'X': 0.10}), (130, 'B', 'AE', 100, {'X': -0.10})]
        m, n = P.mood(ev, 131)
        self.assertEqual(n, 2); self.assertLess(m['X'], 0)
        m, _ = P.mood(ev, 131, exclude='B')
        self.assertAlmostEqual(m['X'], 0.10)

    def test_swing_keeps_shares_valid(self):
        import numpy as np
        M0 = np.array([[0.5, 0.3, 0.2], [0.2, 0.6, 0.2]])
        M = P.apply_swing(M0, ['A', 'B', 'OTH'], {'A': 0.1, 'B': -0.05})
        self.assertTrue(np.allclose(M.sum(1), 1)); self.assertGreater(M[0, 0], 0.5)

    def test_variance_decomposition(self):
        import numpy as np
        rng = np.random.default_rng(0)
        M = rng.dirichlet([3, 3, 1], 60)
        cols = ['A', 'B', 'OTH']
        same, _ = P.mixture({'H1': (M, 1, 0.03), 'H2': (M.copy(), 1, 0.03)}, cols, 0.05, 0.02, n=600)
        for r in same:
            if r.get('variance'):
                self.assertAlmostEqual(sum(r['variance'].values()), 1, places=2)
                self.assertLess(r['variance']['between'], 0.05)
        far = P.apply_swing(M, cols, {'A': 0.15, 'B': -0.15})
        diff, w = P.mixture({'H1': (M, 1, 0.03), 'H2': (far, 1, 0.03)}, cols, 0.05, 0.02, n=600)
        self.assertGreater(diff[0]['variance']['between'], 0.3)
        self.assertTrue(P.significance(diff, 31)['significant'])
        self.assertEqual(w, {'H1': 0.5, 'H2': 0.5})

    def test_coverage_tone_counts_single_party_articles_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'news.sqlite3'
            con = sqlite3.connect(str(db))
            con.execute('CREATE TABLE entries(id TEXT, title TEXT, summary TEXT, published TEXT, retrieved TEXT)')
            now = dt.datetime(2026, 11, 19, tzinfo=dt.timezone.utc)
            rows = []
            for i in range(8):
                rows.append((f'r{i}', 'BJP wins praise in Gujarat as support surges', '', (now - dt.timedelta(days=5)).isoformat(), ''))
                rows.append((f'o{i}', 'BJP faces protest and scandal in Gujarat', '', (now - dt.timedelta(days=90)).isoformat(), ''))
                rows.append((f'b{i}', 'BJP and Congress trade charges in Gujarat', '', (now - dt.timedelta(days=5)).isoformat(), ''))
                rows.append((f'k{i}', 'BJP wins in Kerala', '', (now - dt.timedelta(days=5)).isoformat(), ''))
            con.executemany('INSERT INTO entries VALUES (?,?,?,?,?)', rows); con.commit(); con.close()
            t = P.coverage_tone(db, ['BJP', 'INC', 'OTH'], 'Gujarat', now)
        self.assertEqual(t['BJP']['recent'], 8); self.assertEqual(t['BJP']['before'], 8)
        self.assertGreater(t['BJP']['delta'], 0)
        self.assertNotIn('INC', t)

    def test_run_on_synthetic_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'e.sqlite3'; synthetic_db(db)
            out = P.run(db, now=dt.datetime(2026, 11, 19, tzinfo=dt.timezone.utc), sims=300, with_trees=False)
        self.assertIn('kappa', out['params'])
        self.assertIn(out['backtest']['label'], ('Low', 'Medium', 'High'))
        for st in ('Alpha', 'Beta', 'Gamma'):
            r = out['states'][st]
            self.assertEqual(r['status'], 'ready', r)
            self.assertEqual({h['id'] for h in r['hypotheses']} >= {'H1', 'H3'}, True)
            lead = r['ranges'][0]
            self.assertTrue(lead['lo'] <= lead['median'] <= lead['hi'])
            self.assertAlmostEqual(sum(lead['variance'].values()), 1, places=2)
        self.assertEqual(out['national']['status'], 'ready')

    def test_pulse_runs_only_on_request(self):
        from unittest import mock
        with mock.patch.object(P, 'cached', return_value=None), mock.patch.object(P, 'start') as start, \
                mock.patch.object(Path, 'exists', return_value=True):
            self.assertEqual(P.for_scope('Gujarat')['status'], 'not_run')
            start.assert_not_called()
            P.for_scope('Gujarat', force=True)
            start.assert_called_once()

    def test_hidden_during_silence(self):
        self.assertEqual(P.for_scope('Gujarat', hidden={'projection'})['status'], 'hidden')


class Wiring(unittest.TestCase):
    def test_routes(self):
        s = (ROOT / 'server.py').read_text(encoding='utf-8')
        self.assertIn("'/api/elections/pulse'", s)
        self.assertIn('officials.request(', s)
        self.assertIn("refresh", s)


if __name__ == '__main__':
    unittest.main()
