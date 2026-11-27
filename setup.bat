@echo off
setlocal
cd /d "%~dp0" || exit /b 1
if exist ".venv\Scripts\python.exe" goto install
py -3.11 -c "import sys; assert sys.version_info[:2] == (3,11)" >nul 2>&1
if not errorlevel 1 (
    py -3.11 -m venv .venv
) else (
    python -c "import sys; assert sys.version_info[:2] == (3,11)" >nul 2>&1
    if errorlevel 1 (
        echo Install 64-bit Python 3.11 and run setup.bat again.
        exit /b 1
    )
    python -m venv .venv
)
if errorlevel 1 exit /b 1
:install
".venv\Scripts\python.exe" -c "import sys, struct; assert sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8, 'Use 64-bit Python 3.11'"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements-demo.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -c "from app.ai.inference import get_model; get_model(); print('Model loaded. Run start.bat.')"
exit /b %errorlevel%
