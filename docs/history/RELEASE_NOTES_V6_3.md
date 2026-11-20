# Sanjaya v6.3: Elections, phase 1

Branch: `sanjaya-elections`

## What's new

A new **Elections** page (sidebar, under Monitor) with sub-panels for India, the United States and Israel. India is built first; the other two are placeholders.

### India: three levels

- **Lok Sabha:** 2009, 2014, 2019 and 2024.
- **State assemblies:** every state since the 2008 delimitation, up to the 2026 round, including the 2022 results for Uttar Pradesh, Punjab, Uttarakhand, Goa and Manipur, which vote again in 2027.
- **Municipal corporations:**

| Corporation | Last election | Status |
|---|---|---|
| Mumbai (BMC), Pune, Pimpri-Chinchwad, Nagpur | January 2026 | — |
| Delhi (MCD) | 2022 | — |
| Chennai | 2022 | — |
| Hyderabad (GHMC) | 2020 | Since split into three corporations; next election not yet scheduled |
| Bengaluru (BBMP) | 2015 | Replaced by five Greater Bengaluru corporations; elections due by 31 December 2026 |

Every municipal tally sums to the council size and cites its source.

### On each election

- **Parliament chart:** one dot per seat, grouped by alliance or party, with the majority line. The outer arc shows seat share and the inner arc vote share.
- **Coalition tester:** click parties to see whether together they reach a majority.
- **Constituency map:**
  - The national map is drawn inside the Survey of India outline; state maps inside the Survey of India state boundary.
  - It can be coloured by winning party, by margin, or by seats that changed hands since the previous election.
  - Hover for winner and margin; click for the full contest.
- **Equal-area hex map:** one hexagon per seat.
- **Tables:** seats and vote share with the change from the previous election, the closest contests, and seats that changed hands.

### Data pack, downloaded on first use

About 36 MB from GitHub, built into `election_data/` (git-ignored), in about 10 seconds:

- **Results:** TCPD Lok Dhaba (Ashoka University) and in-rolls/eci_results, both from ECI statistical reports.
- **Constituency boundaries:** DataMeet.
- **India boundary:** the Survey of India outline Sanjaya already ships.

### Checks against published figures

| Election | Totals checked |
|---|---|
| Lok Sabha 2024 | NDA 293, INDIA 234, BJP 240 |
| Uttar Pradesh 2022 | NDA 273, SP alliance 125 |
| Maharashtra 2024 | Mahayuti 230, MVA 46 |

Mumbai North West is the closest contest of 2024, decided by 48 votes.

### Honest edges

- **Maps checked against results:** each election's map is checked against its results by constituency name. Where boundaries were redrawn (Assam 2026, Jammu and Kashmir 2024), there is no map, and the page says why.
- **Map gaps are named:** Gujarat's source lacks 20 city seats, and 5 redrawn Assam seats are left off the 2024 Lok Sabha map. The page lists both rather than drawing them on the wrong shapes.
- **Renamed parties:** codes are mapped across years, so a renamed code isn't counted as a seat changing hands. Examples: Apna Dal (Soneylal) is ADAL then ADS; TRS became BRS.
- **Blackout windows:** a guard for the Election Commission's windows is built in (`election_blackout.json`, sections 126 and 126A of the Representation of the People Act 1951). Polls and projections in the next phase must pass through it.

## Not in this phase

- **Polls and projections:** opinion polls, exit polls with pollster track records, and projection ranges. Next phase, before the 2027 round.
- **US and Israel sub-panels.**
- **Municipal ward maps and ward-level results:** the public ward boundaries don't match the delimitation used in these elections.

## Files

- **New code:**
  - `elections.py`
  - `elections_data.py`
  - `geo_shapes.py`
  - `static/elections.js`
  - `static/elections.css`
- **New data files:**
  - `election_parties.json`
  - `election_alliances.json`
  - `election_municipal.json`
  - `election_blackout.json`
- **Changed:**
  - `server.py`: four routes
  - `static/atlas3.js`, `static/index.html`: page registration, sidebar entry
  - `.gitignore`
  - `README.md`: section 5.3b, feature table, credits, project layout
- **Tests:** `tests/test_v63_elections.py`, 27 tests. A synthetic two-seat pack exercises the whole pipeline, and published totals are checked when the real pack is present. All 208 tests pass.
