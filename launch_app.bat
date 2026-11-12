@echo off
chcp 65001 >nul
title Desktop Automation Console
cd /d "%~dp0"

set "APP=%~dp0flutter_app\build\windows\x64\runner\Release\desktop_console.exe"

if not exist "%APP%" (
  echo [ERROR] Flutter app not built:
  echo   %APP%
  echo Run: powershell -ExecutionPolicy Bypass -File scripts\build_flutter.ps1
  pause
  exit /b 1
)

rem Start the backend in background. It exits by itself if the port is taken,
rem so running this twice is safe.
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 -X utf8 -m app.server
  ping -n 3 127.0.0.1 >nul 2>&1
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    start "" /min py -3 -X utf8 -m app.server
    ping -n 3 127.0.0.1 >nul 2>&1
  )
)

start "" "%APP%"
exit /b 0
