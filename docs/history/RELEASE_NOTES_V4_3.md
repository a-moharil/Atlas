# ATLAS SIGNAL v4.3 — MyGov, Emergency Newsroom and Conflict Atlas

This release extends v4.2. It retains the earlier refresh-history, per-page refresh, optional crime genre, satellite zoom/NASA and asynchronous macroeconomic retrieval fixes. It does not ship a prepopulated news database or synthetic news.

## Install without losing your archive

1. Stop the old ATLAS server. Extract this ZIP into a **new folder**.
2. If you want your existing archive, annotations, sources and cleanup choices, run from the new folder, before first launch:
   ```text
   python migrate_database.py "FULL_PATH_TO_OLD_FOLDER/observatory.sqlite3"
   ```
   The migration copies through SQLite's backup API and refuses to overwrite an existing destination. Keep your old folder as a backup.
3. On Windows run `start_windows.bat`. On Linux/macOS run `bash start_linux_macos.sh`. Python 3.10+ is required; backend operation uses the standard library.
4. Open `http://127.0.0.1:8765/`. Hard-refresh the browser once to reload the new scripts.
5. Open MyGov, Emergency Newsroom or ISW & conflict atlas in the navigation. Each has a dedicated refresh button. Collection runs while the server is running; it is not a cloud notification service.

Your saved MyGov favourites are browser-local. Newsroom source rules persist in the SQLite database. Genre cleanup remains global. Existing records are retained, although ingestion cleanup can omit newly encountered excluded genres.

## MyGov

Nine sections: overview, schemes, ministries, research, investment, digital infrastructure, updates, papers and source audit.

- Directory of **55 portfolios**: 53 ministries plus the Departments of Space and Atomic Energy; 81 selected scheme/funding records, including 16 doctoral/research routes; 13 digital infrastructure portals and eight budget/investment sources.
- 63 news/discovery feeds, including ministry-site searches, PMO, MyGov, PIB, ANRF, doctoral research, UPI, budget and policy evaluation. Three OpenAlex searches supply scholarly metadata.
- Ministry, domain, funding type, evidence type, publication window and text filters; PM-focused and saved-only views; direct official references.
- PMRF and other doctoral routes are distinct from investigator/institution grants. Postdoctoral opportunities are excluded from the research view. No application is labelled open without verification and no deadline is invented.
- Policy-focus hypotheses are clearly identified as hypotheses. Retrieval charts count headlines, not governmental effort or expenditure. Approved allocations are not claimed as money already spent.
- The directory is broad, **not an exhaustive register of every central/state scheme**. myScheme and ministry discovery routes provide expansion. Consult official scheme documents for current rules. Search coverage can miss unindexed releases and scholarly title filtering can miss relevant work.

## Emergency Newsroom

- Red/charcoal newsroom with a lead story, chronological rail, issue groups, publication times, source links and related headline coverage.
- Transparent rules prioritise recent political/security developments. Windows: 6, 12, 24 or 48 hours. Undated and stale items are omitted. Priority labels mean recommended reading order, not verified emergency severity.
- **Source family → publisher → feed** controls, with searchable groups and bulk include/exclude. Exclusions affect only this panel. Parent changes clear child overrides; specific choices can then override parents. Source families are descriptive, not ideological or reliability ratings.
- Version-checked saves prevent competing tabs from silently overwriting each other. A successful parent rule also applies to new matching feeds.
- Related headlines are approximate text-similarity groups, not confirmed event identity or independent corroboration. Source-region filters describe publisher coverage, not incident location.
- Gentle new-item pulses, motion-off control, reduced-motion support and pause/resume. No rapid flashing.
- Display checks the local index periodically. Dedicated refresh requests collection; the shared collector prevents duplicate simultaneous jobs. It is a research briefing, not a guaranteed real-time alert service.

## ISW & conflict atlas

- Bundled coastline data and a Canvas globe/world map: drag, zoom, theatre selection and keyboard-accessible theatre buttons. Geographic anchors are navigation coordinates, not troop locations or frontline geometries.
- Ukraine/Russia, Iran, Syria, Gaza/Israel/Lebanon, and Yemen/Red Sea research views. Four verified public ISW/CTP ArcGIS StoryMap identities are configured for Ukraine, Iran, Syria and Gaza. There is no configured embedded Yemen map; its source directory and research view remain available.
- Original published map viewers open on demand with attribution and an always-visible original link. A nonresponding frame is removed after 18 seconds. Cross-origin viewer internals cannot be certified by ATLAS; a document load is not proof every map layer rendered.
- Public item identity and ownership are checked in a cached background job, without blocking the main page. ArcGIS modification time is **not** a frontline observation timestamp.
- Four source-filtered ISW/CTP discovery feeds. Charts count deduplicated retrieved report headlines by publication date/theatre; other reporting is separated for comparison.
- Gaza carries a historical/cadence caution. Check every map's own legend and assessment date. This is not a complete global war inventory.
- No ISW shapefiles, map layers or territorial-change datasets are copied or derived. Quantitative frontline displacement or area-control analysis requires comparable dated geometry and appropriate source permissions. This release does not invent such statistics from screenshots.

## Retrieval and verification limits

Read `TEST_REPORT_V4_3.md` for actual checks. Live tests successfully retrieved ministry discovery, scholarly metadata and ISW/CTP headlines. PIB's direct RSS endpoint returned an empty channel, so its status is failure rather than fabricated success; site-filtered discovery remains available.

Browser visual testing was blocked in this execution environment: local Chromium could not create its required Unix socket, and the remote browser could not reach the local server. Thus the HTML/JS interaction logic and HTTP endpoints were tested, but full visual layout and embedded ArcGIS layer rendering are not certified. Provider timeouts and changed upstream feeds remain possible; last-good caches, bounded background jobs and visible error states handle these without presenting missing data as current observations.

Official references used by the implementation are available directly in the panels and `mygov_catalogue.json`. Earlier historical release notes remain included; this file and the current test report supersede their verification claims.
