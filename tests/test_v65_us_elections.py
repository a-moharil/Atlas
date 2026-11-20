"""v6.5: US elections (House, Senate, governors, president), the 2026 Wikipedia reader, US office-holders,
and models that run only on request. Runs offline on small synthetic data and HTML fixtures."""
import csv
import io
import json
import tempfile
import time
import unittest
import zipfile
import urllib.parse
from pathlib import Path
from unittest import mock

import us_elections as UE
import us_elections_data as UD
import us_live as L
import us_officials as UO
import us_official as SO

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


class StateCounts(unittest.TestCase):
    """Each state's own count, read from its results site in whatever format it publishes."""

    def test_contest_titles(self):
        c = SO.classify
        self.assertEqual(c('US HOUSE OF REPRESENTATIVES DISTRICT 10', 'NC'), ('H', '10', False))
        self.assertEqual(c('Congressional District 6 - U.S. Representative', 'WA'), ('H', '6', False))
        self.assertEqual(c('U. S. REPRESENTATIVE DISTRICT 1', 'TX'), ('H', '1', False))
        self.assertEqual(c('United States Representative District 12 - Statewide Results', 'CA'), ('H', '12', False))
        self.assertEqual(c('U.S. Representative', 'WY'), ('H', '1', False))          # at-large state
        self.assertEqual(c('U.S. Senator (Unexpired Term)', 'OH'), ('S', '', True))
        self.assertEqual(c('Governor & Lt Governor', 'MN'), ('G', '', False))
        for other in ('Lieutenant Governor', 'State Senator District 10', 'State Representative District 10A', 'U.S. Senator - Republican Primary'):
            self.assertIsNone(c(other, 'MN'), other)
        self.assertEqual([SO.party_code(x) for x in ('(Prefers Democratic Party)', 'DFL', 'REP', 'Rep', 'NPA', 'LIB', '')], list('DRDRIOO'[i] for i in (0, 0, 1, 1, 4, 5, 6)))

    def test_clarity_summary(self):
        payload = [{'K': 1, 'C': 'U.S. Senator', 'CH': ['Ann Lee', 'Bo Park', 'Write-In'], 'P': ['DEM', 'REP', ''], 'V': [600, 400, 3], 'PR': 90, 'TP': 100},
                   {'K': 2, 'C': 'County Clerk', 'CH': ['X'], 'P': [''], 'V': [9]}]
        rs = SO.races_from(SO.contests_from(json.dumps(payload).encode()), 'KY', 2026, 'u')
        self.assertEqual(len(rs), 1)
        r = rs[0]
        self.assertEqual((r['office'], r['leader'], r['leader_party'], r['total'], r['margin_pct'], r['counted_pct'], r['called']),
                         ('S', 'Ann Lee', 'D', 1000, 20.0, 90.0, 0))

    def test_california_api(self):
        blob = json.dumps({'raceTitle': 'United States Representative District 22 - Statewide Results', 'Reporting': '98.0% (980 of 1,000) precincts reporting',
                           'candidates': [{'Name': 'Riley Moss', 'Party': 'Dem', 'Votes': '51,000', 'Percent': '51.0', 'incumbent': False},
                                          {'Name': 'Sam Cole', 'Party': 'Rep', 'Votes': '49,000', 'Percent': '49.0', 'incumbent': True}]}).encode()
        r = SO.races_from(SO.contests_from(blob), 'CA', 2026, 'u')[0]
        self.assertEqual((r['id'], r['leader_party'], r['total'], r['counted_pct'], r['counted_basis']), ('H-2026-CA-22', 'D', 100000, 98.0, 'precincts'))

    def test_nested_json_export(self):
        blob = json.dumps({'election': {'ballotItems': [{'ballotItemName': 'Governor', 'candidates': [
            {'candidateName': 'Pat Ruiz', 'party': {'abbreviation': 'REP'}, 'voteCount': 700}, {'candidateName': 'Lee Ho', 'party': {'abbreviation': 'DEM'}, 'voteCount': 650}]}]}}).encode()
        r = SO.races_from(SO.contests_from(blob), 'AZ', 2026, 'u')[0]
        self.assertEqual((r['id'], r['leader'], r['leader_party'], r['margin_pct']), ('G-2026-AZ', 'Pat Ruiz', 'R', 3.7))

    def test_washington_csv(self):
        text = ('"Race","Candidate","Party","Votes","PercentageOfTotalVotes","JurisdictionName"\n'
                '"Congressional District 3 - U.S. Representative","Ann Ray","(Prefers Democratic Party)",1200,52,"Federal"\n'
                '"Congressional District 3 - U.S. Representative","Bob Fox","(Prefers Republican Party)",1100,48,"Federal"\n'
                '"Initiative Measure No. 1","Yes","",5,50,"State"\n')
        r = SO.races_from(SO.contests_from(text.encode()), 'WA', 2026, 'u')[0]
        self.assertEqual((r['id'], r['leader_party'], r['total']), ('H-2026-WA-3', 'D', 2300))

    def test_minnesota_county_rows_add_up(self):
        text = ('MN;01;;0331;Governor & Lt Governor;;0301;A Smith and B Jones;;;R;50;51;600;60.0;1000\n'
                'MN;01;;0331;Governor & Lt Governor;;0401;C Diaz and D Kim;;;DFL;50;51;400;40.0;1000\n'
                'MN;02;;0331;Governor & Lt Governor;;0301;A Smith and B Jones;;;R;49;49;300;30.0;1000\n'
                'MN;02;;0331;Governor & Lt Governor;;0401;C Diaz and D Kim;;;DFL;49;49;700;70.0;1000\n'
                'MN;02;;0331;Governor & Lt Governor;;9901;WRITE-IN;;;WI;49;49;2;0.1;1000\n')
        r = SO.races_from(SO.contests_from(text.encode(), SO.MN_COLS), 'MN', 2026, 'u')[0]
        self.assertEqual((r['leader'], r['leader_party'], r['total'], r['counted_pct']), ('C Diaz and D Kim', 'D', 2000, 99.0))

    def test_north_carolina_precinct_zip(self):
        hdr = 'County\tElection Date\tPrecinct\tContest Group ID\tContest Type\tContest Name\tChoice\tChoice Party\tVote For\tElection Day\tEarly Voting\tAbsentee by Mail\tProvisional\tTotal Votes\tReal Precinct\n'
        rows = ''.join(f'WAKE\t11/03/2026\tP{i}\t1\tC\tUS SENATE\t{n}\t{p}\t1\t0\t0\t0\t0\t{v}\tY\n'
                       for i in range(3) for n, p, v in (('Roy Hale', 'REP', 100), ('Ana Cruz', 'DEM', 120)))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('results_pct_20261103.txt', hdr + rows)
        r = SO.races_from(SO.contests_from(buf.getvalue()), 'NC', 2026, 'u')[0]
        self.assertEqual((r['office'], r['leader'], r['total']), ('S', 'Ana Cruz', 660))

    def test_florida_named_columns(self):
        cols = SO.SOURCES['FL']['columns']
        text = ('ElectionDate\tPartyCode\tPartyName\tRaceCode\tOfficeDesc\tJuris1num\tJuris2num\tPrecincts\tPrecinctsReporting\tCanNameLast\tCanNameFirst\tCanNameMiddle\tCanVotes\n'
                '11/3/2026\tREP\tRepublican Party\tUSR\tUnited States Representative\t7\t\t100\t100\tStone\tJo\t\t5000\n'
                '11/3/2026\tDEM\tDemocratic Party\tUSR\tUnited States Representative\t7\t\t100\t100\tBlue\tMo\t\t4000\n')
        r = SO.races_from(SO.contests_from(text.encode(), cols), 'FL', 2026, 'u')[0]
        self.assertEqual((r['id'], r['leader'], r['leader_party']), ('H-2026-FL-7', 'Jo Stone', 'R'))

    def test_results_page_tables(self):
        page = ('<h1>Election Results - Tuesday, November 3, 2026</h1><p>U. S. SENATOR</p><p>Polling Locations Reporting: 97%</p>'
                '<table><tr><th>Party</th><th>Candidate</th><th>Ballots Cast</th></tr><tr><td>REP</td><td>KEN PAXTON</td><td>1,000</td></tr>'
                '<tr><td>DEM</td><td>JAMES TALARICO</td><td>1,100</td></tr></table>'
                '<p>RAILROAD COMMISSIONER</p><table><tr><th>Candidate</th><th>Votes</th></tr><tr><td>X</td><td>5</td></tr></table>')
        rs = SO.races_from(SO.contests_from(page.encode()), 'TX', 2026, 'u')
        self.assertEqual([(r['id'], r['leader_party'], r['counted_pct']) for r in rs], [('S-2026-TX-', 'D', 97.0)])

    def test_discover_links_on_a_state_page(self):
        page = ('<a href="https://results.enr.clarityelections.com/KY/120000/">2025</a><a href="https://results.enr.clarityelections.com/KY/127500/web.345435/#/summary">2026</a>'
                '<a href="https://results.enr.clarityelections.com/KY/Fayette/127501/">county</a>'
                '<a href="/files/results_20261103.csv">now</a><a href="/files/results_20241105.csv">old</a>'
                '<script>u="https://app.enhancedvoting.com/cdn/results/Georgia/export-110326GeneralElection.json"</script>')
        got = SO.discover(page, 'https://elect.ky.gov/results/', 2026)
        self.assertIn(('clarity', 'https://results.enr.clarityelections.com/KY/127500/'), got)
        self.assertNotIn(('clarity', 'https://results.enr.clarityelections.com/KY/Fayette/127501/'), got)   # statewide already totals it
        self.assertIn(('file', 'https://elect.ky.gov/files/results_20261103.csv'), got)
        self.assertNotIn(('file', 'https://elect.ky.gov/files/results_20241105.csv'), got)
        self.assertIn(('file', 'https://app.enhancedvoting.com/cdn/results/Georgia/export-110326GeneralElection.json'), got)

    def test_county_sites_add_up(self):
        page = ''.join(f'<a href="https://results.enr.clarityelections.com/NJ/{c}/{e}/web.345435/#/summary">{c}</a>' for c, e in (('Essex', 127486), ('Mercer', 127554)))
        summ = {'Essex': [{'C': 'U.S. House of Representatives 10th Congressional District', 'CH': ['A', 'B'], 'P': ['DEM', 'REP'], 'V': [300, 100]}],
                'Mercer': [{'C': 'U.S. House of Representatives 10th Congressional District', 'CH': ['A', 'B'], 'P': ['DEM', 'REP'], 'V': [50, 250]}]}

        def getter(u):
            if u.endswith('current_ver.txt'):
                return b'42'
            for c, v in summ.items():
                if f'/{c}/' in u:
                    return json.dumps(v).encode()
            return page.encode()
        res = SO.read_state('NJ', 2026, getter, {'page': 'https://www.nj.gov/x.shtml'})
        r = res['races'][0]
        self.assertEqual((res['status'], r['id'], r['total'], r['leader'], r['margin_pct']), ('read', 'H-2026-NJ-10', 700, 'A', 0.0))

    def test_one_state_failing_does_not_stop_the_rest(self):
        def getter(u):
            if 'alaska' in u:
                raise OSError('timed out')
            return b'<html>nothing here</html>'
        SO._jobs.clear()
        with mock.patch.object(SO, '_file', return_value=Path(tempfile.gettempdir()) / 'sanjaya_state_counts_test.json'):
            SO.request(2026, getter, force=True, only={'AK', 'AL'})
            for _ in range(200):
                out = SO.request(2026, getter)
                if not out['pending']:
                    break
                time.sleep(0.02)
        self.assertEqual((out['states']['AK']['status'], out['states']['AL']['status']), ('failed', 'unavailable'))
        SO._jobs.clear()

    def test_calls_need_the_count_to_agree(self):
        wiki = L.parse_page('H', 2026, (FIX / 'wp_us_house_2026.html').read_text(encoding='utf-8'))
        def st(rid, state, seat, rows):
            c = {'title': '', 'cands': {(n, p): v for n, p, v in rows}, 'reporting': None, 'pct': None}
            r = SO.races_from([dict(c, title=f'U.S. Representative District {seat}')], state, 2026, 'https://state.example')[0]
            self.assertEqual(r['id'], rid)
            return r
        state = [st('H-2026-AL-1', 'AL', 1, [('Jordan Vale', 'R', 900), ('Kim Low', 'D', 100)]),       # agrees with Wikipedia
                 st('H-2026-CA-22', 'CA', 22, [('Sam Cole', 'R', 510), ('Riley Moss', 'D', 490)]),      # count disagrees
                 st('H-2026-NV-3', 'NV', 3, [('Una Bell', 'D', 10), ('Vic Ode', 'R', 9)])]               # Wikipedia has no row yet
        m = {r['id']: r for r in SO.merge(wiki, state)}
        self.assertTrue(m['H-2026-AL-1']['called']); self.assertEqual(m['H-2026-AL-1']['origin'], 'wikipedia+state')
        self.assertEqual(json.loads(m['H-2026-AL-1']['cands'])[0][4], 1)
        self.assertFalse(m['H-2026-CA-22']['called']); self.assertIn('Shown as not called', m['H-2026-CA-22']['status_text'])
        self.assertEqual((m['H-2026-NV-3']['origin'], m['H-2026-NV-3']['called'], m['H-2026-NV-3']['leader_party']), ('state', 0, 'D'))
        self.assertEqual(m['H-2026-AK-1']['origin'], 'wikipedia')

    def test_result_uses_state_counts(self):
        wiki = {'races': L.parse_page('H', 2026, (FIX / 'wp_us_house_2026.html').read_text(encoding='utf-8')),
                'fetched': 1, 'pending': False, 'step': '', 'error': None, 'page': 'p'}
        c = {'title': 'U.S. Representative District 22', 'cands': {('Sam Cole', 'R'): 510, ('Riley Moss', 'D'): 490}, 'reporting': (9, 10), 'pct': None}
        counts = {'races': SO.races_from([c], 'CA', 2026, 'https://ca.example'), 'states': {'CA': {'status': 'read', 'races': 1}},
                  'pending': False, 'step': '', 'fetched': 2, 'enabled': True}
        with mock.patch.object(UE, 'live_races', return_value=wiki), mock.patch.object(UE, '_rows', return_value=[]), \
                mock.patch.object(SO, 'request', return_value=counts):
            r = UE.result('H', 2026, getter=lambda u: b'', state_getter=lambda u: b'')
        seats = {f"{s['state']}-{s['seat']}": s for s in r['seats']}
        self.assertEqual((seats['CA-22']['origin'], seats['CA-22']['called'], seats['CA-22']['leader_party'], seats['CA-22']['counted']),
                         ('wikipedia+state', False, 'R', 90.0))
        self.assertEqual(r['live']['states']['read'], 1)
        self.assertEqual(sum(p['seats'] for p in r['parties']), 435)

    def test_enhanced_voting_api_and_certification(self):
        data = {'ballotItems': [
            {'id': 1, 'name': 'U.S. Representative District 3', 'ballotOptions': [{'name': 'Ann Ray', 'politicalParty': 'Democratic', 'voteCount': 1200},
                                                                               {'name': 'Bob Fox', 'politicalParty': 'Republican', 'voteCount': 1100}]},
            {'id': 9, 'parentId': 1, 'name': 'U.S. Representative District 3', 'ballotOptions': [{'name': 'Ann Ray', 'politicalParty': 'Democratic', 'voteCount': 50},
                                                                                              {'name': 'Bob Fox', 'politicalParty': 'Republican', 'voteCount': 40}]}]}
        calls = []

        def getter(u):
            calls.append(u)
            if u.endswith('/elections/washington'):
                return b'[{"id": "20261103"}, {"id": "20260804"}]'
            if u.endswith('/20261103/data'):
                return json.dumps(data).encode()
            if u.endswith('/20261103'):
                return b'{"asOf": "2026-11-20", "isOfficialResults": true}'
            raise OSError('HTTP 404 Not Found')
        res = SO.read_state('WA', 2026, getter, SO.SOURCES['WA'])
        r = res['races'][0]
        self.assertEqual((res['status'], res['certified'], r['id'], r['total'], r['certified']), ('read', True, 'H-2026-WA-3', 2300, 1))  # county copy skipped
        self.assertIn('https://results.votewa.gov/results/public/api/elections/washington/20261103/data', calls)
        wiki = [{'id': 'H-2026-WA-3', 'called': 1, 'winner': 'Bob Fox', 'winner_party': 'R', 'state': 'WA', 'cands': '[]', 'origin': 'wikipedia'}]
        m = SO.merge(wiki, res['races'])[0]
        self.assertEqual((m['called'], m['winner'], m['winner_party']), (1, 'Ann Ray', 'D'))     # the certified count wins

    def test_failures_are_explained_per_address(self):
        def getter(u):
            if 'alaska' in u:
                raise OSError('HTTP 403 Forbidden')
            return b'<html><head><script>app()</script></head><body><div id="root"></div></body></html>'
        ak = SO.read_state('AK', 2026, getter)
        self.assertEqual((ak['status'], ak['error']), ('failed', 'HTTP 403 Forbidden'))
        self.assertEqual(ak['tried'][0]['url'], 'https://www.elections.alaska.gov/results/26GENR/ENRbyPrecinct.csv')
        nj = SO.read_state('NJ', 2026, getter)
        self.assertEqual(nj['status'], 'none'); self.assertIn('JavaScript', nj['error'])
        al = SO.read_state('AL', 2026, lambda u: self.fail('no request for a state without a feed'))
        self.assertEqual(al['status'], 'unavailable')

    def test_missing_county_sites_mark_counts_partial(self):
        page = ''.join(f'<a href="https://results.enr.clarityelections.com/NJ/{c}/{e}/">{c}</a>' for c, e in (('Essex', 127486), ('Mercer', 127554)))

        def getter(u):
            if '/Mercer/' in u:
                raise OSError('HTTP 503 Service Unavailable')
            if u.endswith('current_ver.txt'):
                return b'7'
            if '/Essex/' in u:
                return json.dumps([{'C': 'U.S. House of Representatives 10th Congressional District', 'CH': ['A', 'B'], 'P': ['DEM', 'REP'], 'V': [3, 1], 'PR': 1, 'TP': 1}]).encode()
            return page.encode()
        res = SO.read_state('NJ', 2026, getter, {'page': 'https://www.nj.gov/x.shtml'})
        self.assertEqual((res['status'], res['counties'], res['races'][0]['counted_pct']), ('partial', {'found': 2, 'read': 1}, None))
        self.assertIn('1 of 2 county sites', res['races'][0]['status_text'])

    def test_utf16_and_nul_bytes(self):
        text = 'Contest Name\tChoice\tChoice Party\tTotal Votes\nUS SENATE\tAna Cruz\tDEM\t5\nUS SENATE\tRoy Hale\tREP\t4\n'
        for blob in (text.encode('utf-16'), text.replace('Ana', 'A\x00na').encode()):
            r = SO.races_from(SO.contests_from(blob), 'NC', 2026, 'u')[0]
            self.assertEqual((r['office'], r['total']), ('S', 9))

    def test_public_record_fetcher(self):
        s = (ROOT / 'server.py').read_text(encoding='utf-8')
        self.assertIn('def fetch_public_record', s); self.assertIn("raise OSError(f'HTTP {exc.code}", s)
        self.assertIn("which in ('1','wiki')", s); self.assertIn("force_states=which in ('1','states')", s)
        import server
        self.assertRaises(ValueError, server.validate_external_url, 'http://93.184.216.34/x')
        self.assertEqual(server.validate_external_url('http://93.184.216.34/x', allow_http=True), 'http://93.184.216.34/x')
        self.assertRaises(ValueError, server.validate_external_url, 'http://127.0.0.1/x', allow_http=True)
        js = (ROOT / 'static' / 'elections_us.js').read_text(encoding='utf-8')
        self.assertIn('data-us-refresh="wiki"', js); self.assertIn('data-us-refresh="states"', js)

    def test_every_state_has_a_source_and_ap_is_gone(self):
        self.assertEqual(set(SO.SOURCES), set(UD.STATES))
        self.assertTrue(all(v['page'].startswith('https://') for v in SO.SOURCES.values()))
        self.assertFalse((ROOT / 'us_ap.py').exists())
        for f in ('server.py', 'us_elections.py', 'static/elections_us.js'):
            t = (ROOT / f).read_text(encoding='utf-8')
            self.assertNotIn('ap_key', t, f); self.assertNotIn('/api/us/settings', t, f); self.assertNotIn('Associated Press', t, f)


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
