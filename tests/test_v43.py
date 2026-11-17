import unittest,sqlite3,json,datetime as dt,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import emergency as em,conflict_watch as cw
NOW=dt.datetime(2026,11,16,12,tzinfo=dt.timezone.utc)
FEEDS=[dict(id='bbc1',name='BBC World',site='https://bbc.com',region='World'),dict(id='bbc2',name='BBC Europe',site='https://bbc.co.uk',region='Europe'),dict(id='wire',name='Reuters',site='https://reuters.com'),dict(id='isw',name='ISW',site='https://understandingwar.org',isw=True,tier='analysis')]
def item(**kw):
 d=dict(id='test',source_id='bbc1',source='BBC fixture',medium='article',title='Missile attack strikes Ukraine military base',summary='Synthetic fixture',published='2026-11-16T11:00:00+00:00',url='https://example.org/test');d.update(kw);return d
class EmergencyTests(unittest.TestCase):
 def setUp(self):
  self.con=sqlite3.connect(':memory:');self.con.row_factory=sqlite3.Row;em.init(self.con)
 def tearDown(self):self.con.close()
 def test_hierarchy_and_overrides(self):
  em.update(self.con,FEEDS,'family','broadcast',True,0)
  self.assertTrue(em.blocked(em.source_info(FEEDS[0]),em.rules(self.con)))
  em.update(self.con,FEEDS,'feed','bbc1',False,1)
  self.assertFalse(em.blocked(em.source_info(FEEDS[0]),em.rules(self.con)))
  self.assertTrue(em.blocked(em.source_info(FEEDS[1]),em.rules(self.con)))
  em.update(self.con,FEEDS,'family','broadcast',False,2)
  self.assertEqual(em.rules(self.con),{('family','broadcast'):False})
 def test_publisher_alias(self):
  self.assertEqual(em.source_info(FEEDS[0])['publisher'],em.source_info(FEEDS[1])['publisher'])
 def test_version_conflict_rolls_back(self):
  em.update(self.con,FEEDS,'all','all',True,0)
  before=em.rules(self.con)
  with self.assertRaises(ValueError):em.update(self.con,FEEDS,'all','all',False,0)
  self.assertEqual(before,em.rules(self.con))
 def test_new_feeds_inherit(self):
  em.update(self.con,FEEDS,'all','all',True,0)
  self.assertTrue(em.blocked(em.source_info(dict(id='cnn',name='CNN',site='https://cnn.com')),em.rules(self.con)))
 def test_input_validation(self):
  for scope,key,value in [('feed','missing',True),('all','wrong',True),('all','all','false')]:
   with self.assertRaises(ValueError):em.update(self.con,FEEDS,scope,key,value,0)
 def test_age_and_noise(self):
  info=em.source_info(FEEDS[0])
  for kw in [dict(published=None),dict(published='2026-11-17T00:00:00Z'),dict(published='2026-11-10T00:00:00Z'),dict(title='Football war games review'),dict(title='President attends local school')]:
   self.assertIsNone(em.triage(item(**kw),info,NOW,24)[0])
  self.assertEqual(em.triage(item(),info,NOW,24)[0]['priority'],'Priority 1')
 def test_json_and_publisher_dedup(self):
  p=em.payload([item(),item(id='duplicate'),item(id='wire',source_id='wire')],FEEDS,{}, {},0,24,NOW)
  json.dumps(p);self.assertEqual(len(p['groups']),1);self.assertEqual(p['groups'][0]['publisher_count'],2);self.assertEqual(p['groups'][0]['record_count'],2)
 def test_exclusion_is_panel_scoped(self):
  entries=[item()];em.update(self.con,FEEDS,'family','broadcast',True,0)
  p=em.payload(entries,FEEDS,{},em.rules(self.con),1,24,NOW)
  self.assertEqual(p['groups'],[]);self.assertEqual(entries[0]['title'],'Missile attack strikes Ukraine military base');self.assertEqual(p['health']['excluded'],2)
class ConflictTests(unittest.TestCase):
 def test_verified_metadata(self):
  def fetch(url,limit):
   m=next(m for m in cw.MAPS if m['item'] in url)
   return json.dumps(dict(id=m['item'],owner=m['owner'],access='public',type='StoryMap',modified=1000)).encode()
  p=cw.check_maps(fetch);self.assertTrue(all(m['state']=='public item verified' and not m['viewer_verified'] for m in p['maps']))
 def test_identity_and_network_failure(self):
  p=cw.check_maps(lambda *a:b'{"owner":"imposter"}')
  self.assertTrue(all(m['state']=='unavailable' for m in p['maps']))
  def fail(*a):raise TimeoutError('Test timeout')
  self.assertTrue(all(m['state']=='unavailable' for m in cw.check_maps(fail)['maps']))
 def test_report_counts_and_context(self):
  p=cw.payload([item(source_id='isw'),item(source_id='isw'),item()],FEEDS,{},7,NOW)
  self.assertEqual(len(p['reports']),1);self.assertEqual(len(p['context']),1);self.assertEqual(p['counts']['ukraine'],1);json.dumps(p)
 def test_exact_window(self):
  p=cw.payload([item(source_id='isw',published='2026-11-09T11:00:00Z')],FEEDS,{},7,NOW)
  self.assertEqual(p['reports'],[])
if __name__=='__main__':unittest.main()
