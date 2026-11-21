@echo off
rem Puts a shortcut to start_hub.cmd in the Windows Startup folder, so the hub starts at sign-in.
rem Run once. To undo, delete "Pickle hub.lnk" from shell:startup.
set "TARGET=%~dp0start_hub.cmd"
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Pickle hub.lnk"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%~dp0..'; $s.WindowStyle=7; $s.Save()"
echo Autostart set: %LINK%
