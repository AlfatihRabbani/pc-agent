@echo off
REM Build PC-Agent.exe — a small, admin-manifested launcher (no UPX packer, with
REM version metadata + icon, to minimize antivirus false positives).
setlocal
set BUILD=%~dp0
cd /d "%~dp0.."
".venv\Scripts\pyinstaller.exe" --noconfirm --onefile --windowed --uac-admin ^
  --name PC-Agent ^
  --icon "%BUILD%PC-Agent.ico" ^
  --version-file "%BUILD%version_info.txt" ^
  --distpath "%CD%" ^
  --workpath "%BUILD%_work" ^
  --specpath "%BUILD%" ^
  "%BUILD%launcher.py"
echo.
echo Done -^> PC-Agent.exe  (double-click it; it will ask for administrator)
endlocal
