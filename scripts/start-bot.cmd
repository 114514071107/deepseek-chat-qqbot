@echo off
setlocal
set "DSH_LAUNCH_SHELL="
for /f "delims=" %%I in ('where.exe pwsh.exe 2^>nul') do if not defined DSH_LAUNCH_SHELL set "DSH_LAUNCH_SHELL=%%I"
if not defined DSH_LAUNCH_SHELL if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" set "DSH_LAUNCH_SHELL=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not defined DSH_LAUNCH_SHELL set "DSH_LAUNCH_SHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%DSH_LAUNCH_SHELL%" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0start-bot.ps1" %*
set "DSH_LAUNCH_CODE=%ERRORLEVEL%"
if not "%DSH_LAUNCH_CODE%"=="0" (
  echo Launch failed. See the message and log path above.
  if not defined DSH_LAUNCHER_NO_PAUSE pause
)
exit /b %DSH_LAUNCH_CODE%
