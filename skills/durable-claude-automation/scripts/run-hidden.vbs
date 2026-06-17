' run-hidden.vbs — launch a PowerShell script with NO visible window.
' Task Scheduler running powershell.exe directly flashes a console (conhost) window
' on every run, which steals focus. wscript.exe has no console, and Run(...,0,False)
' launches PowerShell with a hidden window — eliminating the flash/focus-steal.
'
' Usage:  wscript.exe "run-hidden.vbs" "C:\path\to\script.ps1"
Set shell = CreateObject("WScript.Shell")
psScript = WScript.Arguments(0)
shell.Run "powershell.exe -ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File """ & psScript & """", 0, False
