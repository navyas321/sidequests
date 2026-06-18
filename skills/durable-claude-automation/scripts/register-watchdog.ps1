<#
  register-watchdog.ps1 — register the Claude app watchdog as a Windows Task Scheduler job
  that runs every N minutes and relaunches the desktop app if it has crashed.

  Launches via wscript + run-hidden.vbs so NO console window flashes on each run
  (powershell.exe under Task Scheduler flashes a conhost window that steals focus —
  critical for a frequent task; -WindowStyle Hidden alone does NOT prevent the flash).

  Two scheduling modes:
    -AtTimes "09:50","16:10"   # DISCRETE weekday triggers, NO polling (recommended — no
                               #   periodic window/CPU blips; checks only at those times)
    -EveryMinutes 5            # legacy polling fallback (every N min)
  Discrete times are preferred: the watchdog only needs to catch a crash, not poll constantly.

  Usage:  register-watchdog.ps1 -AtTimes "09:50","16:10"
          register-watchdog.ps1 -EveryMinutes 10
#>
param(
  [string[]]$AtTimes = @('09:50','16:10'),   # default: twice on weekdays, no polling
  [int]$EveryMinutes = 0,                     # >0 switches to polling mode
  [string]$TaskName = 'ClaudeApp-Watchdog'
)
$ErrorActionPreference = 'Stop'
$watchdog = Join-Path $PSScriptRoot 'claude-app-watchdog.ps1'
$vbs      = Join-Path $PSScriptRoot 'run-hidden.vbs'
$wscript  = "$env:SystemRoot\System32\wscript.exe"

# wscript (no console) -> run-hidden.vbs -> powershell hidden. No window, no focus-steal.
$action = New-ScheduledTaskAction -Execute $wscript -Argument "`"$vbs`" `"$watchdog`""

if ($EveryMinutes -gt 0) {
  # polling fallback: one repetition trigger with a FUTURE start (a past -Once start can cause Access Denied)
  $triggers = @(New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes))
  $desc = "Relaunch Claude app if crashed (hidden; every $EveryMinutes min)"
} else {
  # discrete weekday time triggers, no repetition. NOTE: -AtLogOn needs elevation; omitted by default.
  $triggers = $AtTimes | ForEach-Object { New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $_ }
  $desc = "Relaunch Claude app if crashed (hidden; weekdays $($AtTimes -join '/'), no polling)"
}
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Description $desc -Force | Out-Null
Write-Host "Registered '$TaskName'. Verify: Start-ScheduledTask -TaskName '$TaskName'; then read `$env:LOCALAPPDATA\Claude\app-watchdog.log"
