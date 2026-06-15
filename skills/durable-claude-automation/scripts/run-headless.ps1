<#
  run-headless.ps1 — run a headless `claude -p` job from a prompt file, app-independent.
  Called by a Windows Task Scheduler action (see register-headless-task.ps1), or directly.

  Usage:
    run-headless.ps1 -PromptFile C:\path\prompt.txt -AllowedTools "mcp__my-server" -WorkingDirectory C:\repo
    run-headless.ps1 -PromptFile ... -DryRun        # prepend a READ-ONLY banner, for verification
#>
param(
  [Parameter(Mandatory)] [string]$PromptFile,
  [string]$AllowedTools = '',                 # single-token server grant works; comma-joined lists do NOT parse
  [string]$WorkingDirectory = (Get-Location).Path,
  [string]$LogDir = '',
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
Set-Location $WorkingDirectory

# locate the desktop app's CLI shim
$claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
if (-not $claude) { $claude = "$env:LOCALAPPDATA\Microsoft\WindowsApps\claude.cmd" }
if (-not (Test-Path $claude)) { throw "claude CLI not found (looked for PATH + WindowsApps\claude.cmd)" }

$prompt = Get-Content $PromptFile -Raw
if ($DryRun) { $prompt = "[DRY RUN - verification only. READ-ONLY: do NOT modify anything, place no orders, make no commits. Confirm the data path and reply with a one-line status.]`n`n" + $prompt }

if (-not $LogDir) { $LogDir = Join-Path $WorkingDirectory 'logs' }
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force $LogDir | Out-Null }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $LogDir "headless-$stamp.log"

"[$(Get-Date -Format o)] start headless (DryRun=$DryRun) cwd=$WorkingDirectory" | Tee-Object $log

$args = @('-p', $prompt, '--permission-mode', 'dontAsk')
if ($AllowedTools) { $args += @('--allowedTools', $AllowedTools) }
& $claude @args 2>&1 | Tee-Object $log -Append

$code = $LASTEXITCODE
"[$(Get-Date -Format o)] exit=$code" | Tee-Object $log -Append
exit $code
