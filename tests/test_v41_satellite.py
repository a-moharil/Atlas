"""NASA GIBS and satellite zoom regressions; no provider is faked as live data."""
import sys,os,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ['OBS_SKIP_NETWORK']='1'
import tile_gateway

class SatelliteGatewayTest(unittest.TestCase):
 def test_native_canvas_fills_map_frame(self):
  css=(ROOT/'static'/'atlas3.css').read_text()
  self.assertIn('.mapFrame > canvas.nativeTileCanvas',css)
  self.assertIn('width:100%;height:100%',css)
 def test_overzoom_resampling_and_previous_frame(self):
  script=''.join((ROOT/'static'/'tile_canvas.js').read_text().split())  # formatting-insensitive
  self.assertIn('Math.min(v.zoom,SOURCE_MAX[prov])',script)
  self.assertIn('renderSnapshot(ctx,cx,cy)',script)
  self.assertIn('fallbackAncestor(ctx,v,prov',script)
 def test_nasa_thermal_uses_raster_wms(self):
  links=tile_gateway.tile_candidates('nasa',5,24,12,'2026-11-14')
  self.assertEqual(len(links),1)
  self.assertIn('/wms/',links[0]);self.assertIn('TIME=2026-11-14',links[0])
 def test_daily_satellite_true_color(self):
  links=tile_gateway.tile_candidates('nasa_daily',5,25,12,'2026-11-14')
  self.assertIn('VIIRS_SNPP_CorrectedReflectance_TrueColor',links[0]);self.assertTrue(links[0].endswith('.jpeg'))
  self.assertIn('image%2Fpng',links[1])
 def test_provider_is_allowlisted_and_bounded(self):
  with self.assertRaises(ValueError):tile_gateway.tile_candidates('google',3,4,4,None)
  with self.assertRaises(ValueError):tile_gateway.tile_candidates('nasa',10,50,50,'2026-11-14')
  with self.assertRaises(ValueError):tile_gateway.tile_candidates('nasa',5,20,11,'2026-11-99')
 def test_wmts_failure_falls_back_to_wms(self):
  png=b'\x89PNG\r\n\x1a\n' + b'fixture-only'*10
  attempts=[]
  def fake_get(url,timeout):
   attempts.append(url)
   if '/wmts/' in url:raise ConnectionError('WMTS unavailable in test')
   return png,'image/png'
  with patch.object(tile_gateway,'_fetch_image',side_effect=fake_get):
   data,kind=tile_gateway.get_tile('nasa_daily',5,24,13,'2026-11-14')
  self.assertEqual(data,png);self.assertEqual(kind,'image/png');self.assertEqual(len(attempts),2)
  self.assertIn('/wms/',attempts[1]);tile_gateway.CACHE.clear()
 def test_source_origin_rejects_unknown_redirect(self):
  d=tile_gateway.NoRedirectOutside()
  with self.assertRaises(ValueError):d.redirect_request(None,None,302,'','','http://not-a-real-host.invalid/thing')

if __name__=='__main__':unittest.main()
