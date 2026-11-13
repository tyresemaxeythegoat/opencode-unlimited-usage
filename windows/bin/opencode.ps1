$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& python "$ScriptDir\..\windows\zen_lane.py" @args
exit $LASTEXITCODE
