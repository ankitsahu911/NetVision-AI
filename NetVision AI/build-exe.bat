@echo off
cd /d "%~dp0"
python -m pip install pyinstaller
python -m PyInstaller --clean --noconfirm --onefile --name SmartNetDeviceScanner --add-data "static;static" app.py
echo.
echo Built EXE:
echo %CD%\dist\SmartNetDeviceScanner.exe
pause
