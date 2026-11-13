@echo off
setlocal
cd /d "%~dp0"
echo Starting Opencode Unlimited Windows Uninstaller...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
echo.
pause
