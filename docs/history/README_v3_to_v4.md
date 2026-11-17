# Atlas v5

Start with [v5 release notes](RELEASE_NOTES_V5.md). They supersede the historical notes below.

# ATLAS SIGNAL v4.3

Start with [v4.3 installation and release notes](RELEASE_NOTES_V4_3.md) and [current test results](TEST_REPORT_V4_3.md). These supersede historical claims below.

# ATLAS SIGNAL v4.2

Read [release and installation notes](RELEASE_NOTES_V4_2.md) first. They supersede earlier retrieval and verification claims below.

# ATLAS SIGNAL v4.1 — Satellite Zoom & NASA Layer Repair

This is a **targeted v4.1 maintenance release** built on v4.0. Article constellation, cleanup rules, sources, summit monitoring, broadcasts, the India desk, macroeconomic research and the CCC archive are retained.

## What was broken and what has changed

1. **Native canvas size mismatch (confirmed visual defect).** The map canvas had no explicit full-viewport CSS dimensions, so it rendered only into a browser-default 300 × 150 element. The rest of the larger panel showed its dark CSS background. The canvas now fills its map container; map controls are properly positioned.
2. **Zoom clearing imagery (confirmed algorithmic defect).** The old renderer cleared existing pixels immediately during zoom and skipped all NASA tiles above the provider's maximum tile zoom. The replacement preserves a zoom-adjusted previous frame, reuses cached ancestor imagery while fetching, and requests the highest valid source resolution before upscaling. Zooming beyond original source resolution is explicitly marked **resampled, not new detail**.
3. **No safe fallback when requests fail.** There is now a light, geographical context grid with bundled coastlines instead of a blank black screen. Failures remain visible and a ↻ button retries unsuccessful imagery. A limited browser-direct request can be attempted after the allowlisted local proxy fails; it still requires provider connectivity/CORS.
4. **NASA GIBS retrieval compatibility.** Date-dependent NASA VIIRS layers now try documented **Web Mercator WMTS** first, followed by WMS on failure. A new **NASA daily image** option (Suomi-NPP VIIRS corrected reflectance true-colour) sits beside Blue Marble and Esri satellite. The thermal-anomaly overlay remains separately toggleable; daily imagery and thermal data are not the same product. Tiles use their actual source date and remain traceable to the provider.
5. **Diagnostics are real tile checks.** The map-test button now tests whether Esri, NASA VIIRS thermal, NASA daily true-colour and NASA Blue Marble return valid image bytes. Merely obtaining a NASA WMS GetCapabilities document no longer counts as a successful imagery retrieval. Regional coverage still needs to be inspected separately; transparent thermal images can correctly contain no detections.
6. **Repeated network load and stale frontend.** The Python gateway uses a small expiring in-memory tile cache, validates returned image formats, records method/failure information and bounds concurrent duplicates. CSS/JS use `Cache-Control: no-store` so an older interface is less likely to survive an upgrade.
7. **Official alternatives.** The map includes links to NASA Worldview and Google Earth, opened in their own official sites. Google Earth is **not embedded or reverse-proxied**: Google's published usage rules prohibit embedding Google Earth in another web app. The optional Google Maps JavaScript satellite API is a separate integration requiring a Google Maps Platform key and licensing; v4.1 does not imply it is installed.

## How to install or upgrade on Windows

1. Stop v4 in its terminal (`Ctrl+C`).
2. Extract this package into a **new folder**.
3. To preserve existing article records and preferences, copy your original `observatory.sqlite3` into this folder while both servers are stopped. Do not copy the test fixtures or sample screenshots into the database.
4. Double-click `start_windows.bat` and open **http://127.0.0.1:8765/**.
5. In **Satellite atlas** choose *Satellite* for high-resolution Esri imagery or *NASA daily image* for date-dependent lower-resolution VIIRS imagery. Enable **NASA VIIRS thermal anomalies** independently, and choose an observation date. Use **Test actual NASA tiles** under environmental imagery.
6. Zoom and pan repeatedly. For very close zooms in NASA modes, the imagery will be intentionally pixelated because the source is coarser; this must not be confused with unavailable data.

## If satellite imagery still fails

- Inspect the **current visible tile counts** under the map. `pending` may mean slow loading, `failed` means the tile was not returned, and `shown` means valid image response rendered (it does **not** mean fire is present).
- Use **Test actual NASA tiles** to view the HTTP errors and format validation. The server must reach `gibs.earthdata.nasa.gov` via HTTPS; Esri similarly requires `server.arcgisonline.com`. Corporate VPNs, DNS policies, proxy authentication and provider availability can block these services.
- Switch between Esri satellite, NASA daily, Blue Marble and the independent official **NASA Worldview** viewer to isolate provider access. If only the local application fails while NASA Worldview works, capture the text of the diagnostic panel and the map date.
- NASA layers have **provider-specific maximum spatial resolution and temporal coverage**. A valid transparent thermal tile is not a wildfire heat-intensity field. NASA FIRMS' higher-frequency WMS is a separate service that requires a free `MAP_KEY` and is *not* bundled here.
- Google Earth cannot be iframe embedded in ATLAS. Official Google Maps satellite APIs can be added in a separate licensed integration; scraping their tiles is not a valid workaround.

## Verification and limits

- Original v4 unit, UI and data-regression suite retained.
- Additional tests cover NASA WMTS→WMS fallback, source validation, and the full-size renderer.
- Offline Chromium tests exercised eleven consecutive zoom-ins to z16, switched to NASA daily imagery, and loaded a thermal overlay. All test imagery was **synthetic and used only during testing**; it is not part of the application or presented as a live environmental layer.
- **Live provider availability is not verified** from this build environment, which blocks external DNS. A real NASA satellite image can only be confirmed after installing on a computer/server able to contact the NASA GIBS service. The new diagnostics will disclose failures rather than claim the layer is working.

Official technical sources:
- NASA GIBS WMTS/WMS: https://nasa-gibs.github.io/gibs-api-docs/access-basics/
- NASA GIBS resolution constraints: https://nasa-gibs.github.io/gibs-api-docs/access-advanced-topics/
- NASA FIRMS: https://firms2.modaps.eosdis.nasa.gov/mapserver/wms-info/
- NASA Worldview: https://worldview.earthdata.nasa.gov/
- Google Earth geo-use restrictions: https://about.google/brand-resource-center/products-and-services/geo-guidelines/

---

# ATLAS SIGNAL v4 — Research Constellation, Corpus Cleanup & Global Summits

**Release:** 4.0 · **Baseline event verification:** 16 November 2026 · **Mode:** local-first research server with persistent SQLite and bounded source collection.

This is a **major version**, not v3.4. It upgrades the existing v3.3 application and preserves the news desks, India investigation, macroeconomic and geopolitical research spaces, satellite map, live-news dock, source audit and compact CCC archive.

## New v4 visual research field

Open **Research → Article constellation**. This page has been redesigned as a professional, analytical *article field*, rather than a decorative node cloud:

- A native WebGL point renderer, when supported by the browser and GPU; a Canvas 2D fallback is used where WebGL is unavailable. **Both** are bundled locally without a renderer CDN.
- Projected three-axis semantic positions derived from source titles and feed excerpts, with cosine TF–IDF clustering and sparse principal-direction estimation. These are not embeddings of full articles, verified factual networks, or quantitative causal relationships.
- A rotatable camera, zoom, 3-axis reference frame, covariance-outline cluster envelopes, clickable topic labels, proximity links, individual source inspection and a corresponding article list.
- Semantic, publisher and combined views. India/world, domain, date, query, and publisher filters recompute the selected article population. Group selection highlights the corresponding subset and lists its evidence.
- GPU capabilities are hardware/browser dependent and were **not validated on the test host**; offline Chromium tests exercised the 2D fallback. The algorithmic clustering and filtering were separately tested.

### Corpus cleanup: big genre blocks beneath the constellation

The new **Clean your news universe** section offers persistent block toggles for astrology/horoscopes (enabled by default), celebrity gossip, entertainment, sports scores, lifestyle/fashion, shopping/promotions, travel/leisure, gaming and recipes/food trends.

- Click an entire genre block to toggle **KEEP / EXCLUDE**; click **Save cleanup choices** to commit changes to SQLite. **Allow all genres** disables every block and is reversible.
- Existing matching articles remain in the SQLite archive but are hidden from normal news browsing, the India map, research situations, source comparisons, and article clustering. Turn off an exclusion to see them again.
- Newly fetched matching articles are classified **before storage**, and excluded entries are omitted from the import. A small `cleanup_skips` table records unique skipped source-item IDs by genre; the displayed number counts rejected imports, **not reported real-world events**.
- Every publisher feed still gets checked on schedule. An article filter cannot avoid downloading a publisher's entire RSS feed, so this is **ingestion calibration**, not upstream request reduction or site blocking.
- The classifier uses deliberately conservative *headline-based* deterministic rules and a policy-exception heuristic. It is not a perfect classifier, and some non-news items will escape while ambiguous headlines require review. It never classifies a user's ideology or a publisher's factual reliability.
- Your original database is **not deleted or reset**, nor are excluded stories permanently removed. The app creates a `genre` field and cleanup tables in a backward-compatible migration on first launch.

### Global institutional summit register

The Geopolitical Analysis workspace now has **Global summits & agendas** and **Blocs & institutions** tabs. It holds:

- **22 dated meetings**, with date and source links, including ASEAN, ASEAN+3, East Asia Summit, Quad (explicitly *reported/unconfirmed*), APEC, EU and OSCE events, the G20 Miami summit, UN committee dates and COP31.
- **46 tracked international organisations and coordination fora**: G20, G7, BRICS, SCO, Quad, NATO, OSCE, CSTO, AUKUS, EU, ASEAN, ASEAN+3, East Asia Summit, BIMSTEC, IORA, SAARC, AU, ECOWAS, SADC, EAC, Arab League, GCC, OIC, MERCOSUR, CELAC, CARICOM, Pacific Islands Forum, OPEC, IEA, WTO, IMF, World Bank, BIS, OECD, UNFCCC, IRENA, IAEA, ITU, WHO, UNCTAD and other relevant fora.
- Family filters for **Regional blocs**, **Security partnerships**, **Economic institutions**, **Climate & energy** and **Global institutions**, plus issue and organisation selectors.
- **16 additional official-domain discovery feeds**, bringing the configured news/analysis list to **225**. Discovery uses Google News site-filtered RSS; verify any resulting claims against the linked institutional sources.
- Events and agendas are a **dated and manually curated official-document snapshot**. Auto-discovered meeting headlines are *unverified leads* and are not silently promoted into scheduled events. The directory is extensive, but not literally every global committee, bilateral summit or announced meeting.

## Quick launch / upgrade

1. Extract `ATLAS_SIGNAL_V4.zip` into a **new folder**.
2. Stop the previous ATLAS server and make a backup of your existing data.
3. If retaining the research archive, copy `observatory.sqlite3` from the previous release into the newly extracted folder **after stopping the old process**. With Docker, reuse the existing persistent SQLite volume. Do not copy a live database without a consistent SQLite backup.
4. Windows: double-click **`start_windows.bat`**, then open **http://127.0.0.1:8765/**. Python 3.10+ is required. Linux/macOS: run `./start_linux_macos.sh`; Docker: `docker compose up --build -d`.
5. Open **Article constellation → Clean your news universe**. Review your genre choices and save. Open **Geopolitical analysis → Global summits & agendas** and **Blocs & institutions**.
6. Open **Coverage audit** for real retrieval counts and source errors. **Configured feeds do not equal working feeds**. Environmental raster providers also require network connectivity.

## Testing and limitations

- `python -m unittest discover -s tests -p 'test_*.py' -v` — **37 automated tests passed**, including v4 genre suppression, reversible archive filtering and institutional registry coverage.
- An in-process local HTTP test verified `GET /api/cleanup`, `POST /api/cleanup`, `GET /api/expert-geopolitics`, `GET /api/clusters` and `GET /api/health`.
- An offline Chromium interface test verified the new constellation, cleanup controls, and geopolitical tabs **without JavaScript errors**. Its screenshots use **synthetic test headlines only**, not live records. The test browser did not expose WebGL, so GPU-specific display was not verified.
- This build environment does **not** establish that all external RSS feeds, satellite tiles or third-party live channels work on your own network. The application retains the existing source-health audit and map-provider diagnostic mechanisms.
- This release does not send news elsewhere, delete excluded articles, or provide authenticated public hosting. For continuous operation, run the server on an always-on, access-controlled host.

### API reference

- `GET /api/cleanup` — genre definitions, saved preferences, archive counts and unique new-item skips.
- `POST /api/cleanup` with `{"enabled":["astrology","sports"]}` — persist a new complete set of excluded genres.
- `GET /api/clusters?mode=semantic&focus=India&domain=Geopolitics&days=30` — filtered, three-dimensional semantic projection computed from visible entries.
- `GET /api/expert-geopolitics` — source-linked summit register, cross-bloc directory, recent diplomatic sources and co-mention leads.
- `GET /api/metrics` — actual ingestion, source coverage and retrieval audit data.

**Privacy and provenance:** Genre exclusions are stored locally. Source/publisher labels and visual similarity are *not* article-level credibility ratings. A co-mention is not evidence of cooperation; 3D proximity is not factual corroboration.

---

## Previous release notes (historical)

# ATLAS SIGNAL v3.3 — Satellite reliability + Article Constellation

This update is an **incremental upgrade of v3.2**. It retains live news, the India investigation, institutional/geopolitical analysis, macroeconomics, the source audit, video wall and CCC archive. The new research navigation item is **Article constellation**.

## What changed

### 1. Satellite atlas (self-contained renderer)

- The satellite pane no longer needs the remotely loaded Leaflet JavaScript library. A bundled HTML canvas engine handles map pan, pointer drag, scroll-wheel zoom and provider-attributed tile drawing.
- Imagery and overlay requests use **fixed local backend routes**: `/api/map-tile/{provider}/{z}/{x}/{y}`. The server may retrieve only hard-coded URLs for Esri imagery, OpenStreetMap streets, NASA GIBS and Copernicus EFFIS. No general URL proxy is exposed.
- **Basemap choices:** Esri World Imagery, OpenStreetMap streets, and a separately labelled NASA Blue Marble composite. Blue Marble is **historical satellite-derived imagery**, not a current satellite view. When Esri tiles all fail, the app attempts the NASA composite and reports that fallback.
- **Overlay choices:** NASA VIIRS thermal-anomaly image field, EFFIS fire-weather index, and EFFIS burned-area field, all sourced from provider WMS imagery. The layer selection requires actual valid PNG/JPEG provider responses. It does not create interpolated disaster fields from event points.
- NASA EONET polygon geometries and USGS ShakeMap outlines/contours are displayed **only where their APIs actually supply them**. Earthquake epicentres can be toggled separately. An earthquake epicentre is **not** a shaking-intensity field.
- **Reliability:** tile success and failure counts are recorded per provider during the current server process. Use **Test map connections** and view the detailed audit below the atlas. Server-side access may differ from browser access.
- **No deceptive offline imagery:** if neither the server nor the browser can reach imagery services, the map shows a labelled failure/outline fallback; it never manufactures a satellite photograph. Satellite basemap vintage and last successful request are different metadata. A returned empty anomaly raster should not be treated as proof of zero fires.

This approach specifically removes a major dependency that previously broke when a browser could not load Leaflet, and avoids cross-origin WMS tile access from the user's browser. However, **the local server still needs outbound internet, working DNS, TLS and any required proxy configuration**. Some public layers can be delayed, temporarily unavailable or restrict use. Test a simple map provider before relying on the environmental overlay.

Source specifications: [NASA GIBS WMS](https://nasa-gibs.github.io/gibs-api-docs/access-basics/), [NASA GIBS vector/raster behaviour](https://nasa-gibs.github.io/gibs-api-docs/access-advanced-topics/), [Copernicus EFFIS WMS](https://forest-fire.emergency.copernicus.eu/downloads-instructions), [USGS ShakeMap](https://earthquake.usgs.gov/data/shakemap/).

### 2. Article constellation (new 3D interactive research map)

Open **Research → Article constellation**. The plot is recalculated from the *stored live-source database*, not generated from a static article snapshot.

- **Semantic:** title and available excerpt text → TF–IDF representation → cosine spherical k-means. The number of clusters is determined by sample size, bounded to ten. A sparse iterative principal projection determines three axes. Nodes can be rotated, zoomed, hovered and selected. Connected nodes reflect **textual proximity only**, not agreement, causation or an inferred geopolitical relationship.
- **Publisher:** groups are exactly source labels, with a categorical layout. This does **not** infer publisher ideology or shared factuality.
- **Combined:** fill colour is semantic theme; outer node stroke encodes its publisher. The underlying article metadata retains source, date, provenance and summary for review.
- **Filters:** geographic India / rest of world / all; geopolitics, technology, finance, energy, climate, primary research or full index; 7/30/90/365-day or full-history windows; keyword searches; and per-source selection. Selecting a group lists the underlying records; selecting an article opens the existing source-grounded evidence drawer.
- **Methodological limits:** nearest-neighbour links and three-dimensional positions are approximate, computed from feed headlines/excerpts rather than full text. Near-identical documents receive a small display-only collision offset (which does not alter their assigned cluster). Visual distance should not be interpreted as a calibrated semantic confidence score. Feed records may reflect editorial selection and uneven source coverage; this is discovery, not research adjudication.

The clustering server endpoint is `GET /api/clusters`, supporting `mode`, `focus`, `domain`, `days`, `sources`, `q` and `limit` (maximum 750). Computation uses only standard-library Python; it is not dependent on a commercial embeddings service. The interactive plot is bundled JavaScript, **no external 3D renderer/CDN required**.

### 3. Interface and navigation

- More coherent navy/teal with soft violet and coral source accents, high-contrast article text and deliberate whitespace.
- The full left navigation is vertically scrollable independently of the working area, including the monitor status footer. Lower menu items remain accessible on smaller displays and when the user enlarges fonts.
- The existing adjustable font size and source-orientation methodology remain unchanged.

## Installation / upgrade on Windows

1. Extract the ZIP to a **new folder** (do not mix it into a running older release).
2. Close your previous ATLAS process (Ctrl+C in its command window).
3. If preserving news records, copy `observatory.sqlite3` from your previous ATLAS folder into the new folder **while both servers are stopped**. If the old installation has a separate Docker volume, retain that volume instead. Do not import a fixture database.
4. Double-click `start_windows.bat` and open **http://127.0.0.1:8765/**.
5. Open **Satellite atlas → Test map connections**. Open **Coverage audit** to verify that feed retrieval is actually occurring. Open **Article constellation** once real records have been collected.

Linux/macOS: `python3 server.py --port 8765` or `./start_linux_macos.sh`. Docker: `docker compose up --build -d`; a `tile_gateway.py` and `article_clusters.py` are included in the image. Bind to localhost unless secured by VPN and authentication. This app contains **no built-in public multiuser authentication**.

## Testing and verifiability

`python -m unittest discover -s tests -p 'test_*.py' -v`

This release was tested with synthetic fixtures clearly labelled as such, including UI navigation, cluster drilldown, satellite map controls, tile URL validation and rejection of WMS XML errors disguised as imagery. No synthetic headlines or metrics are supplied as live data. **External provider availability was not independently verified from this offline build environment**, so user-host DNS/HTTP diagnostics still need to succeed for the satellite image layers to be visible.

## Existing v3.2 modules

The original README continues below with documentation for the geopolitical analysis workspace, macroeconomic research, India density map, source audit, video wall, retrieval cadence, source framing and current limits.

---
# ATLAS SIGNAL v3.2 · Expert Research Workspaces

This release extends v3.1 without removing the India investigation, satellite atlas, live-news wall, technology desk, coverage audit or CCC archive.

## New geopolitical analysis workspace

- **Summit and committee calendar:** a **source-linked, date-stamped official-document register** in `expert_events.json`. The baseline is dated **16 November 2026**. It contains APEC 2026, COP31, UNGA committee sessions, and the UN Security Council's November programme, with a direct official agenda URL for each item. Dates and agendas in this file are *not automatically re-verified*. Consult the link and update the JSON when source documents are revised.
- **Automated summit/meeting discovery leads:** headline/excerpt matches from the continuing RSS collector, explicitly **not** certified as scheduled meetings until manually verified.
- **Foreign-ministry statements monitor:** official-domain discovery queries for India MEA, US State Department, China MFA, EU EEAS, Japan MOFA, Australia DFAT, United Nations bodies, and others. These are Google News **discovery feeds**, not authenticated direct ministry feeds. The panel also gives links to authoritative ministry portals and UN documents.
- **Situation updates:** source-grounded excerpts and original links, never unsourced invented short briefs.
- **Actor co-mention structures:** networks derived from retained brief texts. These are **hypotheses for investigation**, not proven meetings, causes, alignments or alliances. Source examples are linked.
- **Interpretation matrix:** topic-wise juxtaposition of distinct-source excerpts and independently available publisher-level orientation labels; it does not claim automated article-level ideology, reliability or scholarly neutrality.
- **UN and international organisation schedules:** direct links to UN General Assembly calendars, Security Council programmes, UN Digital Library, APEC, WTO, UNFCCC, ASEAN, IMF, BIS and other institutions.

## New macroeconomic research workspace

- Five tabs: **Macroeconomic overview, Global trade, Technology, Climate, Energy**.
- World Bank **Indicators API v2**, retrieved on demand from the running Python backend with an in-memory **six-hour cache**. Up to eight selected countries per chart, annual series from 2010 onward, original source links, latest observed year per country, and visible missing values. **Annual updates are not live market ticks.**
- Included indicators: GDP growth, inflation, trade/GDP, exports/GDP, high-technology export share, R&D investment, CO₂ per capita, renewable energy final-use share, net energy imports and energy use per capita.
- Optional **UN Comtrade public bilateral merchandise-trade preview**, with user-selected reporter, partner, year and imports/exports; explicitly a limited, potentially unavailable preview. Does not quietly substitute estimates when no source data arrive.
- A sector-specific source watch and links to IMF WEO (including the October 2026 release), WTO, OECD, UN Comtrade, IEA, BIS, UNFCCC.

## Running and verification

Run `start_windows.bat` on Windows (or `python server.py --port 8765` after extracting), then open `http://127.0.0.1:8765/` and select either research workspace in the sidebar. The existing collector runs every 15 minutes while the app server is running; official-site discovery feeds are included in the same status and refresh audit. Research workspace API endpoints:

- `GET /api/expert-geopolitics` — source-linked event register, institutional links, recent retrieved leads, actor/topic co-mentions and comparative evidence records.
- `GET /api/expert-macro?indicator=NY.GDP.MKTP.KD.ZG&countries=IND,USA,CHN` — official annual indicator observations or an explicit unavailable state.
- `GET /api/expert-trade?reporter=IND&partner=CHN&year=2024&flow=X` — UN Comtrade preview or explicit unavailable state.

External API hosts cannot be reached from the offline build/test environment. The browser and automated regression tests therefore use clearly isolated synthetic fixtures; production ZIP includes no fictional news or macro records. Online retrieval requires internet access on the machine running ATLAS. Neither the meeting register nor publisher orientation is promoted to verified freshness without a matching primary source.

**Data provenance:** UN session listings: https://www.un.org/calendar/en/date ; Security Council: https://main.un.org/securitycouncil/en/content/programme-work ; APEC: https://www.apec.org/ ; COP31: https://unfccc.int/event/cop-31 ; World Bank API: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api ; UN Comtrade docs: https://comtradeplus.un.org/en/api-docs .

---

# ATLAS SIGNAL v3.1 — India + World Intelligence

A **local-first, server-backed intelligence workbench** with broad news retrieval, India-focused reporting, science/technology, finance and energy, public scholarly metadata, a verified-source coverage audit, broadcaster news monitoring, and a real satellite + environmental GIS atlas.

It is **not** an exported HTML news snapshot. The interface is served by a Python backend. When the server has outbound internet access, the collector attempts RSS, YouTube Atom, and research sources, keeps indexed metadata in SQLite, and automatically refreshes. When the network is unavailable, it shows the source failures, empty states, or dated cached records. It never fabricates fresh headlines, live broadcasts, or observations.

## Quick start

**Windows**
1. Extract the entire ZIP into a folder you can keep.
2. Install Python 3.10+ from https://www.python.org/downloads/ (enable “Add Python to PATH”).
3. Double-click `start_windows.bat`.
4. In a browser open **http://127.0.0.1:8765/**.
5. Navigate to **Coverage audit**. The first collection run may take time as more than 190 configured news sources are checked. A *registered* source does not imply a *successful* source.

**Linux/macOS**
```bash
cd ATLAS_Signal_Observatory_v3_1
chmod +x start_linux_macos.sh
./start_linux_macos.sh
# Visit http://127.0.0.1:8765/
```

**Docker**
```bash
docker compose up --build -d
# Visit http://127.0.0.1:8765/
docker compose logs -f
```
The Compose file persists its SQLite database in a Docker volume and binds to localhost. Docker requires no system-level Python install. For continuous monitoring, run on an always-on host, with a VPN or authenticated reverse proxy for remote access.

The **backend** is standard-library Python. Browser maps use online Leaflet JavaScript, Esri satellite images, NASA WMS and optional Windy/Copernicus feeds; those *do* require network access and the provider to permit their use. No Google Maps API key is required; the satellite basemap comes from Esri rather than Google.

## v3.1 investigative upgrade and map repair

**Defects diagnosed and repaired:** (1) The map fallback panel had an author-level `display:grid` rule overriding its HTML `hidden` attribute and could physically obscure the satellite map. Global `[hidden]{display:none!important}` fixes this. (2) Switching view/mode could replace the Leaflet map container without first destroying the associated instance; map teardown now runs before every DOM remount. (3) The app relied on one Leaflet CDN and gave insufficient information when it failed. CDN fallback, base-tile load/fail counters, satellite→street fallback and **Test map connections** have been added. The diagnostics check Esri, NASA GIBS and India polygon hosting from your local Python server. **Browser-side tile failures remain independently visible**: a successful backend probe is not proof that your browser can render a map. Satellite tiles themselves cannot be tested in the offline build environment.

**Cross-panel filtering:** World news is now strictly World/Policy source coverage with the default **Rest of world** view excluding India-related stories. Explicit tabs permit **India in world media** or all World/Policy reports. A World-region selector covers Europe, Africa, Middle East, East Asia, Southeast Asia, Central Asia, the Americas and Oceania. India news has **All India / National / Cities & states / India abroad**, plus state and city selectors. Technology and Finance/energy remain separate topical desks. Exact same-title stories on the same date are collapsed in the reading interface, with the original records retained in the SQLite evidence database. Headline clustering is intentionally conservative; it does not merge dissimilar editorials into an apparent consensus.

**India regional investigation:** A dedicated **India investigation** navigation view now shades each Indian state/territory with a peach-to-red scale by the count of distinct *retrieved, geographically attributed news stories* over 1, 7, 30 or 90 days. Topic and location-confidence filters are provided. Clicking a region displays publisher-excerpt briefs and links to the underlying source. The field is a news **coverage intensity** measure, NOT measured real-world event incidence or geographic risk. A headline location receives stronger evidentiary status than an excerpt location, which is stronger than a geographically scoped RSS query. The latter can be excluded. One article may name multiple states, and a state may have zero coverage because its feeds are unavailable. Source-distribution and political-leaning biases in publisher selection influence this map. **This is not a district crime or climate-intensity map.**

**Actual boundaries vs fallback:** The server exposes `/api/india-boundaries`, which retrieves/caches a 36-state/union-territory polygon dataset from GeoDataViewer/DataMeet (CC BY 2.5 India), avoiding common browser CORS issues. Its underlying boundary vintage is historical; it is not an official legal/survey record. If retrieval fails, an interactive locally bundled country-clipped approximate Voronoi analysis-zone map is displayed and **explicitly marked not administrative boundaries**. The fallback is spatially informative but less precise. The real map depends on the original provider being reachable at least once. The attribution remains visible.

**Windy is now below the India investigation map and below the global atlas**, not used as a replacement for either. The official embed URL and selector offer wind, rain and temperature field views; map providers still control embedding permissions.

**Source expansion:** 71 new city- and state-oriented discovery feeds and 29 global regional outlets cover far more of India and the international world than before. These are configuration entries, not guaranteed healthy upstream subscriptions. Local geography-scoped sources poll no more often than once per hour during ordinary cycles to reduce Google News throttling; **Refresh feeds** explicitly forces them too. 5 YouTube upload feeds and 4 scholarly searches remain. Source health and completed retrieval attempts are displayed in Coverage audit. This version stores local geographic analysis results by computing them from the existing SQLite history, so it does not require a separate event datastore.

**Migration:** If you already have a populated `observatory.sqlite3` from v3, stop the old server, then run:

```
python migrate_database.py "C:\path\to\old\ATLAS_Signal_Observatory_v3\observatory.sqlite3"
```

The migration utility refuses to overwrite an existing destination database. On Docker, reuse an existing named volume or import the previous database manually. The ZIP does not contain live collected headlines or user data.

**Test status:** 21 regression tests pass, including an offline interactive India region map and story drill-down, cross-panel filtering, server ingestion and source failures, and uninterrupted player navigation. The illustrative screenshot in `previews/india_investigation.png` is **marked fictional** and must not be interpreted as real headline coverage.

---

## What's new in v3.1

- **192 configured news/analysis RSS feeds** across World (49), India (87), Technology (17), Finance (16), Research/analysis (12), Climate (5), Energy (4), Policy (2). These are *configuration counts*, not proof of successful feeds. Some sources are Google News publisher-filtered discovery proxies rather than publisher-owned RSS. The registry also contains **5 YouTube Atom upload channels** and **4 OpenAlex scholarly searches**, giving **201 configured periodic retrieval endpoints**. **5 broadcaster live-stream status checks** are separate from the 201.
- **News desks:** Situation room; World news; India desk; Technology; Finance and energy. Search and source-level political leaning controls do not remove disfavoured viewpoints by default.
- **Coverage & refresh audit:** SQLite source-attempt ledger, successful/failed checks, returned feed items vs *newly inserted unique records*, request latency, most recent successful retrieval, source errors, completed collection runs, hourly refresh graph, registered vs successful source distribution and 14-day publication-frequency distribution. Click **Refresh feeds**, then watch the run and audit update when it actually finishes. The server heartbeat is *not* the same as feed success.
- **Persistent five-broadcaster video wall:** DW News, WION, CNN-News18, NDTV and Reuters. ATLAS checks official YouTube broadcaster live pages rather than assuming the most recent upload or a past livestream is presently live. Only a confirmed active stream gets **LIVE VERIFIED**. If verification fails, use the official broadcaster live page or an explicitly *unverified* previous stream. Reuters and others may not broadcast continuously. The floating player remains mounted while you move between news desks, so it is not restarted by the dashboard's news refresh.
- **Satellite atlas:** a real pan/zoom Esri World Imagery satellite map, optional OpenStreetMap basemap, NASA GIBS VIIRS thermal-anomaly raster by observation date, optional Copernicus EFFIS fire-weather and burned-area WMS overlays (subject to provider availability), EONET polygons where source geometries exist, USGS recent earthquakes with per-earthquake original ShakeMap MMI intensity contours if provided, and official Windy wind/rain/temperature field embeds.
- **Academic/analysis focus:** ORF, Takshashila, E-International Relations and other policy institutes; OpenAlex paper searches. Summaries are limited by the retrieved source text, not hallucinated full-article analyses.
- **CCC remains a compact archive:** original June 2025 PDF and a dated, static proposition record. It is one research view, not the dashboard's overarching political interpretation.

## Reading the coverage statistics

The **Configured endpoints** card measures registry entries. It is a target, *not* actual present coverage. **Last-check successful** counts sources whose *most recent attempted retrieval* succeeded. **Stored records** counts retained distinct items. **Returned items** counts all articles an RSS provider supplies, including already-seen items. **New records** counts only new database insertions. Re-running a static feed should increase returned items but not new inserts. **Failed** source checks remain in the history with error and latency. **Publication frequency** uses available source publication timestamps from records retrieved within the last 14 days; it is **not** the total volume actually published by that publisher.

The plot is based on completed ingestion attempts logged to the persistent `ingestion_attempts` table. It is not an animated placeholder. If the chart stays blank, check the server terminal, network connectivity, provider access and source table. No service is shown as healthy solely because the browser can reach `localhost`.

Collection is scheduled every **15 minutes** while the server runs (`OBS_REFRESH_SECONDS=900`, min 300); scholarly searches use a slower cadence. Browser state checks the local backend every **15 seconds** (the database changes only when retrievals actually finish). Channel live status is checked at a separately rate-limited interval (`ATLAS_LIVE_REFRESH_SECONDS=900` by default). Concurrent requests can take more than one browser polling interval to complete. Do not expose public port 8765 to the internet.

## Video and social platform limitations

A YouTube *channel* does not guarantee a publicly embeddable, continuous live broadcast. The official YouTube `/live` page is checked for affirmative live status; network restrictions, anti-bot systems, upstream changes, copyright/geographic restrictions and publisher iframe settings can prevent verification or playback. An unverified stream is **not** presented as verified live. When verified, YouTube provides playback; the app does not rehost or download copyrighted videos. Native direct MP4/WebM files can be played if you supply them and have the necessary rights. X may require sign-in and is not presented as a free searchable global feed; public Bluesky uses its public API.

## GIS and environmental methodology

- **Esri World Imagery** provides actual photographic satellite base tiles. Data credit remains visible on the map. Esri imagery is not necessarily today's imagery.
- **NASA GIBS VIIRS** provides satellite-detected thermal-anomaly *pixels*, not estimated burned area, wildfire heat-flux magnitude, fire-weather danger or active fire-perimeter polygons. Select a satellite observation date; imagery can arrive with delay or be incomplete on the current date.
- **Copernicus EFFIS** fire-weather fields describe meteorological **fire danger**, not a measured active wildfire intensity; burned-area products are separate. Third-party WMS may fail or change layer names without notice; the official EFFIS viewer is linked as a fallback.
- **NASA EONET** event geometries are used exactly as supplied. If only a representative point is provided, it does not become an invented wildfire polygon.
- **USGS** earthquakes may appear as optional epicentre points, but impact-area/ground-shaking views load **official ShakeMap Modified Mercalli Intensity contours** for a chosen event, if available. An earthquake's magnitude is not an intensity field.
- **Windy** provider-hosted maps render wind/rain/temperature **weather/forecast fields**. These should not be described as climate trends or climate-change attribution.

Remote satellite and overlay providers must be online in the *browser*, and API datasets must be reachable by the *Python server*. Provider fees, CORS, WMS revisions, terms and uptime can change. ATLAS explicitly displays map errors rather than drawing artificial impact surfaces.

## Source framing and intellectual integrity

The source orientation shown on story cards is a **publisher-level** classification drawn from named, linkable AllSides profiles *only where covered*. Most publishers, especially Indian and academic outlets, remain **Unrated** rather than being assigned a fictitious political leaning. The original rating provider's US-oriented left/right taxonomy is imperfect for Indian and international contexts. Ratings are not independent assessments of an individual article, author, neutrality or factual reliability. The article brief is derived only from feed metadata and excerpt; full article analysis requires user-supplied text or an explicitly invoked optional model call. Correlated headlines are not proof of independent corroboration.

Some RSS feeds carry headlines and excerpts only. Source-oriented summaries are therefore intentionally limited, with the evidence basis shown. This is not a general automated, paywall-bypassing full-text crawler.

### Optional AI research analysis

Set `ATLAS_OPENAI_API_KEY` *on the local server*, never in browser source code. This activates optional, user-triggered analysis when supported; the model is a separately billed API service and output must be verified. The rest of ATLAS works without this credential. Do not send material without appropriate access or rights.

## Security and architecture

- Personal local server with no built-in user authentication. Bind to `127.0.0.1` and use a VPN/authenticated proxy for access from elsewhere.
- Python standard library backend: `server.py` and ingestion/metrics `atlas_v3.py`; environmental source logic `atlas_plus.py`; optional model comparison `analysis_api.py`.
- Local SQLite default `observatory.sqlite3`; Docker uses `/storage/observatory.sqlite3`. **A populated database is not included**. Retained records persist across application restarts when using the same folder/volume.
- HTTP API includes `/api/health`, `/api/state`, `/api/metrics`, `/api/map-geojson`, `/api/shakemap`, `/api/live-channels` plus POST actions for `/api/refresh` and `/api/refresh-live`.
- Source configuration: `source_registry.json`; publisher provenance `static/publisher_profiles.json`; CCC documents `static/CCC_June_2025.pdf` and `static/ccc_snapshot.json`.
- Frontend: `static/index.html`, `static/atlas3.css`, `static/atlas3.js`; `static/legacy_v2.html` remains as a reference to the prior interface.
- Sanitised, restricted source addition for public HTTPS feeds. Do not deploy without further security hardening and review.

## Testing / external validation

Run the standard library test suite:
```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```
The browser UI test requires Playwright/Chromium and is skipped when unavailable. The build was tested with **21 passing regression tests**, including synthetic RSS feed deduplication, real request-log accounting, failure preservation, accessible UI navigation and media persistence. The synthetic test articles remain in temporary test databases and **do not ship as real news**.

**Network constraint at build time:** This build environment could not contact the external publishers and satellite services. The code and offline tests passed, but upstream live connectivity, current livestream verification and real satellite tile rendering can only be checked on an online installation. Upon first launch check the Coverage audit table and visible provider errors before relying on the output.

## Common troubleshooting

| Symptom | Meaning / action |
|---|---|
| Browser says server offline | Start the Python application and open the exact localhost URL. |
| `201 configured; 0 successful` | This does **not** mean live news is running. Wait for the first collection; inspect the source error table. Check DNS, proxies, TLS and external source availability. |
| Refresh graph empty | No completed source attempts yet, or server running with `OBS_SKIP_NETWORK=1` in testing. |
| Google News feed returns 403/empty | Regional rate limits or provider changes; use official publisher sources where possible. |
| Live video unverified | Channel not currently streaming, geo-locked/embedding disabled or official page inaccessible. Open original channel live URL. |
| Satellite map blank | Leaflet CDN or Esri tiles blocked. Online browser and permitted map provider access are required; use original NASA/USGS/Windy/EFFIS linked viewers. |
| Earthquake intensity contours unavailable | USGS has not published a ShakeMap or its source endpoint is inaccessible. Do not substitute a generated intensity ring. |
| Source count not 192 | Custom feeds may have been added, or registry updated. Registered totals change accordingly. |

---

ATLAS SIGNAL | Research tool, not a news certification service. Source coverage, recency, quality and external provider licensing must be verified independently.
