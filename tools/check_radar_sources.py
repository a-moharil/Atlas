"""Check that every research radar source can be reached from this computer.

    python tools/check_radar_sources.py

Sends one small request to each source (arXiv API, arXiv RSS, Hugging Face,
OpenAlex, Crossref, OpenML, the deadlines dataset) and prints what came back.
Atlas does not need to be running. If you saved an OpenAlex key in Atlas, it is used.
"""
import sqlite3
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import research_radar  # noqa: E402

UA = 'Atlas research radar (local, https://github.com/a-moharil/Atlas)'


def fetch(url, max_bytes=None):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json, application/xml, */*'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read((max_bytes or 8_000_000) + 1)


def db_connect():
    con = sqlite3.connect(ROOT / 'observatory.sqlite3')
    con.row_factory = sqlite3.Row
    return con


def main():
    use_db = (ROOT / 'observatory.sqlite3').exists()
    print('Checking research radar sources from this computer…\n')
    results = research_radar.probe(fetch, db_connect if use_db else None)
    width = max(len(r['source']) for r in results)
    for r in results:
        mark = 'OK  ' if r['ok'] else 'FAIL'
        print(f"  {mark}  {r['source']:<{width}}  {r['ms']:>6} ms  {r['detail']}")
    bad = [r for r in results if not r['ok']]
    print()
    if not bad:
        print('Every source answered. The radar can fetch on this computer.')
    else:
        print(f'{len(bad)} source(s) did not answer. Common causes: no internet, a firewall or proxy, or a temporary outage.')
        print('The radar keeps working with the other sources and retries the failing ones on its schedule.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
