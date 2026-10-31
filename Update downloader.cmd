@echo off
cd /d "%~dp0"
echo Close ClipDock first using Stop ClipDock.cmd.
echo This updates the free download engine to handle platform changes.
".venv\Scripts\python.exe" -m pip install --upgrade "yt-dlp[default]"
pause
