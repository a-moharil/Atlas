"""Take a screenshot of every Atlas page for the README preview.

Run this while Atlas is running and has collected news for a while:

    pip install playwright
    python tools/take_screenshots.py

It drives a browser you already have (Microsoft Edge or Google Chrome), so no
browser download is needed. Images go to docs/screenshots/, and a gallery page
is written to docs/SCREENSHOTS.md.

Options:
    --base URL       where Atlas runs (default http://127.0.0.1:8765/)
    --only room,lm   capture only these shots (names from the list below)
    --width/--height window size (default 1600 x 1000)
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'screenshots'

# name, page, caption, seconds to wait for data, maps and embeds
SHOTS = [
    ('01-situation-room', 'room', 'Situation room: the day at a glance, with coverage spread and Earth hazards', 6),
    ('02-world-desk', 'news', 'World desk: every story with its publisher, access tag and coverage gauge', 5),
    ('03-india-desk', 'india', 'India desk: national, regional and India-in-the-world reporting', 5),
    ('04-compare-coverage', 'news', 'Compare coverage: the same story across outlets, matched by meaning', 5),
    ('05-story-card', 'news', 'A story card: masthead, bias and access tags, and the half-donut coverage gauge', 5),
    ('06-emergency-newsroom', 'emergency', 'Emergency newsroom: priority political and security updates, grouped into stories', 8),
    ('07-live-tv-video', 'media', 'Live TV and video: only streams and uploads YouTube confirms are playable', 6),
    ('08-earth-watch', 'earth', 'Earth watch: global wind field, hazards and climate anomalies', 14),
    ('08b-earth-watch-india', 'earth', 'Earth watch, India view: Windy live wind, rain and temperature', 14),
    ('09-satellite-atlas', 'map', 'Satellite atlas: imagery and hazard layers with the Survey of India boundary', 12),
    ('10-india-regional-map', 'investigate', 'India regional map: where Indian coverage is concentrated', 8),
    ('11-conflict-atlas', 'conflict', 'Conflict atlas: published maps, reporting and theatres', 8),
    ('12-geopolitics', 'geopolitics', 'Geopolitics: summits, blocs and diplomatic sources', 6),
    ('13-macroeconomics', 'macro', 'Macroeconomics: indicators, trade and energy', 6),
    ('14-article-constellation', 'constellation', 'Article constellation: a 3-D map of retrieved reporting', 10),
    ('15-research-library', 'research', 'Research library: think tanks and scholarly metadata', 6),
    ('16-mygov-policy', 'mygov', 'MyGov policy: ministries, schemes and research funding', 6),
    ('17-sources', 'sources', 'Sources: publishers, bias ratings, paywalls, primary and blocked outlets', 6),
    ('18-language-model', 'lm', 'Language model: grouping by meaning and generated labels, all on your computer', 5),
    ('19-coverage-audit', 'coverage', 'Coverage audit: feed health and collection history', 5),
]

# Hidden in every shot: transient toasts and the undo bar.
HIDE_CSS = '#wallBar,#toast,.toast,#atlasErr{display:none!important}'


def launch(p):
    for channel in ('msedge', 'chrome', None):
        try:
            return p.chromium.launch(channel=channel) if channel else p.chromium.launch()
        except Exception:
            continue
    sys.exit('No browser found. Install Microsoft Edge or Google Chrome, '
             'or run: python -m playwright install chromium')


def settle(page, seconds):
    page.add_style_tag(content=HIDE_CSS)
    page.wait_for_timeout(int(seconds * 1000))
    page.mouse.move(2, 2)  # no hover states in the picture


def capture(page, base, name, view, seconds):
    page.goto('about:blank')  # fresh load, so no drawer or shuffle carries over
    page.goto(f'{base}#{view}')
    page.wait_for_load_state('domcontentloaded')
    settle(page, seconds)
    path = OUT / f'{name}.jpg'
    if name == '04-compare-coverage':
        button = page.locator('[data-story]').first
        if not button.count():
            return None
        button.click()
        page.wait_for_timeout(2500)
    elif name == '08b-earth-watch-india':
        page.locator('[data-ewregion="india"]').first.click()
        page.wait_for_timeout(int(seconds * 1000))  # Windy loads its own map
    elif name == '05-story-card':
        card = page.locator('#main .story:has(.gauge)').first
        if not card.count():
            card = page.locator('#main .story').first
        if not card.count():
            return None
        card.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        card.screenshot(path=str(path), type='jpeg', quality=88)
        return path
    page.screenshot(path=str(path), type='jpeg', quality=86)
    return path


def gallery(done):
    lines = ['# Atlas screenshots', '',
             'Captured from a running copy of Atlas with `tools/take_screenshots.py`. '
             'Headlines and logos belong to their publishers.', '']
    for name, caption in done:
        lines += [f'### {caption.split(":")[0]}', '', caption, '',
                  f'![{caption}](screenshots/{name}.jpg)', '']
    (ROOT / 'docs' / 'SCREENSHOTS.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', default='http://127.0.0.1:8765/')
    ap.add_argument('--only', default='')
    ap.add_argument('--width', type=int, default=1600)
    ap.add_argument('--height', type=int, default=1000)
    a = ap.parse_args()
    base = a.base if a.base.endswith('/') else a.base + '/'
    try:
        urllib.request.urlopen(base + 'api/health', timeout=5).read()
    except Exception:
        sys.exit(f'Atlas is not answering at {base}. Start it first (start_windows.bat), '
                 'let it collect for a while, then run this again.')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit('Playwright is not installed. Run: pip install playwright')

    wanted = {x.strip() for x in a.only.split(',') if x.strip()}
    shots = [s for s in SHOTS if not wanted or s[0] in wanted or s[1] in wanted]
    OUT.mkdir(parents=True, exist_ok=True)
    done = []
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={'width': a.width, 'height': a.height},
                                device_scale_factor=1, color_scheme='dark')
        for name, view, caption, seconds in shots:
            print(f'  {name:28} ', end='', flush=True)
            try:
                path = capture(page, base, name, view, seconds)
            except Exception as e:  # one page failing shouldn't stop the rest
                print(f'skipped ({str(e).splitlines()[0][:80]})')
                continue
            if path:
                done.append((name, caption))
                print(f'{path.stat().st_size // 1024} KB')
            else:
                print('skipped (no articles on this page yet)')
        browser.close()
    if not wanted:
        gallery(done)
    print(f'\n{len(done)} screenshots in {OUT}')
    print('Look through them, delete any you do not want, then commit docs/ and push.')


if __name__ == '__main__':
    main()
