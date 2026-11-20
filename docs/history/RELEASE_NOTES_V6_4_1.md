# Sanjaya v6.4.1 · Fuller cabinets, refresh buttons, and a pulse for far elections

## In office now
- **Cause of the short lists:** v6.4 relied on Wikidata alone, and its query asked for every office in India before filtering. That query was slow enough to time out nationally, and Wikidata rarely records state ministers. On a real machine only the Governor came back for Uttar Pradesh.
- **Wikipedia is now the primary source:**
  - The current chief ministers, deputy chief ministers, governors and lieutenant governors lists.
  - The *Union Council of Ministers* article.
  - The state's current ministry article, linked from the chief-ministers list, or found by Wikipedia search when the link is missing.
- `wikitables.py` reads those tables: rowspans, split headers, row headers, hidden sort keys, footnotes and portraits. Former ministers ("Left office" filled) are skipped.
- **Wikidata now adds contacts and photos.** Its query narrows offices by label before joining holders, and it has a longer timeout.
- **Photos:** Wikipedia page images (free licences only) fill in anyone still without one.
- **Progress:** the fetch runs in the background and the panel shows each step (fetching, found, nothing found, unreachable). The list fills in as sources answer.
- **Refresh** re-fetches now, without blanking the list.
- **Caching:** pages are kept six hours and the list twelve hours. If a source is down, the last good copy is used.
- **Other portfolios** are shown under each person's main office.

## Next election
- **Recompute** retrains the seat model and refreshes the pulse.
- **Pulse** (new, `pulse.py`): shown for elections more than six months away, including the 2029 Lok Sabha.
  - Hypotheses H1 to H5: national mood, Lok Sabha anchor (assembly swing for the Lok Sabha), time for change, the tree ensemble, and coverage tone.
  - Each is fitted on past results, simulated with its own error plus drift for the months left, then pooled.
  - "Under which hypothesis" table: each hypothesis's median seats for the leading parties, its weight and its backtest accuracy.
  - "Where the uncertainty comes from": law of total variance, per party. The components are hypothesis choice, state-wide swing, time left and seat noise.
  - Flagged as significant when hypothesis choice explains 10% or more of a leading party's spread.
  - **Backtest:** pulses taken 12 months before 60 state elections (2017 to 2026). They called 48% of seats correctly (H1 47%, H2 49%, H3 48%), and ranges held the result 67% of the time. Trust label: **Low**.
  - **Coverage tone** (H5) uses Sanjaya's own news archive. It is not backtested yet, and it is used only with at least 25 recent single-party articles.

## Tests
`tests/test_v641_officials_pulse.py`: 14 tests, with fixtures shaped like the real Wikipedia articles. Full suite: 239 tests.
