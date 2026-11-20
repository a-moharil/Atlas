# Elections in Sanjaya: India, the United States, and the models

This guide explains the **Elections** page in full:
- where every number comes from;
- what each view shows;
- how the statistical models work, step by step;
- how far to trust them.

The README has the short version (section 5.3b onward).

Five rules hold everywhere on the page:

1. **Results, not calls.** Sanjaya shows results as declared or counted. It never declares a winner itself.
2. **Models are labelled.** Every model output is marked as a model, not a poll, with a trust label from its own backtest.
3. **Models run only when you ask.** Opening the page trains or simulates nothing. You press **Run forecast** or **Run pulse** (India) or **Search news coverage** (US 2026). The answer is saved until you ask again.
4. **The Election Commission's silence period is respected.** Projections are hidden during notified blackout windows.
5. **Maps follow official boundaries.** India maps are drawn inside the Survey of India boundary. Contacts for office-holders are official channels only.

## Contents

1. [India: data](#1-india-data)
2. [India: what the page shows](#2-india-what-the-page-shows)
3. [India: who is in office now](#3-india-who-is-in-office-now)
4. [The seat forecast (elections within six months)](#4-the-seat-forecast-elections-within-six-months)
5. [The pulse (elections further away)](#5-the-pulse-elections-further-away)
6. [How far to trust the models](#6-how-far-to-trust-the-models)
7. [The United States](#7-the-united-states)
8. [What Sanjaya does not do](#8-what-sanjaya-does-not-do)
9. [Files and settings](#9-files-and-settings)

---

## 1. India: data

The results pack is downloaded once, the first time you open Elections (about 36 MB, from GitHub). It is stored in `election_data/`, which is never committed.

| File | What it holds | Source and licence |
|---|---|---|
| `All_States_AE.csv.gz` | Assembly results, every state, to May 2023 | TCPD Lok Dhaba, "TCPD Indian Elections Data v2.0", Trivedi Centre for Political Data, Ashoka University (free and open use, with citation) |
| `All_States_GE.csv.gz` | Lok Sabha results to 2019 | TCPD Lok Dhaba (as above) |
| `AE_2023_2026.csv.gz` | Assembly results, November 2023 to May 2026 | `in-rolls/eci_results`, built from Election Commission of India statistical reports (MIT) |
| `GE_2024.csv.gz` | Lok Sabha 2024 | `in-rolls/eci_results` (MIT) |
| Constituency maps | Assembly and parliamentary constituency shapes | DataMeet community maps |
| India and state outlines | The boundary drawn around every India map | Survey of India |

Both result sources come from the Election Commission's own statistical reports. Each row is a candidate in a constituency: votes, vote share, party, turnout, number of candidates and reserved-seat status (SC/ST). Sanjaya builds them into `election_data/elections.sqlite3`.

Two corrections are made while building:
- A countermanded poll is folded into the previous election.
- Party codes that changed name are joined, so a party's history reads as one line. For example ADS→ADAL, AAP→AAAP, AIADMK→ADMK, TRS→BRS, JKNC→JKN and NPP→NPEP.

Municipal corporations (Mumbai, Pune, Pimpri-Chinchwad, Nagpur, Delhi, Hyderabad, Chennai, Bengaluru) come from `election_municipal.json`. Every figure there is checked against a cited source. These work without the download.

## 2. India: what the page shows

Choose a level (**Lok Sabha** 2009–2024, **State assemblies** since the 2008 delimitation, **Municipal corporations**), then a state and a year.

- **Parliament chart.** One dot per seat, grouped by alliance or party, with the majority line.
  - The outer arc is each group's share of seats and the inner arc its share of the vote. The gap between the two is the first-past-the-post effect.
  - Click parties to test whether a coalition reaches a majority.
- **Alliances.** These are drawn only where their totals have been checked against published figures: Lok Sabha 2024; Uttar Pradesh, Punjab and Goa 2022; Maharashtra 2024. Elsewhere results are shown party by party. Alliances are defined in `election_alliances.json`.
- **Map.** Constituencies coloured by:
  - the winning party;
  - the margin (darker means closer);
  - or whether the seat changed hands since the previous election.

  The national map is drawn inside the Survey of India outline and state maps inside the Survey of India state boundary. Hover for the winner and margin; click for the full contest.
- **Equal-area hexes.** One hexagon per seat, placed near its real location, so a small city seat counts visually as much as a large rural one.
- **Tables.** Parties with seats, vote share and change from the previous election; the closest contests; the seats that changed hands.
- **Maps that can't be drawn.** Where constituencies were redrawn after the map data was made (Assam 2026, Jammu and Kashmir 2024), that election has no map. The chart and tables are complete. Gujarat's map source lacks 20 city constituencies in Ahmedabad and Surat.

## 3. India: who is in office now

Beside the results is a list of who governs the selected place, in order of precedence:

| Scope | Who is listed |
|---|---|
| National | The President and Vice President (non-party offices), then the Prime Minister, then the Union Cabinet (Home, Defence, Finance and External Affairs first), then Ministers of State |
| State | The Governor or Lieutenant Governor, the Chief Minister and deputies, then the council of ministers |
| Municipal corporation | The Mayor and Deputy Mayor |

Each entry shows:
- photo, office, other portfolios, party and date in office;
- **official contacts only**: the office's website, and an email address when it is on a government domain.

Sources, read in the background with a step-by-step progress list:
- Wikipedia's current-office lists and the Union Council of Ministers article.
- The state's current ministry article, for its cabinet.
- Wikidata, for official contacts and photos.

Pages are cached for six hours and the list for twelve. **Refresh** reads everything again.

`election_officials.json` corrects the live sources (hide, edit, add) and carries the 2026 mayors. Photos are Wikimedia files, loaded by your browser and credited; none are stored in Sanjaya.

## 4. The seat forecast (elections within six months)

*Code: `forecast.py`. Model version `ens-1`. Needs numpy, which comes with the language-model pack.*

### 4.1 When it appears

- Sanjaya estimates each state's next assembly election as **five years after the last one**.
- **More than six months away:** the page says *Wait for more data* and shows a countdown. Section 5's pulse covers that period.
- **Within six months:** press **Run forecast** (about a minute). You get a seat range per party, the majority line and a trust label.
- There is no forecast for the Lok Sabha before 2029, and none for municipal corporations, because wards are redrawn between polls.

### 4.2 What the model predicts

The model predicts **each significant party's vote share in each seat** at the next election. Seats are then won in simulation.

**Which parties.** Significant parties are those with at least 2% of the state-wide vote last time, or 3% in the Lok Sabha election held since. At most 8 are kept. Everyone else, including independents and NOTA, forms one residual bloc, "Others".

### 4.3 What it learns from

Every past assembly election since 2008 that has an earlier one to learn from. Each row is one party in one seat, with 17 features:

| Feature | Meaning |
|---|---|
| `share_1`, `share_2` | The party's vote share in this seat one and two elections back (`has_2` marks whether two-back exists) |
| `state_1`, `state_2` | The party's state-wide share one and two elections back |
| `trend_ls`, `has_ls` | Swing since the last assembly election, as seen in the Lok Sabha election held in between (Lok Sabha share minus last assembly share), and whether one exists |
| `incumbent` | Whether the party won the most seats last time |
| `rank_1`, `lead_1` | Its rank in the seat last time, and its lead (or deficit) against the best other party |
| `n_cand`, `turnout` | Number of candidates, turnout |
| `reserved_sc`, `reserved_st` | Reserved-seat status |
| `enp` | Effective number of parties in the seat: 1 / Σ share² |
| `is_others` | Whether this row is the "Others" bloc |
| `gap_years` | Years since the last election |

Seats are matched across elections by number and name. Seats that changed after delimitation drop out rather than being forced together.

### 4.4 The model

Two ensembles of regression trees, written with numpy only and averaged:

- **Bagging:** 60 trees, depth 6, at least 30 rows per leaf. Each tree is trained on a bootstrap sample and sees 70% of the features. This is the random-forest idea.
- **Gradient boosting:** 150 shallow trees (depth 3, at least 30 rows per leaf). Each fits what the previous trees got wrong, with learning rate 0.08, on 80% of rows each round.

Features are binned into 33 quantile bins before splitting, which keeps it fast. In each seat the predicted shares are clipped at zero and rescaled to sum to 1.

### 4.5 From shares to seat ranges

The model's errors come from its own backtest (section 6). In each seat, the predicted share for a party is compared with what happened. That error is split into two parts:
- **State-wide error:** the average error per party across the state. This is the swing nobody saw coming.
- **Seat-level error:** whatever is left.

Their spreads, `sd_state` and `sd_seat`, drive **1,000 simulated elections**:

    simulated share(seat, party) = predicted share + N(0, sd_state)   [one draw per party, shared by every seat]
                                                    + N(0, sd_seat)    [one draw per seat and party]
    the seat goes to the party with the highest simulated share

Each simulation gives a seat total per party. The page shows the **10th to 90th percentile** as the range and the 50th as the middle. "Others" seats are reported as a bloc, never as a party.

### 4.6 What it knows nothing about

The model has no information about:
- candidates;
- alliances formed after the last election;
- campaigns, defections or polls.

News coverage is not a feature yet. It joins once Sanjaya has archived coverage for a full election cycle.

## 5. The pulse (elections further away)

*Code: `pulse.py`. Model version `pulse-1`.*

When an election is more than six months away, there is too little signal for the seat forecast. The **pulse** answers a narrower question: *if today's signals held, where would they point, and how uncertain is that?*

It is an ensemble of simple, named hypotheses about how votes move between elections. Each is fitted on past results and shown on its own row, so you can see which assumption drives the answer. Press **Run pulse**; it is available for every state and for the 2029 Lok Sabha.

### 5.1 The signals

**National mood.** For each party, Sanjaya takes the swing (change in state-wide vote share) in every election held elsewhere since this state last voted, within the last 36 months. It then averages them, giving each election this weight:

    weight = 2^(−months ago / 18) × √(size of the election) × (0.5 if it was a Lok Sabha election, else 1)

Recent and larger elections count more; the half-life is 18 months.

**Lok Sabha swing.** The change from the state's last assembly share to its share in the latest Lok Sabha election held there.

**Term elapsed.** The fraction of the five-year term that has passed (0 to 1).

### 5.2 The hypotheses

Each hypothesis gives a state-wide swing per party. That swing is added to every seat's last result, and the "Others" bloc absorbs the difference so shares still sum to 1.

| | Hypothesis | Swing for party p | Fitted how |
|---|---|---|---|
| **H1** | National mood: parties gain or lose everywhere at once | κ × mood(p) | κ by least squares on past elections (clipped to 0–1.5) |
| **H2** | Lok Sabha anchor: voters drift toward how they last voted for Parliament | λ × Lok Sabha swing(p) | λ by least squares (0–1.5) |
| **H3** | Time for change: governments lose ground over a term; big parties regress toward the mean | term elapsed × (β₁·incumbent + β₂·last share + β₀) | ridge regression (penalty 0.5) on past elections |
| **H4** | Seat patterns: past seat-level patterns repeat | the tree ensemble of section 4, given the national mood as its swing input | as section 4 (state elections only) |
| **H5** | Coverage tone: national mood, tilted by news tone | H1 + 0.03 × (tone change for p − average tone change) | gain 0.03 is a set prior, not fitted |

Details for each:
- **H1–H3 fitting.** The parameters are fitted on every past state election, viewed six months before the poll, using only what was known then.
- **H3 and the term.** H3 is scaled by the term elapsed, so it grows as the election nears.
- **H5's tone measure.**
  - Coverage of each party in Sanjaya's own news archive is compared: the last 30 days against the five months before.
  - Tone is scored with a small news lexicon (wins, surge, praise… against scandal, defeat, rebellion…).
  - When the articles have language-model embeddings, that score is averaged with a similarity score. The similarity score measures how close each article is to "the party wins support, gains ground and is praised" versus "the party loses support, faces scandal and is criticised".
  - H5 is used only with at least 25 recent articles, across at least two parties with five or more each. It carries weight 0.6 against 1.0 for the others.
- **Lok Sabha 2029.** H2 becomes "each state moves by its own assembly swing since 2024". State-wide noise is drawn separately for each state, so states don't all swing together.

### 5.3 Simulation and ranges

- Each hypothesis is simulated with its own fitted error, its spread of misses in the past, as state-wide noise.
- Each also gets **drift** for the months left: a standard deviation of 2.5 vote-share points per year until the poll, growing with the square root of time.
- Seat-level noise is the same as in section 4.
- 1,600 simulations are pooled across hypotheses in proportion to their weights. The pooled 10th–90th percentile is the range shown, and each hypothesis's own median is shown beside it.

### 5.4 Where the uncertainty comes from

The page splits the spread of each leading party's seat total with the **law of total variance**:

    total variance = between hypotheses + within hypotheses
    between = Σ w_h × (mean_h − overall mean)²
    within  = Σ w_h × var_h, divided further into state-wide error, drift for the months left, and seat-level noise

"Between" is how much the answer depends on *which story about voters is true*.

When it explains **10% or more** of the spread for a leading party, the page says the choice of hypothesis matters and points you to the per-hypothesis table. Below 10%, the hypotheses broadly agree, and the uncertainty is mostly ordinary noise and time.

## 6. How far to trust the models

Both models are tested the same way: a **rolling backtest**. For each year from 2017 to 2026, train on everything before that year, predict that year's elections, and compare with what happened. The model never sees the answer.

| Measure | Meaning |
|---|---|
| Call accuracy | Share of seats where the predicted leading party won |
| Baseline | Share of seats called by assuming every seat stays with its last winner |
| Coverage | How often the actual seat total fell inside the 10th–90th range (ideal: about 80%) |

The **trust label** is **High** at ≥80% calls with ≥70% coverage. It is **Low** below 65% calls or below 50% coverage. Anything in between is **Medium**.

Results at release:

| Model | Calls | Baseline | Coverage | Label |
|---|---|---|---|---|
| Seat forecast (section 4) | 52% | 48% | — | **Low** |
| Pulse, a year ahead, 60 state elections 2017–2026 (H1–H3) | 48% | about the same | 67% | **Low** |

How to read these:
- The forecast beats "nothing changes", but not by much. That is honest: Indian assembly elections swing hard, and the model knows nothing about candidates, alliances or campaigns.
- Far from an election, the pulse mostly tells you **how uncertain** things are. Its value is the ranges and the uncertainty split, not the middle number.
- H4 and H5 are not in the pulse backtest. H4 shares the forecast's own backtest. H5 can't be tested until Sanjaya has archived coverage through a full election.

The backtest per state is shown with each forecast, so you can see where the model has done better or worse.

## 7. The United States

Choose **United States** in the level menu. The data is downloaded on first use, separately from India's.

- **Results.**
  - House since 1976; Senate, governors and president since the late 1990s.
  - Sources: FiveThirtyEight's election-results archive (CC BY 4.0) through 2024, and a reviewed file for off-year governor races (`us_elections_extra.json`).
  - Electoral votes follow each state's result, including the Maine and Nebraska districts. Apportionment follows each census.
- **Maps.** A state map with Alaska and Hawaii as insets, and a House tile map with one hexagon per district. Colours have one meaning each:
  - solid: won (lighter means closer);
  - striped with a dashed edge: not yet called, striped toward whoever leads;
  - slate: no race there that year.
- **2026, from three sources:**
  - **Each state's own count.** Election results are public records. `us_official.py` reads each state's results site in its own format; the sources and their status are in `STATE_RESULT_SOURCES_2026.md`.
  - **Wikipedia's results tables.** These say which races are decided.
  - **News coverage Sanjaya holds**, on request. For races with no state count, articles are ranked against each race with the language model's embeddings, and the vote counts or shares printed next to the candidates' names are read.
- **When a race counts as won.** When the state certifies it, or when Wikipedia lists it as decided and the state's count has the same party ahead. News coverage never calls a race and never overrides a state count.
- **No news agency's data is used.**
- **In office now.** The President, Vice President and Cabinet. For a state: its governor, two senators and House delegation. Official contacts only.
- **Forecasts.** There is no US forecast model yet. When one comes, it will run only on request, like India's.

## 8. What Sanjaya does not do

- **Call a winner.** Projections and pulses are labelled as models.
- **Show polls yet.** Opinion and exit polls, with each pollster's record, come in a later release. During the Election Commission's blackout windows (Representation of the People Act 1951, sections 126 and 126A), they and all projections are hidden automatically. Add notified windows to `election_blackout.json`.
- **Ward maps for municipal corporations.** The public ward maps don't match the boundaries used, so only seat totals are shown.
- **Run anything in the background.** Models run when you ask. Live US counts are read only while a 2026 page is open.

## 9. Files and settings

| File | Purpose |
|---|---|
| `elections.py`, `elections_data.py` | India results: building the pack, views |
| `forecast.py` | Seat forecast (section 4) |
| `pulse.py` | Pulse (section 5) |
| `officials.py`, `wikitables.py`, `election_officials.json` | Who is in office (India) and corrections |
| `election_parties.json`, `election_alliances.json`, `election_municipal.json` | Party names and colours, checked alliances, municipal results with sources |
| `election_blackout.json` | Election Commission silence windows |
| `us_elections.py`, `us_elections_data.py` | US results |
| `us_live.py`, `us_official.py`, `us_coverage.py` | 2026: Wikipedia, state counts, news coverage |
| `us_officials.py`, `us_elections_extra.json` | US office-holders; off-year governor races |
| `docs/STATE_RESULT_SOURCES_2026.md` | Where each US state publishes its count |
| `election_data/` (not committed) | Downloaded results packs, model caches and live reads |
