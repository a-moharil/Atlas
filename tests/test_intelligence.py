"""Source integrity, evidence handling and optional geophysical feeds: offline regression tests."""
import os,sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['OBS_SKIP_NETWORK']='1'
import server,atlas_plus

class IntelligenceTest(unittest.TestCase):
 def test_nasa_event(self):
  payload={'events':[{'id':'EONET_1','title':'Fire in reported area','link':'https://eonet.gsfc.nasa.gov/events/1','geometry':[{'date':'2026-11-16T01:00:00Z','type':'Point','coordinates':[77,24]}]}]}
  p=atlas_plus.normalize_geo('wildfires',payload)
  self.assertEqual((p[0]['lon'],p[0]['lat']),(77,24));self.assertEqual(p[0]['kind'],'wildfires')
 def test_usgs_quake(self):
  payload={'features':[{'id':'quake1','properties':{'title':'M 5.2','mag':5.2,'time':1794787200000,'url':'https://earthquake.usgs.gov/earthquakes/eventpage/x'},'geometry':{'type':'Point','coordinates':[114,-6,12]}}]}
  p=atlas_plus.normalize_geo('earthquakes',payload)
  self.assertEqual(p[0]['mag'],5.2)
  self.assertEqual((p[0]['lon'],p[0]['lat']),(114,-6))
 def test_wind_sample_is_sparse(self):
  payload=[{'current':{'wind_speed_10m':15,'wind_direction_10m':130,'temperature_2m':19.5,'time':'2026-11-16T00:00'}}]
  p=atlas_plus.normalize_geo('wind',payload)
  self.assertEqual(len(p),1)
  self.assertEqual(p[0]['speed'],15)
 def test_digests_do_not_invent_verified_claims(self):
  article={'id':'x1','title':'Delegation meets to discuss trade','source':'Example','summary':'Participants discussed logistics. No statement was issued.'}
  a=atlas_plus.source_digest(article,[])
  self.assertIn('Participants discussed logistics',a['digest'])
  self.assertFalse(a['can_assess_full_article'])
  self.assertEqual(len(a['related']),0)
  self.assertIn('not independent',a['limits'].lower())
 def test_source_metadata_scope(self):
  v=server.PROFILES['profiles']
  self.assertEqual(v['reuters_world']['lean'],'Center')
  self.assertEqual(v['fox_world']['lean'],'Right')
  self.assertNotIn('orf',v)  # not invent an ideological label for an unrated institute
 def test_geo_cache_survives_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   with patch.object(server,'DB_FILE',Path(tmp)/'test.sqlite'):
    server.init_db()
    payload={'events':[{'id':'F1','title':'Wildfire','link':'https://eonet.gsfc.nasa.gov','geometry':[{'date':'2026-11-16','type':'Point','coordinates':[9,40]}]}]}
    with patch.object(server,'fetch_bytes',return_value=json.dumps(payload).encode()):
     atlas_plus.fetch_one_layer('wildfires',server.fetch_bytes,server.db_connect,server.utc_now)
    first=atlas_plus.geo_state(server.db_connect)['wildfires']
    self.assertEqual(first['state'],'ok');self.assertEqual(len(first['points']),1)
    with patch.object(server,'fetch_bytes',side_effect=OSError('upstream unavailable')):
     atlas_plus.fetch_one_layer('wildfires',server.fetch_bytes,server.db_connect,server.utc_now)
    after=atlas_plus.geo_state(server.db_connect)['wildfires']
    self.assertEqual(after['state'],'error')
    self.assertEqual(after['points'],first['points'])
    self.assertEqual(after['retrieved'],first['retrieved'])

if __name__=='__main__':unittest.main()
