@echo off
rem Start Sanjaya and open it in the browser.
rem Uses, in order: the Python chosen by install_sanjaya_windows.bat, this folder's
rem .venv, the "py" launcher, then "python" on PATH. Needs Python 3.9 or newer.
setlocal
cd /d "%~dp0"
title Sanjaya
set "URL=http://127.0.0.1:8765/"
set "PY="

if exist ".sanjaya_python.txt" set /p PY=<".sanjaya_python.txt"
if defined PY if not exist "%PY%" set "PY="
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
rem Resolve the launcher or PATH entry to a full path, so folders with spaces work.
if not defined PY for /f "delims=" %%i in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%i"
if not defined PY for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%i"
if not defined PY goto nopython

"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if errorlevel 1 goto oldpython

rem Already running? Then just open it.
powershell -NoProfile -Command "try{Invoke-WebRequest '%URL%' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if not errorlevel 1 (
  echo Sanjaya is already running. Opening %URL%
  start "" "%URL%"
  exit /b 0
)

echo.
echo   S A N J A Y A   ^|  %URL%
echo   Keep this window open while you use Sanjaya. Close it, or press Ctrl+C, to stop.
echo.
rem Open the browser as soon as the server answers (up to 90 seconds).
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 90;$i++){try{Invoke-WebRequest '%URL%' -UseBasicParsing -TimeoutSec 2 | Out-Null; Start-Process '%URL%'; break}catch{Start-Sleep 1}}"
"%PY%" server.py --host 127.0.0.1 --port 8765
echo.
pause
exit /b 0

:nopython
echo.
echo   Sanjaya needs Python 3.9 or newer, and none was found.
echo   Easiest: double-click install_sanjaya_windows.bat in this folder.
echo   Or install Python from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
echo.
pause
exit /b 1

:oldpython
echo.
echo   The Python found here is older than 3.9. Double-click install_sanjaya_windows.bat
echo   to install a current Python just for Sanjaya, or update Python from python.org.
echo.
pause
exit /b 1
