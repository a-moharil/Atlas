"""v6.3: Elections page. Results, maps and the rules that keep them honest.

Most tests build a tiny data pack from synthetic files, so they run anywhere without
downloads. Tests marked 'real pack' run only when election_data/ has been downloaded,
and check totals against published figures.
"""
import datetime as dt
import gzip
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import elections
import elections_data as D
import geo_shapes as G

ROOT = Path(__file__).resolve().parents[1]
REAL = D.DB.exists() and (D.manifest() or {}).get('version') == D.PACK_VERSION


def write_shapefile(base, polys, rows):
    """Minimal polygon shapefile + dBase writer for tests."""
    recs = b''
    for i, ring in enumerate(polys, 1):
        pts = b''.join(struct.pack('<2d', x, y) for x, y in ring)
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        body = struct.pack('<i4d2i', 5, min(xs), min(ys), max(xs), max(ys), 1, len(ring)) + struct.pack('<i', 0) + pts
        recs += struct.pack('>2i', i, len(body) // 2) + body
    header = struct.pack('>i20xi', 9994, (100 + len(recs)) // 2) + struct.pack('<2i4d32x', 1000, 5, 0, 0, 1, 1)
    Path(base + '.shp').write_bytes(header + recs)
    fields = [('ST_NAME', 'C', 30), ('AC_NO', 'N', 5), ('AC_NAME', 'C', 30)]
    hdr = struct.pack('<B3BIHH20x', 3, 26, 1, 1, len(rows), 32 + 32 * len(fields) + 1, 1 + sum(f[2] for f in fields))
    for name, t, ln in fields:
        hdr += name.encode().ljust(11, b'\x00') + t.encode() + b'\x00' * 4 + bytes([ln, 0]) + b'\x00' * 14
    hdr += b'\x0d'
    body = b''.join(b' ' + b''.join(str(r[f[0]]).encode().ljust(f[2])[:f[2]] for f in fields) for r in rows)
    Path(base + '.dbf').write_bytes(hdr + body + b'\x1a')


CSV_HEAD = ['State_Name', 'Year', 'month', 'Poll_No', 'Position', 'Candidate', 'Party', 'Votes', 'Valid_Votes', 'Electors',
            'Constituency_No', 'Constituency_Name', 'Constituency_Type', 'Margin', 'Margin_Percentage', 'Turnout_Percentage']


def write_csv(path, rows):
    buf = io.StringIO()
    buf.write(','.join(CSV_HEAD) + '\n')
    for r in rows:
        buf.write(','.join(str(r.get(k, '')) for k in CSV_HEAD) + '\n')
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        f.write(buf.getvalue())


def cand(state, year, no, name, pos, who, party, votes, valid=1000, margin=100, poll=0):
    return {'State_Name': state, 'Year': year, 'month': 3, 'Poll_No': poll, 'Position': pos, 'Candidate': who, 'Party': party,
            'Votes': votes, 'Valid_Votes': valid, 'Electors': 1600, 'Constituency_No': no, 'Constituency_Name': name,
            'Constituency_Type': 'GEN', 'Margin': margin, 'Margin_Percentage': margin / 10, 'Turnout_Percentage': 62.5}


class TinyPack(unittest.TestCase):
    """Build a two-constituency state and check every layer of the pipeline."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        raw, data = t / 'raw', t / 'data'
        raw.mkdir()
        sq = lambda x0: [(x0, 26.0), (x0 + 1, 26.0), (x0 + 1, 27.0), (x0, 27.0), (x0, 26.0)]
        write_shapefile(str(raw / 'India_AC'), [sq(80.0), sq(81.0)],
                        [{'ST_NAME': 'UTTAR PRADESH', 'AC_NO': 1, 'AC_NAME': 'Behat'},
                         {'ST_NAME': 'UTTAR PRADESH', 'AC_NO': 2, 'AC_NAME': 'Nakur'}])
        (raw / 'india_pc_2019_simplified.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'st_name': 'Uttar Pradesh', 'pc_no': 1, 'pc_name': 'Saharanpur'},
             'geometry': {'type': 'Polygon', 'coordinates': [[list(p) for p in sq(80.0)]]}}]}))
        write_csv(raw / 'All_States_AE.csv.gz', [
            cand('Uttar_Pradesh', 2017, 1, 'BEHAT', 1, 'A', 'BJP', 500), cand('Uttar_Pradesh', 2017, 1, 'BEHAT', 2, 'B', 'SP', 400),
            cand('Uttar_Pradesh', 2017, 2, 'NAKUR', 1, 'C', 'ADAL', 450), cand('Uttar_Pradesh', 2017, 2, 'NAKUR', 2, 'D', 'SP', 440),
            cand('Uttar_Pradesh', 2022, 1, 'BEHAT', 1, 'E', 'SP', 520), cand('Uttar_Pradesh', 2022, 1, 'BEHAT', 2, 'F', 'BJP', 420),
            cand('Uttar_Pradesh', 2022, 1, 'BEHAT', 3, 'NOTA', 'NOTA', 10),
            cand('Uttar_Pradesh', 2022, 2, 'NAKUR', 1, 'G', 'ADS', 470, margin=20), cand('Uttar_Pradesh', 2022, 2, 'NAKUR', 2, 'H', 'SP', 450),
            cand('Uttar_Pradesh', 2020, 2, 'NAKUR', 1, 'X', 'INC', 999, poll=1),            # by-election: ignored
            cand('Uttar_Pradesh', 2002, 1, 'BEHAT', 1, 'Old', 'INC', 999)])               # before 2008: ignored
        write_csv(raw / 'All_States_GE.csv.gz', [cand('Uttar_Pradesh', 2019, 1, 'SAHARANPUR', 1, 'P', 'BSP', 600)])
        write_csv(raw / 'AE_2023_2026.csv.gz', [])
        write_csv(raw / 'GE_2024.csv.gz', [cand('Uttar_Pradesh', 2024, 1, 'SAHARANPUR', 1, 'Q', 'INC', 650)])
        cls.patches = [mock.patch.object(D, 'DATA', data), mock.patch.object(D, 'GEO', data / 'geo'),
                       mock.patch.object(D, 'DB', data / 'elections.sqlite3'), mock.patch.object(D, 'MANIFEST', data / 'manifest.json')]
        for p in cls.patches:
            p.start()
        data.mkdir()
        D.build(raw_dir=raw)
        elections._cache.clear()

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        elections._cache.clear()
        cls.tmp.cleanup()

    def test_catalog_lists_the_state_and_its_elections(self):
        c = elections.catalog()
        self.assertTrue(c['pack']['ready'])
        st = next(s for s in c['states'] if s['state'] == 'Uttar_Pradesh')
        self.assertEqual([e['year'] for e in st['elections']], [2022, 2017])   # 2002 and the by-election are excluded
        self.assertTrue(st['map'])
        self.assertEqual([e['year'] for e in c['national']], [2024, 2019])

    def test_result_totals_majority_and_shares(self):
        r = elections.result('AE-Uttar_Pradesh-2022')
        self.assertEqual(r['seats_total'], 2)
        self.assertEqual(r['majority'], 2)
        sp = next(p for p in r['parties'] if p['code'] == 'SP')
        self.assertEqual(sp['seats'], 1)
        self.assertAlmostEqual(sp['share'], 100 * (520 + 450) / 2000, places=2)
        self.assertEqual(r['nota_votes'], 10)
        self.assertNotIn('NOTA', [p['code'] for p in r['parties']])

    def test_same_party_under_a_new_code_is_not_a_flip(self):
        r = elections.result('AE-Uttar_Pradesh-2022')
        ads = next(p for p in r['parties'] if p['code'] == 'ADS')
        self.assertEqual(ads['seat_change'], 0)                    # ADAL in 2017, ADS in 2022: same party
        self.assertEqual([f[:4] for f in r['flips']], [['Uttar_Pradesh', 1, 'BJP', 'SP']])

    def test_closest_contest_first(self):
        r = elections.result('AE-Uttar_Pradesh-2022')
        self.assertEqual(r['closest'][0]['name'], 'Nakur')

    def test_map_and_hexes(self):
        r = elections.result('AE-Uttar_Pradesh-2022')
        self.assertTrue(r['map']['available'])
        g = elections.geo('ac', 'Uttar_Pradesh')
        self.assertEqual(sorted(i['no'] for i in g['items']), [1, 2])
        self.assertEqual(len(set(map(tuple, g['hex'].values()))), 2)   # one hexagon per seat
        self.assertEqual({s['geo'] for s in r['seats']}, {'1', '2'})

    def test_geo_rejects_paths(self):
        with self.assertRaises(ValueError):
            elections.geo('ac', '../secrets')

    def test_lok_sabha_maps_by_name(self):
        r = elections.result('GE-2024')
        self.assertEqual(r['seats'][0]['geo'], 'Uttar_Pradesh|1')
        self.assertEqual(r['previous']['year'], 2019)


class Shapes(unittest.TestCase):
    def test_simplify_keeps_ends_and_drops_collinear(self):
        line = [(0, 0), (1, 0.0001), (2, 0), (3, 0), (3, 3)]
        out = G.simplify(line, 0.01)
        self.assertEqual(out[0], (0, 0))
        self.assertEqual(out[-1], (3, 3))
        self.assertLess(len(out), len(line))

    def test_centroid_of_square(self):
        c = G.centroid([[(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]])
        self.assertAlmostEqual(c[0], 1)
        self.assertAlmostEqual(c[1], 1)

    def test_mercator_round_trip(self):
        import math
        lon, lat = 77.2, 28.6
        x = G.R_MERC * math.radians(lon)
        y = G.R_MERC * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
        a, b = G.mercator_to_lonlat(x, y)
        self.assertAlmostEqual(a, lon, places=6)
        self.assertAlmostEqual(b, lat, places=6)

    def test_hex_layout_one_cell_each(self):
        pts = [(i % 20 + (i // 20) * 0.3, i // 20) for i in range(403)]
        h = D.hex_layout(pts, list(range(403)))
        self.assertEqual(len(h), 403)
        self.assertEqual(len({tuple(v) for v in h.values()}), 403)

    def test_transliterations_match(self):
        for a, b in [('Chaprauli', 'Chhaprauli'), ('Captainganj', 'Kaptanganj'), ('Andaman & Nicobar Islands', 'Andaman and Nicobar Islands')]:
            self.assertTrue(D._same_place(a, b), (a, b))
        self.assertFalse(D._same_place('Lucknow', 'Varanasi'))


class Blackout(unittest.TestCase):
    def _with(self, windows):
        path = Path(tempfile.mkdtemp()) / 'b.json'
        path.write_text(json.dumps({'windows': windows}))
        return mock.patch.object(elections, 'BLACKOUT_FILE', path)

    def test_exit_poll_window_hides_exit_polls_only(self):
        w = [{'state': 'Uttar_Pradesh', 'kind': 'exit_poll', 'start': '2027-02-10T07:00:00+05:30', 'end': '2027-03-07T18:30:00+05:30'}]
        with self._with(w):
            inside = dt.datetime(2027, 2, 20, 12, tzinfo=dt.timezone.utc)
            self.assertEqual(elections.hidden_kinds('Uttar_Pradesh', inside), {'exit_poll'})
            self.assertEqual(elections.hidden_kinds('Punjab', inside), set())
            after = dt.datetime(2027, 3, 7, 13, 1, tzinfo=dt.timezone.utc)     # 18:31 IST
            self.assertEqual(elections.hidden_kinds('Uttar_Pradesh', after), set())

    def test_silence_hides_polls_and_projections(self):
        w = [{'state': '*', 'kind': 'silence', 'start': '2027-02-08T07:00:00+05:30', 'end': '2027-02-10T18:00:00+05:30'}]
        with self._with(w):
            t = dt.datetime(2027, 2, 9, tzinfo=dt.timezone.utc)
            self.assertEqual(elections.hidden_kinds('Goa', t), {'opinion_poll', 'projection'})

    def test_shipped_file_has_no_active_windows_and_documents_the_law(self):
        d = json.loads((ROOT / 'election_blackout.json').read_text(encoding='utf-8'))
        self.assertEqual(d['windows'], [])
        self.assertIn('126A', d['_about'])


class Municipal(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'election_municipal.json').read_text(encoding='utf-8'))

    def test_the_eight_corporations(self):
        cities = {c['city'] for c in self.data['corporations']}
        self.assertEqual(cities, {'Mumbai', 'Pune', 'Pimpri-Chinchwad', 'Nagpur', 'Delhi', 'Hyderabad', 'Chennai', 'Bengaluru'})

    def test_tallies_sum_to_council_size_and_majority_is_half_plus_one(self):
        for c in self.data['corporations']:
            self.assertEqual(sum(n for _, n in c['parties']), c['seats'], c['id'])
            self.assertEqual(c['majority'], c['seats'] // 2 + 1, c['id'])
            self.assertTrue(c['sources'], c['id'])

    def test_every_party_has_a_name(self):
        known = elections.parties()
        for c in self.data['corporations']:
            for code, _ in c['parties']:
                self.assertIn(code, known, f"{c['id']}: {code}")

    def test_result_shape(self):
        r = elections.result('MC-Mumbai-2026')
        self.assertEqual(r['seats_total'], 227)
        self.assertEqual(next(a for a in r['alliances'] if a['name'] == 'Mahayuti')['seats'], 118)
        self.assertFalse(r['map']['available'])


@unittest.skipUnless(REAL, 'real pack: download the elections data to run')
class RealPack(unittest.TestCase):
    def test_lok_sabha_2024_alliances(self):
        r = elections.result('GE-2024')
        al = {a['name']: a['seats'] for a in r['alliances']}
        self.assertEqual((r['seats_total'], al['NDA'], al['INDIA']), (543, 293, 234))
        self.assertEqual(next(p for p in r['parties'] if p['code'] == 'BJP')['seats'], 240)

    def test_state_alliances(self):
        for eid, want in [('AE-Uttar_Pradesh-2022', {'NDA': 273, 'SP alliance': 125}), ('AE-Maharashtra-2024', {'Mahayuti': 230, 'MVA': 46})]:
            r = elections.result(eid)
            self.assertEqual({a['name']: a['seats'] for a in r['alliances']}, want)

    def test_redrawn_states_get_no_map(self):
        for eid in ('AE-Assam-2026', 'AE-Jammu_&_Kashmir-2024'):
            self.assertFalse(elections.result(eid)['map']['available'], eid)


class Wiring(unittest.TestCase):
    def test_page_is_registered(self):
        js = (ROOT / 'static' / 'atlas3.js').read_text(encoding='utf-8')
        html = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('elections: ["ATLASElections", "elections.js"]', js)
        self.assertIn('data-page="elections"', html)
        self.assertIn('/elections.js', html)
        self.assertIn('/elections.css', html)

    def test_background_refresh_does_not_rebuild_the_page(self):
        js = (ROOT / 'static' / 'atlas3.js').read_text(encoding='utf-8')
        hyd = js[js.index('async function hydrate('):js.index('return true;', js.index('async function hydrate('))]
        self.assertIn('"elections",', hyd)                                  # excluded from the full re-render
        self.assertIn('window.ATLASElections?.refreshIfStale?.()', hyd)    # refreshed quietly instead
        el = (ROOT / 'static' / 'elections.js').read_text(encoding='utf-8')
        self.assertIn('return { layout, mount, destroy, refreshIfStale }', el)
        self.assertIn('if (changed && document.querySelector(".elPage")) quietDraw();', el)

    def test_server_routes(self):
        src = (ROOT / 'server.py').read_text(encoding='utf-8')
        for route in ('/api/elections/catalog', '/api/elections/result', '/api/elections/geo', '/api/elections/download'):
            self.assertIn(route, src)

    def test_pack_downloads_only_from_github(self):
        for s in D.SOURCES:
            self.assertTrue(s[1].startswith('https://raw.githubusercontent.com/'), s[1])

    def test_pack_is_not_committed(self):
        self.assertIn('election_data/', (ROOT / '.gitignore').read_text(encoding='utf-8'))

    def test_maps_draw_the_survey_of_india_boundary(self):
        js = (ROOT / 'static' / 'elections.js').read_text(encoding='utf-8')
        self.assertIn('/data/india_outline_soi.geojson', js)
        self.assertIn('elBoundary', js)


if __name__ == '__main__':
    unittest.main()
