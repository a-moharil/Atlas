# Sanjaya v6.5.6: every state's researched source, and news coverage as a third source

## State sites (`us_official.py`)
- Each state now uses the source researched in `docs/STATE_RESULT_SOURCES_2026.md`, with one reader per format family:
  - **Clarity:** CO, IA, SC, WV. Election ids are pinned, or found by date in `elections.json`, which Clarity gzips.
  - **Enhanced Voting export:** AZ, GA, UT.
  - **Enhanced Voting API:** VA, ID, WA, UT. Names come as multilingual lists, and `isOfficialResults` marks a state as certified.
  - **Data files:** CA, MN (now `governor.txt`), NC, FL (new host), SD, AK, DE, HI.
  - **One reader each:** RI, OR, LA, ND, CT, VT, IN, OH, PA.
  - **Results pages:** NE, NM, MT ("Results SW"), KS, IL, TX.
- Contest names newly recognised:
  - "Member, House of Representatives (1st District)"
  - "1ST CONGRESS"
  - "United States House of Representatives 1"
  - "Dist I"
  - "First District"
  - "Governor / Lieutenant Governor"
- Party marks are stripped from names: "REP Name", "D-Name", "(D) NAME, First", "Name (REP)", "Name (I) (Rep)". "Last, First" is reordered.
- States that refuse scripts, publish no machine-readable count, publish only after certification, or have no race are not fetched. They show as *Doesn't allow automated reading*, *No machine-readable count*, *Certified files only, after the count* or *No race this year*, with the reason.

## Requests
- After a 403, 405 or 406, the request is retried once with a plain `Sanjaya/6.5` User-Agent.
- Timeouts and certificate failures are reported in plain words. A timeout notes that the site may not accept connections from outside the US.
- The download cap is now 80 MB (Arizona's export is larger than 60 MB).

## Third source: news coverage (`us_coverage.py`)
- **Search news coverage** looks, for races with no state count, through the articles in Sanjaya's database.
  - Articles are ranked against a description of each race with the language model's stored embeddings, or by matching words when the language model isn't installed.
  - It reads vote counts and shares next to each candidate's surname, and "X leads Y 52% to 46%" pairs. "N% of the vote counted" is read as the counted share, never as a candidate's.
  - It prefers the most recent article that cites the official count.
- Labelled with the publisher and date. It never calls a race and never overrides a state count. Where it contradicts a Wikipedia call, it is set aside, with a note.
- It runs only when asked. The answer is kept in `election_data/us/coverage_2026.json`.

## Tests
- 18 new tests, using real state responses copied from election-watch-discord (MIT; credited in `tests/fixtures/state_counts/README.txt`).
- 291 tests pass.
