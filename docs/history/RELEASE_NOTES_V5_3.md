# Atlas v5.3: Research radar

This release adds one new page, **Research radar**, under Research in the sidebar. The other pages are unchanged. The only edits to existing code wire up the new page: one added helper in `semantic.py`, new endpoints in `server.py`, and the navigation entry.

## What's on the page

- **For you:** new arXiv papers in cs.LG, stat.ML, cs.AI, cs.NE, cs.CL and cs.SE, sorted into five lanes:
  - AutoML and pipeline synthesis
  - Training dynamics and diagnostics
  - Transformers and representations
  - Software engineering for ML
  - Data-centric ML and data science

  Each paper shows its "% match" to your closest paper and names that paper. The lanes have dice and Remove, like the news walls.
- **Vanschoren and AMOR/e:** papers with Joaquin Vanschoren as an author, from arXiv and OpenAlex, with current AMOR/e members' names highlighted.
- **Themes:** the period's papers grouped by meaning, labelled with phrases the papers share (not written by a model).
- **Related-work check:** paste an abstract or draft paragraph. Atlas returns the closest recent papers it holds, plus older work from OpenAlex re-ranked on your computer.
- **Benchmarks and datasets:** the newest OpenML datasets and tasks, trending Hugging Face models, and Hugging Face upvotes on radar papers.
- **Deadlines:** NeurIPS, ICML, ICLR, KDD, ICSE and MSR from the open ccf-deadlines dataset, converted to your time zone. The AutoML Conference links to its official site.
- **Reading queue:** save, set status, keep notes, export BibTeX (all or selected).
- **Weekly digest:** optional, written by your local Ollama model, marked *Generated*. Only titles the model was given are kept as highlights.
- **Your papers:** six seeded papers:
  - Towards efficient AutoML
  - Scale-invariant diagnostics
  - TABASCO
  - ASFBot
  - Temporal Geometry of Deep Networks
  - The Research Square preprint

  Add or remove papers by arXiv ID, DOI or title.

## How it works

- **Matching:** uses the same local multilingual embedding model as news grouping. Without the model pack, it falls back to keyword matching and says so.
- **Refresh schedule:** sources are fetched in the background while the page is open, then cached. arXiv every 6 hours, the lab every 12, Hugging Face every 6, and OpenML and deadlines daily.
- **Storage:** papers older than 30 days are pruned, except queued and lab papers.
- **Settings:** in `radar_config.json`.

## Verification

- **Tests:**
  - 112 Python tests pass, 19 of them new in `tests/test_v53_radar.py`.
  - Under Python 3.9, everything except the numpy-based v5.1 test passes.
  - The front-end checks pass.
- **Fixtures:** they mirror the API response formats. The deadline fixtures are real copies of the ccf-deadlines files.
- **In Chrome:** with fixture data and stand-in models, every tab works: dice, remove, save, notes, status, BibTeX export, the related-work check, adding papers and the digest.
- **Not yet verified against the live services:** the live arXiv, OpenAlex, Crossref, OpenML and Hugging Face APIs could not be reached from the build machine. They are first exercised on your computer. The live Research Square paper's title was also not visible to the build; Atlas looks it up through Crossref on first run.
