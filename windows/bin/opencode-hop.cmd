@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%..\windows\zen_hop.py" %*
exit /b %ERRORLEVEL%
