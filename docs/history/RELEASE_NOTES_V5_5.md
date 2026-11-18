# Atlas v5.5: coverage graph, diffusion and a better primary-sources bar

## Primary sources bar

- **Controls first:** *Primary first*, *All sources*, a count ("7 of 14 on this page") and the list button sit at the start, so they no longer need scrolling to reach.
- **Chips:** only sources with articles on the current page get a chip, sorted by how many they have, with at most eight shown. The bar wraps onto a second line instead of scrolling sideways.
- **Multi-select:** click several chips to see those outlets together. *Only* on a chip (shown on hover) shows that outlet alone.
- **"+N more":** opens a searchable list of every primary source, grouped (Indian outlets, international outlets, government and institutions, research and analysis), with checkboxes, per-page counts and *Only*.

## Coverage graph (Situation room, World, India, Technology, Finance)

- **Three layers:** sources, then stories (the existing meaning groups), then articles.
- **Overview:** outlets on the page as nodes.
  - **Solid lines:** shared stories (Jaccard over each outlet's stories).
  - **Dashed lines:** similar topics. Each outlet's articles are matched to their closest counterparts at the other outlet, rather than comparing one averaged vector per outlet, so outlets that cover many subjects still compare fairly.
  - A switch shows both kinds of line, or either one.
- **Zoom:** click an outlet for its stories, then open a story for its articles. Filter the page from there. *Expand* opens a full-screen view.

## Diffusion

- **Where:** a *Diffuse* button on every story card and every article in the graph.
- **How it works:** personalised PageRank from the chosen article over articles, stories and outlets, with each article's eight nearest neighbours by meaning as extra links. It covers the last 7 days on every desk.
- **What it returns:** the seed story and its outlets; related stories close in meaning, with their desks; stories reached only through shared outlets, shown separately; and outlets that usually cover this kind of story but haven't covered this one.
- **Search further:** an open Google News search for the story's key terms, plus a search on each of up to three gap outlets. New articles join the desk you started from, are embedded in the background, and the diffusion refreshes.

## Verification

- **Tests:**
  - 129 Python tests pass, including 6 new ones in `tests/test_v55_graph.py`: edges, page scoping, story zoom, diffusion rings and gaps, query building, and the endpoints including an offline Search further.
  - Under Python 3.9, everything except the numpy-based v5.1 test passes.
  - The front-end checks pass.
- **In Chrome** with seeded data and a stand-in model, all of these were exercised with no page errors:
  - the bar's multi-select, *Only*, the list's search and checkboxes;
  - the graph on all five pages, node selection, story zoom and edge switching;
  - the expanded view, diffusion, diffusing again from inside it, and Search further's offline message.
- **Not verified here:** Search further needs Google News, which the build machine could not reach. Diffusion quality depends on the real language model and is first seen on your data.
