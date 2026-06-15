<#
  claude-app-watchdog.ps1 — relaunch the Claude desktop app if it has crashed/exited, so the
  remote-control session (claude.ai/phone) and in-app state can re-attach.

  The remote-control bridge does NOT auto-reconnect after the owning process dies (GH #60790),
  and there is no `remoteControlAtStartup` setting. Keeping the app process alive is the
  foundation for remote-session resilience. Idempotent: no-op while a `claude` process exists.

  Run by Windows Task Scheduler every few minutes (see register-watchdog.ps1).
#>
param([switch]$Force)

# auto-detect the Store AppID (portable across machines)
$appId = (Get-StartApps | Where-Object { $_.Name -eq 'Claude' } | Select-Object -First 1).AppID
$logDir = Join-Path $env:LOCALAPPDATA 'Claude'
$log = Join-Path $logDir 'app-watchdog.log'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$stamp = Get-Date -Format o

if (-not $appId) { "[$stamp] ERROR - could not resolve Claude AppID via Get-StartApps" | Add-Content $log; exit 1 }

$running = @(Get-Process -Name claude -ErrorAction SilentlyContinue)
if ($running.Count -gt 0 -and -not $Force) {
  "[$stamp] OK - $($running.Count) claude process(es) running; no action" | Add-Content $log
  exit 0
}

"[$stamp] Claude app not running - relaunching via shell:AppsFolder\$appId" | Add-Content $log
try {
  Start-Process "shell:AppsFolder\$appId" -ErrorAction Stop
  "[$stamp] relaunch invoked OK" | Add-Content $log
  exit 0
} catch {
  "[$stamp] RELAUNCH FAILED: $_" | Add-Content $log
  exit 1
}
