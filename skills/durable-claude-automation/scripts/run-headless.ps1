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

# Resolve the CLI: override -> native installer exe -> PATH -> legacy WindowsApps shim (last resort).
# A claude.cmd wrapper can exist on PATH and still be broken (it may look for a CLI bundled inside the
# desktop app's package, which an app update can remove), so prefer the real exe and PROVE it runs.
function Resolve-ClaudeCli {
  if ($env:CLAUDE_CLI -and $env:CLAUDE_CLI.Trim()) { return $env:CLAUDE_CLI.Trim() }
  $native = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
  if (Test-Path $native) { return $native }
  $onPath = (Get-Command claude -ErrorAction SilentlyContinue).Source
  if ($onPath) { return $onPath }
  $shim = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\claude.cmd'
  if (Test-Path $shim) { return $shim }
  return $null
}
$claude = Resolve-ClaudeCli
if (-not $claude) { throw "claude CLI not found (looked for CLAUDE_CLI, ~\.local\bin\claude.exe, PATH, WindowsApps\claude.cmd)" }
$ver = (& $claude --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "claude CLI at '$claude' does not run: $ver" }
# Free, model-less login check. Read ONLY loggedIn (the same JSON carries account details).
$loggedIn = $null
try { $loggedIn = ((& $claude auth status 2>$null | Out-String) | ConvertFrom-Json).loggedIn } catch { }
if ($loggedIn -eq $false) { throw "claude CLI at '$claude' is logged out - run 'claude auth login' once on this machine" }

$prompt = Get-Content $PromptFile -Raw
if ($DryRun) { $prompt = "[DRY RUN - verification only. READ-ONLY: do NOT modify anything, place no orders, make no commits. Confirm the data path and reply with a one-line status.]`n`n" + $prompt }

if (-not $LogDir) { $LogDir = Join-Path $WorkingDirectory 'logs' }
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force $LogDir | Out-Null }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $LogDir "headless-$stamp.log"

"[$(Get-Date -Format o)] start headless (DryRun=$DryRun) cwd=$WorkingDirectory cli=$claude ($ver)" | Tee-Object $log

$args = @('-p', $prompt, '--permission-mode', 'dontAsk')
if ($AllowedTools) { $args += @('--allowedTools', $AllowedTools) }
& $claude @args 2>&1 | Tee-Object $log -Append

$code = $LASTEXITCODE
"[$(Get-Date -Format o)] exit=$code" | Tee-Object $log -Append
exit $code
