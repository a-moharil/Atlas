# Atlas v5.9: Wikipedia page and Ask drawer

## Wikipedia (English)

- New page under Research: search English Wikipedia and read articles inside Atlas. Uses Wikipedia's public APIs (no key) with an identifying User-Agent, as Wikipedia asks.
- Article links open within Atlas, with *Back* and *Search results*. In-page footnote links jump within the article. Other namespaces (File:, Category:…) open on Wikipedia.
- Articles are cleaned with an allowlist: no scripts, styles, event handlers or unknown attributes; images only from upload.wikimedia.org; element ids prefixed. Edit links, navboxes and maintenance boxes are removed.
- Searches, pages and plain text are cached in SQLite (400 entries; refreshed after 6 hours for searches, 3 days for pages). When Wikipedia can't be reached, saved copies are served and marked.
- **Held in Atlas:** related articles Atlas holds, found from the title and the lead's bolded names (for example *IAEA*).

## Ask drawer

- Opens from the top bar on every page, or from *Ask* in any panel's search bar.
- Answers come from Atlas articles (this panel, or everything) and the open Wikipedia page, written by the local Ollama model. Model choice is saved as `ask_model`; the default is the story-label model.
- Retrieval reuses the panel search. Questions are long, so any query word counts, and the ranking does the rest. Meaning is blended in when the language model is on. Up to eight articles (two per outlet) and five Wikipedia passages (the lead is always offered).
- Every sentence must cite [A#] or [W#]. Atlas drops citations to sources that don't exist and underlines sentences that cite nothing. Citations link to the source list.
- The answer streams in. If Ollama is offline, the sources are still shown.
- **Open in Google AI Mode** opens the question on google.com in a new tab (`udm=50`). The Gemini API is left for later.
- Docks beside the page on screens 1280px and wider.

## API

- `GET /api/wiki/search?q=` and `GET /api/wiki/page?title=` (the page response includes `html`, `description`, `thumbnail`, `aliases`, and the cache state).
- `POST /api/ask {question, ids?, wiki?}` returns `{status: writing|no_model|no_sources, job?, sources{atlas, wikipedia}, mode, model}`.
- `GET /api/ask/job/<id>`, `GET /api/ask/models`, `POST /api/ask/settings {model}`.

## Tests

`tests/test_v59_wiki_ask.py` covers HTML cleaning, title rules, passages, caching with an offline fallback, citation checking, prompt and job, loose ranking, the Wikipedia and Ask endpoints, panel scope, and the Ollama-offline path. Full suite: 159 tests pass on Python 3.13. On 3.9 everything passes except `test_v51_lm`, which needs numpy (unchanged).
