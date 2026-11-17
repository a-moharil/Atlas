@echo off
setlocal
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)
echo.
echo ATLAS v5 -- India ^& World Intelligence
 echo Browser address: http://127.0.0.1:8765/
echo.
python server.py --host 127.0.0.1 --port 8765
pause
