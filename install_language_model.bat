@echo off
setlocal
cd /d "%~dp0"
echo.
echo ATLAS -- optional language model pack
echo Installs fastembed (ONNX Runtime, CPU only, no PyTorch) and downloads the
echo multilingual grouping model (about 220 MB) into this folder's model_cache.
echo.
python --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)
python -m pip install --upgrade -r requirements-lm.txt
if errorlevel 1 (
  echo.
  echo Installation failed. Check your internet connection and try again.
  pause
  exit /b 1
)
echo.
echo Downloading the model now so the first start is quick...
python -c "from fastembed import TextEmbedding; m=TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='model_cache'); print('Model ready:', len(list(m.embed(['test']))[0]), 'dimensions')"
if errorlevel 1 (
  echo The model will download automatically the next time Atlas starts.
)
echo.
echo Done. Start Atlas with start_windows.bat. Optional labels: install Ollama from
echo https://ollama.com/download and run:  ollama pull qwen2.5:1.5b
pause
