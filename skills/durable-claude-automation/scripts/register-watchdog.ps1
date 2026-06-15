<#
  register-watchdog.ps1 — register the Claude app watchdog as a Windows Task Scheduler job
  that runs every N minutes and relaunches the desktop app if it has crashed.

  Usage:  register-watchdog.ps1            # default: every 3 minutes
          register-watchdog.ps1 -EveryMinutes 5
#>
param([int]$EveryMinutes = 3, [string]$TaskName = 'ClaudeApp-Watchdog')
$ErrorActionPreference = 'Stop'
$watchdog = Join-Path $PSScriptRoot 'claude-app-watchdog.ps1'
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

$action = New-ScheduledTaskAction -Execute $ps -Argument "-ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File `"$watchdog`""
# single repetition trigger with a valid FUTURE start (a past -Once start can cause Access Denied)
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Relaunch Claude desktop app if it crashes (remote-session resilience)" -Force | Out-Null
Write-Host "Registered '$TaskName' (every $EveryMinutes min). Verify: Start-ScheduledTask -TaskName '$TaskName'; then read `$env:LOCALAPPDATA\Claude\app-watchdog.log"
