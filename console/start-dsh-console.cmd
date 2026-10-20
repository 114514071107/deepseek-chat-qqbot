@echo off
rem ds-niang console launcher - delegates to windowless vbs
rem double-click, then open http://127.0.0.1:7850 in browser
wscript "%~dp0start-dsh-console.vbs"
echo dsh-console started on http://127.0.0.1:7850
