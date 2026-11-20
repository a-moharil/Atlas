import unittest,tempfile,threading,time,sys,json
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tmpdir import TempDir
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import content_cleanup as cc,retrieval_jobs as jobs,tile_gateway as tiles,server,atlas_v3
class Reliability(unittest.TestCase):
 def test_crime_and_policy_distinction(self):
  for title in ['Police arrest robbery suspect in Mumbai','Murder investigation opened','Woman kidnapped in Delhi']:
   self.assertEqual(cc.classify(title),'crime')
  for title in ['Parliament debates murder sentencing legislation','War crimes investigation at United Nations','Government policy on theft prevention']:
   self.assertNotEqual(cc.classify(title),'crime')
  self.assertNotIn('crime',cc.DEFAULT)
 def test_async_dedup_and_persistence(self):
  gate=threading.Event();count=[]
  def loader():count.append(1);gate.wait(2);return {'points':[{'value':4}],'data_status':'retrieved'}
  with tempfile.TemporaryDirectory() as td:
   key='test-persistence';jobs.JOBS.pop(key,None)
   a=jobs.request(key,loader,td);b=jobs.request(key,loader,td,True)
   self.assertTrue(a['pending']);self.assertTrue(b['pending']);gate.set()
   for _ in range(100):
    if not jobs.JOBS[key]['running']:break
    time.sleep(.01)
   self.assertEqual(len(count),1)
   jobs.JOBS.pop(key);out=jobs.request(key,lambda:self.fail('disk cache missed'),td)
   self.assertEqual(out['points'][0]['value'],4)
 def test_stale_data_survives_failure(self):
  with tempfile.TemporaryDirectory() as td:
   jobs.JOBS['stale-test']={'data':{'points':[1]},'checked':0,'running':False,'error':None}
   def bad():raise TimeoutError('provider read timeout')
   jobs.request('stale-test',bad,td)
   for _ in range(100):
    if not jobs.JOBS['stale-test']['running']:break
    time.sleep(.01)
   out=jobs.request('stale-test',bad,td)
   self.assertEqual(out['points'],[1]);self.assertEqual(out['data_status'],'stale');self.assertIn('timeout',out['error'])
 def test_live_run_and_minute_buckets(self):
  with TempDir() as td,patch.object(server,'DB_FILE',Path(td)/'test.sqlite'):
   server.init_db();r=atlas_v3.run_start(server.db_connect,server.utc_now)
   for minute in ['10','11']:
    atlas_v3.record(server.db_connect,r,'bbc_world','2026-11-16T10:00:00Z',f'2026-11-16T10:{minute}:00Z',True,2,1,'',50)
   out=atlas_v3.metrics(server.db_connect,server.all_feed_configs(),[],[],None,True)
   self.assertEqual(len(out['timeline']),2);self.assertEqual(out['latest_run']['succeeded'],2)
 def test_tile_failure_cooldown(self):
  tiles.FAILED.clear();tiles.CACHE.clear()
  with patch.object(tiles,'_fetch_image',side_effect=TimeoutError('test outage')) as fetch:
   for _ in range(2):
    with self.assertRaises(RuntimeError):tiles.get_tile('nasa',2,2,1,'2026-11-02')
   self.assertEqual(fetch.call_count,1)
  tiles.FAILED.clear()
 def test_crime_migration_and_restore(self):
  with TempDir() as td,patch.object(server,'DB_FILE',Path(td)/'test.sqlite'):
   server.init_db()
   with closing(server.db_connect()) as con,con:
    cc.apply(con,['crime'],server.utc_now());self.assertIn('crime',cc.active(con))
    cc.apply(con,[],server.utc_now());self.assertNotIn('crime',cc.active(con))
if __name__=='__main__':unittest.main()

class ProxyValidation(unittest.TestCase):
 def test_curated_provider_proxy_dns_only(self):
  import socket
  with patch.object(server.socket,'getaddrinfo',side_effect=socket.gaierror('local DNS unavailable')),patch.object(server.urllib.request,'getproxies',return_value={'https':'http://proxy.example:8080'}):
   self.assertEqual(server.validate_external_url('https://api.worldbank.org/v2/'),'https://api.worldbank.org/v2/')
   with self.assertRaises(ValueError):server.validate_external_url('https://untrusted.example/feed')
  with patch.object(server.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
   with self.assertRaises(ValueError):server.validate_external_url('https://api.worldbank.org/v2/')
