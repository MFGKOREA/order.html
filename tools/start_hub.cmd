@echo off
rem Pickle hub: start it and restart it if it ever stops. Settings (keys, folder) come from
rem hub.env next to this file: lines like  set PICKLE_DRIVE=G:\내 드라이브\피클  (never commit hub.env).
chcp 65001 >nul
cd /d "%~dp0.."
if exist "%~dp0hub.env.cmd" call "%~dp0hub.env.cmd"
if "%PICKLE_DRIVE%"=="" set "PICKLE_DRIVE=G:\내 드라이브\피클"
start "hub-watch" /min cmd /c "%~dp0watch_hub.cmd"
:loop
python tools\hub.py --drive "%PICKLE_DRIVE%" --ai %HUB_ARGS%
echo %date% %time% hub stopped, restarting in 10 s
timeout /t 10 /nobreak >nul
goto loop
