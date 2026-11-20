' Reading Companion - silent launcher
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
py = sh.ExpandEnvironmentStrings("%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe")
If Not fso.FileExists(py) Then py = "pythonw.exe"
sh.Run """" & py & """" & " """ & dir & "\app.py""", 0, False
