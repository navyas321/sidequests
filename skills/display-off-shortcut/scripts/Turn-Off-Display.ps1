param(
  [ValidateSet('off','on')]
  [string]$Action = 'off'
)

# Broadcast SC_MONITORPOWER to turn the display off (software path, stays mouse/keyboard wakeable)
# or wake it back on (input nudge + power-on message + best-effort DDC/CI hardware wake).
#
# 'off' uses the Windows WM_SYSCOMMAND / SC_MONITORPOWER software path — no third-party utility
# required. The panel stays wakeable by moving the mouse or pressing any key at the desk.
#
# 'on'  first nudges mouse input (wakes a software-off panel instantly), then broadcasts the
# power-on message, then tries DDC/CI VCP 0xD6=1 on every physical monitor (in case a panel was
# ever put into a true hardware-off state). DDC/CI is best-effort: errors are silently ignored,
# so the script never fails on monitors that don't support it.

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

public static class DisplayControl {
    [DllImport("user32.dll")]
    public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, int dx, int dy, uint dwData, IntPtr dwExtraInfo);

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

    public const uint WM_SYSCOMMAND       = 0x0112;
    public const int  SC_MONITORPOWER     = 0xF170;
    public const uint MOUSEEVENTF_MOVE    = 0x0001;
    public static readonly IntPtr HWND_BROADCAST = new IntPtr(0xffff);

    public static List<IntPtr> MonitorHandles = new List<IntPtr>();

    /// <summary>Send WM_SYSCOMMAND SC_MONITORPOWER lParam=2 (software display-off).</summary>
    public static void Off() {
        SendMessage(HWND_BROADCAST, WM_SYSCOMMAND, (IntPtr)SC_MONITORPOWER, (IntPtr)2);
    }

    /// <summary>Send WM_SYSCOMMAND SC_MONITORPOWER lParam=-1 (power on).</summary>
    public static void On() {
        SendMessage(HWND_BROADCAST, WM_SYSCOMMAND, (IntPtr)SC_MONITORPOWER, (IntPtr)(-1));
    }

    /// <summary>Micro mouse nudge — wakes a software-off panel without moving the cursor visibly.</summary>
    public static void Nudge() {
        mouse_event(MOUSEEVENTF_MOVE,  1, 0, 0, IntPtr.Zero);
        mouse_event(MOUSEEVENTF_MOVE, -1, 0, 0, IntPtr.Zero);
    }
}
"@

if ($Action -eq 'off') {
    # Brief delay so the keypress / click that launched the script doesn't immediately re-wake the panel.
    Start-Sleep -Milliseconds 600
    [DisplayControl]::Off()
} else {
    # Wake sequence:
    #   1. Nudge mouse  — instantly wakes a panel that was put to sleep via SC_MONITORPOWER.
    #   2. Power-on msg — reinforces the wake signal.
    #   3. DDC/CI 0xD6=1 — best-effort hardware power-on for monitors that support it; silently skipped otherwise.
    #   4. Second nudge — ensures cursor is visible after wake.
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
        # DDC/CI not supported or failed — swallow silently, the software wake above already fired.
    }

    [DisplayControl]::Nudge()
}
