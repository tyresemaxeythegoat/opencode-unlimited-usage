$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& python "$ScriptDir\..\windows\doctor.py" @args
exit $LASTEXITCODE
