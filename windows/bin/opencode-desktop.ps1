$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& python "$ScriptDir\..\windows\desktop_launcher.py" @args
exit $LASTEXITCODE
