# Atlas v5.6: an interpretable diffusion view

The diffusion view was hard to read: outlets and stories were mixed on one radial chart, labels collided, and the list order didn't match its "closest first" heading. v5.6 rebuilds it around three questions: what is related, who covered it, and when.

## Diffusion view

- **Header card** for the starting story: clean title, lean gauge, desks, counts, first seen, and how many usual outlets haven't covered it.
- **Story map** (Map and coverage tab):
  - distance from the centre = difference in meaning, with rings at 80%, 60% and 40% similar;
  - quarter = desk (World and Policy, Technology and Research, Finance and Energy, India);
  - size = number of outlets;
  - numbered dots matching the list and the table; grey a–d for stories that share outlets but not meaning;
  - outlets are no longer drawn on the map.
- **Who covered what:** an outlet × story table, grouped by lean. Filled dots = covered (coloured by lean); dashed rings = usual outlets that haven't covered the story. Unknown aggregators fold into *Other outlets (n)*. Rows select an outlet; column numbers open a story. The selection is shared by the map, table and list.
- **Timeline tab:** time across, similarity up; a line per story with articles as dots coloured by lean. Lines with nearly equal similarity are nudged apart.
- **Lists:** numbered, most similar first, eight shown with *Show more*. Each story has a small lean gauge; each article shows the outlet's logo, lean label (Left, Lean left, Centre, Lean right, Right, Not rated) and paywall label.

## Fixes

- Related stories are now ordered by similarity. The random walk still finds the candidates (up to 16).
- Story titles drop the trailing " - Publisher" / " | Publisher" and prefer a primary or rated outlet's headline over the newest aggregator copy. This applies to the overview graph too.
- The same headline from the same outlet is listed once.
- "1 source", "1 article", "1 story": singular counts.
- Overview graph: labels no longer overlap each other or other nodes, have a dark halo for legibility, and unrated aggregators are drawn fainter and labelled last.

## API

`POST /api/graph/diffuse` now also returns `outlets` (name, lean, logo, paywall, known, primary for every outlet shown) and a `first` timestamp on each story card.

## Tests

`tests/test_v56_diffusion_view.py`: title cleaning, similarity order, preferred titles, de-duplication and outlet details. Full suite: 133 tests on Python 3.13; on 3.9 everything passes except `test_v51_lm`, which needs numpy (unchanged).
