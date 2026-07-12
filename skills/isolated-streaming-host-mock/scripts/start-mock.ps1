<#
  start-mock.ps1 — start an ISOLATED mock Sunshine/Apollo/Vibepollo host for testing a
  streaming client, on a machine that ALREADY runs a real host. Idempotent: no-op if the
  offset base port is already bound.

  ISOLATION (why this never disrupts the real host or your gaming):
   - A FULL host install prefix is copied to $Dir (see the SKILL for what to exclude), with
     OFFSET ports via the config `port = <base>` value — no collision with the real host's
     defaults (47984/47989/47990/48010).
   - The binary is run FROM its own directory (cwd = prefix) with its OWN config/state dir,
     so assets/shaders/plugins resolve and all state stays inside the copy. A bare external
     config without the full prefix CRASHES ("Platform failed to initialize" ->
     "terminate called recursively").
   - Idle = no display capture. A stream uses a VIRTUAL display driver (e.g. SudoVDA), so the
     physical monitor you game on is never grabbed.

  Usage:
    start-mock.ps1                       # uses the defaults below
    start-mock.ps1 -Dir C:\path\to\mock-host\host -BasePort 48900
#>
param(
  [string]$Dir      = "$PSScriptRoot\host",     # the copied, isolated install prefix
  [int]   $BasePort = 48900,                      # offset base; ALL host ports derive from this
  [string]$Config   = "config\sunshine.conf",     # config path RELATIVE to $Dir
  [string]$Exe      = "sunshine.exe"              # the host binary inside the prefix
)
$ErrorActionPreference = "Stop"

# Already running? (someone owns the base port) -> idempotent no-op.
$existing = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -eq $BasePort } | Select-Object -First 1
if ($existing) { Write-Host "Mock already running (PID $($existing.OwningProcess)) on :$BasePort."; exit 0 }

# Run the binary FROM its own directory (cwd = prefix) so assets/shaders/plugins resolve and
# state stays inside the copy. -WindowStyle Hidden keeps it out of the way.
$p = Start-Process -FilePath "$Dir\$Exe" -ArgumentList $Config `
        -WorkingDirectory $Dir -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput "$Dir\mock-out.txt" -RedirectStandardError "$Dir\mock-err.txt"
Start-Sleep -Seconds 6

# Confirm OUR PID owns the base port (not just anyone).
$ok = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -eq $BasePort -and $_.OwningProcess -eq $p.Id }

# Best-effort tailnet IP (100.64.0.0/10 CGNAT range Tailscale uses) for the connect hint.
$ip = (Get-NetIPAddress -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -like '100.*' } | Select-Object -First 1).IPAddress
if (-not $ip) { $ip = '<host-ip>' }

if ($ok) {
    Write-Host "Mock started: PID $($p.Id)"
    Write-Host "  Stream host : ${ip}:$BasePort            (or discover via mDNS by sunshine_name)"
    Write-Host "  Web manager : https://${ip}:$($BasePort + 1)   (creds from your config)"
} else {
    Write-Host "Mock failed to bind :$BasePort - see $Dir\mock-err.txt"; exit 1
}
