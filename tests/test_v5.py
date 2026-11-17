"""ATLAS v5: publisher intelligence, source preferences, video gating, Earth watch parsers."""
import json, os, sqlite3, sys, tempfile, unittest, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import publishers, earth_watch, video_check, logos


class PublisherTests(unittest.TestCase):
    def test_feed_host_prefers_site_query(self):
        f = {'id': 'x', 'url': 'https://news.google.com/rss/search?q=site%3Aswarajyamag.com+when%3A3d', 'site': 'https://news.google.com'}
        self.assertEqual(publishers.feed_host(f), 'swarajyamag.com')
        self.assertEqual(publishers.feed_host({'id': 'g', 'url': 'https://news.google.com/rss/headlines', 'site': 'https://news.google.com'}), 'feed:g')

    def test_profile_averages_raters(self):
        p = publishers.profile('dw.com')  # AllSides Center + MBFC Lean Left
        self.assertEqual(p['lean'], -1)
        self.assertEqual(len(p['raters']), 2)
        self.assertEqual(publishers.profile('thehindu.com')['paywall'], 'metered')
        self.assertIsNone(publishers.profile('orfonline.org')['lean'])

    def test_premium_url_detection(self):
        e = {'url': 'https://indianexpress.com/article/explained/premium/x-123/'}
        self.assertEqual(publishers.article_paywall(e, 'indianexpress.com'), 'premium')
        self.assertEqual(publishers.article_paywall({'url': 'https://ft.com/content/1'}, 'ft.com'), 'hard')

    def test_google_news_title_suffix(self):
        self.assertEqual(publishers.title_publisher('Budget passes - The Hindu'), 'thehindu.com')

    def test_story_spread(self):
        publishers.set_feeds([{'id': 'a', 'url': 'https://www.thehindu.com/feed', 'site': 'https://thehindu.com'},
                              {'id': 'b', 'url': 'https://swarajyamag.com/feed', 'site': 'https://swarajyamag.com'},
                              {'id': 'c', 'url': 'https://ptinews.com/feed', 'site': 'https://ptinews.com'}])
        rows = [dict(id=f'id{i}', source_id=s, medium='article', title='Parliament passes landmark delimitation amendment bill today',
                     retrieved='2026-11-16', url=f'https://x/{i}') for i, s in enumerate('abc')]
        rows.append(dict(id='other', source_id='a', medium='article', title='Monsoon rainfall deficit hits kharif sowing', retrieved='2026-11-16', url='https://x/9'))
        spread = publishers.stories(rows)
        self.assertEqual(spread['id0']['sources'], 3)
        self.assertEqual(spread['id0']['dist'], {'left': 1, 'center': 1, 'right': 1, 'unrated': 0})
        self.assertEqual(spread['other']['sources'], 1)

    def test_block_clause(self):
        con = sqlite3.connect(':memory:'); publishers.init(con)
        publishers.set_feeds([{'id': 'n18', 'url': 'https://news18.com/rss', 'site': 'https://news18.com'}])
        publishers.set_pref(con, 'news18.com', 'blocked', 'now')
        sql, vals = publishers.visibility_clause(con)
        self.assertIn('source_id NOT IN', sql); self.assertIn('n18', vals); self.assertIn('news18.com', vals)
        publishers.set_pref(con, 'news18.com', 'normal', 'now')
        self.assertEqual(publishers.visibility_clause(con)[0], '1=1')
        with self.assertRaises(ValueError): publishers.set_pref(con, 'x.com', 'favourite', 'now')


class VideoTests(unittest.TestCase):
    def test_oembed_states(self):
        def ok(url, n): return json.dumps({'title': 'T', 'author_name': 'DW', 'thumbnail_url': 'https://i.ytimg.com/vi/x/hq.jpg'}).encode()
        def gone(url, n): raise urllib.error.HTTPError(url, 404, 'nf', {}, None)
        def noembed(url, n): raise urllib.error.HTTPError(url, 401, 'na', {}, None)
        self.assertEqual(video_check.oembed('Lh5GXucy2EU', ok)['state'], 'playable')
        self.assertEqual(video_check.oembed('Lh5GXucy2EU', gone)['state'], 'unavailable')
        self.assertEqual(video_check.oembed('Lh5GXucy2EU', noembed)['state'], 'blocked')
        self.assertEqual(video_check.oembed('bad', ok)['state'], 'invalid')


class EarthTests(unittest.TestCase):
    def test_gdacs(self):
        data = {'features': [{'geometry': {'type': 'Point', 'coordinates': [88.1, 21.2]}, 'properties': {'eventtype': 'TC', 'eventid': 1, 'name': 'Tropical Cyclone X', 'alertlevel': 'Orange', 'fromdate': '2026-11-14T00:00:00', 'url': {'report': 'https://www.gdacs.org/report.aspx?eventid=1'}, 'severitydata': {'severitytext': '120 km/h'}}}]}
        e = earth_watch.parse_gdacs(data)[0]
        self.assertEqual((e['kind'], e['level']), ('cyclone', 'orange'))
        self.assertTrue(earth_watch.in_india(e['lat'], e['lon']))

    def test_eonet_and_usgs(self):
        eo = {'events': [{'id': 'E1', 'title': 'Fire', 'categories': [{'id': 'wildfires'}], 'geometry': [{'date': '2026-11-15T00:00:00Z', 'type': 'Point', 'coordinates': [77, 30], 'magnitudeValue': 300, 'magnitudeUnit': 'acres'}]}]}
        self.assertEqual(earth_watch.parse_eonet(eo)[0]['kind'], 'wildfire')
        us = {'features': [{'id': 'q', 'geometry': {'type': 'Point', 'coordinates': [140, 35, 10]}, 'properties': {'mag': 6.4, 'time': 1763251200000, 'title': 'M 6.4'}}]}
        q = earth_watch.parse_usgs(us)[0]
        self.assertEqual(q['level'], 'orange'); self.assertIn('10 km', q['severity'])

    def test_pulse_csv(self):
        csv = '# ERA5\n# comment\ndate,2t,clim_91-20,ano_91-20,status\n2026-11-13,13.9,13.4,0.5,final\n2026-11-14,14.1,13.4,0.7,preliminary\n'
        r = earth_watch.parse_pulse(csv)
        self.assertEqual(r['latest']['anomaly'], 0.7); self.assertEqual(r['latest']['status'], 'preliminary')
        r2 = earth_watch.parse_pulse('date,2t,clim_91-20\n2026-11-14,14.1,13.4\n')
        self.assertAlmostEqual(r2['latest']['anomaly'], 0.7, places=3)

    def test_field_uv(self):
        lats, lons = earth_watch.grid('india'); n = len(lats) * len(lons)
        def fake(url, size):
            k = url.count('%2C') + 1 if 'latitude=' in url else 1
            k = len(url.split('latitude=')[1].split('&')[0].split('%2C'))
            return json.dumps([{'current': {'time': '2026-11-16T12:00', 'wind_speed_10m': 10, 'wind_direction_10m': 270, 'temperature_2m': 25, 'precipitation': 0, 'cloud_cover': 10}}] * k).encode()
        f = earth_watch.field('india', fake)
        self.assertEqual(len(f['u']), len(lats)); self.assertAlmostEqual(f['u'][0][0], 10.0, places=1)  # westerly → blows east
        self.assertAlmostEqual(f['v'][0][0], 0.0, places=1)


class LogoTests(unittest.TestCase):
    def test_rejects_unknown_and_script_svg(self):
        with self.assertRaises(ValueError): logos.get('evil.example', {'thehindu.com'}, Path(tempfile.mkdtemp()), None)
        self.assertIsNone(logos.kind(b'<svg onload="x()"></svg>'))
        self.assertEqual(logos.kind(b'\x89PNG\r\n' + b'0' * 200), 'image/png')


class BoundaryTests(unittest.TestCase):
    def test_official_boundary_bundle(self):
        g = json.loads((ROOT / 'static/data/india_states_soi.geojson').read_text())
        names = {f['properties']['name'] for f in g['features']}
        self.assertEqual(len(names), 36); self.assertIn('Ladakh', names)
        ladakh = next(f for f in g['features'] if f['properties']['name'] == 'Ladakh')
        pts = []
        def walk(c):
            if isinstance(c[0], (int, float)): pts.append(c)
            else: [walk(x) for x in c]
        walk(ladakh['geometry']['coordinates'])
        self.assertGreater(max(p[1] for p in pts), 36.5)   # Gilgit-Baltistan inside the official boundary
        self.assertGreater(max(p[0] for p in pts), 79.8)   # Aksai Chin inside the official boundary


if __name__ == '__main__':
    unittest.main()
