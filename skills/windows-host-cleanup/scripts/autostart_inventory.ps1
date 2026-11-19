# Read-only inventory of what starts automatically on a Windows 10/11 PC, across the common
# sources, with each entry's on/off state. Changes nothing. ASCII only (PowerShell 5.1 reads cp1252).
#
# Covers: both Startup folders; Run and RunOnce (HKCU, HKLM, HKLM 32-bit); Policies\Explorer\Run;
# Task Manager's StartupApproved state; Store (MSIX) app startup tasks; non-default Winlogon
# Shell/Userinit; Active Setup stubs; scheduled tasks triggered at logon, boot, unlock/connect or by
# an event; auto-start services. NOT covered: drivers, shell extensions, Winsock/LSA providers, WMI
# subscriptions and other deep hooks. For an exhaustive list use Sysinternals Autoruns.
#
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File autostart_inventory.ps1
#         ... -Csv out.csv          (write a CSV instead of a table)
#         ... -IncludeMicrosoft     (also list Microsoft tasks, services and Store apps)
# Run elevated to read every service binary's publisher; unelevated still lists everything.
param([string]$Csv, [switch]$IncludeMicrosoft)
$ErrorActionPreference = 'SilentlyContinue'
$rows = New-Object System.Collections.Generic.List[object]

function Add-Row($source, $name, $state, $command) {
  $rows.Add([pscustomobject]@{ Source = $source; Name = $name; State = $state; Command = $command })
}

# Read registry value names/values exactly (Get-ItemProperty -Name treats [ ] as wildcards).
function Get-Values($path) {
  $k = Get-Item -LiteralPath $path
  if (-not $k) { return @() }
  return @($k.GetValueNames() | Where-Object { $_ -ne '' } | ForEach-Object { [pscustomobject]@{ Name = $_; Value = $k.GetValue($_) } })
}

# StartupApproved (what Task Manager toggles): first byte even = on, odd = off. Empirical; Microsoft
# documents no format. A missing value means the item was never toggled, i.e. on.
function Get-Approved($hive, $sub, $name) {
  $k = Get-Item -LiteralPath "$hive\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\$sub"
  if (-not $k) { return 'ON' }
  $v = $k.GetValue($name)
  if ($null -eq $v -or $v.Length -eq 0) { return 'ON' }
  if (($v[0] -band 1) -eq 1) { return 'OFF' } else { return 'ON' }
}

# 1. Startup folders
$folders = @(
  @{ Path = [Environment]::GetFolderPath('Startup'); Hive = 'HKCU:'; Label = 'Startup folder (user)' },
  @{ Path = [Environment]::GetFolderPath('CommonStartup'); Hive = 'HKLM:'; Label = 'Startup folder (all users)' }
)
foreach ($f in $folders) {
  Get-ChildItem -LiteralPath $f.Path -File | Where-Object { $_.Name -ne 'desktop.ini' } | ForEach-Object {
    Add-Row $f.Label $_.Name (Get-Approved $f.Hive 'StartupFolder' $_.Name) $_.FullName
  }
}

# 2. Run / RunOnce / policy Run keys
$runKeys = @(
  @{ Key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'; Hive = 'HKCU:'; Sub = 'Run'; Label = 'Run (HKCU)' },
  @{ Key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'; Hive = $null; Sub = $null; Label = 'RunOnce (HKCU)' },
  @{ Key = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run'; Hive = 'HKLM:'; Sub = 'Run'; Label = 'Run (HKLM)' },
  @{ Key = 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'; Hive = 'HKLM:'; Sub = 'Run32'; Label = 'Run (HKLM 32-bit)' },
  @{ Key = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce'; Hive = $null; Sub = $null; Label = 'RunOnce (HKLM)' },
  @{ Key = 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce'; Hive = $null; Sub = $null; Label = 'RunOnce (HKLM 32-bit)' },
  @{ Key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run'; Hive = $null; Sub = $null; Label = 'Policy Run (HKCU)' },
  @{ Key = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run'; Hive = $null; Sub = $null; Label = 'Policy Run (HKLM)' }
)
foreach ($r in $runKeys) {
  foreach ($v in (Get-Values $r.Key)) {
    $state = 'ON'
    if ($r.Sub) { $state = Get-Approved $r.Hive $r.Sub $v.Name }
    Add-Row $r.Label $v.Name $state ([string]$v.Value)
  }
}

# 3. Winlogon Shell / Userinit, only when changed from the Windows defaults
$wl = Get-Item -LiteralPath 'HKLM:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon'
if ($wl) {
  $shell = [string]$wl.GetValue('Shell')
  if ($shell -and $shell.Trim() -ne 'explorer.exe') { Add-Row 'Winlogon Shell (non-default)' 'Shell' 'ON' $shell }
  $ui = [string]$wl.GetValue('Userinit')
  if ($ui -and ($ui.Trim().TrimEnd(',') -notmatch '^[A-Za-z]:\\Windows\\system32\\userinit\.exe$')) {
    Add-Row 'Winlogon Userinit (non-default)' 'Userinit' 'ON' $ui
  }
}

# 4. Active Setup stubs (run once per user at logon); Windows' own stubs hidden unless -IncludeMicrosoft
foreach ($root in @('HKLM:\Software\Microsoft\Active Setup\Installed Components', 'HKLM:\Software\WOW6432Node\Microsoft\Active Setup\Installed Components')) {
  Get-ChildItem -LiteralPath $root | ForEach-Object {
    $stub = [string]$_.GetValue('StubPath')
    $isWindowsStub = ($stub -notmatch '(?i)\.exe') -or ($stub -match '(?i)(%SystemRoot%|\\Windows\\|^\s*"?(rundll32|regsvr32|ie4uinit|unregmp2)(\.exe)?)')
    if ($stub -and ($IncludeMicrosoft -or -not $isWindowsStub)) {
      $label = [string]$_.GetValue('')
      if (-not $label) { $label = $_.PSChildName }
      $state = if ([string]$_.GetValue('IsInstalled') -eq '0') { 'OFF' } else { 'ON' }
      Add-Row 'Active Setup' $label $state $stub
    }
  }
}

# 5. Store (MSIX) app startup tasks: State 2/4 = on, 0/1/3 = off (1 = turned off by the user)
$appRoot = 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\SystemAppData'
Get-ChildItem -LiteralPath $appRoot | ForEach-Object {
  $pkg = $_.PSChildName
  Get-ChildItem -LiteralPath $_.PSPath | ForEach-Object {
    $st = $_.GetValue('State')
    if ($null -ne $st) {
      $label = if ($st -eq 2 -or $st -eq 4) { 'ON' } else { "OFF($st)" }
      if ($IncludeMicrosoft -or $pkg -notlike 'Microsoft.*') {
        Add-Row 'Store app startup task' ($pkg + ' / ' + $_.PSChildName) $label ''
      }
    }
  }
}

# 6. Scheduled tasks that fire at logon, boot, unlock/connect, or on an event
$kinds = @{
  'MSFT_TaskLogonTrigger' = 'logon'; 'MSFT_TaskBootTrigger' = 'boot';
  'MSFT_TaskSessionStateChangeTrigger' = 'session'; 'MSFT_TaskEventTrigger' = 'event'
}
Get-ScheduledTask | Where-Object { $IncludeMicrosoft -or $_.TaskPath -notlike '\Microsoft\*' } | ForEach-Object {
  $t = $_
  $hits = @($t.Triggers | ForEach-Object { $kinds[$_.CimClass.CimClassName] } | Where-Object { $_ } | Sort-Object -Unique)
  if ($hits.Count -gt 0) {
    $cmd = ($t.Actions | ForEach-Object { ($_.Execute + ' ' + $_.Arguments).Trim() }) -join ' ; '
    $state = if ($t.State -eq 'Disabled') { 'OFF' } else { 'ON' }
    Add-Row ('Scheduled task (' + ($hits -join '/') + ')') ($t.TaskPath + $t.TaskName) $state $cmd
  }
}

# 7. Auto-start services (publisher read from the binary)
Get-CimInstance Win32_Service | Where-Object { $_.StartMode -eq 'Auto' } | ForEach-Object {
  $path = [string]$_.PathName
  $exe = $path
  if ($path -match '^"([^"]+)"') { $exe = $Matches[1] } elseif ($path -match '^(\S+\.exe)') { $exe = $Matches[1] }
  $company = (Get-Item -LiteralPath $exe).VersionInfo.CompanyName
  $isMs = ($company -like 'Microsoft*') -or ($exe -like '*\Windows\System32\svchost.exe')
  if ($IncludeMicrosoft -or -not $isMs) {
    Add-Row 'Auto-start service' ($_.Name + ' (' + $_.DisplayName + ')') $_.State ($company + ' | ' + $path)
  }
}

if ($Csv) {
  $rows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $Csv
  Write-Output ("{0} entries -> {1}" -f $rows.Count, $Csv)
} else {
  $rows | Sort-Object Source, Name | Format-Table -AutoSize -Wrap Source, State, Name, Command
  Write-Output ("{0} entries ({1} on). Not exhaustive: see the header for what is not covered." -f $rows.Count, @($rows | Where-Object { $_.State -eq 'ON' -or $_.State -eq 'Running' }).Count)
}
