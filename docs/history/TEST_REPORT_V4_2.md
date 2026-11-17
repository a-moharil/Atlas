# Verification — 16 November 2026

## Passed
- 48 backend regression tests: source parsing, persistence, cleanup, clustering,
  India geographic aggregation, expert workspaces, satellite URL/image handling,
  minute-level refresh metrics, running-run counters, background deduplication,
  persistent cache reload, stale-on-error handling and proxy DNS safeguards.
- 11 frontend logic checks under Node: nine panel HTML renderers, visible chart
  markers for a single observation, and refresh without changing the active page.
- All packaged JavaScript files passed `node --check`; Python compilation passed.

## Live provider checks, not fixtures
- Read NASA's actual EPSG:3857 WMTS capabilities. Its response advertised
  2026-11-02 as latest for the two tested VIIRS layers. This is the metadata returned
  during this test, not a promise of provider-wide freshness.
- Corrected VIIRS true-colour .jpeg tile: HTTP 200, image/jpeg, 18,795 bytes
  at z=3/x=5/y=3 for 2026-11-02.
- VIIRS thermal WMS-rendered tile: HTTP 200, image/png, 9,933 bytes, same tile/date.
- Original combined World Bank query timed out. Isolating countries and reducing
  the query to six complete calendar years yielded 12 observations for IND and USA.
  CHN still timed out after retry. Partial results explicitly retain that error.
  The complete request took approximately 70 seconds, entirely in a background
  worker; this is not a subsecond provider retrieval claim.
- The proxy/local-DNS mismatch was reproduced through the application's fetch path
  and repaired for curated providers. Direct local DNS remained unavailable here.

## Blocked / not verified
Three existing browser tests could not launch Chromium: the environment denied
its Unix socket creation (Operation not permitted). They were not counted as
passing. Therefore no claim is made of complete browser interaction, visual
layout, GPU behaviour or sustained YouTube playback validation for this release.
The Node checks test logic, not pixels or actual browser navigation.

No exhaustive live success claim is made for the 225 configured news feeds,
Copernicus products, Comtrade, social platforms or broadcaster embedding. Their
existing failure reporting remains important. NASA can return transparent imagery
where no observations are present. An old/available satellite date is not live data.

## Re-run locally
`python -m unittest discover -s tests -p "test_*.py"`
`node tests/check_frontend.cjs`
Browser tests require Playwright and Chromium at their configured executable path;
the normal application needs only Python's standard library.
