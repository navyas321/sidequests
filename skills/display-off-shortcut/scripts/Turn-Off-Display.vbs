' Self-locating silent launcher - runs Turn-Off-Display.ps1 (next to this file) via
' hidden PowerShell with no console flash. The pair relocates cleanly together.
Dim fso, ps1
Set fso = CreateObject("Scripting.FileSystemObject")
ps1 = fso.GetParentFolderName(WScript.ScriptFullName) & "\Turn-Off-Display.ps1"
CreateObject("WScript.Shell").Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """", 0, False
