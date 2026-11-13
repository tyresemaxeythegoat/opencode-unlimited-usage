Set WshShell = CreateObject("WScript.Shell")
localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
launcherScript = localAppData & "\opencode-unlimited\windows\desktop_launcher.py"
WshShell.Run "pythonw.exe """ & launcherScript & """", 0, False
