# Sanjaya v6.0: a new name, its reason, and your own reading of the gauge

## Atlas is now Sanjaya

- Everything you see in the app is now called Sanjaya: browser title, sidebar, page text, messages, the README. The repository, folder, file names and code identifiers keep the name Atlas (`github.com/a-moharil/Atlas`, `atlas3.js`, `window.ATLAS`), so existing installs, branches and saved settings carry over unchanged.
- **Signature:** the sidebar is signed "Sanjaya · by Samhitha Bhagavatula" and links to *Why Sanjaya*. The page footer carries the same credit.

## Why Sanjaya (new page, System → Why Sanjaya)

- The motivation behind the app. It opens with the first verse of the Bhagavad Gita, Dhritarashtra's question to Sanjaya, in transliteration with an English translation.
- It tells the story of Sanjaya, the charioteer given divine sight to tell the blind king the truth of Kurukshetra, and sets out what the app tries to do: **gather, distinguish, present**. It closes with a note on our own blindness and why the gauge can be recalibrated, and is signed by the author.
- The text lives in `static/about.js` so it can be edited on its own.

## Calibrate the left–right gauge

- The lean label on every card is now a button. Click it to place the outlet yourself (Left … Right, or Not rated) with an optional note.
- Your rating replaces the published one throughout: card labels, gauge arcs and needles, story spreads, *Political spread*, the coverage graph and the diffusion view. Story groups are recomputed straight away.
- Always marked: *yours* on the label, dashed outline, the published rating on hover and in the dialog. *Use the published rating* undoes it.
- *Reading the gauge* shows how many outlets you've placed, with *Review your ratings*: a table of published vs your ratings with Change, Reset and Reset all.
- Outlets the raters don't cover can be rated too.
- Stored in SQLite (`lean_overrides`). New endpoint: `POST /api/lean {host, lean: -2..2 | "none" | "reset", note}`. `/api/state` now includes `lean_overrides`, and publisher profiles carry `lean_user`, `lean_original` and `lean_note`.

## Tests

`tests/test_v60_sanjaya.py` covers overrides applying and resetting, rating unrated outlets, validation, persistence, story spreads following an override (cache invalidation), the endpoint and state, the visible name, and the Why Sanjaya page. Full suite: 166 tests pass on Python 3.13. On 3.9 everything passes except `test_v51_lm`, which needs numpy (unchanged).
