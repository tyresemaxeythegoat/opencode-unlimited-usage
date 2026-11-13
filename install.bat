@echo off
setlocal
cd /d "%~dp0"
echo Starting Opencode Unlimited Windows Installer...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
