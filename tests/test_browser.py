"""Browser regression for ATLAS SIGNAL v3, with clearly isolated synthetic fixtures."""
import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['OBS_SKIP_NETWORK']='1'
import server,atlas_v3
from tests.tmpdir import TempDir
try:from playwright.sync_api import sync_playwright
except ImportError:sync_playwright=None

CHROME=next((c for c in ('/usr/bin/chromium','/usr/bin/google-chrome') if Path(c).exists()),None)
@unittest.skipIf(sync_playwright is None or CHROME is None,'Playwright/Chromium not available')
class BrowserTest(unittest.TestCase):
 def test_navigation_refresh_chart_and_persistent_video(self):
    h=(ROOT/'static/index.html').read_text();css=(ROOT/'static/atlas3.css').read_text();js=(ROOT/'static/atlas3.js').read_text()
    h=h.replace('<link rel="stylesheet" href="/atlas3.css">','<style>'+css+'</style>')
    # Browser fixtures never make outbound web requests or contain purported live news.
    import re
    h=re.sub(r'<link rel="stylesheet" href="https://unpkg.com/leaflet[^>]*>', '', h)
    h=re.sub(r'<script src="https://unpkg.com/leaflet[^>]*></script>', '', h)
    h=h.replace('<script src="/atlas3.js" defer></script>','').replace('<script src="/india_investigation.js" defer></script>','')
    with TempDir() as td,patch.object(server,'DB_FILE',Path(td)/'observatory.sqlite3'):
        server.init_db()
        # No fake news: one explicitly fictional fixture under a synthetic URL.
        item=dict(id='fictional_1234567890abcde',source_id='bbc_world',source='Synthetic Test News',tier='reporting',region='Global',medium='article',title='India synthetic test of technology supply chains',url='https://example.com/fictional',summary='This is a test fixture, not an actual article.',published='2026-11-16T00:00:00Z',retrieved='2026-11-16T00:01:00Z',author='Test',video_id=None)
        server.persist_records([item]);state=server.read_state()
        run=atlas_v3.run_start(server.db_connect,server.utc_now)
        atlas_v3.record(server.db_connect,run,'reuters_india',server.utc_now(),server.utc_now(),True,2,1,'',104)
        atlas_v3.run_finish(server.db_connect,run,server.utc_now)
        metrics=atlas_v3.metrics(server.db_connect,server.all_feed_configs(),server.REGISTRY['channels'],server.REGISTRY['research'],server.utc_now(),False)
    brief=server.atlas_plus.source_digest(item,[])
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,executable_path=CHROME,args=['--no-sandbox']);page=b.new_page(viewport={'width':1400,'height':850});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.set_content(h)
        page.evaluate('data=>{window.fetch=async (u)=>({ok:true,status:200,json:async()=>data[String(u).startsWith("/api/brief")?"/api/brief":String(u)]||{features:[],status:"error"}})}',{'/api/state':state,'/api/metrics':metrics,'/api/brief':brief})
        page.add_script_tag(content=(ROOT/'static/india_investigation.js').read_text());page.add_script_tag(content=js);page.wait_for_timeout(350)
        self.assertIn('1',page.locator('#sourcesBadge').inner_text())
        for key in ['room','news','india','technology','finance','coverage','map','investigate','media','research','ccc']:
            page.locator(f'button[data-page="{key}"]').first.click()
            self.assertTrue(page.locator('#main h1').count(),key)
        page.locator('button[data-page="coverage"]').first.click()
        self.assertIn('Collection runs',page.locator('#main').inner_text())
        page.locator('button[data-page="news"]').first.click()
        self.assertEqual(page.locator('#main [data-story]').count(),0)
        page.locator('button[data-worldtab="all"]').click()
        self.assertEqual(page.locator('#main [data-story]').count(),1)
        page.locator('button[data-page="india"]').first.click()
        self.assertIn('This is a test fixture',page.locator('#main').inner_text())  # v5: excerpt shown without a label
        page.locator('[data-story]').first.click();page.wait_for_timeout(90)
        self.assertTrue(page.locator('#storyPanel').is_visible())
        self.assertIn('This is a test fixture',page.locator('#storyContent').inner_text())
        page.locator('button[data-close="true"]').first.click()
        page.locator('button[data-page="media"]').first.click()
        page.locator('#videoUrl').fill('https://youtu.be/Lh5GXucy2EU')
        page.locator('#playCustom').click()
        self.assertEqual(page.locator('#playerContent iframe').count(),1)
        page.locator('button[data-page="technology"]').first.click()
        self.assertEqual(page.locator('#playerContent iframe').count(),1)
        page.locator('#fontMore').click()
        self.assertEqual(page.locator('html').evaluate("(el)=>el.style.getPropertyValue('--font')"),'20px')
        self.assertEqual(errors,[])
        b.close()
if __name__=='__main__':unittest.main()
