# ATLAS SIGNAL 4.2 — retrieval and refresh repairs

## Install
Stop the old server. Extract this package into a NEW folder. Copy your existing
`observatory.sqlite3` into it while both servers are stopped; keep a backup.
Run `start_windows.bat` and open http://127.0.0.1:8765/. Hard-refresh the browser
once (Ctrl+F5). The new crime classification migration runs automatically.
Optional: carry over `research_cache` after it has been created by this version.

## Changes
- Refresh-history chart shows visible markers even with only one recorded bucket.
  It uses the latest 72 active minute buckets, explicitly labelled UTC. Empty
  intervals are not filled with invented observations. Running collection counters
  are calculated from completed attempts instead of remaining zero until finish.
- Refresh content is available within every active workspace except the static CCC
  archive. It checks ALL configured feeds, keeps the current page and filters, and
  shows current collection progress. The global button remains available. Records
  and metrics poll every 15 seconds; refresh does not imply every provider succeeds.
- Crime & policing is a separate, optional cleanup category beneath Constellation.
  It is included by default. Enabling exclusion hides matching stored articles and
  suppresses matching imports. Disabling restores stored records, but cannot restore
  previously skipped new imports unless the publisher serves them again. Classifier
  is headline-based and fallible; policy/war/government articles are retained.
- NASA true-colour uses the advertised .jpeg WMTS resource. The VIIRS thermal
  product is vector in WMTS, so this canvas viewer requests NASA's rendered WMS
  PNG representation instead. No fictional heat field is generated.
- NASA availability is read from GetCapabilities. Requests newer than a layer's
  advertised latest date use that date and disclose the substitution beside the
  map. An older date does NOT become live data. Archive gaps can still be empty.
- Satellite requests have a bounded six-request gateway, per-tile failure cooldown,
  and a 26-second client watchdog so an image cannot occupy a load slot forever.
  Existing imagery, ancestor fallback and overzoom handling remain in place.
- World Bank and Comtrade now retrieve in deduplicated background jobs. Local
  requests return immediately; the client polls progress. Successful responses
  persist in research_cache and remain visible, marked stale, after a later failure.
  Retry and upstream errors are explicit. Macro requests are isolated per country,
  at most three concurrently; partial results identify country failures. The default
  query covers the six most recent completed calendar years to reduce request size.
  More historical data remain available through the official dataset link.
- World Bank and Comtrade workers allow 30 seconds per network attempt and retry
  transient network failures once. This is a socket timeout, not a guaranteed total
  deadline; queued background work never blocks navigation. Repeated failures are
  cooled down for 60 seconds; explicit Retrieve bypasses that cooldown.
- A configured HTTPS proxy can resolve shipped provider hosts if local DNS fails.
  New user-provided feed hosts still require normal public-address validation;
  known private addresses and non-HTTPS redirects remain rejected.

## Verification and limits
See TEST_REPORT_V4_2.md. Provider availability is not guaranteed. Cached values,
provider requests, successfully parsed observations and truly current information
are distinct states. Broad functionality tests do not certify all 225 feeds or
all external streaming providers. Earlier previews in this package are historical
screenshots, not evidence of this release's live operation.

## Provider specifications
https://nasa-gibs.github.io/gibs-api-docs/access-basics/
https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml
https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures
