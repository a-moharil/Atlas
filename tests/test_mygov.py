import unittest,sys,datetime as dt,tempfile,json,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mygov,server
NOW=dt.datetime(2026,11,16,tzinfo=dt.timezone.utc)
FEEDS=[{'id':'mygov_meity','mygov':True,'ministry':'meity','name':'MeitY discovery','tier':'discovery'}, {'id':'mygov_pib','mygov':True,'name':'PIB','tier':'primary'}, {'id':'mygov_evaluation','mygov':True,'name':'Evaluation','tier':'analysis'}]
def entry(**kw):
 d=dict(id='test',source_id='mygov_meity',source='Synthetic fixture only',medium='article',title='India digital infrastructure research allocation',summary='Synthetic test record, not real news.',published='2026-11-15T00:00:00Z',retrieved='2026-11-16T00:00:00Z',url='https://example.org/fixture');d.update(kw);return d
class MyGovTest(unittest.TestCase):
 def test_directory_integrity(self):
  c=mygov.CATALOGUE;mids={m['id'] for m in c['ministries']}
  self.assertEqual(len(mids),55);self.assertEqual(len(c['schemes']),81)
  self.assertTrue(all(s['ministry'] in mids for s in c['schemes']))
  self.assertTrue(all(s['application_status']=='Not verified open' and s['deadline'] is None for s in c['schemes']))
  self.assertFalse(any(mygov.POSTDOC.search(s['name']) for s in c['schemes']))
 def test_official_and_discovery_distinct(self):
  config={f['id']:f for f in FEEDS}
  self.assertEqual(mygov.classify(entry(),config)['evidence_type'],'Discovery lead')
  self.assertEqual(mygov.classify(entry(source_id='mygov_pib'),config)['evidence_type'],'Official release')
  self.assertEqual(mygov.classify(entry(source_id='openalex_mygov_dpi',medium='paper'),config)['evidence_type'],'Scholarly metadata')
 def test_false_relevance_and_stage_not_verified(self):
  self.assertIsNone(mygov.classify(entry(source_id='unknown',title='Football match in Europe',summary='Sports results'),{}))
  r=mygov.classify(entry(),{f['id']:f for f in FEEDS});self.assertEqual(r['stage_hint'],'Budget / allocation');self.assertFalse(r['stage_verified']);self.assertIn('meity',r['ministries'])
 def test_window_dedup_and_health(self):
  items=[entry(),entry(id='duplicate'),entry(id='old',title='Old India government policy',published='2020-01-01T00:00:00Z'),entry(id='future',title='Future India scheme',published='2030-01-01T00:00:00Z')]
  p=mygov.payload(items,FEEDS,{'mygov_meity':{'state':'error','error':'Timeout'}},30,NOW)
  self.assertEqual(len(p['records']),1);self.assertEqual(p['source_health']['failed'],1);self.assertEqual(p['source_health']['never'],2)
  self.assertEqual(p['topics']['Digital'],1)
 def test_postdoc_identification(self):
  for title in ['Post-doctoral research vacancy','Postdoc fellowship in India','Post doctoral opportunity']:
   self.assertTrue(mygov.classify(entry(title=title),{f['id']:f for f in FEEDS})['postdoc'])
 def test_invalid_window(self):
  with self.assertRaises(ValueError):mygov.payload([],[],{},0,NOW)
 def test_new_feeds_unique(self):
  feeds=server.REGISTRY['feeds'];ids=[f['id'] for f in feeds];self.assertEqual(len(ids),len(set(ids)))
  self.assertEqual(sum(bool(f.get('mygov')) for f in feeds),63)
  self.assertEqual(sum(q['id'].startswith('mygov_') for q in server.REGISTRY['research']),3)
 def test_scoped_refresh_excludes_other_desks(self):
  with tempfile.TemporaryDirectory() as td,patch.object(server,'DB_FILE',Path(td)/'test.sqlite'),patch.object(server,'FETCH_RUNNING',False),patch.object(server,'fetch_source',return_value=0) as f,patch.object(server,'fetch_papers') as p,patch.object(server,'refresh_live_channels') as live,patch.object(server.atlas_plus,'fetch_one_layer') as layer:
   server.init_db();server.refresh_cycle(force_local=True,scope='mygov')
   self.assertEqual(f.call_count,63);self.assertTrue(all(c.args[0].get('mygov') for c in f.call_args_list));p.assert_called_once_with('mygov');live.assert_not_called();layer.assert_not_called();self.assertFalse(server.FETCH_RUNNING)
if __name__=='__main__':unittest.main()
