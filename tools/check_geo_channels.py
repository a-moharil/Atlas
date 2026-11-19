"""Check the geopolitics reel's YouTube channels from this computer.

    python tools/check_geo_channels.py

Fetches each channel's public upload feed and prints the channel name YouTube reports,
how many uploads are from the last 24 hours, and the newest title. A wrong channel ID
shows up as an error or as an unexpected name. Atlas does not need to be running.
"""
import datetime as dt
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = json.loads((ROOT / 'source_registry.json').read_text(encoding='utf-8'))
NS = {'a': 'http://www.w3.org/2005/Atom'}


def channels():
    cfg = REG.get('geo_reel', {})
    inc = set(cfg.get('include', []))
    return cfg.get('channels', []) + [c for c in REG['channels'] if c['id'] in inc]


def main():
    now = dt.datetime.now(dt.timezone.utc)
    bad = 0
    for c in channels():
        url = 'https://www.youtube.com/feeds/videos.xml?channel_id=' + c['channel_id']
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Atlas reel check (local)'})
            root = ET.fromstring(urllib.request.urlopen(req, timeout=30).read())
            name = root.findtext('a:title', '', NS)
            entries = root.findall('a:entry', NS)
            recent = sum(1 for e in entries if now - dt.datetime.fromisoformat(e.findtext('a:published', '', NS).replace('Z', '+00:00')) < dt.timedelta(hours=24))
            newest = entries[0].findtext('a:title', '', NS) if entries else '(no uploads)'
            flag = '' if name.lower()[:4] in c['name'].lower() or c['name'].lower()[:4] in name.lower() else '   <- name differs, check the ID'
            print(f"OK    {c['name']:<24} YouTube says: {name}{flag}\n      {recent} uploads in 24 h · newest: {newest[:90]}")
        except Exception as exc:
            bad += 1
            print(f"FAIL  {c['name']:<24} {type(exc).__name__}: {str(exc)[:120]}")
    print(f"\n{len(channels()) - bad} of {len(channels())} channels reachable.")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
