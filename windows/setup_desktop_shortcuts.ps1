<#
.SYNOPSIS
    Creates OpenCode (Unlimited) shortcuts on Desktop and in Start Menu
#>

$WshShell = New-Object -ComObject WScript.Shell
$LocalAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
$DesktopPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
$ProgramsPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)

$OpenCodeExe = "$LocalAppData\Programs\ai.opencode.desktop\OpenCode.exe"
if (-not (Test-Path $OpenCodeExe)) {
    exit 0
}

$ShortcutLocations = @(
    "$DesktopPath\OpenCode (Unlimited).lnk",
    "$ProgramsPath\OpenCode (Unlimited).lnk"
)

foreach ($loc in $ShortcutLocations) {
    try {
        $shortcut = $WshShell.CreateShortcut($loc)
        $shortcut.TargetPath = $OpenCodeExe
        $shortcut.WorkingDirectory = "$LocalAppData\Programs\ai.opencode.desktop"
        $shortcut.Description = "OpenCode Desktop (Protected by Zen Guard)"
        $shortcut.IconLocation = "$OpenCodeExe,0"
        $shortcut.Save()
        Write-Host "Created shortcut: $loc" -ForegroundColor Green
    } catch {
        Write-Warning "Could not create shortcut at ${loc}: $_"
    }
}
