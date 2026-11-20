# 2026 state results sources: research for the state-count readers

Researched on 2026-11-20 and built in v6.5.6 (`us_official.SOURCES` follows this table; each reader is tested on a
real response in `tests/fixtures/state_counts/`).

Sources of this research:
- Each state's own pages.
- Your v6.5.5 run (from the Netherlands).
- Two open-source projects that tested many of these addresses live in October and November 2026, both MIT-licensed:
  - `IEatDirtySocksForFun/election-watch-discord`: per-state adapters, plus trimmed real responses used below to check formats.
  - `AlexanderNicholasIvanov/who-is-running`: Clarity election ids.
- Open America's coverage list (22 states with a machine-readable count) as a cross-check.

Only official state (or state-vendor) addresses are listed. Nothing here bypasses a bot check, captcha, login or access gate. Where a state blocks scripts, it stays on Wikipedia.

## What the run and the research show

- On real samples from each state, the current general readers parsed only 4 of 28 formats (Iowa, Colorado,
  South Carolina, Florida). Most states need a small reader for their own format.
- Several 403s were for the state's *landing page*, while the data sits on another host that is not blocked:
  - Arizona: the app.enhancedvoting.com CDN.
  - Colorado, Iowa and South Carolina: Clarity's CDN.
  - Rhode Island: Amazon S3.
- Some state sites reject browser-style requests but accept a plainly named client; Ohio's API, for example, accepted
  `election-watch-discord/0.1 (+url)`. Plan: after a 403, retry once with a plain
  `Sanjaya/6.5 (+https://github.com/a-moharil/Atlas)` User-Agent. That is honest identification, not a bypass.
- Michigan and Montana time out from here. Michigan also times out from the US (election-watch-discord), so it is the
  site itself. Montana's results pages answer from the US, so it may block foreign connections.

## State by state

Legend:
- **Works**: read today.
- **Ready**: a free official feed exists and its format is known.
- **Blocked**: the state's server refuses scripts.
- **None**: no machine-readable count.
- **Later**: certified files only, published after the count.

| State | Status | Address (2026 general) | Format / reader |
|---|---|---|---|
| AL | None | — (results app has no data endpoint; Clarity /AL/ is 404) | Wikipedia only |
| AK | Ready, see note | `https://www.elections.alaska.gov/results/26GENR/ENRbyPrecinct.csv` | CSV per precinct: `Contest_title`, `candidate_name`, `Party_Code`, `total_votes`; sum per contest. First-choice RCV counts only. Note: the server sends an incomplete TLS certificate chain, so Python's verification fails; we do not turn verification off. |
| AZ | Ready | `https://app.enhancedvoting.com/cdn/results/Arizona/export-110326GeneralElection.json` | Enhanced Voting export (`results.ballotItems[].ballotOptions[]`: `name`, `politicalParty`, `voteCount`). It was reached in your run; only the old 60 MB cap stopped it (now 80 MB). |
| AR | None | `arkansas.tally-enr.com/results/arkansas/<uuid>/FullDataFile.json` | The 2026 file has contest IDs but no contest names (names come from an authenticated API), so races can't be identified. Wikipedia only. |
| CA | Works | `api.sos.ca.gov/returns/...` | CA API (current reader) |
| CO | Ready | `https://results.enr.clarityelections.com/CO/127407/` | Clarity (`current_ver.txt` → `<ver>/json/en/summary.json`). Contest names: "Representative to the 120th United States Congress - District N", "Governor / Lieutenant Governor", "United States Senator". |
| CT | Ready | `https://ctemspublic.pcctg.net/ng-app/data/Elections.json` → election 108 → `election/108/Version.json` → `election/108/<v>/Lookupdata.json` + `Electiondata.json` | Four static JSON files: offices, candidates and parties come from Lookupdata, votes from `stateVotes`. Fusion lines are merged by candidate. |
| DE | Ready | `https://elections.delaware.gov/results/enr/Election_StatewideResults_ID_GE2026.json` | A list of rows (`Contest Title`, `Party Name`, `Total Votes`, `Precincts Reported`, `Total Precincts`) |
| DC | No race | — | DC elects no House member with a vote, no senator and no governor; nothing to read. Show "no race" instead of "could not be reached". |
| FL | Ready | `https://flelectionfiles.floridados.gov/enightfilespublic/20261103_ElecResultsFL.txt` (new host) | Tab-separated, one row per candidate per county: `RaceCode` (USS, USR + `Juris1num`, GOV), `RaceName`, `CountyName`, `Precincts`, `PrecinctsReporting`, `CanNameFirst/Last`, `PartyCode`, `CanVotes` |
| GA | Ready | `https://results.sos.ga.gov/cdn/results/Georgia/export-11032026GeneralAndSpecialElection.json` | Enhanced Voting export (same reader as AZ). Names look like "Name (I) (Rep)"; strip the suffixes. |
| HI | Ready | `https://files.hawaii.gov/elections/files/results/2026/General/summary.txt` | Fixed-layout text summary (needs its own reader; checked against 2024 only) |
| ID | Ready | `https://results.voteidaho.gov/results/public/api/elections/id/nov2026/data` | Enhanced Voting API (`ballotItems`; names are lists of `{languageId, text}`) |
| IL | Ready, HTML | `https://www.elections.il.gov/electionoperations/ElectionVoteTotals.aspx` | Server-rendered page that shows the newest election; contest names like "1ST CONGRESS". The page must name the 2026 general, or the reader refuses it. |
| IN | Ready | `https://enr.indianavoters.in.gov/archive/2026General/data/settings.json` → `OffCatC_1005_<V>.json` (US House), `OffCatC_1006_<V>.json` (US Senate) | `Root.StatewideSummary.Race[]`: `OFFICE_TITLE`, `Candidates.Candidate[]` with `VOTES` and `PARTY_NAME` |
| IA | Ready | `https://results.enr.clarityelections.com/IA/127077/` | Clarity (the current reader already parses it) |
| KS | Ready, HTML | `https://www.sos.ks.gov/ent/national.html` (+ `statewide.html`) | One page per category; candidate names carry a party prefix ("D-Name"). Skip a page whose "Last Update" belongs to an earlier election. |
| KY | Blocked | `vrsws.sos.ky.gov/liveresults/` answers 403 behind an "Acceptable Use Policy" gate | Wikipedia only; respect the gate |
| LA | Ready | `https://voterportal.sos.la.gov/ElectionResults/ElectionResults/Data?blob=20261103/RacesCandidates_Multiparish.htm` + `...Votes_Multiparish.htm` | JSON despite the `.htm` name. Races and candidates are joined to votes by race and choice ID. Party comes from a "(REP)" suffix. |
| ME | None | — | Only per-contest Excel files and RCV PDFs after the count |
| MD | Later | `elections.maryland.gov/elections/archive/2026/election_data/` (`PG26_*BreakDown.csv` once certified) | Certified CSV; no election-night feed found |
| MA | None | — | No election-night feed; certified CSVs on electionstats only |
| MI | None | `mielections.us` times out (from the US too) | County Clarity sites only, which would give partial totals; Wikipedia only |
| MN | Works | `electionresultsfiles.sos.mn.gov/20261103/{ushouse,ussenate,governor}.txt` | Use `governor.txt` instead of the large all-races file |
| MS | Later | `www.sos.ms.gov/elections/electionresults/2026ElectionRecapSheets.csv` (linked from the 2026 general page once certified) | Certified recap CSV |
| MO | Blocked | Cloudflare challenge | Wikipedia only |
| MT | Ready, HTML (maybe US-only) | `https://electionresults.mt.gov/resultsSW.aspx?type=FED&map=CTY&eid=450002987` (+ `type=STATE`) | ASP.NET "Results SW" pages (same family as NE and NM). Election id from candidatefiling.mt.gov. Times out from the Netherlands. |
| NE | Ready, HTML | `https://electionresults.nebraska.gov/resultsSW.aspx?type=SW&map=CTY` and `type=CG` | "Results SW" pages |
| NV | Blocked | Imperva bot challenge | Wikipedia only |
| NH | Blocked | 403 from the CloudFront firewall; no official feed | Wikipedia only |
| NJ | Partial | County Clarity sites (the statewide results are PDFs only) | Current reader, marked "Partly read" |
| NM | Ready, HTML (403 here) | `https://electionresults.sos.nm.gov/resultsSW.aspx?text=All&type=FED&map=CTY` | "Results SW" (NM markup: name in `<h1>`, party in `<h2>`) |
| NY | Blocked | The front end answers 403; the data host has no index of contests | Wikipedia only |
| NC | Works | results zip (current) or `er.ncsbe.gov/enr/20261103/data/contest.txt` | — |
| ND | Ready | `https://api.resultsnd.sos.nd.gov/Contest/GetContestSearchList?cid=north-dakota&electionID=348` + `.../GetContestResults?cId=north-dakota&electionID=348&contestType=SW` | Two JSON files joined on `contestID` and `choiceID`; includes `isOfficial` |
| OH | Ready, may be blocked here | `https://liveresults.ohiosos.gov/Api/v1/Contest/getContestList` → `GetContestDetailsObject?contestName=..&contestObjectId=..` | JSON; district contests come as one row per county, summed. Refuses generic clients; the plain-name retry is likely needed. |
| OK | Blocked | 403 firewall | Wikipedia only |
| OR | Ready | `https://orresultswebservices.azureedge.us/ResultsAjax.svc/GetMapData?type=FED&category=SW&raceID=0&osn=0&county=0&party=0` (+ `type=SWPAR` for governor) | JSON `{d:[rows]}`, one row per candidate, with the state's own `Winner` flag |
| PA | Ready, may be blocked here | `https://www.electionreturns.pa.gov/api/ElectionReturn/GetOfficeData?...` (election 117; office 2 US Senate, 3 Governor, 11 US House) | JSON wrapped in a JSON string; the site gave 403 in your run |
| RI | Ready | `https://rigov.s3.amazonaws.com/election/results/2026/general_election/statewide.json` | `contests[]` → `candidates[]` (`name`, `party_code`, `votes`), with precincts. On S3, so not behind the ri.gov firewall. |
| SC | Ready | `https://results.enr.clarityelections.com/SC/127300/` | Clarity; names carry a party prefix ("REP Name"); `PR = 0` means reporting is not published |
| SD | Ready | `https://electionresults.sd.gov/resultsCSV.aspx?text=All&type=SWR&map=CTY` | Plain CSV (statewide races, including the at-large House seat) |
| TN | Blocked | 403 firewall; statewide results are PDFs | Wikipedia only |
| TX | Works | `electionresults.sos.state.tx.us/results.html` | Current HTML reader |
| UT | Ready | `https://electionresults.utah.gov/results/public/api/elections/Utah/general11032026/data`, or the export `app.enhancedvoting.com/cdn/results/Utah/export-general11032026.json` | Enhanced Voting (API or export) |
| VT | Ready | `https://static.electionresults.vermont.gov/elections/elections.json` → `<guid>.json` → `<guid>-f-<stamp>.json` (federal), `-s-` (statewide) | Static JSON with town rows summed by candidate id |
| VA | Ready | `https://enr.elections.virginia.gov/results/public/api/elections/virginia/2026-November-General/data` | Enhanced Voting API. The election id is fixed, because the listing has answered 404 since late October. Contest names: "Member, House of Representatives (Nth District)". |
| WA | Ready | `https://results.vote.wa.gov/results/20261103/export/20261103_AllState.xml` (or `.csv`), and the API `results.votewa.gov/results/public/api/elections/washington/20261103/data` | Export with `RaceName`, `Party` ("(Prefers … Party)"), `Votes`, `Winner`; the API is Enhanced Voting |
| WV | Ready | `https://results.enr.clarityelections.com/WV/127496/` | Clarity |
| WI | Blocked | Cloudflare; the commission publishes county-reported results only | Wikipedia only |
| WY | None | PDFs only | Wikipedia only |

### Totals

- Read today: 4 (CA, MN, NC, TX), plus NJ partly.
- Ready with a known feed: 30, though OH, PA and NM may stay blocked from the Netherlands and AK has the certificate problem. That is close to Open America's 22, which is a subset of these.
- Certified only, later: 2 (MD, MS).
- No race: 1 (DC).
- Blocked or no machine-readable count: 14 (AL, AR, KY, ME, MA, MI, MO, NV, NH, NY, OK, TN, WI, WY). Wikipedia only.

## Readers the build needs

Several states share a format, so one reader covers each group:

1. **Clarity:** CO, IA, SC, WV, and county sites for NJ.
   - Pin each state's election id.
   - Otherwise discover the id by date from `<site>/<ST>/elections.json`, which Clarity gzips without being asked.
2. **Enhanced Voting export:** AZ, GA, UT.
3. **Enhanced Voting API:** VA, ID, WA, UT. Names are lists of `{languageId, text}`; skip county copies (`parentId`).
4. **Delimited rows** (one table reader, with columns named per state): FL, DE (JSON rows), SD, AK, WA export (CSV/XML).
5. **Joined JSON:**
   - LA (races + votes)
   - ND (contests + results)
   - CT (lookup + data)
   - VT (index + files)
   - IN (settings + category files)
6. **Simple JSON:** RI, OR, OH, PA.
7. **"Results SW" HTML (ASP.NET):** NE, NM, MT. KS, IL and HI each need a small parser of their own.

Changes to contest matching:
- "Member, House of Representatives (Nth District)"
- "Representative to Congress - District N"
- "Representative in Congress"
- "1ST CONGRESS"
- "Representative to the 120th United States Congress - District N"
- "Governor / Lieutenant Governor"
- "U.S. Senator - Unexpired Term …" (special)

Strip party prefixes and suffixes from names: "REP Name", "D-Name", "Name (I) (Rep)".

Other changes:
- Read gzip-compressed responses.
- Retry once with a plain User-Agent after a 403.
- Show DC as "no race".
- Show blocked states as "This state's site doesn't allow automated reading" rather than an error.
- Every reader gets a test built from a trimmed real sample. The samples come from the MIT-licensed project and keep its notice.
