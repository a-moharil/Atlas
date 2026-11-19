# Atlas v5.8: a search bar on every article panel

## What changed

- **A search bar on every panel that lists articles or videos:** Situation room (*Most covered now*), World, India, Technology, Finance, *Recent broadcaster uploads*, *Geopolitics reel*, and Research (*Analysis, policy and institutional sources*; *Academic research*). Each searches only its own panel, after the panel's tabs and filters. The desks' old substring filter is replaced.
- **Query syntax:** words (most must match), `"quoted phrases"`, commas (or `;`, `|`, `OR`) for either topic. Articles covering several comma-separated topics rank higher. Light suffix matching.
- **Match by** *Best available*, *Meaning + keywords*, *Meaning* or *Keywords*.
  - Keywords: BM25 over headline (twice), excerpt and outlet name.
  - Meaning: cosine similarity with the local multilingual model (paraphrase-multilingual-MiniLM-L12-v2). Articles not yet embedded are embedded on the fly (up to 600 per search). Floor 0.40.
  - Both: keyword matches plus articles at 0.46 or above in meaning, ranked 0.6 × meaning + 0.4 × keywords.
  - When the model is off, meaning searches fall back to keywords and say so.
- **Why it matched:** each result lists the words it contains and its similarity in meaning.
- **Fetching:** when nothing held matches, Atlas runs Google News searches for the query (one per topic, last 7 days), files the results under the panel's desk as *Search further*, refreshes, and searches again. Google results worded differently are listed separately. With fewer than five matches, a button fetches on request. The video panels and *Academic research* don't fetch.
- Google News's " - Publisher" suffix is removed from fetched headlines.
- Searches survive page refreshes; typing focus is kept. Esc or *Clear search* restores the panel.

## API

- `POST /api/find {q, mode: auto|both|meaning|keywords, ids?, extra?, source?: state|reel, limit?}` returns `{mode, groups, results[{id, score, meaning, keyword, terms}], pool, note, entries, publishers, semantic}`. `entries` carries articles that aren't in the page state (fetched or older).
- `POST /api/find/fetch {q, desk}` returns `{queries, fetched, added, notes, ids}`.
- *Search further* in the coverage graph now uses the same Google News fetch.

## Tests

`tests/test_v58_find.py` covers parsing, the matching rule, stemming, phrases, comma topics, meaning and blended ranking, web queries, both endpoints, desk filing of fetched articles, and the meaning path with a stand-in model. Full suite: 151 tests pass on Python 3.13. On 3.9 everything passes except `test_v51_lm`, which needs numpy (unchanged).
