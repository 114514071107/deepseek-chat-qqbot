' Wait for the same cmd final result. Hidden window does not imply success.
Dim shell, fso, dir, result
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set shell = CreateObject("WScript.Shell")
result = shell.Run(Chr(34) & dir & "\start-dsh-console.cmd" & Chr(34), 0, True)
WScript.Quit result
