# Sanjaya v6.2: one-click setup for Windows

Branch: `sanjaya-branded`

## What's new

- **`install_sanjaya_windows.bat`: one-click setup (README 3.4, Choice B).** It runs `tools/windows/install_sanjaya.ps1` (Windows PowerShell 5.1, which ships with Windows 10 and 11), which:
  1. finds Python 3.9 or newer, or installs Python 3.12.10 for the current user without admin rights (`winget` first, then the python.org installer, run only if its Authenticode signature is from the Python Software Foundation);
  2. creates a private `.venv` in the Sanjaya folder;
  3. installs the language-model pack (`fastembed`) and downloads the multilingual model. If the pack won't install on Python 3.9 (current `fastembed` and ONNX Runtime need 3.10+), it offers to add Python 3.12 just for Sanjaya;
  4. asks whether to install Ollama (default yes): `winget`, or the ollama.com installer if its signature names Ollama; then pulls `qwen2.5:1.5b`;
  5. creates a **Sanjaya** shortcut with the emblem (`static/favicon.ico`) on the Desktop and in the Start menu;
  6. prints what works and what doesn't, then starts Sanjaya.

  It's safe to run again (finished steps are skipped) and logs everything to `setup_log.txt`. Flags: `-Yes`, `-NoOllama`, `-NoShortcut`.
- **`start_windows.bat`** uses the Python the setup chose (`.sanjaya_python.txt`), then `.venv`, then `py -3`, then `python`. Paths with spaces work. It opens the browser when the server answers, and if Sanjaya is already running it just opens the browser.
- **`install_language_model.bat`** installs into `.venv` when it exists.
- **The README** section 3 is now *Choice A: build from the core* and *Choice B: one click*, with a table of what still works when a part fails. The Python minimum is 3.9 everywhere (3.12 recommended).
- **Launch film:** the poster still is in `docs/brand/sanjaya-launch-poster.png`. The README has a commented placeholder for the video link (see below).

## Limits

- A `.bat` file can't carry its own icon. The emblem is on the shortcut the setup creates.
- Unsigned scripts from the internet trigger SmartScreen (*More info → Run anyway*), and some managed work PCs block them. Choice A still works there.
- macOS and Linux keep Choice A for now.

## Adding the launch film once the final cut exists

1. On GitHub, open `README.md` on this branch and click the pencil (edit).
2. Find the `<!-- Launch film ... -->` block under *See every page*. Delete the comment marks and the `PASTE-THE-USER-ATTACHMENTS-LINK-HERE` line.
3. Drag the MP4 (under 100 MB) onto that spot. GitHub uploads it and inserts a `https://github.com/user-attachments/assets/...` link, which plays inline in the README.
4. Commit. The video is hosted by GitHub, not stored in the repository.

## Tests

`tests/test_v62_setup.py` checks the following:

- ASCII-only scripts and CRLF line endings;
- no PowerShell 7-only syntax;
- the Python minimum;
- the setup → launcher hand-off;
- signature checks;
- Ollama defaulting to yes;
- model names matching `lm_labels.py` and `semantic.py`;
- README sections and the poster.

Full suite: 181 tests pass. The PowerShell script parses without errors, and its selection logic was exercised under PowerShell 7 on Linux. A real run needs Windows: a clean Windows Sandbox or a spare PC.

## Fixes

- `tests/test_v62_setup.py` read files with the system code page, which fails on Windows (cp1252). It now reads UTF-8.
- `mygov.py` read `mygov_catalogue.json` with the system code page, so on Windows the curly apostrophes and dashes in scheme names showed as `â€™` and `â€”`. It now reads UTF-8. `retrieval_jobs.py` reads and writes its cache as UTF-8 too (the files are ASCII JSON, so existing caches still load).
