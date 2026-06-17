<#
  register-watchdog.ps1 — register the Claude app watchdog as a Windows Task Scheduler job
  that runs every N minutes and relaunches the desktop app if it has crashed.

  Launches via wscript + run-hidden.vbs so NO console window flashes on each run
  (powershell.exe under Task Scheduler flashes a conhost window that steals focus —
  critical for a frequent task; -WindowStyle Hidden alone does NOT prevent the flash).

  Usage:  register-watchdog.ps1            # default: every 5 minutes, hidden
          register-watchdog.ps1 -EveryMinutes 10
#>
param([int]$EveryMinutes = 5, [string]$TaskName = 'ClaudeApp-Watchdog')
$ErrorActionPreference = 'Stop'
$watchdog = Join-Path $PSScriptRoot 'claude-app-watchdog.ps1'
$vbs      = Join-Path $PSScriptRoot 'run-hidden.vbs'
$wscript  = "$env:SystemRoot\System32\wscript.exe"

# wscript (no console) -> run-hidden.vbs -> powershell hidden. No window, no focus-steal.
$action = New-ScheduledTaskAction -Execute $wscript -Argument "`"$vbs`" `"$watchdog`""
# single repetition trigger with a valid FUTURE start (a past -Once start can cause Access Denied)
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Relaunch Claude desktop app if it crashes (remote-session resilience)" -Force | Out-Null
Write-Host "Registered '$TaskName' (every $EveryMinutes min). Verify: Start-ScheduledTask -TaskName '$TaskName'; then read `$env:LOCALAPPDATA\Claude\app-watchdog.log"
