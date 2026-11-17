"""Offline parser and API tests. No fabricated content is packaged as live news."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['OBS_SKIP_NETWORK']='1'
import server

RSS=b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Research</title>
<item><title>India and maritime strategy</title><link>https://example.org/a</link><description><![CDATA[<p>An &amp; article.</p>]]></description><pubDate>Sun, 15 Nov 2026 11:00:00 GMT</pubDate></item>
<item><title>Future research record</title><link>https://example.org/b</link><description>Short</description></item></channel></rss>'''
ATOM=b'''<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015"><entry><title>Short news clip</title><yt:videoId>oHg5SJYRHA0</yt:videoId><link rel="alternate" href="https://www.youtube.com/watch?v=oHg5SJYRHA0"/><published>2026-11-15T11:00:00+00:00</published></entry></feed>'''
SRC={'id':'test','name':'Research test','tier':'analysis','region':'India','url':'https://example.org/feed.xml'}

class FeedTest(unittest.TestCase):
    def test_rss(self):
        rows=server.parse_feed(RSS,SRC)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['published'],'2026-11-15T11:00:00Z')
        self.assertIsNone(rows[1]['published'])
        self.assertEqual(rows[0]['summary'],'An & article.')
    def test_atom_video(self):
        row=server.parse_feed(ATOM,SRC,'video')[0]
        self.assertEqual(row['video_id'],'oHg5SJYRHA0')
        self.assertEqual(row['medium'],'video')
    def test_xml_invalid(self):
        with self.assertRaises(ValueError):server.parse_feed(b'<nope',SRC)
    def test_reject_private(self):
        for url in ('http://example.org/feed','https://localhost/feed','https://127.0.0.1/feed','file:///etc/passwd'):
            with self.assertRaises(ValueError):server.validate_external_url(url)
    def test_store_and_fetch_status(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(server,'DB_FILE',Path(d)/'test.sqlite3'):
                server.init_db()
                with patch.object(server,'fetch_bytes',return_value=RSS):
                    count=server.fetch_source(SRC)
                self.assertEqual(count,2)
                st=server.read_state()
                self.assertEqual(len(st['entries']),2)
                self.assertEqual(st['status']['test']['state'],'ok')
                with patch.object(server,'fetch_bytes',side_effect=OSError('network unavailable')):
                    server.fetch_source(SRC)
                st=server.read_state()
                self.assertEqual(st['status']['test']['state'],'error')
                self.assertIsNotNone(st['status']['test']['success'])
                self.assertEqual(len(st['entries']),2) # cached data retained

if __name__=='__main__': unittest.main()
