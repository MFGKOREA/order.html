@echo off
rem If 허브상태.txt is more than 3 minutes old, stop the hub process. start_hub.cmd brings it back.
chcp 65001 >nul
cd /d "%~dp0.."
if exist "%~dp0hub.env.cmd" call "%~dp0hub.env.cmd"
if "%PICKLE_DRIVE%"=="" set "PICKLE_DRIVE=G:\내 드라이브\피클"
:loop
python tools\watchdog.py --drive "%PICKLE_DRIVE%" --stale 180
if errorlevel 2 (
  echo %date% %time% heartbeat older than 3 minutes, stopping hub.py
  powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*tools\\hub.py*' -and $_.CommandLine -notlike '*watchdog.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
)
timeout /t 30 /nobreak >nul
goto loop
