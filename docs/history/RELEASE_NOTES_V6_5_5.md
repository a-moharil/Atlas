# Sanjaya v6.5.5: state sites that refused, and separate refresh buttons

## Reaching state sites
- State sites are now requested by `fetch_public_record` with browser-style headers.
  - Before, most state firewalls answered Sanjaya's feed-reader User-Agent with an HTTP error.
  - The User-Agent still names Sanjaya and its GitHub page.
- Plain-HTTP state sites and redirects are allowed. The public-address checks are unchanged: local and private addresses are refused.
- Errors now name what happened, e.g. "HTTP 403 Forbidden", "HTTP 404 Not Found" or "not reachable (certificate verify failed)". Before, they showed only "HTTPError".

## New source: Enhanced Voting
- Washington, Utah, Virginia, Georgia and Arizona are read from Enhanced Voting's public results API: `<site>/results/public/api/elections/<state>/<yyyymmdd>/data`.
- Washington moved from `results.vote.wa.gov` to `results.votewa.gov`, which explains its old HTTP error.
- County copies of statewide contests (`parentId`) are skipped.
- The API's `isOfficialResults` flag marks a state as certified. A certified count is the legal result, so its races count as decided even if Wikipedia hasn't updated.

## Diagnosing a state
- Every state lists each address tried and its outcome under **Each state's results site**.
- Pages that load their results with JavaScript are named as such.
- New status *Partly read*: a county-run state (New Jersey) where some county sites failed. Its counts are marked partial and show no counted percentage.

## Files
- UTF-16 files and stray NUL bytes are read correctly, and very long CSV fields no longer stop a file. This was North Carolina's "Error".

## Buttons
- **Re-read state sites** and **Re-read Wikipedia** replace **Check now**. The server accepts `refresh=states`, `refresh=wiki`, or `refresh=1` for both.

## Tests
- 5 new tests: the Enhanced Voting API and certification, per-address failure reasons, partial county sums, UTF-16/NUL files, and the fetcher plus the two buttons. 274 tests pass.
