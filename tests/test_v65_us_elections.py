"""v6.5: US elections (House, Senate, governors, president), the 2026 Wikipedia reader, US office-holders,
and models that run only on request. Runs offline on small synthetic data and HTML fixtures."""
import csv
import io
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import us_elections as UE
import us_elections_data as UD
import us_live as L
import us_officials as UO

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests' / 'fixtures'
HDR = ['id', 'race_id', 'state_abbrev', 'state', 'office_id', 'office_name', 'office_seat_name', 'cycle', 'stage', 'special', 'party',
       'politician_id', 'candidate_id', 'candidate_name', 'ballot_party', 'ranked_choice_round', 'votes', 'percent', 'unopposed', 'winner',
       'alt_result_text', 'source']


def rows_csv(rows):
    f = io.StringIO()
    w = csv.DictWriter(f, HDR)
    w.writeheader()
    for i, r in enumerate(rows):
        base = {k: '' for k in HDR}
        base.update({'id': str(i), 'special': 'false', 'stage': 'general'})
        base.update(r)
        w.writerow(base)
    return f.getvalue()


def race(st, seat, cycle, cands, office='U.S. House', race_id=None, special='false'):
    out = []
    for j, (name, party, votes, win) in enumerate(cands):
        out.append({'race_id': race_id or f'{st}{seat}{cycle}', 'state_abbrev': st, 'state': UD.STATES.get(st, st), 'office_seat_name': seat,
                    'cycle': str(cycle), 'candidate_id': f'{name}{cycle}', 'candidate_name': name, 'ballot_party': party,
                    'votes': str(votes), 'winner': 'true' if win else 'false', 'special': special, 'office_name': office})
    return out


class Reading(unittest.TestCase):
    def build(self, files):
        d = tempfile.mkdtemp()
        for n, text in files.items():
            Path(d, n).write_text(text, encoding='utf-8')
        return Path(d)

    def test_fusion_votes_runoffs_and_split_electoral_votes(self):
        house = (race('NY', 'District 1', 2024, [('Ann Fusion', 'DEM', 100, True), ('Ann Fusion', 'WFP', 20, True), ('Bob R', 'REP', 110, False)]) +
                 race('GA', 'District 2', 2024, [('C', 'DEM', 50, False), ('D', 'REP', 49, False)]) +
                 [dict(r, stage='runoff') for r in race('GA', 'District 2', 2024, [('C', 'DEM', 40, False), ('D', 'REP', 60, True)])] +
                 race('OK', 'District 3', 2024, [('Solo', 'REP', 0, True)]))
        house[-1]['unopposed'] = 'true'; house[-1]['votes'] = ''
        pres = (race('ME', '', 2024, [('Dee', 'DEM', 60, True), ('Arr', 'REP', 40, False)], office='President') +
                race('M2', '', 2024, [('Dee', 'DEM', 45, False), ('Arr', 'REP', 55, True)], office='President'))
        raw = self.build({'house.csv': rows_csv(house), 'senate.csv': rows_csv([]), 'governor.csv': rows_csv([]),
                          'president.csv': rows_csv(pres), 'races.csv': 'id,type,state_abbrev,incumbent_party,date\n'})
        races = {r['id']: r for r in UD.read_races(raw)}
        ny = races['H-2024-NY-1']
        self.assertEqual((ny['winner'], ny['winner_party'], ny['winner_votes']), ('Ann Fusion', 'D', 120))   # fusion lines added up
        self.assertEqual(races['H-2024-GA-2']['stage'], 'runoff')
        self.assertEqual(races['H-2024-GA-2']['winner'], 'D')
        self.assertTrue(races['H-2024-OK-3']['unopposed'])
        self.assertEqual(races['P-2024-ME-2']['winner_party'], 'R')                              # Maine's 2nd district vote

    def test_apportionment_eras(self):
        self.assertEqual(UD.era_of(2024), 2020); self.assertEqual(UD.era_of(2022), 2020); self.assertEqual(UD.era_of(2020), 2010)
        ap = {2020: {'CA': 52, 'WY': 1}}
        self.assertEqual(UD.electoral_votes(ap, 2024), {'CA': 54, 'WY': 3, 'DC': 3})


class Live(unittest.TestCase):
    def test_house_page(self):
        rs = {r['id']: r for r in L.parse_page('H', 2026, (FIX / 'wp_us_house_2026.html').read_text(encoding='utf-8'))}
        self.assertEqual(rs['H-2026-AL-1']['winner'], 'Jordan Vale'); self.assertTrue(rs['H-2026-AL-1']['called'])
        self.assertEqual(rs['H-2026-AK-1']['winner'], 'Nick Archer III')                      # leading, but
        self.assertFalse(rs['H-2026-AK-1']['called'])                                         # ranked-choice count pending
        self.assertEqual((rs['H-2026-CA-4']['winner_party'], rs['H-2026-CA-4']['called']), ('D', 1))   # same-party race
        self.assertIn('H-2026-TX-18-special', rs)
        self.assertNotIn('H-2026--', ''.join(rs))

    def test_senate_classes_and_specials(self):
        rs = L.parse_page('S', 2026, (FIX / 'wp_us_senate_2026.html').read_text(encoding='utf-8'))
        hist = [{'state': 'FL', 'seat': 'I', 'cycle': 2024}, {'state': 'FL', 'seat': 'III', 'cycle': 2022}]
        L.assign_senate_classes(rs, hist)
        ids = {r['id'] for r in rs}
        self.assertTrue({'S-2026-ME-II', 'S-2026-AK-II', 'S-2026-OH-III-special', 'S-2026-FL-III-special'} <= ids)

    def test_places(self):
        self.assertEqual(L.place('West Virginia 2'), ('WV', '2'))
        self.assertEqual(L.place('Virginia 2'), ('VA', '2'))
        self.assertEqual(L.place('Wyoming at-large'), ('WY', '1'))


class AssociatedPress(unittest.TestCase):
    def payload(self):
        return json.loads((FIX / 'ap_2026_sample.json').read_text(encoding='utf-8'))

    def test_parse_calls_leads_and_runoffs(self):
        import us_ap
        rs = {r['id']: r for r in us_ap.parse(self.payload(), 2026)}
        al = rs['H-2026-AL-1']
        self.assertEqual((al['winner'], al['winner_party'], al['called']), ('Jordan Vale', 'R', 1))
        ak = rs['H-2026-AK-1']                                   # at-large is seat 1; AP has not called it
        self.assertEqual((ak['called'], ak['winner'], ak['leader_party'], ak['counted_pct']), (0, None, 'D', 82))
        ga = next(r for r in rs.values() if r['state'] == 'GA')
        self.assertFalse(ga['called']); self.assertIn('runoff', ga['status_text'])
        self.assertTrue(any(r['special'] and r['state'] == 'OH' for r in rs.values()))
        self.assertNotIn('apiKey', json.dumps(list(rs.values())))

    def test_ap_wins_over_wikipedia_and_leads_are_not_calls(self):
        import us_ap
        payload = json.dumps(self.payload()).encode()
        wiki = {'races': L.parse_page('H', 2026, (FIX / 'wp_us_house_2026.html').read_text(encoding='utf-8')),
                'fetched': 1, 'pending': False, 'step': '', 'error': None, 'page': 'p'}
        us_ap._cache.clear()
        with mock.patch.object(UE, 'live_races', return_value=wiki), mock.patch.object(UE, '_rows', return_value=[]), \
                mock.patch.object(UE, 'house', wraps=UE.house):
            r = UE.result('H', 2026, getter=lambda url: payload, ap_key='KEY')
        seats = {f"{s['state']}-{s['seat']}": s for s in r['seats']}
        self.assertEqual(seats['CA-22']['origin'], 'ap')                 # Wikipedia said called; AP has not called it
        self.assertFalse(seats['CA-22']['called'])
        self.assertEqual(seats['CA-22']['leader_party'], 'R')
        self.assertEqual(seats['CA-4']['origin'], 'wikipedia')           # AP did not return it: Wikipedia fills in
        self.assertEqual(r['live']['ap']['races'], 3)
        self.assertEqual(r['lean'].get('R'), 1); self.assertEqual(r['lean'].get('D'), 1)
        self.assertEqual(sum(p['seats'] for p in r['parties']), 435)

    def test_no_key_no_request(self):
        import us_ap
        called = []
        out = us_ap.request(2026, '', lambda u: called.append(u))
        self.assertEqual((out['races'], called), ([], []))

    def test_settings_route_keeps_the_key_server_side(self):
        s = (ROOT / 'server.py').read_text(encoding='utf-8')
        self.assertIn("'/api/us/settings'", s)
        self.assertIn("{'ap_key':bool(key)}", s)


class Officials(unittest.TestCase):
    def getter(self):
        leg = [{'id': {'bioguide': 'X000001', 'wikipedia': 'Sen One'}, 'name': {'official_full': 'Sen One'},
                'terms': [{'type': 'sen', 'start': '2021-01-03', 'end': '2027-01-03', 'state': 'CA', 'party': 'Democrat', 'state_rank': 'senior',
                           'url': 'https://one.senate.gov', 'phone': '202-224-0001', 'contact_form': 'https://one.senate.gov/contact'}]},
               {'id': {'bioguide': 'X000002'}, 'name': {'first': 'Rep', 'last': 'Two'},
                'terms': [{'type': 'rep', 'start': '2023-01-03', 'end': '2025-01-03', 'state': 'CA', 'district': 7, 'party': 'Republican'},
                          {'type': 'rep', 'start': '2025-01-03', 'end': '2027-01-03', 'state': 'CA', 'district': 7, 'party': 'Republican', 'phone': '202-225-0002'}]},
               {'id': {'bioguide': 'X000003'}, 'name': {'official_full': 'Not Mine'}, 'terms': [{'type': 'rep', 'start': '2025-01-03', 'end': '2027-01-03', 'state': 'TX', 'district': 1, 'party': 'Republican'}]}]
        ex = [{'name': {'first': 'Pres', 'last': 'Ident'}, 'terms': [{'type': 'prez', 'start': '2017-01-20', 'end': '2021-01-20', 'party': 'Republican'},
                                                                    {'type': 'prez', 'start': '2025-01-20', 'end': '2099-01-20', 'party': 'Republican'}]},
              {'name': {'official_full': 'Vee Pea'}, 'terms': [{'type': 'viceprez', 'start': '2025-01-20', 'end': '2099-01-20', 'party': 'Republican'}]}]
        pages = {UO.CABINET: 'wp_us_cabinet.html', UO.GOVERNORS: 'wp_us_governors.html'}

        def get(url):
            if url == UO.LEG:
                return json.dumps(leg).encode()
            if url == UO.EXEC:
                return json.dumps(ex).encode()
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
            if q.get('action') == 'parse':
                return json.dumps({'parse': {'text': (FIX / pages[q['page']]).read_text(encoding='utf-8')}}).encode()
            return json.dumps({'query': {'pages': []}}).encode()
        return get

    def test_national(self):
        import officials as O
        O._pages.clear()
        with tempfile.TemporaryDirectory() as d:
            out = UO.build('us', self.getter(), d)
        names = [(p['group'], p['name'], p['position']) for p in out['people']]
        self.assertEqual(names[0], ('Head of state and government', 'Pres Ident', 'President of the United States'))
        self.assertEqual(out['people'][0]['since'], '2025-01-20')                 # a non-consecutive term starts again
        self.assertEqual(names[1][0], 'Vice President')
        cab = [n for n in names if n[0] == 'Cabinet']
        self.assertEqual(cab[0][1:], ('Avery Stone', 'Secretary of State'))      # the vice president row is not repeated
        self.assertIn(('Cabinet-level officials', 'Dana Hill', 'White House Chief of Staff'), names)

    def test_state(self):
        import officials as O
        O._pages.clear()
        with tempfile.TemporaryDirectory() as d:
            out = UO.build('us-state:CA', self.getter(), d)
        names = [(p['group'], p['name']) for p in out['people']]
        self.assertEqual(names, [('Governor', 'Frankie Lane'), ('U.S. Senators', 'Sen One'), ('U.S. Representatives', 'Rep Two')])
        two = out['people'][2]
        self.assertEqual(two['since'], '2023-01-03')
        self.assertEqual([c['url'] for c in two['contacts']], ['tel:+1-202-225-0002'])
        self.assertTrue(out['people'][1]['photo']['src'].endswith('/X000001.jpg'))
        with self.assertRaises(ValueError):
            UO.parse_scope('us-state:ZZ')


@unittest.skipUnless(UD.status()['ready'], 'US results pack not built, or built by an older version (rebuild it from the Elections page)')
class RealPack(unittest.TestCase):
    def test_known_totals(self):
        h = UE.result('H', 2024)
        self.assertEqual({p['code']: p['seats'] for p in h['parties']}, {'D': 215, 'R': 220})
        s = UE.result('S', 2024)
        self.assertEqual({p['code']: p['seats'] for p in s['parties']}, {'D': 45, 'I': 2, 'R': 53})
        g = UE.result('G', 2024)
        self.assertEqual({p['code']: p['seats'] for p in g['parties']}, {'D': 23, 'R': 27})
        self.assertEqual({p['code']: p['seats'] for p in UE.result('S', 2016)['parties']}, {'D': 46, 'I': 2, 'R': 52})   # King counted as independent
        self.assertEqual(s['change'], {'R': 4, 'D': -4})                                            # against the Senate after 2022
        self.assertNotEqual(UE.result('S', 2018)['map'], UE.result('S', 2024)['map'])                # each year draws its own races
        for y, want in ((2024, {'D': 226, 'R': 312}), (2016, {'D': 232, 'R': 306}), (2004, {'D': 252, 'R': 286}), (2000, {'D': 267, 'R': 271})):
            p = UE.result('P', y)
            self.assertEqual({x['code']: x['seats'] for x in p['parties']}, want, y)


class Wiring(unittest.TestCase):
    def test_routes_and_page(self):
        s = (ROOT / 'server.py').read_text(encoding='utf-8')
        for route in ("'/api/us/catalog'", "'/api/us/result'", "'/api/us/officials'", "'/api/us/download'", "'/api/us/geo'"):
            self.assertIn(route, s)
        html = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('/elections_us.js', html)
        js = (ROOT / 'static' / 'elections.js').read_text(encoding='utf-8')
        self.assertIn('ATLASElectionsUS.mount', js)
        self.assertIn('elections_data/', (ROOT / '.gitignore').read_text(encoding='utf-8').replace('election_data/', 'elections_data/'))

    def test_download_card_is_clickable_and_reports_progress(self):
        js = (ROOT / 'static' / 'elections_us.js').read_text(encoding='utf-8')
        draw = js[js.index('  function draw() {'):js.index('  const pctDone')]
        self.assertLess(draw.index('wire();'), draw.index('packCard()'))    # the handler exists before the card is shown
        self.assertIn('Starting the download', js)
        self.assertIn('role="progressbar"', js)
        self.assertEqual(UD.STEPS, len(UD.SOURCES) + 2)

    def test_download_steps_advance(self):
        seen = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(UD, 'read_races', return_value=[]), \
                mock.patch.object(UD, 'write_db'), mock.patch.object(UD, 'build_geo', return_value={}), \
                mock.patch.object(UD, 'OUT', Path(d)), mock.patch.object(UD, 'DB', Path(d) / 'x.sqlite3'):
            Path(d, 'us_elections.tmp.sqlite3').write_text('')
            def fetch(url):
                seen.append(UD._job['done'])
                return b'a,b\n'
            UD.build(fetch, raw_dir=d)
        self.assertEqual(seen, list(range(len(UD.SOURCES))))
        self.assertEqual(UD._job['done'], UD.STEPS)

    def test_one_meaning_per_colour(self):
        js = (ROOT / 'static' / 'elections_us.js').read_text(encoding='utf-8')
        self.assertIn('data-us-mode', js)                      # this year's races / whole chamber
        self.assertIn('const SLATE', js)                       # no race this year: neutral, not a faded party colour
        self.assertNotIn('opacity=".38"', js)                  # seats not up are hollow, not faded
        self.assertIn('elected earlier, not up', js)

    def test_no_model_runs_without_a_request(self):
        js = (ROOT / 'static' / 'elections.js').read_text(encoding='utf-8')
        self.assertIn('Run forecast', js); self.assertIn('Run pulse', js)


if __name__ == '__main__':
    unittest.main()
