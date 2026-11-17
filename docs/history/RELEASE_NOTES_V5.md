# Atlas v5 — glass interface, publisher intelligence, Earth watch

v5 builds on v4.3. Every desk, research workspace, the MyGov observatory, the emergency newsroom and the conflict atlas are retained. This file supersedes earlier notes where they disagree.

## Install or upgrade

1. Stop the old server and extract this folder somewhere new.
2. To keep your archive, preferences and source rules, run once before the first launch:
   `python migrate_database.py "FULL_PATH_TO_OLD_FOLDER/observatory.sqlite3"`
   The database gains an `origin_host` column and three small tables (`source_prefs`, `video_status`) automatically.
3. Windows: `start_windows.bat`. Linux/macOS: `bash start_linux_macos.sh`. Docker: `docker compose up --build -d` (the Dockerfile now copies every module; v4.3's image was missing several).
4. Open http://127.0.0.1:8765/ and hard-refresh once.

## What changed

**Interface.** A new shell and design system: frosted glass panes over a deep ink-teal "orbital" backdrop, Schibsted Grotesk for the interface, a strict radius hierarchy, line icons, sentence-case labels and a responsive layout down to phone width. Fonts are bundled (SIL Open Font Licence); no CDN is required. Leaflet is no longer loaded.

**Sources page (new).** Every publisher Atlas reads, with its logo (fetched from the publisher's own site, cached in `logo_cache/`), its name set in a masthead-style typeface, outlet-level bias, factuality, ownership, state-media flag and paywall model.
- **Primary** publishers lead every desk (toggle "Primary first") and appear as a clickable strip at the top of the Situation room, World, India, Technology and Finance desks. Clicking a chip filters the desk to that publisher.
- **Block** is global: the publisher's feeds are skipped during collection, items it publishes through Google News are dropped at ingestion, and stored stories are hidden from every page including the emergency newsroom, India map, constellation and research views. Unblocking restores them; nothing is deleted.

**Bias spread per article (Ground News style).** Headlines from different publishers are grouped into stories. Each card shows a half-donut of the left / centre / right share of outlets covering that story, with a needle at the publisher's own rating. "Compare coverage" opens the full spread and every matching headline. Ratings come from Media Bias/Fact Check and AllSides (verified November 2026 for the Indian outlets), averaged when both exist. They describe outlets on a US-derived axis, not articles.

**Paywalls.** Every publisher is classified Free, Registration, Metered, Some paywalled or Hard paywall, and individual articles whose URLs the publisher marks as subscriber-only (Express Premium, Mint Premium, ET Prime, TOI+, CNBC Pro and similar) are tagged Subscriber-only. Desks can hide paywalled stories. Paywall models change; the classifications are dated in `publishers.json`.

**Google News discovery feeds.** Atlas now records the real publisher behind each Google News item (`<source url>`), so those stories get logos, ratings, paywall tags and blocking too.

**Video.** Only videos YouTube's oEmbed endpoint confirms are public and embeddable are listed; removed, private and embed-blocked uploads are hidden and counted. The live wall shows only streams verified live, plus checked recordings; channels that are off air collapse into a row of official links. A v4.3 bug (`timeout` undefined) made every live check fail; it is fixed.

**Emergency newsroom.** Rebuilt layout: lead story, two-column priority grid, sticky chronological timeline, issue chips, publisher logos, coverage gauge and "also reporting" outlets on each card.

**Maps of India.** The India regional map now uses the Survey of India state map published by DataMeet (36 states and union territories, Ladakh and Jammu and Kashmir as union territories, the external boundary as on the official map of India), bundled in `static/data/`. The old "approximate zones" fallback and the remote GeoDataViewer download are gone. The Satellite atlas overlays the same official outline on every basemap, because OpenStreetMap tiles draw de-facto lines.

**Earth watch (new).** Animated wind (and ocean-current) particles, temperature and rainfall fields from Open-Meteo for the globe or India, hazard markers from GDACS, NASA EONET and USGS with alert levels and filters, and the daily global air and sea-surface temperature anomaly from Copernicus Climate Pulse (ERA5). The India map's embedded Windy frame is replaced by links into this view.

## Verification

- `python -m unittest discover -s tests -p "test_*.py"`: 84 tests pass, including the three Chromium interaction tests (no skips when Chrome or Chromium is installed). New `tests/test_v5.py` covers publisher resolution, rating averaging, premium-URL detection, story spread, block filtering, oEmbed states, hazard/climate/field parsers, logo safety and the official boundary.
- `node tests/check_*.cjs`: 38 frontend checks pass.
- The interface was exercised in Chrome against a server with a synthetic test database (never shipped).
- **Not verified from the build machine:** live responses from news feeds, YouTube, GDACS, NASA, USGS, Copernicus, Open-Meteo or publisher logo sources, because outbound access was blocked. Parsers follow each provider's documented format; any provider that changes format shows as unavailable rather than inventing data. Open-Meteo's free tier is generous but rate-limited; fields are cached for 90 minutes and fetched only when Earth watch is opened.
