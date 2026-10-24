@echo off
rem Compatibility entry: actual startup, checks and lifecycle live in PowerShell.
call "%~dp0start-bot.cmd" %*
exit /b %ERRORLEVEL%
