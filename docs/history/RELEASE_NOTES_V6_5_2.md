# Sanjaya v6.5.2 · Associated Press for 2026, and lean shading

## Associated Press (`us_ap.py`)
- AP's election results and race calls are licensed and need an AP Elections API key. Paste a key into the field on any 2026 US page; Sanjaya stores it in `observatory.sqlite3` and never returns it to the page. **Remove AP key** clears it.
- With a key, AP is read first: House, Senate and governor races in one request, kept for two minutes and refreshed every two minutes while the page is open. Wikipedia fills only the races AP has not returned. Without a key, Wikipedia is used as before, read every six hours or now with **Check now**.
- A race is called only when AP marks a winner. If AP advances it to a runoff, it stays uncalled and the card says so. Each race card shows its source and, from AP, roughly how much of the expected vote is counted.
- If AP is unreachable or refuses the key, the page says why and shows the last races AP returned.

## Lean shading
- A race that has not been called is striped in the colour of whoever is ahead, with a dashed edge, on the state map, the House tiles and the chamber chart. Races with no count yet are grey stripes.
- The party list adds "Not yet called" rows, for example "Democratic ahead 12". The tally line reads "Democratic: 210 called + 12 ahead". Leads are never counted as wins.

## Tests
4 new tests in `tests/test_v65_us_elections.py`, with an AP-shaped fixture of fictional races. They cover AP calls, leads and runoffs; AP taking priority over Wikipedia; no request without a key; and the key staying server-side. Full suite: 257 tests.
