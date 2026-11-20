# Sanjaya v6.5 · United States elections, and models only on request

## Models run only when you ask
- The India forecast and pulse no longer train or simulate when the page opens. **Run forecast** and **Run pulse** start them, which takes about a minute each.
- Results are saved and shown on later visits until the results pack changes or you run them again. The pulse no longer refreshes itself every six hours.
- Whether an election is near (seat ranges) or far (wait for more data, plus the pulse) is decided from the calendar in the results database, without loading a model.

## United States (new sub-panel)
- **House:** 1976 to 1980 and 1992 to 2026. **Senate and governors:** 2000 to 2026. **President:** 2000 to 2024, with electoral votes by state.
- **Sources:** FiveThirtyEight's election-results archive (CC BY 4.0) through 2024, downloaded on first use (about 9 MB). FiveThirtyEight closed in 2025, so its archive ends there.
- **Data handling:**
  - Fusion-ballot votes are added up per candidate, and runoffs replace the first round.
  - Louisiana's November primaries count when they produced a winner.
  - Unopposed seats are kept.
- **Checked against the record:**
  - House 2024 R 220 to D 215; Senate after 2024 R 53, D 45, I 2; governors after 2024 R 27, D 23.
  - Pledged electoral votes for 2000, 2004, 2008, 2012, 2016, 2020 and 2024 (for example 312 to 226 in 2024, 271 to 267 in 2000).
- **2026 midterms:** read from Wikipedia's results pages (`us_live.py`) while counting finishes.
  - A race is decided only when its status says so; otherwise it shows as not yet called.
  - Same-party races (California's top two) are decided by party.
  - Senate specials get their class from the state's seat history.
  - Races not yet on the page are shown as uncalled seats, so the chamber always has 435 or 100.
- **Off-year governor races after 2024:** 2023 Kentucky, Louisiana and Mississippi; 2025 New Jersey and Virginia. These are in `us_elections_extra.json`.
- **Maps:**
  - States are drawn in an Albers projection with Alaska and Hawaii as insets, shaded by margin, with seats not up faded.
  - House districts are a tile map, one hexagon per district grouped by state, built per census apportionment. It stays correct when states redraw lines, which several did in 2025 and 2026.
- **Charts:** a chamber chart with seats not up faded, and an electoral-vote bar with the 270 line.
- **Click a state or district** for its candidates, votes and margin.
- **Tables:** closest races and seats that changed party.
- **In office now:**
  - President and Vice President from congress-legislators (CC0), Cabinet from Wikipedia.
  - Per state: governor (Wikipedia), two senators and the House delegation (congress-legislators), with public-domain portraits.
  - Official websites, contact forms and Capitol office phone numbers only.
- **Forecasts for US races:** a later step; they will run only on request.

## Shared improvements
- `wikitables.py` reads abbreviated dates ("Jan 8, 2019") and "Inauguration" columns. It prefers a cell's text over a seal or portrait in the cell next to it.
- `officials.request` takes a builder, so other countries reuse the background job with progress.

## Tests
`tests/test_v65_us_elections.py`: 10 tests, plus on-request tests in the v6.4 files. Full suite: 251 tests.
