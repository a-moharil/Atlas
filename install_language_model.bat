@echo off
rem Sanjaya -- optional language-model pack, on its own (Choice A).
rem install_sanjaya_windows.bat does this for you as part of the one-click setup.
setlocal
cd /d "%~dp0"
echo.
echo Sanjaya -- optional language model pack
echo Installs fastembed (ONNX Runtime, CPU only, no PyTorch) and downloads the
echo multilingual grouping model (about 220 MB) into this folder's model_cache.
echo fastembed needs Python 3.10 or newer; the rest of Sanjaya runs on 3.9.
echo.
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY for /f "delims=" %%i in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%i"
if not defined PY for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%i"
if not defined PY (
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo or double-click install_sanjaya_windows.bat, which installs it for you.
  pause
  exit /b 1
)
echo Using %PY%
"%PY%" -m pip install --upgrade -r requirements-lm.txt
if errorlevel 1 (
  echo.
  echo Installation failed. Check your internet connection. If your Python is 3.9,
  echo run install_sanjaya_windows.bat: it can add Python 3.12 just for Sanjaya.
  echo Sanjaya still runs without this pack; stories then group by keywords only.
  pause
  exit /b 1
)
echo.
echo Downloading the model now so the first start is quick...
"%PY%" -c "from fastembed import TextEmbedding; m=TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='model_cache'); print('Model ready:', len(list(m.embed(['test']))[0]), 'dimensions')"
if errorlevel 1 (
  echo The model will download automatically the next time Sanjaya starts.
)
echo.
echo Done. Start Sanjaya with start_windows.bat. For Ask answers and story labels,
echo install Ollama from https://ollama.com/download and run:  ollama pull qwen2.5:1.5b
pause
