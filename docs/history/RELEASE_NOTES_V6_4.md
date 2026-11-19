# Sanjaya v6.4 · Who governs, and the next election

Two panels join the Elections page, under the results for the selected level and place.

## In office now
- National: President and Vice President (shown as non-party offices), Prime Minister, then the Union Cabinet (Home, Defence, Finance and External Affairs first), then Ministers of State.
- State: Governor or Lieutenant Governor, Chief Minister and deputies, then ministers.
- Municipal: Mayor and Deputy Mayor.
- Vertical, scrolling list with round photos, office, party, date in office, official contacts and source for every entry.
- Source: Wikidata, live, cached 12 hours, served stale when offline. Stale statements nobody closed are dropped when a newer holder of the same office exists.
- `election_officials.json` corrects Wikidata (`hide`, `edit`, `people`) and carries what it lacks: national fallbacks, and the mayors elected in 2026 (Mumbai, Pune, Pimpri-Chinchwad, Nagpur, Delhi) plus Chennai, each with a news source. Hyderabad and Bengaluru have no elected council at present and say so.
- Contacts are official channels only: the office's website, and email on a government domain. Personal sites, phone numbers and residences are never shown.
- Photos are Wikimedia Commons files loaded by the browser at view time, credited per file. None are stored in the repository.

## Next election
- Bagging (60 trees, depth 6, feature subsampling) and gradient boosting (150 trees, depth 3, learning rate 0.08), averaged. numpy only.
- Trained on every (seat, party) pair from assembly results since 2008: about 66,000 rows.
- Ranges: 10th to 90th percentile of 1,000 simulations, with state-wide and seat-level errors drawn from the backtest.
- Rolling-origin backtest, 2017 to 2026, 60 elections: 52% of seats called correctly (baseline "seat stays with its last winner": 48%); actual seat totals inside the range 73% of the time. Trust label: **Low**.
- More than six months before the expected poll: "Wait for more data". Within six months: ranges with the trust label. On 19 November 2026 that means Goa, Manipur, Punjab, Uttar Pradesh and Uttarakhand.
- Hidden during the ECI silence period, like other projections. No Lok Sabha or municipal forecast.
- News-coverage embeddings are not used yet; they join once a full cycle of coverage is archived.

## Fixes
- A countermanded poll held months after the general election (Karanpur, Rajasthan, January 2024) no longer appears as a one-seat "Rajasthan 2024" election; it is folded into Rajasthan 2023.

## Tests
`tests/test_v64_officials_forecast.py`: 16 tests (Wikidata parsing, official-contact filter, precedence, overrides, offline fallback, tree learning, trust tiers, a synthetic end-to-end run, time gating, silence period). Full suite: 225 tests.
