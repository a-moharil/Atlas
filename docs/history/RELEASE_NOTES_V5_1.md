# Atlas v5.1 — grouping by meaning and generated story labels

Builds on v5.0.3 (newsroom fix, Windy for India). Nothing else changes; without the optional pack Atlas behaves exactly like v5.0.3 and shows "Keyword mode".

## Install

1. Extract this folder. To keep your data, copy `observatory.sqlite3` from your current Atlas folder into it (or run `python migrate_database.py "OLD_FOLDER\observatory.sqlite3"`).
2. **Grouping by meaning (recommended):** double-click `install_language_model.bat` once (macOS/Linux: `bash install_language_model.sh`). It installs fastembed, which runs ONNX on the processor with no PyTorch and no graphics card, and downloads the multilingual model (about 220 MB) into `model_cache/`. After that it works offline.
3. **Labels and summaries (optional):** install Ollama from https://ollama.com/download, run `ollama pull qwen2.5:1.5b`, then tick "Write labels and summaries" under System → Language model.
4. Start Atlas with `start_windows.bat` as usual.

## What it does

- **Model:** `paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions, 50+ languages, including Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati and Urdu. A Hindi headline and an English headline about the same event can join one story.
- **What gets embedded:** each headline (without the trailing "- Publisher") plus the start of the feed excerpt. Full articles are never fetched.
- **When it runs:** in the background after every collection, with at most 4 processor threads, pausing between batches. It processes new articles only, and each article's vector is stored once in the database.
- **How stories are grouped:** pairs above the strictness threshold, published within the time window (default 3 days), are joined strongest first. Two groups merge only if their centres also meet the threshold, which stops chains of loosely related headlines from merging separate events.
- **Bias gauge:** the coverage spread now comes from these groups, and the gauge says "by meaning" or "by keywords".
- **Emergency newsroom:** priority groups are formed by meaning. The status bar shows the mode, and cards show generated labels and summaries when they are switched on.
- **Compare coverage:** the nearest articles by meaning within 7 days, each with a "% match".
- **Fallback:** if the pack is missing, the model is still loading, or under 60% of recent articles are processed, Atlas groups by headline keywords. The top-bar pill says "Keyword mode", and so does the newsroom.

## Labels and summaries (off by default)

- **What it does:** for the top multi-outlet newsroom groups, a small local model writes a neutral label, a one-to-two sentence summary and a note on how outlets differ.
- **What the model sees:** only the headlines and excerpts Atlas holds. It is told not to add facts, and always answers in English.
- **How it is marked:** results are cached per group, tagged "Generated", and name the model. They never replace publisher text.
- **Privacy:** Ollama must run on this computer (127.0.0.1). Nothing goes to an online AI service.
- **Speed:** qwen2.5:1.5b is the default, about 1 GB and a few seconds per label on a laptop processor. qwen2.5:3b writes better but is slower.

## Tuning

System → Language model → **Check the grouping on your news** lists headline pairs near the threshold, each marked joined or kept apart. Raise strictness if different events are being joined; lower it if the same event is kept apart. The default of 0.72 is a starting point and has not yet been tested on real headlines.

## Verification

- `python -m unittest discover -s tests -p "test_*.py"`: 92 tests pass. New `tests/test_v51_lm.py` covers paraphrase joining, chain prevention, the time window, keyword fallback, newsroom matching, settings validation, the label prompt and parsing, and a full run against a stand-in Ollama.
- The full flow was exercised in Chrome with a stand-in embedding model and a stand-in Ollama, including the language model page, newsroom labels and drawer match percentages.
- **Not verified on the build machine:** the real model download and its grouping quality, and real Ollama output, because downloads were blocked there. Both are first exercised on your computer.
