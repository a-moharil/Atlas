import datetime as dt
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import india_intel
NOW=dt.datetime(2026,11,16,tzinfo=dt.timezone.utc)

def r(title,uid,summary='',source_id='national'):
 return dict(id=uid,source_id=source_id,source='Test',medium='article',title=title,
             summary=summary,url=f'https://example.com/story/{uid}',published='2026-11-15T12:00:00Z',retrieved='2026-11-16T00:00:00Z')

class IndiaCoverageTests(unittest.TestCase):
 def test_place_detection(self):
  states,basis,cities=india_intel.geographic_matches(r('Bengaluru Metro expansion announced','one'))
  self.assertEqual(states,['Karnataka']);self.assertEqual(basis,'headline')
  self.assertEqual(cities['Karnataka'],['Bengaluru'])
 def test_digest_clustering_and_city_intensity(self):
  rows=[r('Bengaluru Metro expansion announced','one'),r('Bengaluru Metro expansion announced','two'),r('Chennai rains trigger warning','three')]
  out=india_intel.india_coverage(rows,[],now=NOW)
  self.assertEqual(out['counts']['duplicate_stories'],1)
  self.assertEqual(next(s for s in out['states'] if s['name']=='Karnataka')['count'],1)
  self.assertEqual(next(s for s in out['states'] if s['name']=='Tamil Nadu')['count'],1)
 def test_source_scoped_confidence_separate(self):
  rows=[r('City budget debated in council','one',source_id='city_mumbai')]
  cfg=[{'id':'city_mumbai','local_city':'Mumbai','local_state':'Maharashtra'}]
  all_=india_intel.india_coverage(rows,cfg,now=NOW)
  explicit=india_intel.india_coverage(rows,cfg,scope='explicit',now=NOW)
  self.assertEqual(all_['counts']['located_distinct_articles'],1)
  self.assertEqual(explicit['counts']['located_distinct_articles'],0)
 def test_irrelevant_articles_unlocated(self):
  out=india_intel.india_coverage([r('World leaders discuss policy','one')],[],now=NOW)
  self.assertEqual(out['counts']['unlocated'],1)
 def test_topic_filter(self):
  out=india_intel.india_coverage([r('Delhi election results','one'),r('Delhi rain forecast','two')],[],topic='weather',now=NOW)
  self.assertEqual(out['counts']['located_distinct_articles'],1)
if __name__=='__main__':unittest.main()
