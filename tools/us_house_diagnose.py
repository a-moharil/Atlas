"""Why are House races shown as "not yet called"? Standard library only; run from the repository root:

    python tools/us_house_diagnose.py            # reads Wikipedia now
    python tools/us_house_diagnose.py --cached   # uses the copy Sanjaya last saved (election_data/us/wp_cache)
    python tools/us_house_diagnose.py --office S # Senate (G for governors)

It reads "<year> United States House of Representatives elections" the same way Sanjaya does and sorts every race
into one bucket: called by the status text, called by Wikipedia's winner tick, or not called (and why). It also
prints the most common status texts of the races left uncalled, so a wording the reader does not know is easy to
spot. The report is printed and saved to election_data/us/diagnose_<office>_<year>.txt. Nothing else is changed.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import officials as O            # noqa: E402
import us_live as L              # noqa: E402
import wikitables as W           # noqa: E402
from us_elections_data import OUT  # noqa: E402


def getter(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Sanjaya-diagnose/1.0 (local news reader)'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--office', default='H', choices=['H', 'S', 'G'])
    ap.add_argument('--year', type=int, default=2026)
    ap.add_argument('--cached', action='store_true')
    a = ap.parse_args()
    title = L.PAGES[a.office].format(y=a.year)
    html = O.wp_page(title, getter, OUT / 'wp_cache', force=not a.cached)
    out = []
    say = out.append
    tabs = [t for t in W.tables(html) if L._col(t['header'], 'candidates') is not None]
    say(f'Page: {title}  ({len(html):,} characters of HTML, {len(tabs)} tables with a Candidates column)')
    heads = collections.Counter(' | '.join(t['header']) for t in tabs)
    for h, n in heads.most_common(4):
        say(f'  header x{n}: {h[:200]}')
    races = L.parse_page(a.office, a.year, html)
    say(f'Races read: {len(races)}')
    buckets = collections.Counter()
    status_uncalled = collections.Counter()
    examples = {}
    for r in races:
        cands = json.loads(r['cands'])
        status = r.get('status_text') or ''
        said = bool(L.CALLED.search(status)) and not L.OPEN.search(status)
        if r['called']:
            key = 'called: status text' if said else 'called: winner tick only (new in this branch)'
        elif not cands:
            key = 'not called: no candidates read'
        elif L.PENDING.search(status) or L.OPEN.search(status):
            key = 'not called: status says still open'
        elif said:
            key = 'not called: status says decided, but the winner\'s party could not be read'
        elif not any(c[3] is not None for c in cands):
            key = 'not called: no status, no tick, no percentages'
        else:
            key = 'not called: percentages but no status and no tick'
        buckets[key] += 1
        examples.setdefault(key, r['id'] + '  status=' + repr(status[:90]) + '  cands=' + repr([c[:2] + [c[3]] for c in cands[:3]]))
        if not r['called']:
            status_uncalled[re.sub(r'\d+', '#', status.strip())[:90] or '(empty)'] += 1
    by_party = collections.Counter(r['winner_party'] for r in races if r['called'])
    say(f'Called: {sum(1 for r in races if r["called"])}  by party: {dict(by_party)}')
    for k, n in sorted(buckets.items()):
        say(f'  {n:4d}  {k}')
        say(f'        e.g. {examples[k]}')
    say('Most common status texts among races not called:')
    for s, n in status_uncalled.most_common(15):
        say(f'  {n:4d}  {s}')
    ticks = html.count('Green tick') + html.count('Green_check') + html.count('Yes_check')
    say(f'Tick images on the page (Green tick / Green check / Yes check): {ticks}')
    text = '\n'.join(out)
    print(text)
    dest = OUT / f'diagnose_{a.office}_{a.year}.txt'
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')
        print(f'\nSaved to {dest}')
    except OSError:
        pass


if __name__ == '__main__':
    main()
