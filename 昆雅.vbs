Option Explicit
' Quenya learning app launcher. ASCII only. Runs pythonw hidden, no console window.
Dim fso, sh, root, pyw, app
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = "C:\Users\1\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe"
app = root & "\app\learn_app.py"
If Not fso.FileExists(pyw) Then
    MsgBox "Python runtime not found:" & vbCrLf & pyw, 16, "Quenya"
    WScript.Quit 1
End If
If Not fso.FileExists(app) Then
    MsgBox "App not found:" & vbCrLf & app, 16, "Quenya"
    WScript.Quit 1
End If
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = root
sh.Run """" & pyw & """ """ & app & """", 0, False