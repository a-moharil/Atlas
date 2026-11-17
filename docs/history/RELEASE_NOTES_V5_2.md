# Atlas v5.2: shuffle and remove from wall

Builds on v5.1. Nothing else changes. Earth watch, Windy, grouping by meaning and the language model page are as before.

## Install

Extract this folder and copy `observatory.sqlite3` and `model_cache/` from your v5.1 folder into it. Then start Atlas as usual.

## Shuffle (dice button)

Every panel that lists headlines now has a dice button:

- **Situation room → Most covered now:** deals a new lead story from the widely covered ones, plus 7 headlines from up to 400 held. The panel is renamed "A fresh deal" while shuffled.
- **World, India, Technology, Finance:** deals headlines at random from everything that matches your current tab and filters, not just the newest 110.
- **Research:** analysis sources and academic papers, each with its own dice.
- **Live TV and video:** recent broadcaster uploads.
- **Emergency newsroom:** shuffles the order of the story cards. The timeline stays chronological.

Each roll draws a different set and the dice shows a new face. The order holds through the automatic background refresh, so the wall doesn't jump while you read. Use "Usual order" to go back to the normal ranking.

## Remove from wall

- **On a card:** each article has a Remove (×) control. It's shown in full on hover and always on touch screens.
- **Same headline from several outlets:** syndicated copies are removed together.
- **Newsroom:** Remove hides the whole story card. If new articles join a story you removed, it stays hidden as long as most of its articles are ones you removed.
- **Undo:** the bar at the bottom offers Undo for 7 seconds. "N removed · Restore all" appears beside the dice whenever anything is hidden.
- **What it doesn't change:** removal only hides an article from the display panels. The article stays in the database, in the bias gauge and outlet counts, and in Compare coverage. The choice is saved in `observatory.sqlite3`, so it survives restarts and works in any browser.

## Verification

- 93 Python tests pass, including the new `tests/test_v52_wall.py` (hide, undo, clear, state), plus the existing front-end checks.
- In Chrome:
  - Shuffling changed both the lead and the list, held through a background refresh, and "Usual order" restored the original.
  - Remove and Undo round-tripped through the server.
  - Desks, Research, Video and the Newsroom each showed working dice and Remove controls.
  - No page errors.
