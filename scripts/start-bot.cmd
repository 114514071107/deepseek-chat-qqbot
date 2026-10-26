@echo off
setlocal
rem User entry starts Bot and the authenticated Console (default port 7850).
rem Keep defaults in the core so explicit switches/ports are never duplicated.
set "DSH_LAUNCH_WITH_CONSOLE=1"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0launcher-shell.ps1" -CoreScript "%~dp0start-bot.ps1" %*
set "DSH_LAUNCH_CODE=%ERRORLEVEL%"
if not "%DSH_LAUNCH_CODE%"=="0" (
  echo Launch failed. See the message and log path above.
  if not defined DSH_LAUNCHER_NO_PAUSE pause
)
exit /b %DSH_LAUNCH_CODE%
