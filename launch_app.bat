@echo off
chcp 65001 >nul
title Desktop Automation Console
cd /d "%~dp0"

set "APP=flutter_app\build\windows\x64\runner\Release\desktop_console.exe"

if not exist "%APP%" (
  echo [ERROR] Flutter app not built: %APP%
  echo Run: powershell -ExecutionPolicy Bypass -File scripts\build_flutter.ps1
  pause
  exit /b 1
)

rem Backend exits immediately if the port is already in use, so this is safe to repeat.
for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY set "PY=%%i"
if defined PY (
  set "PYW=%PY:python.exe=pythonw.exe%"
  start "" "%PYW%" -X utf8 -m app.server
  ping -n 3 127.0.0.1 >nul 2>&1
)

start "" "%APP%"
exit /b 0
