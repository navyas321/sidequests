param(
  [ValidateSet('off','on')]
  [string]$Action = 'off',
  [int]$GuardMs   = 4000,   # 'off': how long to re-assert the off if something wakes the panel with no user input
  [int]$SettleMs  = 350,    # 'off': required quiet-input window before the first off is sent
  [switch]$DryRun,          # run the full timing/guard logic but never actually power the panel down
  [switch]$NoLog
)

# Turn the display off (software / DPMS path, stays wakeable by mouse or keyboard) or back on.
#
# Why the off path is not one broadcast: "first press turns the screen off, then it wakes ~1s later; second press sticks".
# The old version fired ONE fire-and-forget SC_MONITORPOWER broadcast after a blind fixed 600 ms.
# Windows re-powers the panel on ANY input, and a key-UP counts: on the first press you hold
# Ctrl+Alt+O a beat longer while waiting for the screen to react, so the release lands AFTER the
# off broadcast and instantly wakes it. The second press is a quick tap, the release lands before
# the 600 ms, and it sticks. Blind timing cannot win that race, and it also cannot survive a
# non-input wake (display helper / virtual display driver re-powering the panel).
#
# The fix is mechanism-agnostic:
#   1. Wait until every key and mouse button is physically RELEASED (not a blind sleep).
#   2. Wait until the input queue has been quiet for -SettleMs.
#   3. Send the off broadcast.
#   4. Guard for -GuardMs: if the panel gets woken WITHOUT genuine user input, re-assert the off.
#      The moment real input arrives (you move the mouse / press a key), the guard releases
#      immediately so waking at the desk still works exactly as before.
#
# Broadcasts now go out via SendMessageTimeout(SMTO_ABORTIFHUNG) so one hung top-level window
# cannot stall the hotkey.

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct PhysicalMonitor {
    public IntPtr hPhysicalMonitor;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
    public string szPhysicalMonitorDescription;
}

[StructLayout(LayoutKind.Sequential)]
public struct LASTINPUTINFO {
    public uint cbSize;
    public uint dwTime;
}

[StructLayout(LayoutKind.Sequential)]
public struct POINT {
    public int X;
    public int Y;
}

public static class DisplayControl {
    [DllImport("user32.dll")]
    public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam,
                                                   uint fuFlags, uint uTimeout, out IntPtr lpdwResult);

    [DllImport("user32.dll")]
    public static extern short GetAsyncKeyState(int vKey);

    [DllImport("user32.dll")]
    public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);

    [DllImport("kernel32.dll")]
    public static extern uint GetTickCount();

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, int dx, int dy, uint dwData, IntPtr dwExtraInfo);

    [DllImport("user32.dll")]
    public static extern bool GetCursorPos(out POINT lpPoint);

    public delegate bool MonitorEnumProc(IntPtr hMonitor, IntPtr hdcMonitor, IntPtr lprcMonitor, IntPtr dwData);
    [DllImport("user32.dll")]
    public static extern bool EnumDisplayMonitors(IntPtr hdc, IntPtr lprcClip, MonitorEnumProc lpfnEnum, IntPtr dwData);

    [DllImport("dxva2.dll")]
    public static extern bool GetNumberOfPhysicalMonitorsFromHMONITOR(IntPtr hMonitor, out uint pdwNumberOfPhysicalMonitors);

    [DllImport("dxva2.dll")]
    public static extern bool GetPhysicalMonitorsFromHMONITOR(IntPtr hMonitor, uint dwPhysicalMonitorArraySize, [Out] PhysicalMonitor[] pPhysicalMonitorArray);

    [DllImport("dxva2.dll")]
    public static extern bool DestroyPhysicalMonitors(uint dwPhysicalMonitorArraySize, [In] PhysicalMonitor[] pPhysicalMonitorArray);

    [DllImport("dxva2.dll")]
    public static extern bool SetVCPFeature(IntPtr hMonitor, byte bVCPCode, uint dwNewValue);

    public const uint WM_SYSCOMMAND    = 0x0112;
    public const int  SC_MONITORPOWER  = 0xF170;
    public const uint MOUSEEVENTF_MOVE = 0x0001;
    public const uint SMTO_ABORTIFHUNG = 0x0002;
    public static readonly IntPtr HWND_BROADCAST = new IntPtr(0xffff);

    public static List<IntPtr> MonitorHandles = new List<IntPtr>();

    private static void Power(int state) {
        IntPtr result;
        SendMessageTimeout(HWND_BROADCAST, WM_SYSCOMMAND, (IntPtr)SC_MONITORPOWER, (IntPtr)state,
                           SMTO_ABORTIFHUNG, 1000, out result);
    }

    /// <summary>SC_MONITORPOWER lParam=2 - software display-off.</summary>
    public static void Off() { Power(2); }

    /// <summary>SC_MONITORPOWER lParam=-1 - power on.</summary>
    public static void On() { Power(-1); }

    /// <summary>True while ANY key or mouse button is physically held down.</summary>
    public static bool AnyKeyDown() {
        for (int vk = 1; vk <= 254; vk++) {
            if (vk == 0x03) continue;                 // VK_CANCEL - Ctrl+Break artifact
            if ((GetAsyncKeyState(vk) & 0x8000) != 0) return true;
        }
        return false;
    }

    /// <summary>Tick of the last real user input (0 if unavailable).</summary>
    public static uint LastInputTick() {
        LASTINPUTINFO li = new LASTINPUTINFO();
        li.cbSize = (uint)Marshal.SizeOf(typeof(LASTINPUTINFO));
        if (!GetLastInputInfo(ref li)) return 0;
        return li.dwTime;
    }

    /// <summary>Milliseconds since the last input event of ANY kind (diagnostic only - see CursorKey).</summary>
    public static uint IdleMs() {
        uint t = LastInputTick();
        if (t == 0) return 0;
        return unchecked(GetTickCount() - t);
    }

    /// <summary>Cursor position as "x,y". Compared across polls to detect REAL pointer movement.
    /// Deliberately used instead of GetLastInputInfo: a faulty controller / Steam Input can pin the
    /// system idle timer at 0 with synthetic zero-delta events (measured at 16 Hz on one
    /// machine), which would make an idle-timer-based guard release instantly and never re-assert.</summary>
    public static string CursorKey() {
        POINT p;
        if (!GetCursorPos(out p)) return "?";
        return p.X + "," + p.Y;
    }

    /// <summary>Micro mouse nudge - wakes a software-off panel without moving the cursor visibly.</summary>
    public static void Nudge() {
        mouse_event(MOUSEEVENTF_MOVE,  1, 0, 0, IntPtr.Zero);
        mouse_event(MOUSEEVENTF_MOVE, -1, 0, 0, IntPtr.Zero);
    }
}
"@

$LogPath = Join-Path $env:LOCALAPPDATA 'display-off\turn-off-display.log'
function Write-Log([string]$msg) {
  if ($NoLog) { return }
  try {
    $dir = Split-Path $LogPath -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'), $msg | Add-Content -Path $LogPath -Encoding UTF8
  } catch { }
}

function Trim-Log {
  if ($NoLog) { return }
  try {
    if (Test-Path $LogPath) {
      $lines = Get-Content $LogPath
      if ($lines.Count -gt 300) { $lines[-300..-1] | Set-Content -Path $LogPath -Encoding UTF8 }
    }
  } catch { }
}

function Send-Off {
  if ($DryRun) { return }
  [DisplayControl]::Off()
}

if ($Action -eq 'off') {
  Write-Log ("--- off requested (guard={0}ms settle={1}ms{2}) ---" -f $GuardMs, $SettleMs, $(if ($DryRun) { ' DRYRUN' } else { '' }))

  # 1. Wait for the launching keystroke / click to be fully RELEASED.
  #    This is the race the old fixed 600 ms sleep kept losing: a key-up delivered after the
  #    broadcast re-powers the panel instantly.
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ([DisplayControl]::AnyKeyDown() -and $sw.ElapsedMilliseconds -lt 5000) {
    Start-Sleep -Milliseconds 20
  }
  Write-Log ("keys released after {0} ms" -f $sw.ElapsedMilliseconds)

  # 2. Wait for the POINTER to hold still for -SettleMs (covers a mouse-click launch and any
  #    trailing movement). Cursor position is used rather than the system idle timer on purpose:
  #    see CursorKey() - synthetic input can pin the idle timer at 0 forever.
  $sw2 = [Diagnostics.Stopwatch]::StartNew()
  $stillSince = [Diagnostics.Stopwatch]::StartNew()
  $lastCur = [DisplayControl]::CursorKey()
  while ($stillSince.ElapsedMilliseconds -lt $SettleMs -and $sw2.ElapsedMilliseconds -lt 2000) {
    Start-Sleep -Milliseconds 20
    $c = [DisplayControl]::CursorKey()
    if ($c -ne $lastCur) { $lastCur = $c; $stillSince.Restart() }
  }
  Write-Log ("pointer still after {0} ms (system idle timer reads {1} ms)" -f $sw2.ElapsedMilliseconds, [DisplayControl]::IdleMs())

  # 3. Off.
  Send-Off
  $baseCur = [DisplayControl]::CursorKey()
  Write-Log "display off sent"

  # 4. Guard: keep re-asserting the off unless a REAL interaction happens - the pointer actually
  #    moves, or a key / mouse button is actually held down. Both are immune to the synthetic
  #    zero-delta input that defeats an idle-timer check. Waking at the desk still works instantly:
  #    the first genuine mouse move or keypress releases the guard.
  $guard = [Diagnostics.Stopwatch]::StartNew()
  $reasserts = 0
  $released  = $false
  while ($guard.ElapsedMilliseconds -lt $GuardMs) {
    Start-Sleep -Milliseconds 250
    $cur = [DisplayControl]::CursorKey()
    if ($cur -ne $baseCur -or [DisplayControl]::AnyKeyDown()) {
      Write-Log ("real user interaction at +{0} ms - guard released, panel wakes (expected)" -f $guard.ElapsedMilliseconds)
      $released = $true
      break
    }
    Send-Off
    $reasserts++
  }
  if (-not $released) {
    Write-Log ("guard finished: {0} re-asserts over {1} ms, no real interaction" -f $reasserts, $guard.ElapsedMilliseconds)
  }
  Trim-Log
} else {
  # Wake sequence:
  #   1. Nudge mouse  - instantly wakes a panel that was put to sleep via SC_MONITORPOWER.
  #   2. Power-on msg - reinforces the wake signal.
  #   3. DDC/CI 0xD6=1 - best-effort hardware power-on; silently skipped where unsupported.
  #   4. Second nudge - ensures the cursor is visible after wake.
  Write-Log "--- on requested ---"
  [DisplayControl]::Nudge()
  [DisplayControl]::On()

  try {
    [DisplayControl]::MonitorHandles.Clear()
    $enumCallback = [DisplayControl+MonitorEnumProc]{
      param($hMon, $hdcMon, $lprc, $dwData)
      [void][DisplayControl]::MonitorHandles.Add($hMon)
      $true
    }
    [DisplayControl]::EnumDisplayMonitors([IntPtr]::Zero, [IntPtr]::Zero, $enumCallback, [IntPtr]::Zero) | Out-Null

    foreach ($hMonitor in [DisplayControl]::MonitorHandles) {
      $count = 0
      if ([DisplayControl]::GetNumberOfPhysicalMonitorsFromHMONITOR($hMonitor, [ref]$count)) {
        $physArr = New-Object PhysicalMonitor[] $count
        if ([DisplayControl]::GetPhysicalMonitorsFromHMONITOR($hMonitor, $count, $physArr)) {
          foreach ($pm in $physArr) {
            [void][DisplayControl]::SetVCPFeature($pm.hPhysicalMonitor, [byte]0xD6, 1)
          }
          [DisplayControl]::DestroyPhysicalMonitors($count, $physArr) | Out-Null
        }
      }
    }
  } catch {
    # DDC/CI not supported or failed - the software wake above already fired.
  }

  [DisplayControl]::Nudge()
  Write-Log "display on sent"
  Trim-Log
}
