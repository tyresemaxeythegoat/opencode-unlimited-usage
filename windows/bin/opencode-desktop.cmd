@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%..\windows\desktop_launcher.py" %*
exit /b %ERRORLEVEL%
