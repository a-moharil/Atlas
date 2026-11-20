"""v6.5.6: the state-by-state sources from docs/STATE_RESULT_SOURCES_2026.md, each reader tested on a real response
(tests/fixtures/state_counts, see its README), and the third source: numbers reported in Sanjaya's news coverage."""
import json
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

import us_coverage as CV
import us_elections as UE
import us_elections_data as UD
import us_official as SO
from tests.tmpdir import TempDir

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests' / 'fixtures' / 'state_counts'


def b(name):
    return (FIX / name).read_bytes()


def j(name):
    return SO.load_json(b(name))


def races(state, contests):
    return {r['id']: r for r in SO.races_from(contests, state, 2026, 'u')}


class Readers(unittest.TestCase):
    def test_every_state_has_a_researched_kind(self):
        self.assertEqual(set(SO.SOURCES), set(UD.STATES))
        kinds = {k: v['kind'] for k, v in SO.SOURCES.items()}
        self.assertEqual(kinds['DC'], 'norace')
        self.assertEqual({k for k, v in kinds.items() if v == 'blocked'}, {'KY', 'MO', 'NV', 'NH', 'NY', 'OK', 'TN', 'WI'})
        for st, spec in SO.SOURCES.items():
            if spec['kind'] in SO.NOFETCH:
                self.assertTrue(spec.get('why'), st)

    def test_clarity_states(self):
        co = races('CO', SO.contests_from(b('co_summary.json')))
        self.assertTrue({'S-2026-CO-', 'H-2026-CO-1', 'G-2026-CO'} <= set(co))            # "Governor / Lieutenant Governor"
        ia = races('IA', SO.contests_from(b('ia_summary.json')))
        self.assertEqual((ia['S-2026-IA-']['leader'], ia['S-2026-IA-']['leader_party']), ('Josh Turek', 'D'))
        sc = races('SC', SO.contests_from(b('sc_summary.json')))
        self.assertEqual((sc['H-2026-SC-1']['leader'], sc['H-2026-SC-1']['leader_party']), ('Nancy Mace', 'R'))   # "REP Nancy Mace"
        self.assertEqual(SO._clarity_eid('x', 2026, lambda u: b('co_elections.json')), '127407')

    def test_gzipped_listing(self):
        import gzip
        self.assertEqual(SO._clarity_eid('x', 2026, lambda u: gzip.compress(b('co_elections.json'))), '127407')

    def test_enhanced_voting_export_and_api(self):
        ut = races('UT', SO.contests_from(b('ut_export.json')))
        self.assertEqual((ut['S-2026-UT-']['leader'], ut['S-2026-UT-']['leader_party']), ('JOHN CURTIS', 'R'))
        va = races('VA', SO.contests_from(b('va_api.json')))                               # names are {languageId, text} lists
        self.assertEqual((va['G-2026-VA']['leader'], va['G-2026-VA']['leader_party'], va['G-2026-VA']['counted_pct']),
                         ('Abigail D. Spanberger', 'D', 100.0))
        idr = races('ID', SO.contests_from(b('id_api.json')))
        self.assertTrue({'S-2026-ID-', 'H-2026-ID-1', 'G-2026-ID'} <= set(idr))

    def test_virginia_through_read_state(self):
        calls = []

        def getter(u):
            calls.append(u)
            return b('va_api.json')
        res = SO.read_state('VA', 2026, getter)
        self.assertEqual(res['status'], 'read')
        self.assertEqual(calls[0], 'https://enr.elections.virginia.gov/results/public/api/elections/virginia/2026-November-General/data')

    def test_json_formats(self):
        de = races('DE', SO.contests_from(b('de.json'), SO.SOURCES['DE']['columns']))
        self.assertTrue({'S-2026-DE-', 'H-2026-DE-1'} <= set(de))
        ri = races('RI', SO.read_ri(j('ri.json')))
        self.assertEqual((ri['H-2026-RI-1']['leader'], ri['H-2026-RI-1']['counted_pct']), ('Gabriel Amo', 100.0))
        orr = races('OR', SO.read_oregon(j('or_fed.json')))
        self.assertTrue({'S-2026-OR-', 'H-2026-OR-1'} <= set(orr))
        la = races('LA', SO.read_la(j('la_races.json'), j('la_votes.json')))
        self.assertEqual((la['H-2026-LA-1']['leader'], la['H-2026-LA-1']['leader_party']), ('Steve Scalise', 'R'))   # "(REP)"
        nd, official = SO.read_nd(j('nd_contests.json'), j('nd_results.json'))
        self.assertIn('H-2026-ND-1', races('ND', nd)); self.assertFalse(official)
        ct = races('CT', SO.read_ct(j('ct_lookup.json'), j('ct_data.json')))
        self.assertTrue({'G-2026-CT', 'H-2026-CT-1'} <= set(ct))
        vt = races('VT', SO.read_vt([j('vt_f.json')]))
        self.assertEqual((vt['S-2026-VT-']['leader'], vt['S-2026-VT-']['leader_party']), ('BERNIE SANDERS', 'I'))
        ind = races('IN', SO.read_indiana([j('in_1005.json')]))                          # "United States Representative, First District"
        self.assertEqual(ind['H-2026-IN-1']['leader'], 'Frank J. Mrvan')
        oh = races('OH', SO.read_ohio([j('oh_cd01.json')]))
        self.assertIn('H-2026-OH-1', oh)
        pa = races('PA', SO.read_pa(j('pa_house.json')))                                   # JSON inside a JSON string
        self.assertEqual((pa['H-2026-PA-1']['leader'], pa['H-2026-PA-1']['leader_party']), ('BRIAN FITZPATRICK', 'R'))

    def test_pages_and_text_files(self):
        ne = races('NE', SO.read_results_sw(SO.decode(b('ne_cg.html'))))
        self.assertEqual(set(ne), {'H-2026-NE-1', 'H-2026-NE-2', 'H-2026-NE-3'})
        nm = races('NM', SO.read_results_sw(SO.decode(b('nm_fed.html'))))
        self.assertTrue({'S-2026-NM-', 'H-2026-NM-1'} <= set(nm))
        ks = races('KS', SO.read_ks(SO.decode(b('ks_national.html'))))
        self.assertEqual(set(ks), {'S-2026-KS-', 'H-2026-KS-1'})
        il = races('IL', SO.read_html(SO.decode(b('il_fed.html'))))                           # "1ST CONGRESS"
        self.assertEqual(il['H-2026-IL-1']['leader'], 'JONATHAN L. JACKSON')
        hi = races('HI', SO.contests_from(b('hi_summary.txt'), SO.HI_COLS))                  # "(D) HIRONO, Mazie K.", "Dist I"
        self.assertEqual((hi['S-2026-HI-']['leader'], hi['H-2026-HI-1']['leader']), ('Mazie K. HIRONO', 'Ed CASE'))
        sd = races('SD', SO.contests_from(b('sd_swr.csv'), SO.SOURCES['SD']['columns']))
        self.assertEqual((sd['S-2026-SD-']['leader'], sd['S-2026-SD-']['counted_pct']), ('Mike Rounds', 18.2))
        fl = races('FL', SO.contests_from(b('fl.tsv'), SO.SOURCES['FL']['columns']))
        self.assertEqual(fl['S-2026-FL-']['leader'], 'Rick Scott')
        ak = races('AK', SO.contests_from(b('ak.csv')))
        self.assertEqual((ak['H-2026-AK-1']['leader'], ak['H-2026-AK-1']['leader_party']), ('Nick Begich', 'R'))

    def test_multi_file_states_through_read_state(self):
        routes = [('Elections.json', json.dumps([{'ID': '108', 'Name': '11/03/2026 -- November 2026 State Election'}]).encode()),
                  ('Version.json', b('ct_version.json')), ('Lookupdata', b('ct_lookup.json')), ('Electiondata', b('ct_data.json')),
                  ('GetContestSearchList', b('nd_contests.json')), ('GetContestResults', b('nd_results.json')),
                  ('resultsSW.aspx?type=CG', b('ne_cg.html'))]

        def getter(u):
            for k, v in routes:
                if k in u:
                    return v
            raise OSError('HTTP 404 Not Found')
        for st, n in (('CT', 2), ('ND', 1), ('NE', 3)):
            res = SO.read_state(st, 2026, getter)
            self.assertEqual((res['status'], len(res['races'])), ('read', n), st)

    def test_party_marks_in_names(self):
        self.assertEqual(SO.clean_candidate('D-Adam Hamilton'), ('Adam Hamilton', 'D'))
        self.assertEqual(SO.clean_candidate('David A. Perdue (I) (Rep)'), ('David A. Perdue', 'Rep'))
        self.assertEqual(SO.clean_candidate('Ali Al-Hassan', 'DEM'), ('Ali Al-Hassan', 'DEM'))
        self.assertEqual(SO.clean_candidate('Smith, Jr.'), ('Smith, Jr.', ''))

    def test_no_request_for_states_without_a_feed(self):
        for st in ('KY', 'DC', 'MD', 'WY'):
            res = SO.read_state(st, 2026, lambda u: self.fail(f'{st} fetched {u}'))
            self.assertEqual(res['status'], SO.SOURCES[st]['kind']); self.assertTrue(res['error'])


class Fetching(unittest.TestCase):
    def test_retry_once_as_sanjaya_after_403_and_plain_reasons(self):
        import server
        import urllib.error
        seen = []

        class Res:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return b'ok'

        def opener(*a, **k):
            class O:
                def open(self, req, timeout=None):
                    seen.append(req.get_header('User-agent'))
                    if len(seen) == 1:
                        raise urllib.error.HTTPError(req.full_url, 403, 'Forbidden', {}, None)
                    return Res()
            return O()
        with mock.patch.object(server, 'validate_external_url', return_value=None), \
                mock.patch.object(server.urllib.request, 'build_opener', side_effect=opener):
            self.assertEqual(server.fetch_public_record('https://example.gov/x'), b'ok')
        self.assertIn('Mozilla', seen[0]); self.assertTrue(seen[1].startswith('Sanjaya/'))

        def timeout_opener(*a, **k):
            class O:
                def open(self, req, timeout=None):
                    raise urllib.error.URLError('timed out')
            return O()
        with mock.patch.object(server, 'validate_external_url', return_value=None), \
                mock.patch.object(server.urllib.request, 'build_opener', side_effect=timeout_opener):
            with self.assertRaises(OSError) as cm:
                server.fetch_public_record('https://example.gov/x')
        self.assertIn('outside the US', str(cm.exception))


class Coverage(unittest.TestCase):
    RACE = {'id': 'H-2026-MI-7', 'office': 'H', 'cycle': 2026, 'state': 'MI', 'seat': '7', 'special': 0, 'origin': 'wikipedia',
            'called': 0, 'winner_party': None, 'status_text': 'Too close to call',
            'cands': json.dumps([['Curtis Hertel', 'D', None, None, 0], ['Tom Barrett', 'R', None, None, 0]])}

    def news_db(self, tmp, rows):
        db = Path(tmp) / 'news.sqlite3'
        con = sqlite3.connect(db)
        con.execute('CREATE TABLE entries (id TEXT PRIMARY KEY, source_id TEXT, source TEXT, tier TEXT, region TEXT, medium TEXT, '
                    'title TEXT, url TEXT, summary TEXT, author TEXT, published TEXT, retrieved TEXT, video_id TEXT)')
        for i, (title, summary, when, src) in enumerate(rows):
            con.execute('INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (f'e{i}', 's', src, 't', 'r', 'm', title, f'https://news.example/{i}', summary, '', when, when, None))
        con.commit(); con.close()
        return db

    def test_extracts_votes_shares_and_pairs(self):
        cands = [('Curtis Hertel', 'D'), ('Tom Barrett', 'R')]
        found, counted = CV.extract('Hertel had 181,204 votes and Barrett 179,880 votes with 97% of the expected vote counted.', cands)
        self.assertEqual(found, {'Curtis Hertel': (181204.0, None), 'Tom Barrett': (179880.0, None)}); self.assertEqual(counted, 97.0)
        found, _ = CV.extract('Hertel leads Barrett 50.3% to 48.9% in Michigan', cands)
        self.assertEqual(found, {'Curtis Hertel': (None, 50.3), 'Tom Barrett': (None, 48.9)})
        found, _ = CV.extract('Barrett, a former state senator, spoke to 300 supporters', cands)
        self.assertIsNone(CV._usable(found))

    def test_search_prefers_recent_official_numbers_and_never_calls(self):
        rows = [('Michigan 7th district: Hertel leads Barrett 50.1% to 49.0%', 'Early returns.', '2026-11-04', 'Old Paper'),
                ('Hertel, Barrett race in Michigan tightens', 'Hertel has 181,204 votes to Barrett 179,880 votes, according to the '
                 'Secretary of State, with 97% of the expected vote counted.', '2026-11-06', 'Detroit Daily'),
                ('Hertel wins bake-off', 'Hertel 12% sugar', '2026-10-01', 'Too Early')]
        with TempDir() as tmp:
            db = self.news_db(tmp, rows)
            with mock.patch.object(CV, '_vectors', return_value=(None, None)):
                res, method, n = CV.search(2026, [self.RACE], db)
        self.assertEqual((method, n), ('words', 1))
        r = res['H-2026-MI-7']
        self.assertEqual((r['leader'], r['winner_votes'], r['counted_pct'], r['coverage']['publisher'], r['coverage']['cites_official']),
                         ('Curtis Hertel', 181204, 97.0, 'Detroit Daily', True))
        merged = CV.apply([self.RACE], res)[0]
        self.assertEqual((merged['called'], merged['origin'], merged['leader_party']), (0, 'wikipedia+coverage', 'D'))

    def test_embeddings_rank_the_articles(self):
        import numpy as np
        rows = [('Michigan results: Hertel 52% to Barrett 47%', '', '2026-11-05', 'A'),
                ('Hertel and Barrett: 49% vs 50%', 'Hertel 49%, Barrett 50% in Michigan', '2026-11-06', 'B')]
        with TempDir() as tmp:
            db = self.news_db(tmp, rows)
            vecs = {'e0': np.array([1, 0], dtype=np.float32), 'e1': np.array([0, 1], dtype=np.float32)}
            sem = mock.Mock(); sem.embed_texts.return_value = [np.array([1, 0.1], dtype=np.float32)]
            with mock.patch.object(CV, '_vectors', return_value=(vecs, sem)):
                res, method, _ = CV.search(2026, [self.RACE], db)
        self.assertEqual(method, 'embeddings')
        self.assertEqual(res['H-2026-MI-7']['coverage']['publisher'], 'A')             # e1 scores below the floor

    def test_coverage_never_overrides_a_call_or_a_state_count(self):
        cov = {'H-2026-MI-7': {'leader': 'Tom Barrett', 'leader_party': 'R', 'cands': json.dumps([['Tom Barrett', 'R', None, 51.0, 0]]),
                               'coverage': {'publisher': 'X'}, 'source': 'u'}}
        called = {**self.RACE, 'called': 1, 'winner_party': 'D', 'winner': 'Curtis Hertel'}
        out = CV.apply([called], cov)[0]
        self.assertEqual((out['called'], out['origin']), (1, 'wikipedia')); self.assertIn('set aside', out['coverage_note'])
        state = {**self.RACE, 'origin': 'wikipedia+state'}
        self.assertEqual(CV.apply([state], cov)[0]['origin'], 'wikipedia+state')

    def test_runs_only_on_request(self):
        with TempDir() as tmp, mock.patch.object(CV, '_file', return_value=Path(tmp) / 'cov.json'), \
                mock.patch.object(CV, 'search', side_effect=AssertionError('searched without being asked')):
            out = CV.request(2026, 'H', [self.RACE], Path(tmp) / 'none.sqlite3')
        self.assertFalse(out['pending'])

    def test_wiring(self):
        s = (ROOT / 'server.py').read_text(encoding='utf-8')
        self.assertIn("search_coverage=which=='coverage'", s)
        js = (ROOT / 'static' / 'elections_us.js').read_text(encoding='utf-8')
        self.assertIn('data-us-refresh="coverage"', js); self.assertIn('never calls a race', js)


if __name__ == '__main__':
    unittest.main()
