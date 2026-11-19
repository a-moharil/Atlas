@echo off
rem Sanjaya one-click setup for Windows (README, section 3, Choice B).
rem Installs Python if needed, the language-model pack and, if you agree, Ollama;
rem then puts a Sanjaya shortcut on the Desktop and starts Sanjaya.
rem Safe to run again: finished steps are skipped. Log: setup_log.txt
setlocal
cd /d "%~dp0"
title Sanjaya setup
color 0E

where powershell >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Windows PowerShell was not found, so the one-click setup cannot run.
  echo  Follow README section 3, Choice A, to install Python by hand.
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\windows\install_sanjaya.ps1" %*
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

echo.
echo  Starting Sanjaya. Your browser opens when it is ready.
echo  Keep this window open while you use Sanjaya; close it to stop Sanjaya.
echo.
call "%~dp0start_windows.bat"
