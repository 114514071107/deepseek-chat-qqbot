@echo off
setlocal
rem Same authenticated worker/controller and final result as the instance entry.
set "DSH_LAUNCH_WITH_CONSOLE="
set "DSH_ENTRY_RUNTIME_ROOT="
if exist "%~dp0..\start-bot.ps1" (
  set "DSH_ENTRY_RUNTIME_ROOT=%~dp0.."
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0..\launcher-shell.ps1" -CoreScript "%~dp0..\start-bot.ps1" -Component Console %*
) else (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0..\scripts\launcher-shell.ps1" -CoreScript "%~dp0..\scripts\start-bot.ps1" -Component Console %*
)
exit /b %ERRORLEVEL%
