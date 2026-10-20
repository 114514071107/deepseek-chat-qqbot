' ds-niang console launcher (windowless, independent process)
' double-click, then open http://127.0.0.1:7850 in browser
Dim shell, fso, dir
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = dir
shell.Run "node """ & dir & "\server.js"" --port 7850", 0, False
