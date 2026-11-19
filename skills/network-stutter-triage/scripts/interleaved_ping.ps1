# Interleaved ping recorder: one loop pings every target back to back, one row per pass, so the
# targets are measured at nearly the same moment (a lost ping delays the later targets in that pass
# by up to -TimeoutMs). That shared timing is what lets ping_report.py decide "the network" versus
# "that one device". Each row is written as soon as it is measured, so Ctrl+C keeps what was recorded.
# ASCII only (Windows PowerShell 5.1 reads scripts as cp1252).
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File interleaved_ping.ps1 -Targets 192.168.1.1,192.168.1.20 -Seconds 150 -Out pings.csv
# Run nothing else network-heavy from this host while it records.
param(
  [Parameter(Mandatory = $true)][string[]]$Targets,
  [int]$Seconds = 150,
  [int]$IntervalMs = 700,
  [int]$TimeoutMs = 1000,
  [string]$Out = "pings.csv"
)
$ErrorActionPreference = 'Stop'
# "powershell -File" passes "a,b,c" as ONE string; split it so both call styles work.
$Targets = @($Targets | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
# Resolve relative AND absolute paths against the current location (Join-Path breaks absolute ones).
$OutPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Out)
$ping = New-Object System.Net.NetworkInformation.Ping
$writer = New-Object System.IO.StreamWriter($OutPath, $false, (New-Object System.Text.UTF8Encoding($false)))
$passes = 0
try {
  $writer.WriteLine("t_ms," + ($Targets -join ","))
  $writer.Flush()
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $deadline = $Seconds * 1000
  while ($sw.ElapsedMilliseconds -lt $deadline) {
    $t0 = $sw.ElapsedMilliseconds
    $row = @("$t0")
    foreach ($ip in $Targets) {
      try {
        $r = $ping.Send($ip, $TimeoutMs)
        if ($r.Status -eq 'Success') { $row += "$($r.RoundtripTime)" } else { $row += "-1" }
      } catch {
        $row += "-1"
      }
    }
    $writer.WriteLine($row -join ",")
    $writer.Flush()
    $passes++
    $spent = $sw.ElapsedMilliseconds - $t0
    if ($spent -lt $IntervalMs) { Start-Sleep -Milliseconds ($IntervalMs - $spent) }
  }
} finally {
  $writer.Close()
}
Write-Output ("{0} passes x {1} targets -> {2}" -f $passes, $Targets.Count, $OutPath)
