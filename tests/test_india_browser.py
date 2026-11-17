"""Visual interaction regression. Fictional article fixtures are never shipped as news."""
import datetime as dt, json,os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['OBS_SKIP_NETWORK']='1'
from unittest.mock import patch
import india_intel,server
try:from playwright.sync_api import sync_playwright
except ImportError:sync_playwright=None

CHROME=next((c for c in ('/usr/bin/chromium','/usr/bin/google-chrome') if Path(c).exists()),None)
@unittest.skipIf(sync_playwright is None or CHROME is None,'No Chromium')
class RegionalBrowserTests(unittest.TestCase):
 def test_heatmap_selection_and_briefs(self):
  html=(ROOT/'static/index.html').read_text();css=(ROOT/'static/atlas3.css').read_text()
  html=html.replace('<link rel="stylesheet" href="/atlas3.css">','<style>'+css+'</style>')
  import re
  html=re.sub(r'<link rel="stylesheet" href="https://unpkg.com/leaflet[^>]*>', '', html)
  html=re.sub(r'<script src="https://unpkg.com/leaflet[^>]*></script>', '', html)
  html=re.sub(r'<script src="/[a-z_0-9]+\.js" defer></script>','',html)
  now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
  nowiso=now.isoformat().replace('+00:00','Z')
  fictional=[
  dict(id='test_1',source_id='city_bengaluru',source='FICTIONAL TEST FEED',medium='article',tier='reporting',title='Bengaluru Metro infrastructure test report',summary='Demonstration-only excerpt about a fictional infrastructure project, not a real news report.',url='https://example.com/test1',published=nowiso,retrieved=nowiso,region='India'),
  dict(id='test_2',source_id='city_chennai',source='FICTIONAL TEST FEED',medium='article',tier='reporting',title='Chennai rainfall monitoring test',summary='Synthetic test rainfall description, no actual observation.',url='https://example.com/test2',published=nowiso,retrieved=nowiso,region='India'),
  dict(id='test_3',source_id='city_mumbai',source='FICTIONAL TEST FEED',medium='article',tier='reporting',title='Mumbai local budget monitoring example',summary='Test-only synthetic city finance notice.',url='https://example.com/test3',published=nowiso,retrieved=nowiso,region='India'),
  ]
  coverage=india_intel.india_coverage(fictional,server.REGISTRY["feeds"],now=now)
  state={'entries':fictional,'registry':server.REGISTRY,'publisher_profiles':{'profiles':{}},'live_channels':[]}
  metrics={'stored_entries':3,'sources':[],'configured_sources':163}
  bounds={'geometry':json.loads((ROOT/'static/data/india_states_soi.geojson').read_text())}
  outline=json.loads((ROOT/'static/data/india_outline_soi.geojson').read_text())
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,executable_path=CHROME,args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1600,'height':1030},device_scale_factor=1)
   page.route('https://**/*',lambda route:route.abort())
   page.set_content(html)
   payload={'/api/state':state,'/api/metrics':metrics,'/api/india-coverage':coverage,'/api/india-boundaries':bounds,'/data/india_outline_soi.geojson':outline}
   page.evaluate('data=>{window.fetch=async (u)=>{let k=String(u).split("?")[0];if(String(u).startsWith("https://"))throw new Error("Offline fixture");let d=data[k]||{};return {ok:true,status:200,json:async()=>d}}}',payload)
   errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.add_script_tag(content=(ROOT/'static/india_investigation.js').read_text())
   page.add_script_tag(content=(ROOT/'static/atlas3.js').read_text())
   page.locator('[data-page="investigate"]').first.click()
   page.locator('#indiaGeoMap svg path.st').first.wait_for(timeout=10000)
   self.assertEqual(page.locator('#indiaGeoMap svg path.st').count(),36)
   self.assertIn('survey of india',page.locator('#indiaGeoBanner').inner_text().lower())
   self.assertIn('Distinct geo-attributed',page.locator('#indiaCounts').inner_text())
   page.locator('#indiaStateButtons [data-indiastate="Karnataka"]').first.click()
   self.assertIn('Bengaluru Metro',page.locator('#indiaDetails').inner_text())
   self.assertIn('Demonstration-only excerpt',page.locator('#indiaDetails').inner_text())
   self.assertEqual(errors,[])
   if os.environ.get('ATLAS_SCREENSHOT'):
    page.evaluate("document.querySelector('.heroTitle').insertAdjacentHTML('beforebegin','<div class=\"notice\">DEMONSTRATION ONLY · SYNTHETIC TEST ARTICLES, NOT LIVE NEWS</div>')")
    page.screenshot(path=str(ROOT/'previews/india_investigation.png'),full_page=True)
   browser.close()
