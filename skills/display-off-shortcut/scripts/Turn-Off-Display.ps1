Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class Display {
    [DllImport("user32.dll")]
    public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    public const int WM_SYSCOMMAND = 0x0112;
    public const int SC_MONITORPOWER = 0xF170;
    public const int MONITOR_OFF = 2;
    public static readonly IntPtr HWND_BROADCAST = new IntPtr(0xffff);
}
"@
# Brief delay so the click / keypress that launched this doesn't immediately wake the display.
Start-Sleep -Milliseconds 600
[Display]::SendMessage([Display]::HWND_BROADCAST, [Display]::WM_SYSCOMMAND, [IntPtr][Display]::SC_MONITORPOWER, [IntPtr][Display]::MONITOR_OFF) | Out-Null
