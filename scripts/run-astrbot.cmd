@echo off
rem DEPLOY: if AstrBot root is not D:\dsbot, replace all D:\dsbot below
set "PATH=%PATH%;D:\dsbot\bin"
cd /d D:\dsbot
venv\Scripts\astrbot.exe run >> D:\dsbot\astrbot-run.log 2>&1
