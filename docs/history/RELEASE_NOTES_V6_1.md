# Sanjaya v6.1: the emblem

- **The Sanjaya emblem** is now part of the app:
  - In the sidebar, in place of the old globe mark, using the transparent logo.
  - As the browser tab icon (`favicon.ico`, plus 32, 180 and 192 px PNG icons).
  - At the top of *Why Sanjaya*.
- *Why Sanjaya* has a new section, **The emblem**, on what each part means: the eye, the reins as circuit traces, the pupil as a network (and a chariot wheel), and the balance of heritage and present in amber and deep blue-green.
- **README:** the emblem heads the page. It uses the transparent version in GitHub's dark mode and the deep blue-green version in light mode, so the network pupil stays visible on both. A short paragraph explains the emblem.
- **Brand files:**
  - `static/brand/`: the emblem trimmed to its edges (1200 px and 240 px wide) and app icons.
  - `docs/brand/`: README images and `sanjaya-social-preview.png`, 1280×640 px, for GitHub's social preview.
- The server now serves `.ico` and `.jpg` files with the right content type.

The emblem files are derived from the final logo package (transparent master, app icons and brand-ground master): trimmed and resized only, never redrawn.
