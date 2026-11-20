"""v6.4: who governs (officials) and the next-election forecast.

Officials tests use a recorded-shape Wikidata answer, so they run offline. Forecast tests train the
numpy ensemble on a small synthetic results database; they are skipped where numpy is not installed.
"""
import datetime as dt
import json
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import forecast as F
import officials as O
from tests.tmpdir import TempDir

ROOT = Path(__file__).resolve().parents[1]
HAS_NUMPY = F.numpy_ok()


def b(**kw):
    return {k: {'value': v} for k, v in kw.items()}


SPARQL = {'results': {'bindings': [
    b(pos='wd:P1', posLabel='Chief Minister of Kerala', person='wd:A', personLabel='Current CM', start='2026-05-20T00:00:00Z',
      partyLabel='Indian National Congress', image='http://commons.wikimedia.org/wiki/Special:FilePath/Some%20Face.jpg',
      posSite='https://kerala.gov.in/', site='https://my-personal-blog.example.com/', email='mailto:cm@kerala.gov.in'),
    b(pos='wd:P1', posLabel='Chief Minister of Kerala', person='wd:B', personLabel='Former CM never closed', start='2016-05-25T00:00:00Z'),
    b(pos='wd:P2', posLabel='Governor of Kerala', person='wd:C', personLabel='The Governor', start='2025-01-02T00:00:00Z', partyLabel='Bharatiya Janata Party'),
    b(pos='wd:P3', posLabel='Member of the Kerala Legislative Assembly', person='wd:D', personLabel='An MLA'),
    b(pos='wd:P4', posLabel='Minister of Finance (Kerala)', person='wd:E', personLabel='Q123456'),
    b(pos='wd:P5', posLabel='Minister of Health (Kerala)', person='wd:F', personLabel='Health Minister', start='2026-05-20T00:00:00Z'),
]}}


class Officials(unittest.TestCase):
    def test_scope_parsing(self):
        self.assertEqual(O.parse_scope('IN')[1], 'IN')
        self.assertEqual(O.parse_scope('state:Jammu_&_Kashmir')[1], 'state:Jammu_&_Kashmir')
        for bad in ('state:../../x', 'county:X', 'state:"; DROP', 'city:'):
            with self.assertRaises(ValueError):
                O.parse_scope(bad)

    def test_query_finds_place_by_office_and_escapes(self):
        q = O.query_for('state', 'Jammu_&_Kashmir')
        self.assertIn('"Chief Minister of Jammu and Kashmir"@en', q)
        self.assertIn('pq:P582', q)                       # only open-ended terms
        self.assertIn('"Mayor of A \\"B\\""@en', O.query_for('city', 'A "B"'))

    def test_parse_keeps_current_holders_and_official_channels(self):
        people = O.parse('state', SPARQL)
        names = {p['name'] for p in people}
        self.assertIn('Current CM', names)
        self.assertNotIn('Former CM never closed', names)   # stale statement loses to the newer one
        self.assertNotIn('An MLA', names)                    # legislators are not the government
        self.assertFalse(any(n.startswith('Q') for n in names))
        cm = next(p for p in people if p['name'] == 'Current CM')
        urls = [c['url'] for c in cm['contacts']]
        self.assertIn('https://kerala.gov.in/', urls)
        self.assertIn('mailto:cm@kerala.gov.in', urls)
        self.assertFalse(any('example.com' in u for u in urls))   # personal sites are dropped
        self.assertTrue(cm['photo']['src'].startswith('https://commons.wikimedia.org/wiki/Special:FilePath/Some_Face.jpg'))
        self.assertTrue(cm['photo']['credit'].startswith('https://commons.wikimedia.org/wiki/File:'))

    def test_order_and_apolitical_offices(self):
        people, _ = O.apply_overrides('state', 'state:Kerala', O.parse('state', SPARQL), {'scopes': {}})
        self.assertEqual([p['position'] for p in people][:2], ['Governor of Kerala', 'Chief Minister of Kerala'])
        self.assertIsNone(people[0]['party'])                # governors are shown without a party
        nat, _ = O.apply_overrides('national', 'IN', [
            {'name': 'x', 'position': 'Minister of Railways', 'contacts': []},
            {'name': 'y', 'position': 'Prime Minister of India', 'contacts': []},
            {'name': 'z', 'position': 'President of India', 'contacts': []},
            {'name': 'w', 'position': 'Minister of Home Affairs', 'contacts': []}], {'scopes': {}})
        self.assertEqual([p['name'] for p in nat], ['z', 'y', 'w', 'x'])

    def test_overrides_fallback_replace_and_hide(self):
        live = O.parse('state', SPARQL)
        o = {'scopes': {'state:Kerala': {
            'hide': ['Health Minister'],
            'people': [{'name': 'Fallback CM', 'position': 'Chief Minister of Kerala', 'fallback': True},
                       {'name': 'Fixed Governor', 'position': 'Governor of Kerala',
                        'contacts': [{'label': 'Bad', 'url': 'javascript:alert(1)'}, {'label': 'Raj Bhavan', 'url': 'https://rajbhavan.kerala.gov.in/'}]}]}}}
        people, _ = O.apply_overrides('state', 'state:Kerala', live, o)
        names = [p['name'] for p in people]
        self.assertIn('Current CM', names); self.assertNotIn('Fallback CM', names)
        self.assertIn('Fixed Governor', names); self.assertNotIn('The Governor', names)
        self.assertNotIn('Health Minister', names)
        gov = next(p for p in people if p['name'] == 'Fixed Governor')
        self.assertEqual([c['url'] for c in gov['contacts']], ['https://rajbhavan.kerala.gov.in/'])

    def test_offline_still_answers_from_the_shipped_file(self):
        def down(url):
            raise OSError('offline')
        O._pages.clear()
        d = O.build('IN', down)
        self.assertTrue(d['live_error'])
        self.assertEqual([p['position'] for p in d['people']][:3], ['President of India', 'Vice President of India', 'Prime Minister of India'])
        m = O.build('city:Mumbai', down)
        self.assertEqual(m['people'][0]['position'], 'Mayor of Mumbai')
        h = O.build('city:Hyderabad', down)
        self.assertIsNone(h['live_error'])                   # no live lookup where the file says there is no council
        self.assertTrue(h['note'])

    def test_shipped_file_is_clean(self):
        data = json.loads((ROOT / 'election_officials.json').read_text(encoding='utf-8'))
        text = json.dumps(data)
        self.assertNotIn('upload.wikimedia.org', text)       # photos are never stored
        self.assertNotIn('tel:', text)
        for scope, o in data['scopes'].items():
            O.parse_scope(scope)
            for p in o.get('people', []):
                for c in p.get('contacts', []):
                    self.assertTrue(c['url'].startswith('https://'), c)
        for city in ('Mumbai', 'Pune', 'Pimpri_Chinchwad', 'Nagpur', 'Delhi', 'Chennai', 'Hyderabad', 'Bengaluru'):
            self.assertIn(f'city:{city}', data['scopes'])


def synthetic_db(path, seed=3):
    """Three states, five assembly rounds, two Lok Sabha rounds; two parties swinging plus a minor one."""
    rng = random.Random(seed)
    con = sqlite3.connect(str(path))
    con.execute('CREATE TABLE elections(id TEXT PRIMARY KEY, kind TEXT, state TEXT, year INT, month INT, seats INT)')
    con.execute('CREATE TABLE seats(election TEXT, state TEXT, no INT, name TEXT, type TEXT, winner TEXT, party TEXT, votes INT, '
                'runner TEXT, runner_party TEXT, runner_votes INT, valid INT, electors INT, margin INT, margin_pct REAL, '
                'turnout REAL, n_cand INT, party_votes TEXT)')

    def poll(eid, kind, st, year, month, n, lean):
        con.execute('insert into elections values (?,?,?,?,?,?)', (eid, kind, st, year, month, n))
        for no in range(1, n + 1):
            base = 0.42 + 0.1 * ((no % 7) / 7 - 0.5) + lean + rng.gauss(0, 0.04)
            a = max(0.05, min(0.85, base)); c = rng.uniform(0.03, 0.12); bb = max(0.02, 1 - a - c - 0.05)
            pv = {'AAA': int(a * 1e5), 'BBB': int(bb * 1e5), 'CCC': int(c * 1e5), 'IND': 5000}
            w = max(pv, key=pv.get)
            con.execute('insert into seats values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (eid, st, no, f'Seat {st} {no}', 'SC' if no % 9 == 0 else 'GEN', 'x', w, pv[w], 'y', 'z', 0, 100000, 150000, 1, 1.0, 66.0, 6, json.dumps(pv)))
    for st, start in (('Alpha', 2008), ('Beta', 2009), ('Gamma', 2010)):
        for k, year in enumerate(range(start, 2027, 5)):
            poll(f'AE-{st}-{year}', 'AE', st, year, 3, 40, 0.06 * (-1) ** k)
    for year in (2014, 2019, 2024):
        con.execute('insert into elections values (?,?,?,?,?,?)', (f'GE-{year}', 'GE', None, year, 5, 0))
        for st in ('Alpha', 'Beta', 'Gamma'):
            for no in range(1, 4):
                pv = {'AAA': 50000 + rng.randint(-8000, 8000), 'BBB': 40000, 'CCC': 6000}
                con.execute('insert into seats values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (f'GE-{year}', st, no, f'PC {no}', 'GEN', 'x', 'AAA', 1, 'y', 'z', 0, 1, 1, 1, 1.0, 60.0, 5, json.dumps(pv)))
    con.commit(); con.close()


@unittest.skipUnless(HAS_NUMPY, 'numpy not installed (it comes with the language-model pack)')
class Trees(unittest.TestCase):
    def test_tree_learns_a_step(self):
        import numpy as np
        rng = np.random.default_rng(0)
        X = rng.uniform(0, 1, (2000, 3)); y = (X[:, 1] > 0.5).astype(float) * 0.6 + 0.2
        m = F.Ensemble(bag={'trees': 8, 'depth': 3, 'min_leaf': 20, 'feat_frac': 1.0}, boost={'rounds': 20, 'depth': 2, 'min_leaf': 20, 'lr': 0.2, 'subsample': 0.8}).fit(X, y)
        p = m.predict(np.array([[0.5, 0.1, 0.5], [0.5, 0.9, 0.5]]))
        self.assertLess(p[0], 0.4); self.assertGreater(p[1], 0.6)

    def test_trust_tiers(self):
        self.assertEqual(F.trust_label(0.52, 0.72), 'Low')
        self.assertEqual(F.trust_label(0.7, 0.75), 'Medium')
        self.assertEqual(F.trust_label(0.85, 0.75), 'High')
        self.assertEqual(F.trust_label(0.85, 0.4), 'Low')

    def test_run_on_synthetic_results(self):
        with TempDir() as d:
            db = Path(d) / 'e.sqlite3'; synthetic_db(db)
            out = F.run(db, now=dt.datetime(2026, 11, 19, tzinfo=dt.timezone.utc),
                        bag={'trees': 6, 'depth': 4, 'min_leaf': 20, 'feat_frac': 0.7},
                        boost={'rounds': 15, 'depth': 2, 'min_leaf': 20, 'lr': 0.1, 'subsample': 0.8}, sims=120)
        self.assertGreater(out['backtest']['elections'], 0)
        self.assertIn(out['backtest']['label'], ('Low', 'Medium', 'High'))
        self.assertIsNotNone(out['backtest']['baseline_accuracy'])
        alpha = out['states']['Alpha']              # last poll 2023-03, next expected 2028-03
        self.assertNotIn('ranges', alpha)
        beta = out['states']['Beta']                # last poll 2024-03 -> 2029: far away
        self.assertGreater(beta['months_away'], 6)
        gamma = out['states']['Gamma']              # last 2025-03 -> 2030
        self.assertGreater(gamma['months_away'], 6)


class Gating(unittest.TestCase):
    """Forecasts are gated by the calendar, and the model only runs when the reader asks for it."""
    def cache(self):
        return {'model': F.MODEL_VERSION, 'generated': 'x', 'noise': {}, 'backtest': {'label': 'Low'},
                'states': {'Uttar_Pradesh': {'ranges': [{'code': 'BJP', 'lo': 1, 'median': 2, 'hi': 3}], 'trust': {'label': 'Low'}}}}

    def run_for(self, expected, now, hidden=(), cache=True, force=False):
        y, m = (int(x) for x in expected.split('-'))
        sched = {'last': 'AE-Uttar_Pradesh-2022', 'expected': expected, 'months_away': F._mkey(y, m) - F._mkey(now.year, now.month),
                 'seats_total': 403, 'majority': 202}
        with mock.patch.object(F, 'numpy_ok', return_value=True), mock.patch.object(F, 'schedule', return_value=sched), \
                mock.patch.object(F, 'cached', return_value=self.cache() if cache else None), \
                mock.patch.object(F, 'start') as start, mock.patch.object(Path, 'exists', return_value=True):
            d = F.for_state('Uttar_Pradesh', now=now, hidden=hidden, force=force)
            return d, start

    def test_close_elections_show_saved_ranges_with_a_trust_label(self):
        d, start = self.run_for('2027-03', dt.datetime(2026, 11, 19))
        self.assertEqual(d['status'], 'ready'); self.assertEqual(d['trust']['label'], 'Low')
        start.assert_not_called()

    def test_model_runs_only_on_request(self):
        d, start = self.run_for('2027-03', dt.datetime(2026, 11, 19), cache=False)
        self.assertEqual(d['status'], 'not_run'); start.assert_not_called()
        d, start = self.run_for('2027-03', dt.datetime(2026, 11, 19), cache=False, force=True)
        self.assertEqual(d['status'], 'computing'); start.assert_called_once()

    def test_far_elections_wait_without_any_model(self):
        d, start = self.run_for('2027-12', dt.datetime(2026, 11, 19), cache=False)
        self.assertEqual(d['status'], 'waiting'); self.assertNotIn('ranges', d)
        self.assertIn('Wait for more data', d['message']); start.assert_not_called()

    def test_silence_period_hides_projections(self):
        d, _ = self.run_for('2027-03', dt.datetime(2027, 2, 20), hidden={'projection'})
        self.assertEqual(d['status'], 'hidden'); self.assertNotIn('ranges', d)

    def test_national(self):
        self.assertEqual(F.national(dt.datetime(2026, 11, 19))['status'], 'waiting')


class Wiring(unittest.TestCase):
    def test_routes_and_panels(self):
        server = (ROOT / 'server.py').read_text(encoding='utf-8')
        self.assertIn("'/api/elections/officials'", server)
        self.assertIn("'/api/elections/forecast'", server)
        self.assertIn('hidden_kinds', server)
        js = (ROOT / 'static' / 'elections.js').read_text(encoding='utf-8')
        for needle in ('In office now', 'Next election', 'Model, not a poll', 'Photo: Wikimedia', 'loading="lazy"', 'data-el-refresh', 'Under which hypothesis'):
            self.assertIn(needle, js)

    def test_coverage_embeddings_are_not_used_yet(self):
        self.assertNotIn('embed', ' '.join(F.FEATURES))


if __name__ == '__main__':
    unittest.main()
