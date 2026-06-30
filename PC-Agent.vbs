' Launch PC-Agent silently (no console window). Double-click this, or make a
' shortcut to it (pin to taskbar / Start, or drop in shell:startup to auto-run at login).
Set s = CreateObject("WScript.Shell")
base = "E:\aitest\pc-agent"
s.CurrentDirectory = base
s.Run """" & base & "\.venv\Scripts\pythonw.exe"" """ & base & "\app\chat_app.py""", 0, False
