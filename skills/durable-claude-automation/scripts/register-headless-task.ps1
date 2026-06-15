<#
  register-headless-task.ps1 — register a Windows Task Scheduler job that runs a headless
  `claude -p` job on a weekly schedule. OS-level: survives Claude app restarts/updates AND reboots.

  Usage:
    register-headless-task.ps1 -TaskName "MyJob" -PromptFile C:\path\prompt.txt `
      -AllowedTools "mcp__my-server" -WorkingDirectory C:\repo `
      -At 10:04 -DaysOfWeek Mon,Tue,Wed,Thu,Fri
#>
param(
  [Parameter(Mandatory)] [string]$TaskName,
  [Parameter(Mandatory)] [string]$PromptFile,
  [string]$AllowedTools = '',
  [Parameter(Mandatory)] [string]$WorkingDirectory,
  [Parameter(Mandatory)] [string]$At,                                  # "10:04" 24h or "10:04AM"
  [string[]]$DaysOfWeek = @('Monday','Tuesday','Wednesday','Thursday','Friday'),
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'run-headless.ps1'
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

# expand day abbreviations
$map = @{ Mon='Monday';Tue='Tuesday';Wed='Wednesday';Thu='Thursday';Fri='Friday';Sat='Saturday';Sun='Sunday' }
$days = $DaysOfWeek | ForEach-Object { if ($map.ContainsKey($_)) { $map[$_] } else { $_ } }

$argline = "-ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File `"$runner`" -PromptFile `"$PromptFile`" -WorkingDirectory `"$WorkingDirectory`""
if ($AllowedTools) { $argline += " -AllowedTools `"$AllowedTools`"" }
if ($DryRun)       { $argline += " -DryRun" }

$action    = New-ScheduledTaskAction -Execute $ps -Argument $argline -WorkingDirectory $WorkingDirectory
$trigger   = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $At
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -DontStopOnIdleEnd -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Headless claude job (durable; survives app restarts)" -Force | Out-Null
Write-Host "Registered '$TaskName' (weekdays $At). Verify: Start-ScheduledTask -TaskName '$TaskName'; then Get-ScheduledTaskInfo '$TaskName' and read logs\."
