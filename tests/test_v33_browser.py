"""Offline interaction regression. All injected article names are synthetic test fixtures."""
import os,re,sys,unittest,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['OBS_SKIP_NETWORK']='1'
import article_clusters
try:from playwright.sync_api import sync_playwright
except ImportError:sync_playwright=None

CHROME=next((c for c in ('/usr/bin/chromium','/usr/bin/google-chrome') if Path(c).exists()),None)
@unittest.skipIf(sync_playwright is None or CHROME is None,'Chromium unavailable')
class ConstellationBrowser(unittest.TestCase):
 def test_interactive_constellation_and_map(self):
  static=ROOT/'static';h=(static/'index.html').read_text()
  for css in ['atlas3.css','constellation.css','expert_panels.css']:
   h=h.replace(f'<link rel="stylesheet" href="/{css}">',f'<style>{(static/css).read_text()}</style>')
  h=re.sub(r'<link rel="stylesheet" href="https://unpkg.com/leaflet[^>]*>', '', h)
  h=re.sub(r'<script src="https://unpkg.com/leaflet[^>]*></script>', '', h)
  h=re.sub(r'<script src="/[a-z_0-9]+\.js" defer></script>', '', h)
  data=[]
  topics=['SYNTHETIC India semiconductor supply chain industrial investment','SYNTHETIC Russia Ukraine strategic diplomatic negotiations','SYNTHETIC weather wildfire disaster energy transition','SYNTHETIC inflation interest rate financial growth']
  for i in range(48):data.append(dict(id='synthetic-'+str(i),title=topics[i%4]+' '+str(i),summary='Synthetic test description, not a real news article',medium='article',tier='analysis',region='India',source='Test Publisher '+str(i%5),source_id='source'+str(i%5),published='2026-11-16T00:00:00Z',retrieved='2026-11-16T00:00:00Z',url='https://example.org/synthetic'+str(i)))
  registry=[{'id':'source'+str(i),'desk':'World','region':'India'} for i in range(5)]
  fixture=article_clusters.cluster_payload(data,registry,mode='semantic',days=30)
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True,executable_path=CHROME,args=['--no-sandbox']);page=b.new_page(viewport={'width':1480,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.set_content(h)
   st={'entries':data,'registry':{'feeds':registry,'channels':[]},'publisher_profiles':{'profiles':{}},'live_channels':[]}
   me={'stored_entries':48,'sources':[]}
   page.evaluate('''d=>{window.fetch=async (u)=>{let key=String(u);let result=key.startsWith('/api/clusters')?d.cluster:key.startsWith('/api/state')?d.state:key.startsWith('/api/metrics')?d.metrics:key.startsWith('/coastlines.json')?[]:{features:[],status:'unavailable'};return {ok:true,status:200,json:async()=>result};}}''',{'cluster':fixture,'state':st,'metrics':me})
   for script in ['india_investigation.js','expert_panels.js','tile_canvas.js','article_constellation.js','atlas3.js']:
    page.add_script_tag(content=(static/script).read_text())
   page.wait_for_timeout(450)
   page.locator('button[data-page="constellation"]').first.click();page.wait_for_timeout(500)
   self.assertTrue(page.locator('#clusterCanvas').is_visible())
   self.assertIn('48 records',page.locator('#clusterMetrics').inner_text())
   self.assertTrue(page.locator('.v4Article').count()>0)
   page.evaluate('window.scrollTo(0,0)')
   page.screenshot(path=str(ROOT/'previews'/'constellation_overview_v33.png'))
   page.locator('.v4Article').first.click()
   self.assertIn('SYNTHETIC',page.locator('#clusterSelection').inner_text())
   page.locator('#clusterConnections').click();self.assertIn('off',page.locator('#clusterConnections').inner_text())
   page.screenshot(path=str(ROOT/'previews'/'constellation_v33.png'))
   page.locator('button[data-page="map"]').first.click();page.wait_for_timeout(250)
   self.assertTrue(page.locator('#satCanvas').is_visible())
   page.locator('#satZoomIn').click();page.locator('button[data-mapfocus="world"]').click()
   self.assertEqual(page.locator('#satCanvas').count(),1)
   page.screenshot(path=str(ROOT/'previews'/'atlas_native_v33.png'))
   self.assertEqual(errors,[],errors)
   b.close()
if __name__=='__main__':unittest.main()
