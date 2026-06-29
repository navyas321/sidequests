<#
  watcher-preflight.ps1 — shared health preflight for headless claude / MCP watchers.

  Why this exists: headless `claude -p` watchers fail silently in multiple ways:
    (a) auth tokens rotate and 401s go unnoticed for hours
    (b) Scheduled-Task "Last Result: 0" is meaningless for detached launchers
    (c) Windows cp1252 codec crashes when claude prints UTF-8 (e.g. MCP "checkmark")
    (d) required MCP servers may be disconnected before the watcher starts real work

  This script fixes that whole class of "basic" failures once and for all:
    1. Forces UTF-8 everywhere (PYTHONUTF8 + console + $OutputEncoding)  -> no more cp1252 crashes
    2. Pings subscription auth headless                                   -> AUTH_FAIL caught BEFORE the real work
    3. Verifies required MCP servers are Connected                        -> TOOLS_MISSING caught loudly
    4. Writes a per-watcher health record under $HealthDir               -> dashboards + alerts can read it

  Usage — dot-source it (so the UTF-8 env sticks in the caller) AND check the global:
    . "$PSScriptRoot\watcher-preflight.ps1" -Name my-watcher
    if (-not $global:PreflightOK) { exit 11 }

    . "$PSScriptRoot\watcher-preflight.ps1" -Name my-watcher -RequiredServers my-mcp-server
    if (-not $global:PreflightOK) { exit 11 }

  Health record shape (JSON):
    { name, status, detail, authOK, toolsOK, checkedAt, lastSuccessAt? }
  Status values: OK | AUTH_FAIL | TOOLS_MISSING | ERROR

  Reference implementation: life-in-tabs (backlog-watcher + RobinhoodPlanB + /api/health/watchers).

  Windows PowerShell 5.1 compatible (no -AsHashtable, no ternary, no null-coalescing).
#>
param(
  [Parameter(Mandatory=$true)][string]$Name,
  [string[]]$RequiredServers = @(),
  [string]$Claude = "$env:LOCALAPPDATA\Microsoft\WindowsApps\claude.cmd",
  [string]$HealthDir = (Join-Path $env:USERPROFILE 'ask-claude\health'),
  [switch]$SkipAuthPing
)

# ---- 1. Force UTF-8 (kills the recurring cp1252 encode crash) ----
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { chcp 65001 | Out-Null } catch {}
# Subscription auth (never a metered key in headless watchers)
Remove-Item Env:\ANTHROPIC_API_KEY -ErrorAction SilentlyContinue

if (-not (Test-Path $Claude)) { $resolved = (Get-Command claude -ErrorAction SilentlyContinue).Source; if ($resolved) { $Claude = $resolved } }

if (-not (Test-Path $HealthDir)) { New-Item -ItemType Directory -Force $HealthDir | Out-Null }
$healthFile = Join-Path $HealthDir ($Name + '.json')

function Write-WatcherHealth([string]$status, [string]$detail, [bool]$authOK, [bool]$toolsOK) {
  $rec = [ordered]@{
    name      = $Name
    status    = $status          # OK | AUTH_FAIL | TOOLS_MISSING | ERROR
    detail    = $detail
    authOK    = $authOK
    toolsOK   = $toolsOK
    checkedAt = (Get-Date -Format o)
  }
  if ($status -eq 'OK') { $rec['lastSuccessAt'] = (Get-Date -Format o) }
  $tmp = "$healthFile.tmp"
  ($rec | ConvertTo-Json -Depth 6) | Out-File -LiteralPath $tmp -Encoding utf8
  Move-Item -Force $tmp $healthFile
}

$global:PreflightOK = $false

# ---- 2. Auth ping ----
if (-not $SkipAuthPing) {
  $ping = ''
  try { $ping = ('Reply with exactly the token PREFLIGHT_OK and nothing else' | & $Claude -p --permission-mode bypassPermissions 2>&1 | Out-String) }
  catch { $ping = "EXCEPTION: $($_.Exception.Message)" }
  if ($ping -notmatch 'PREFLIGHT_OK') {
    $snippet = (($ping -replace '\s+',' ').Trim())
    if ($snippet.Length -gt 160) { $snippet = $snippet.Substring(0,160) }
    Write-WatcherHealth 'AUTH_FAIL' "headless auth failed - run 'claude /login' interactively. probe: $snippet" $false $false
    Write-Warning "[$Name] PREFLIGHT AUTH_FAIL - $snippet"
    return
  }
}

# ---- 3. Required MCP servers Connected ----
if ($RequiredServers.Count -gt 0) {
  $mcp = ''
  try { $mcp = (& $Claude mcp list 2>&1 | Out-String) } catch { $mcp = "EXCEPTION: $($_.Exception.Message)" }
  $lines = $mcp -split "`r?`n"
  $missing = @()
  foreach ($s in $RequiredServers) {
    $ok = $false
    foreach ($l in $lines) { if (($l -match [regex]::Escape($s)) -and ($l -match 'Connected')) { $ok = $true; break } }
    if (-not $ok) { $missing += $s }
  }
  if ($missing.Count -gt 0) {
    Write-WatcherHealth 'TOOLS_MISSING' ("required MCP not Connected: " + ($missing -join ', ')) $true $false
    Write-Warning "[$Name] PREFLIGHT TOOLS_MISSING - $($missing -join ', ')"
    return
  }
}

Write-WatcherHealth 'OK' 'preflight passed (auth + tools)' $true $true
$global:PreflightOK = $true
