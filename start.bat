@echo off
chcp 65001 >nul
title Desktop Automation Console
cd /d "%~dp0"

for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY set "PY=%%i"
if not defined PY (
  echo [ERROR] Python not found in PATH.
  echo Install Python 3.11+ and make sure "python" works in a terminal.
  pause
  exit /b 1
)

"%PY%" -X utf8 -m app.server --open

echo.
echo Server stopped.
pause
