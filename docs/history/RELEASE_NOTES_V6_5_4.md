# Sanjaya v6.5.4: 2026 counts from every state's own results site

## State counts (`us_official.py`, new)
- Election results are public records. For 2026, Sanjaya now reads the vote count from each of the 50 states' and DC's official results sites.
- Known data files are read directly: California's results API, Arizona's JSON export, Minnesota's results text files, Washington's CSV export, North Carolina's results zip and Florida's election-night file.
- Other states start from their official results page:
  - Sanjaya follows the page's links to the system behind it: Clarity, Enhanced Voting, or a CSV, JSON or ZIP file dated for this election.
  - If there are no such links, it reads results tables on the page itself.
  - New Jersey's county-run sites are added together.
- The readers cover Clarity summaries, any JSON holding candidates with votes, delimited text (comma, tab, semicolon or pipe), ZIP archives and HTML tables.
- States are read one at a time in the background, every 30 minutes while a 2026 page is open, or now with **Check now**. One state failing never stops the others. Results are cached in `election_data/us/state_counts_2026.json`.
- **Each state's results site** (under the status line) lists every state as *Read*, *Nothing readable yet* or *Could not be read*, with a link to the official site.
- You can correct a state's address without code in `election_data/us/state_sources.json`.

## Calls
- A race is shown as won only when Wikipedia lists it as decided and the state's count has the same party ahead.
- If the two disagree, the race stays uncalled and its card says why.
- A race the state reports but Wikipedia hasn't listed shows from the count, uncalled.
- Race cards name where the count and the call came from, and show precincts reporting where the state publishes it.

## Removed
- The Associated Press connector (`us_ap.py`), the AP key field on the 2026 page, the `/api/us/settings` route and their tests. Sanjaya uses no news agency's data.

## Tests
- 14 new tests:
  - Contest-title matching.
  - Every reader: Clarity, the California API, nested JSON, Washington CSV, Minnesota by county, North Carolina's precinct zip, Florida's columns and HTML tables.
  - Link discovery.
  - County sites adding up.
  - A failing state not stopping the rest.
  - Calls needing agreement.
  - The results route.
  - Every state having a source, and AP being gone.
- These replace the four AP tests. 269 tests pass.
