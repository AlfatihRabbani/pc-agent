@echo off
REM Launch the PC-Agent chat app (model auto-loads on open).
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "app\chat_app.py"
