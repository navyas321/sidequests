' Launches the display-off PowerShell script with no visible window (no console flash).
' Self-locating: finds Turn-Off-Display.ps1 next to this .vbs, so the pair can live anywhere.
Dim fso, here, ps1
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = fso.BuildPath(here, "Turn-Off-Display.ps1")
CreateObject("WScript.Shell").Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """", 0, False
