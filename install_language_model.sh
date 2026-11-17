#!/usr/bin/env sh
# ATLAS optional language model pack: fastembed (CPU, ONNX) + multilingual grouping model.
set -eu
cd "$(dirname "$0")"
python3 -m pip install --upgrade -r requirements-lm.txt
python3 -c "from fastembed import TextEmbedding; m=TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='model_cache'); print('Model ready:', len(list(m.embed(['test']))[0]), 'dimensions')" || echo "The model will download on the next Atlas start."
echo "Done. Optional labels: install Ollama (https://ollama.com/download) and run: ollama pull qwen2.5:1.5b"
