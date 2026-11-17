"""Offline contract tests for expanded source registry, actual ingestion telemetry and authoritative geometry."""
import os,sys,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['OBS_SKIP_NETWORK']='1'
import server,atlas_v3
FEED=b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Example</title>
<item><title>Published news item about transport</title><link>https://example.com/a</link><description>Officials announced a meeting.</description><pubDate>Mon, 16 Nov 2026 00:00:00 GMT</pubDate></item>
<item><title>Published financial regulation news</title><link>https://example.com/b</link><description>The central bank published a circular.</description><pubDate>Mon, 16 Nov 2026 00:30:00 GMT</pubDate></item></channel></rss>'''
class V3(unittest.TestCase):
    def test_registry_and_desk_diversity(self):
        desks={f['desk'] for f in server.REGISTRY['feeds']}
        self.assertTrue({'India','Technology','Finance','World','Energy','Climate','Research'}.issubset(desks))
        self.assertGreaterEqual(len(server.REGISTRY['feeds']),70)
        self.assertTrue({'dw_live','wion_live','cnn_news18_live','ndtv_live','reuters_live'}.issubset({x['id'] for x in server.REGISTRY['live_channels']}))
    def test_actual_attempt_ledger_and_new_vs_returned(self):
        with tempfile.TemporaryDirectory() as d, patch.object(server,'DB_FILE',Path(d)/'test.sqlite3'):
            server.init_db()
            feed={'id':'test_ledger','name':'Example Finance','url':'https://example.com/feed.xml','region':'India','tier':'reporting','desk':'Finance'}
            run=atlas_v3.run_start(server.db_connect,server.utc_now)
            with patch.object(server,'fetch_bytes',return_value=FEED):
                self.assertEqual(server.fetch_source(feed,run_id=run),2)
                self.assertEqual(server.fetch_source(feed,run_id=run),2)
            with patch.object(server,'fetch_bytes',side_effect=ValueError('Synthetic connection failure')):
                self.assertEqual(server.fetch_source(feed,run_id=run),0)
            atlas_v3.run_finish(server.db_connect,run,server.utc_now)
            result=atlas_v3.metrics(server.db_connect,[feed],[],[],server.utc_now(),False)
            self.assertEqual(result['latest_run']['attempted'],3)
            self.assertEqual(result['latest_run']['succeeded'],2)
            self.assertEqual(result['latest_run']['failed'],1)
            self.assertEqual(result['latest_run']['returned'],4)
            self.assertEqual(result['latest_run']['inserted'],2)
            self.assertEqual(result['publication_by_source'][0]['last_14d'],2)
            self.assertEqual(result['stored_entries'],2)
            self.assertEqual(result['sources'][0]['last_result'],'error')
    def test_map_sources_never_synthesize_fields(self):
        with patch.object(atlas_v3,'CACHE',{}):
            out=atlas_v3.map_catalog('wildfire_events',lambda url,n: b'{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,0]]]},"properties":{"title":"Source record"}}]}')
            self.assertEqual(out['count'],1)
            self.assertEqual(out['features'][0]['geometry']['type'],'Polygon')
            out2=atlas_v3.map_catalog('wildfire_events',lambda url,n: (_ for _ in ()).throw(Exception('Not called because cached')))
            self.assertTrue(out2['cached'])
        with self.assertRaises(ValueError):atlas_v3.shakemap('https://evil.com/download',lambda url,n:b'{}')
        with self.assertRaises(ValueError):atlas_v3.map_catalog('made_up_layer',lambda url,n:b'{}')
if __name__=='__main__': unittest.main()
