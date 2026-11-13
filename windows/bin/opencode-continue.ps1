$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$scriptDir\..\windows\auto_continue.py" @args
