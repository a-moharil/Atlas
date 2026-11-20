"""ATLAS v4 research archive controls, no live news or unverified summit dates."""
import json,os,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'));os.environ['OBS_SKIP_NETWORK']='1'
from tmpdir import TempDir
import server,content_cleanup,expert_research
class V4Backend(unittest.TestCase):
 def row(self,title,n):
  return dict(id=f'entry{n:016d}',source_id='t',source='Synthetic publisher',tier='reporting',region='India',medium='article',title=title,url=f'https://example.org/{n}',summary='Synthetic sample, no real-world record.',published='2026-11-16T00:00:00Z',retrieved=server.utc_now(),video_id=None,author='')
 def test_suppression_is_reversible_and_ingest_filters(self):
  with TempDir() as d,patch.object(server,'DB_FILE',Path(d)/'t.db'):
   server.init_db()
   self.assertEqual(server.persist_records([self.row('Horoscope today for Aries',1)]),0)
   self.assertEqual(server.persist_records([self.row('India and Japan discuss strategic maritime trade',2)]),1)
   with closing(server.db_connect()) as con,con:
    self.assertEqual(content_cleanup.snapshot(con)['visible_articles'],1)
    content_cleanup.apply(con,[],server.utc_now())
   self.assertEqual(server.persist_records([self.row('Horoscope today for Taurus',3)]),1)
   self.assertEqual(len(server.read_state()['entries']),2)
   with closing(server.db_connect()) as con,con:content_cleanup.apply(con,['astrology'],server.utc_now())
   self.assertEqual(len(server.read_state()['entries']),1)
   with closing(server.db_connect()) as con,con:
    snap=content_cleanup.snapshot(con)
    self.assertEqual(snap['hidden_in_archive'],1)
    content_cleanup.apply(con,[],server.utc_now())
   self.assertEqual(len(server.read_state()['entries']),2)
 def test_conservative_policy_avoidance(self):
  self.assertEqual(content_cleanup.classify('Government regulates sports betting industry and taxes'), '')
  self.assertEqual(content_cleanup.classify('Capricorn horoscope predictions for this week'),'astrology')
  self.assertEqual(content_cleanup.classify('India foreign policy and tariffs rise'), '')
  self.assertEqual(content_cleanup.classify('Movie review: best films to watch'),'entertainment')
 def test_unknown_genres_not_allowed(self):
  with TempDir() as d,patch.object(server,'DB_FILE',Path(d)/'t.db'):
   server.init_db()
   with closing(server.db_connect()) as con,con:
    with self.assertRaises(ValueError):content_cleanup.apply(con,['foreign_policy'],server.utc_now())
    with self.assertRaises(ValueError):content_cleanup.apply(con,['sports','sports'],server.utc_now())
 def test_summit_scopes_and_verified_statuses(self):
  data=expert_research.EVENTS
  self.assertGreaterEqual(len(data['institutions']),40)
  self.assertGreaterEqual(len(data['events']),20)
  self.assertIn('Quad',{x['name'] for x in data['institutions']})
  for name in ['SCO','BRICS','OSCE','ASEAN','G20','G7','African Union','IORA','BIMSTEC','OPEC','UNFCCC']:
   self.assertIn(name,{x['name'] for x in data['institutions']})
  quad=next(x for x in data['events'] if x['id']=='quad-nov17')
  self.assertEqual(quad['verification'],'reported')
  self.assertTrue(all(x.get('source','').startswith('https://') for x in data['events']))
 def test_registration_summit_feeds(self):
  registry=json.loads((ROOT/'source_registry.json').read_text())
  self.assertGreater(len(registry['feeds']),220)
  self.assertTrue(any(x['id']=='official_sco_events' for x in registry['feeds']))
  self.assertTrue(all(x['url'].startswith('https://') for x in registry['feeds']))
if __name__=='__main__':unittest.main()
