<#
  stop-mock.ps1 — stop ONLY the mock host (the process listening on the offset base port).

  SAFETY (this is the whole point): the real host runs the SAME binary name (sunshine.exe),
  so this NEVER matches by process name — matching by name would kill the real host too.
  It kills strictly the PID that owns the mock's base port. Extra guard: if that PID is
  somehow the same process that owns the REAL host's port, it ABORTS rather than risk the
  real service.

  Usage:
    stop-mock.ps1                         # uses the defaults below
    stop-mock.ps1 -BasePort 48900 -RealPort 47989
#>
param(
  [int]$BasePort = 48900,     # the mock's offset base port
  [int]$RealPort = 47989      # a port owned by the REAL host (default Sunshine/Apollo HTTP)
)

$mock = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -eq $BasePort } | Select-Object -First 1
if (-not $mock) { Write-Host "Mock not running (nothing on :$BasePort)."; exit 0 }
$mpid = $mock.OwningProcess

# Guard: never kill the real host. If the base-port owner is also the real-port owner, abort.
$realPid = (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -eq $RealPort } | Select-Object -First 1).OwningProcess
if ($realPid -and $mpid -eq $realPid) {
    Write-Host "REFUSING: the :$BasePort owner (PID $mpid) is also the real host on :$RealPort. Aborting to protect the real host."
    exit 1
}

Stop-Process -Id $mpid -Force
Write-Host "Mock stopped (PID $mpid). Real host (:$RealPort) untouched."
