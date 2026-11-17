"""Expert workspaces contract tests; fixture values are synthetic and never shipped as observations."""
import json,sys,unittest,datetime as dt
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import expert_research as ex
class ExpertWorkspaces(unittest.TestCase):
 def test_events_dated_primary_documents_and_link_hypothesis(self):
  sample=[dict(id='synthetic',source_id='official_mea',medium='article',title='India and Japan hold a synthetic maritime technology forum',summary='This is a synthetic example for testing India Japan maritime cooperation.',source='Synthetic Feed',url='https://example.com/synthetic',published='2026-11-16T00:00:00Z',tier='analysis')]
  out=ex.geopolitics(sample,now=dt.datetime(2026,11,16,tzinfo=dt.timezone.utc))
  self.assertTrue(any(x['id']=='apec-leaders' and x['status']=='upcoming' for x in out['events']))
  self.assertTrue(any(x['id']=='cop31' and x['status']=='in progress' for x in out['events']))
  self.assertTrue(out['connections']);self.assertIn('not proven',out['connections'][0]['kind'])
  self.assertEqual(len(out['statements']),1)
 def test_macro_worldbank_real_fetch_contract(self):
  payload=[{'page':1,'pages':1,'total':2},[
   {'countryiso3code':'IND','date':'2024','value':6.49},{'countryiso3code':'USA','date':'2024','value':2.8},{'countryiso3code':'IND','date':'2025','value':None}]]
  with patch.object(ex,'CACHE',{}):
   out=ex.macro_data('NY.GDP.MKTP.KD.ZG',['USA','IND'],lambda u,n:json.dumps(payload).encode())
   self.assertEqual(out['data_status'],'retrieved')
   self.assertEqual(len(out['points']),2)
   self.assertTrue(out['source_url'].startswith('https://data.worldbank.org/indicator/'))
   cached=ex.macro_data('NY.GDP.MKTP.KD.ZG',['IND','USA'],lambda u,n:(_ for _ in ()).throw(Exception('Not called')))
   self.assertEqual(cached['cache_state'],'fresh cache')
 def test_worldbank_unavailable_never_returns_invented_data(self):
  with patch.object(ex,'CACHE',{}):
   result=ex.macro_data('EG.IMP.CONS.ZS',['IND'],lambda u,n:(_ for _ in ()).throw(ConnectionError('Offline')))
   self.assertEqual(result['points'],[])
   self.assertEqual(result['data_status'],'unavailable')
  with self.assertRaises(ValueError):ex.macro_data('invalid',['IND'],lambda u,n:b'[]')
  with self.assertRaises(ValueError):ex.macro_data('FP.CPI.TOTL.ZG',['DROP TABLE'],lambda u,n:b'[]')
 def test_un_comtrade_preview_and_absence(self):
  payload={'data':[{'cmdCode':'TOTAL','primaryValue':123456789,'refYear':2024}]}
  ok=ex.trade_preview('IND','CHN',2024,'X',lambda u,n:json.dumps(payload).encode())
  self.assertEqual(ok['value_usd'],123456789)
  self.assertEqual(ok['status'],'ok')
  fail=ex.trade_preview('IND','CHN',2024,'X',lambda u,n:(_ for _ in ()).throw(ValueError('Offline')))
  self.assertIsNone(fail['value_usd'])
  self.assertEqual(fail['status'],'unavailable')
  with self.assertRaises(ValueError):ex.trade_preview('IND','IND',2024,'X',lambda u,n:b'{}')
  with self.assertRaises(ValueError):ex.trade_preview('IND','CHN',2024,'Y',lambda u,n:b'{}')
 def test_official_portals_and_named_data_sources(self):
  self.assertTrue(any(x['name']=='UNFCCC COP31' for x in ex.EVENTS['events']))
  self.assertTrue(any('United Nations' in x[0] for x in ex.PORTALS))
  self.assertGreaterEqual(len(ex.INDICATORS),10)
if __name__=='__main__':unittest.main()
