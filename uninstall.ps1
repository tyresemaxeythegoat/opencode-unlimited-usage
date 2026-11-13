<#
.SYNOPSIS
    Opencode Unlimited Usage - Native Windows Uninstaller
#>

[CmdletBinding()]
param()

Write-Host ""
Write-Host "  ==============================================" -ForegroundColor Yellow
Write-Host "  Opencode Unlimited - Windows Uninstaller" -ForegroundColor Yellow
Write-Host "  ==============================================" -ForegroundColor Yellow
Write-Host ""

# 1. Restore OpenCode Desktop if patched
$UnpatchScript = "$env:LOCALAPPDATA\opencode-unlimited\windows\unpatch_desktop.ps1"
if (Test-Path $UnpatchScript) {
    Write-Host "Restoring OpenCode Desktop original CLI engine..."
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $UnpatchScript | Out-Null
        Write-Host "  OpenCode Desktop unpatched successfully."
    } catch {}
}

# 2. Remove OpenCode (Unlimited) shortcuts
$DesktopLnk = "$([Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop))\OpenCode (Unlimited).lnk"
$ProgramsLnk = "$([Environment]::GetFolderPath([Environment+SpecialFolder]::Programs))\OpenCode (Unlimited).lnk"
if (Test-Path $DesktopLnk) { Remove-Item -Path $DesktopLnk -Force -ErrorAction SilentlyContinue }
if (Test-Path $ProgramsLnk) { Remove-Item -Path $ProgramsLnk -Force -ErrorAction SilentlyContinue }
Write-Host "  Removed desktop shortcuts."

# 3. Stop background processes
Write-Host "Stopping background processes..."
$ProcessPatterns = @("zen_guard.py", "lane_proxy.py", "warp_keeper.py")
Get-CimInstance Win32_Process | ForEach-Object {
    $cmd = $_.CommandLine
    foreach ($p in $ProcessPatterns) {
        if ($cmd -and $cmd -like "*$p*") {
            try {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
                Write-Host "  Terminated process PID $($_.ProcessId) ($p)"
            } catch {}
        }
    }
}

# 2. Remove Startup shortcut
$VbsPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\opencode-unlimited-guard.vbs"
if (Test-Path $VbsPath) {
    Remove-Item -Path $VbsPath -Force -ErrorAction SilentlyContinue
    Write-Host "  Removed startup runner: $VbsPath"
}

# 3. Clean up User PATH
$DestBin = "$env:LOCALAPPDATA\opencode-unlimited\bin"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath) {
    $Entries = $UserPath -split ";" | Where-Object { $_ -ne "" -and $_ -ne $DestBin }
    $NewPath = $Entries -join ";"
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    Write-Host "  Cleaned $DestBin from User PATH"
}

# 4. Remove installation directory
$DestDir = "$env:LOCALAPPDATA\opencode-unlimited"
if (Test-Path $DestDir) {
    try {
        Remove-Item -Path $DestDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  Removed directory: $DestDir"
    } catch {
        Write-Host "  Could not remove some files in $DestDir (they may be locked)"
    }
}

Write-Host ""
Write-Host "  Opencode Unlimited has been successfully uninstalled from Windows." -ForegroundColor Green
Write-Host ""
