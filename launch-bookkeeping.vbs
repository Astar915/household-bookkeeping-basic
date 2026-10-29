Option Explicit

Dim shell, files, projectFolder, pythonwPath, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
projectFolder = files.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = projectFolder

' Restart requests pass the current Python PID. Wait until its window has fully
' exited before starting the next normal instance, avoiding a stale mutex waiter.
If WScript.Arguments.Count > 0 Then
  Dim parentPid, locator, matches
  parentPid = Trim(WScript.Arguments(0))
  If IsNumeric(parentPid) Then
    Set locator = GetObject("winmgmts:\\.\root\cimv2")
    Do
      Set matches = locator.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE ProcessId=" & CLng(parentPid))
      If matches.Count = 0 Then Exit Do
      WScript.Sleep 200
    Loop
  End If
End If

pythonwPath = projectFolder & "\.venv\Scripts\pythonw.exe"
If files.FileExists(pythonwPath) Then
  command = """" & pythonwPath & """ -m bookkeeping.gui"
Else
  command = "pythonw.exe -m bookkeeping.gui"
End If

' tkdnd is an optional unsigned native extension. On this PC Windows blocks
' its DLL, so let Tk launch without native drag/drop; the Add Image button remains.
shell.Environment("PROCESS")("HOUSEHOLD_BOOKKEEPING_DISABLE_NATIVE_DND") = "1"

On Error Resume Next
shell.Run command, 0, False
If Err.Number <> 0 Then
  MsgBox "Pythonw.exe was not found. Install Python 3.11+ and make sure it is on PATH.", 48, "Household Bookkeeping"
End If
Set files = Nothing
Set shell = Nothing
