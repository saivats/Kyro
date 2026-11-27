@echo off
setlocal
cd /d "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    exit /b 1
)
echo KYRO academic demo at http://127.0.0.1:5000
".venv\Scripts\python.exe" demo.py
exit /b %errorlevel%
