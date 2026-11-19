# Atlas v5.9.1: clear answers in the Ask drawer

- Each answer has a × button that removes just that answer.
- *Clear all answers* (above the list, with a count) removes them all.
- Removing an answer while it's still being written stops the drawer following it and frees the Ask button straight away. The local model may finish in the background, but its text isn't shown.
- Answer numbers stay unique after removals, so citation links always point to the right answer's sources.
- Answers live only in the open page and are gone after a reload, as before.

Changed: `static/ask.js`, `static/atlas5.css`, `README.md`. No server or API changes.
