<#
.SYNOPSIS
  Install a "Turn Off Display" Start-menu shortcut with a conflict-free hotkey.

.DESCRIPTION
  Copies the bundled Turn-Off-Display.ps1 / .vbs to a stable install dir, then
  creates a Start-menu .lnk that launches them silently (via wscript -> hidden
  PowerShell). Picks a Ctrl+Alt+<key> hotkey that doesn't collide with any
  existing shortcut hotkey, and avoids the Intel-graphics Ctrl+Alt+Arrow combos.

.PARAMETER InstallDir
  Where the runnable scripts live. Default: %LOCALAPPDATA%\display-off

.PARAMETER Name
  Shortcut display name. Default: "Turn Off Display"

.PARAMETER Hotkey
  Force a specific hotkey (e.g. "Ctrl+Alt+O"). Omit to auto-pick a free one.
  Pass "none" to skip assigning a hotkey.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install-shortcut.ps1
#>
param(
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'display-off'),
  [string]$Name = 'Turn Off Display',
  [string]$Hotkey
)

$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot

# 1. Copy the runnable scripts to a stable location.
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item (Join-Path $src 'Turn-Off-Display.ps1') $InstallDir -Force
Copy-Item (Join-Path $src 'Turn-Off-Display.vbs') $InstallDir -Force
$vbs = Join-Path $InstallDir 'Turn-Off-Display.vbs'

$ws = New-Object -ComObject WScript.Shell

# Normalize a hotkey string ("Alt+Ctrl+O" == "Ctrl+Alt+O") for comparison.
function Normalize-Hotkey([string]$h) {
  if (-not $h) { return '' }
  ($h -split '\+' | ForEach-Object { $_.Trim().ToLower() } | Sort-Object) -join '+'
}

# 2. Pick a conflict-free hotkey unless one was forced.
if ($Hotkey -and $Hotkey.ToLower() -eq 'none') {
  $chosen = $null
} elseif ($Hotkey) {
  $chosen = $Hotkey
} else {
  $dirs = @(
    (Join-Path $env:APPDATA   'Microsoft\Windows\Start Menu\Programs'),
    (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'),
    (Join-Path $env:USERPROFILE 'Desktop'),
    (Join-Path $env:PUBLIC 'Desktop')
  )
  $used = @{}
  foreach ($d in $dirs) {
    if (Test-Path $d) {
      Get-ChildItem $d -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {
        $h = $ws.CreateShortcut($_.FullName).Hotkey
        if ($h) { $used[(Normalize-Hotkey $h)] = $_.Name }
      }
    }
  }
  # Preference order; arrow combos are intentionally excluded (Intel screen-rotation).
  $candidates = @('Ctrl+Alt+O','Ctrl+Alt+M','Ctrl+Alt+B','Ctrl+Alt+J','Ctrl+Alt+L','Ctrl+Alt+0','Ctrl+Alt+9')
  $chosen = $candidates | Where-Object { -not $used.ContainsKey((Normalize-Hotkey $_)) } | Select-Object -First 1
  if (-not $chosen) { Write-Warning 'All preferred hotkeys are taken; installing without a hotkey.' }
}

# 3. Create the Start-menu shortcut.
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$lnk = Join-Path $startMenu "$Name.lnk"
$sc = $ws.CreateShortcut($lnk)
$sc.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$sc.Arguments = '"' + $vbs + '"'
$sc.WorkingDirectory = $InstallDir
$sc.IconLocation = (Join-Path $env:WINDIR 'System32\imageres.dll') + ',108'
$sc.Description = 'Turn off the display (monitor sleep). Move mouse / press a key to wake.'
$sc.WindowStyle = 7
if ($chosen) { $sc.Hotkey = $chosen }
$sc.Save()

$verify = $ws.CreateShortcut($lnk)
Write-Output "Installed: $lnk"
Write-Output "Scripts:   $InstallDir"
if ($verify.Hotkey) { Write-Output "Hotkey:    $($verify.Hotkey)" } else { Write-Output "Hotkey:    (none)" }
