@echo off
setlocal
rem TankMix launcher for Windows. Double-click it.
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)" >nul 2>nul && set "PY=python"
if not defined PY (
  echo.
  echo   Python 3.8+ not found / Python 3.8+ nao encontrado.
  echo   Install it from / Instale em: https://www.python.org/downloads/
  echo   Tick "Add python.exe to PATH" / Marque "Add python.exe to PATH".
  echo.
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)
%PY% "%~dp0tankmix_config.py" %*
if errorlevel 1 pause
