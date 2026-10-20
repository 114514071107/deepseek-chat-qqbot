@echo off
rem Modified 2026-10-21: use venv explicitly; show UTF-8 logs in terminal.
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
cd /d D:\dsbot
set "PATH=D:\dsbot\venv\Scripts;%PATH%;D:\dsbot\bin"
"D:\dsbot\venv\Scripts\astrbot.exe" run
pause
