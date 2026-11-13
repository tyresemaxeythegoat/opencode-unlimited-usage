<#
.SYNOPSIS
    Opencode Unlimited Usage - Native Windows Installer (No WSL required)
.DESCRIPTION
    Installs the native Windows smart lane, guard daemon, hop tool, and doctor utility.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

function Write-Ok($msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "  [!]  $msg" -ForegroundColor Yellow
}

function Write-Bad($msg) {
    Write-Host "  [X]  $msg" -ForegroundColor Red
}

function Write-Say($msg) {
    Write-Host "  $msg"
}

Clear-Host
Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "  Opencode Unlimited Usage - Windows Installer" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------- Prerequisites
# 1. Python check
$PythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    Write-Bad "Python 3 is required but was not found in PATH."
    Write-Say "Please install Python 3 (3.8+) from https://www.python.org/ or via Microsoft Store, and check 'Add to PATH'."
    exit 1
}
Write-Ok "Python found: $($PythonCmd.Source)"

# Check pythonw
$PythonWCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
$PythonWPath = if ($PythonWCmd) { $PythonWCmd.Source } else { $PythonCmd.Source }

# 2. Cloudflare WARP check
$WarpCliPath = "C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe"
if (-not (Test-Path $WarpCliPath)) {
    $WarpCmd = Get-Command warp-cli.exe -ErrorAction SilentlyContinue
    if ($WarpCmd) {
        $WarpCliPath = $WarpCmd.Source
    }
}

if (-not (Test-Path $WarpCliPath)) {
    Write-Warn "Cloudflare WARP CLI not found."
    Write-Say "Attempting to install Cloudflare WARP via winget..."
    try {
        winget install --id Cloudflare.Warp --silent --accept-package-agreements --accept-source-agreements
        Start-Sleep -Seconds 5
    } catch {
        Write-Bad "Winget install failed or unavailable."
        Write-Say "Please manually download and install Cloudflare WARP from: https://1.1.1.1/"
        exit 1
    }
}

if (-not (Test-Path $WarpCliPath)) {
    Write-Bad "warp-cli.exe still not found. Please install Cloudflare WARP from https://1.1.1.1/ and run this script again."
    exit 1
}
Write-Ok "Cloudflare WARP CLI found: $WarpCliPath"

# 3. OpenCode check
$OpenCodeCli = "$env:LOCALAPPDATA\Programs\ai.opencode.desktop\resources\opencode-cli.exe"
$OpenCodeApp = "$env:LOCALAPPDATA\Programs\ai.opencode.desktop\OpenCode.exe"
if (-not (Test-Path $OpenCodeCli) -and -not (Test-Path $OpenCodeApp)) {
    $OcCmd = Get-Command opencode.exe -ErrorAction SilentlyContinue
    if ($OcCmd) {
        Write-Ok "OpenCode found: $($OcCmd.Source)"
    } else {
        Write-Warn "OpenCode not found in default paths. Make sure OpenCode is installed from https://opencode.ai/"
    }
} else {
    Write-Ok "OpenCode detected: $OpenCodeCli"
}

# ---------------------------------------------------------------- Target Directories
$DestDir = "$env:LOCALAPPDATA\opencode-unlimited"
$DestWindows = "$DestDir\windows"
$DestBin = "$DestDir\bin"
$DestGuard = "$DestDir\guard"
$DestShim = "$DestDir\shim"

New-Item -ItemType Directory -Force -Path $DestWindows, $DestBin, $DestGuard, $DestShim | Out-Null

# Resolve source directory
$SourceDir = $PSScriptRoot
if (-not (Test-Path "$SourceDir\windows\core.py")) {
    $SourceDir = "$PSScriptRoot\opencode-unlimited-usage"
}
if (-not (Test-Path "$SourceDir\windows\core.py")) {
    $SourceDir = "."
}

Write-Say "Copying files to $DestDir..."
Copy-Item -Path "$SourceDir\windows\*.py" -Destination $DestWindows -Force
Copy-Item -Path "$SourceDir\windows\*.vbs" -Destination $DestWindows -Force -ErrorAction SilentlyContinue
Copy-Item -Path "$SourceDir\windows\*.ps1" -Destination $DestWindows -Force -ErrorAction SilentlyContinue
Copy-Item -Path "$SourceDir\windows\bin\*" -Destination $DestBin -Force
Write-Ok "Installed scripts to $DestWindows"

# ---------------------------------------------------------------- User PATH
Write-Say "Configuring User PATH environment variable..."
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $UserPath) { $UserPath = "" }

$PathEntries = $UserPath -split ";" | Where-Object { $_ -ne "" }
if ($PathEntries -notcontains $DestBin) {
    $NewUserPath = ($PathEntries + $DestBin) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
    Write-Ok "Added $DestBin to User PATH"
} else {
    Write-Ok "$DestBin is already in User PATH"
}

# Also update current session PATH
if ($env:Path -split ";" -notcontains $DestBin) {
    $env:Path = "$DestBin;$env:Path"
}

# ---------------------------------------------------------------- Configure WARP
Write-Say "Configuring Cloudflare WARP tunnel..."
$regStatus = (& "$WarpCliPath" --accept-tos registration show 2>&1 | Out-String)
if ($regStatus -notmatch "Account type") {
    & "$WarpCliPath" --accept-tos registration new 2>&1 | Out-Null
}
& "$WarpCliPath" --accept-tos mode warp 2>&1 | Out-Null
& "$WarpCliPath" --accept-tos connect 2>&1 | Out-Null

$Connected = $false
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Seconds 2
    $statusOut = (& "$WarpCliPath" --accept-tos status 2>&1 | Out-String)
    if ($statusOut -match "Connected") {
        $Connected = $true
        break
    }
}

if ($Connected) {
    Write-Ok "Cloudflare WARP is Connected (TUN mode)"
} else {
    Write-Warn "WARP is connecting... (The background keeper will maintain it)"
}

# ---------------------------------------------------------------- Background Guard Service
Write-Say "Registering background Zen Guard service..."

# Stop any running old guard processes
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*zen_guard.py*" } | ForEach-Object {
    try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
}

# Create Startup runner script (VBScript ensures zero command window popups)
$StartupDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$VbsPath = "$StartupDir\opencode-unlimited-guard.vbs"
$VbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """$PythonWPath"" """ & WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\opencode-unlimited\windows\zen_guard.py""", 0, False
"@
Set-Content -Path $VbsPath -Value $VbsContent -Encoding ASCII
Write-Ok "Registered logon startup runner: $VbsPath"

# Start the guard immediately
Start-Process -FilePath $PythonWPath -ArgumentList "`"$DestWindows\zen_guard.py`"" -WindowStyle Hidden
Write-Ok "Zen Guard background watcher started"

# ---------------------------------------------------------------- Desktop App Integration
$DesktopExe = "$env:LOCALAPPDATA\Programs\ai.opencode.desktop\OpenCode.exe"
if (Test-Path $DesktopExe) {
    Write-Say "Configuring OpenCode Desktop app integration..."
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$DestWindows\setup_desktop_shortcuts.ps1" | Out-Null
        Write-Ok "Desktop shortcuts created: 'OpenCode (Unlimited)'"
    } catch {}
}

# ---------------------------------------------------------------- Run Diagnostics
Write-Host ""
Write-Say "Running diagnostic health check..."
& python "$DestWindows\doctor.py"

Write-Host ""
Write-Host "  ================================================================" -ForegroundColor Cyan
Write-Host "  INSTALLATION COMPLETE!" -ForegroundColor Green
Write-Host "  ================================================================" -ForegroundColor Cyan
Write-Say "You can now run:"
Write-Host "    opencode             " -NoNewline -ForegroundColor Yellow
Write-Say "Launch OpenCode with automated IPv6 edge rotation"
Write-Host "    opencode-hop         " -NoNewline -ForegroundColor Yellow
Write-Say "Manually rotate to a fresh /64 identity"
Write-Host "    opencode-doctor      " -NoNewline -ForegroundColor Yellow
Write-Say "Check system and tunnel health"
Write-Host ""
Write-Say "Tip: Close and re-open any existing terminal windows so PATH updates take effect."
Write-Host ""
