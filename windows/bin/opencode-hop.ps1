$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& python "$ScriptDir\..\windows\zen_hop.py" @args
exit $LASTEXITCODE
