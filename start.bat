@echo off
chcp 65001 >nul
title Desktop Automation Console
cd /d "%~dp0"

set "PYCMD="

rem Prefer the "py" launcher: it ships with python.org installers and is not
rem hijacked by the Microsoft Store alias.
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYCMD=py -3"
)

rem Fallback to a verified python on PATH (filters out the Store stub).
if not defined PYCMD (
  for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY set "PY=%%i"
  if defined PY (
    "%PY%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYCMD=%PY%"
  )
)

if not defined PYCMD (
  echo [ERROR] No usable Python 3 found.
  echo Install Python 3.11+ from python.org and make sure "py -3" works.
  pause
  exit /b 1
)

%PYCMD% -X utf8 -m app.server --open

echo.
echo Server stopped.
pause
