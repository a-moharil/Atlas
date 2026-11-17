import os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['OBS_SKIP_NETWORK']='1'
import article_clusters,tile_gateway
class NewV33Test(unittest.TestCase):
    def setUp(self):
        self.records=[]
        for i in range(30):
            title=(f'India semiconductor supply chain chips export fabrication plant {i}' if i%2 else f'Russia Ukraine ceasefire negotiations sanctions security talks {i}')
            self.records.append(dict(id='a'+str(i),title=title,summary='Policy implications documented in research excerpt',medium='article',tier='analysis',region='India',source='Outlet '+str(i%4),source_id='src'+str(i%4),published='2026-11-16T00:00:00Z',url='https://example.org/story/'+str(i)))
        self.registry=[{'id':'src'+str(i),'desk':'Technology' if i%2 else 'World','region':'India'} for i in range(4)]
    def test_semantic_model_real_split(self):
        out=article_clusters.cluster_payload(self.records,self.registry,mode='semantic',days=90)
        self.assertEqual(len(out['nodes']),30)
        groups={}
        for n in out['nodes']:groups.setdefault(n['semantic_group'],[]).append(n['title'])
        self.assertTrue(any(all('Ukraine' in s for s in lst) for lst in groups.values()))
        self.assertEqual(len(out['nodes'][0]['position']),3)
        self.assertTrue(all(isinstance(x,float) for n in out['nodes'] for x in n['position']))
    def test_source_and_combined_views(self):
        out=article_clusters.cluster_payload(self.records,self.registry,mode='source',days=90)
        self.assertEqual(len(out['groups']),4)
        self.assertEqual(sum(g['count'] for g in out['groups']),30)
        combined=article_clusters.cluster_payload(self.records,self.registry,mode='combined',days=90)
        self.assertEqual(len(combined['nodes']),30)
        self.assertTrue(all('semantic_group' in a and 'source_id' in a for a in combined['nodes']))
    def test_analytic_filters(self):
        india=article_clusters.cluster_payload(self.records,self.registry,focus='India',days=90)
        self.assertEqual(len(india['nodes']),30)
        research=article_clusters.cluster_payload(self.records,self.registry,domain='Research',days=90)
        self.assertEqual(len(research['nodes']),30)
        search=article_clusters.cluster_payload(self.records,self.registry,query='semiconductor',days=90)
        self.assertEqual(len(search['nodes']),15)
        src=article_clusters.cluster_payload(self.records,self.registry,sources='src1',days=90)
        self.assertEqual(len(src['nodes']),len([x for x in self.records if x['source_id']=='src1']))
    def test_allows_only_providers_and_bounded_tiles(self):
        u=tile_gateway.provider_url('nasa',5,24,13,'2026-11-15')
        self.assertIn('VIIRS_SNPP_Thermal_Anomalies_375m_All',u)
        self.assertIn('EPSG%3A3857',u)
        self.assertIn('BBOX',u)
        for args in [('evil',3,1,1,None),('esri',21,1,1,None),('esri',3,100,2,None),('nasa',3,1,1,'9999-99-99')]:
            with self.assertRaises(ValueError):tile_gateway.provider_url(*args)
    def test_rejects_nonimage_provider_response(self):
        class FakeResponse:
            headers={'Content-Type':'text/xml'}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,limit):return b'<ServiceException>unknown layer</ServiceException>'
        class FakeOpener:
            def open(self,*a,**kw):return FakeResponse()
        from unittest.mock import patch
        with patch.object(tile_gateway,'build_opener',return_value=FakeOpener()):
            with self.assertRaisesRegex(ValueError,'non-image'):tile_gateway.get_tile('nasa',4,7,8,'2026-11-15')
        self.assertGreater(next(x for x in tile_gateway.stats() if x['id']=='nasa')['failed'],0)
if __name__=='__main__':unittest.main()
