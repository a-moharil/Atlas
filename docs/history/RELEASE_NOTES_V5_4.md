# Atlas v5.4: a faster research radar, with search and filters

## Why For you was slow, and what changed

In v5.3, every refresh downloaded the 800 newest arXiv papers in two large API requests. Nothing showed until both had finished and every abstract had been processed by the language model, which could take minutes. Slow responses also hit the request timeout and started over.

Now:

- **Watch phrases:** Atlas extracts distinctive phrases from your papers, such as *pipeline synthesis*, *training dynamics*, *issue trackers* and *hyperbolic representations*. Broad words like "deep" or "transformer" are left out. Edit the phrases under **Your papers**.
- **Targeted arXiv search:** a few small queries (four phrases each, up to 100 papers, newest first) limited to your categories. After the first run, each run asks only for papers newer than the previous one, so hourly checks are cheap.
- **arXiv daily listings (RSS):** one small request per category, the broad feed behind Themes.
- **More open sources:**
  - Hugging Face daily papers (now stored as papers) and Hugging Face paper search for your phrases.
  - OpenAlex search for journals and proceedings, with an optional free key.
- **Progressive display:** each query's papers are saved and processed as soon as they arrive, so the first papers appear within seconds.
- **Background refresh:** sources keep refreshing while Atlas runs, each on its own schedule: arXiv search hourly, daily listings and Hugging Face every 3 hours, OpenAlex and the lab every 12, OpenML and deadlines daily.
- **Polite fetching:** all arXiv requests share one connection with three seconds between requests, as arXiv's terms ask.

## Search and filters

- **Mode switch:** Auto / Keyword / Semantic.
  - **Keyword** supports `"phrases"`, `author:`, `cat:`, `title:` and `-exclusions`.
  - **Semantic** ranks by meaning with the local model and falls back to keywords, saying so, without the model pack.
  - **Auto** explains its choice, and one click reruns the search in the other mode.
- **Filters:** lane, category, source (arXiv, Hugging Face, OpenAlex, lab), minimum match, reading queue, and Hugging Face daily papers.

## Making sure fetching works

- **Your papers → Sources → Test sources** sends one small request to every source and shows which work.
- `python tools/check_radar_sources.py` does the same from the command line, without Atlas running.
- **OpenAlex budget:** OpenAlex now meters keyless use with a small daily budget. The radar keeps OpenAlex queries few and short. If the budget runs out, the status says so and suggests a free key.

## Verification

- **Tests:**
  - 123 Python tests pass, including 30 for the radar, covering RSS parsing (replacements skipped), phrase extraction and editing, incremental dated queries, Hugging Face and OpenAlex intake, the OpenAlex key, the source check, search modes and every filter.
  - Under Python 3.9, everything except the numpy-based v5.1 test passes.
  - The front-end checks pass.
- **Fixtures:** they follow each provider's documented response format, including arXiv's 2024 RSS format.
- **In Chrome** with fixture data: the first papers appeared after about 6 seconds and all sources finished in about 30, mostly arXiv's required pacing.
- **Live services:** the build machine could reach only GitHub, so the live arXiv, Hugging Face, OpenAlex, Crossref and OpenML responses are first exercised on your computer. Run the source check once after installing.
