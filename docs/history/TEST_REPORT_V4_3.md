# ATLAS SIGNAL v4.3 — verification record

Test date: 16 November 2026. These results describe this build, not a guarantee of future provider availability.

## Automated checks

- **68 Python backend/unit tests passed.** This includes existing refresh history, cleanup/crime, satellite, cached retrieval, source parsing, India/geopolitical research and MyGov tests, plus 12 new emergency/conflict tests.
- New tests cover hierarchical exclusion inheritance, publisher aliases, child overrides, parent reset, optimistic version conflicts/rollback, input validation, undated/future/stale/noise rejection, priority rules, JSON-safe headline clustering, source exclusion isolation, ArcGIS identity verification, network failure, report/context separation and exact publication windows.
- **38 frontend logic checks passed** using Node VM/DOM stubs: 11 retained checks, 13 MyGov checks and 14 emergency/conflict checks. These cover tab rendering, filters, HTML escaping, save-error visibility, globe projection/backface exclusion/wrapping, theatre selection and embedded-viewer timeout removal. They do not constitute visual browser tests.
- JavaScript syntax checks passed for the integrated navigation and new panels.
- Local HTTP smoke: 12 page/asset/API GET routes returned 200; source exclusions saved and reset across requests; all three dedicated refresh endpoints selected the correct collection scope.

Reproduce deterministic checks (standard-library Python plus Node):

```text
python -m unittest discover -s tests -p test_v43.py
python -m unittest discover -s tests -p test_mygov.py
node tests/check_frontend.cjs
node tests/check_mygov_frontend.cjs
node tests/check_v43_frontend.cjs
```

The full Python suite includes optional Playwright browser cases. All non-browser suites were run in this build; browser cases hit the environment failure below.

## Live retrieval probes

| Probe | Observed result |
|---|---|
| MyGov news/discovery | 62/63 configured feeds returned usable items; 2,423 stored records in the isolated probe before view filtering/deduplication |
| PIB direct RSS | Returned an empty RSS channel on the follow-up probe; correctly reported no usable items. Its direct endpoint is not certified working |
| Scholarly metadata | Three OpenAlex queries responded, 15 raw records each. Relevance filtering applies afterward; 45 does not mean 45 relevant papers |
| ISW/CTP discovery | 4/4 feeds succeeded; 205 records before deduplication |
| ISW map metadata | 4/4 public StoryMap identities/owners verified: Ukraine, Iran, Syria, Gaza; embedded internal layers NOT verified |
| Emergency sample | 8/8 feeds succeeded: Reuters World/India, AP, BBC World/Asia, Al Jazeera, WION, Fox; combined probe corpus produced 13 eligible candidates and 12 groups in a 48-hour window |

Live results use publisher/search endpoints and may include indexed discoveries, not direct publisher APIs. Temporary probe databases were not included in the release. Diagnostics are retained in `verification/` without article payloads.

## Browser limitation

Three existing browser suites failed to launch Chromium because the execution environment denied the Unix socket required by Chrome's process singleton. The remote browser also could not connect to the local preview (connection refused). No screenshot-based layout certification or successful embedded ArcGIS map-layer render is claimed.

The globe's projection, theatre navigation and timeout logic were tested in a simulated DOM. Its bundled coastlines remove dependence on an external basemap service, but full browser interaction remains to be verified on the user's installation. External StoryMaps have visible original links and explicit verification limits; a document load does not prove a map layer loaded.

## Retained v4.2 fixes

The current regression suite retains coverage of refresh-history single-point rendering, per-page refresh, optional crime genre, satellite cache/zoom fallback and asynchronous macro retrieval. See `TEST_REPORT_V4_2.md` for earlier live NASA and World Bank probes; those provider probes were not repeated for this v4.3 build. Macroeconomic results may remain partial if an upstream country request times out; missing data is not fabricated.

## Scope limits

MyGov is a broad ministry directory and discovery system, not a certified exhaustive government registry or verified list of currently open applications. Newsroom priority is lexical triage rather than verified severity. Conflict charts measure retrieved publication counts, never casualties, territorial gains or combat intensity. No ISW geometries were ingested or derived.
