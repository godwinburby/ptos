@echo off
:: PTOS Start Script for Windows
:: Run from inside the ptos folder.
:: Kept simple -- no pipes, no parentheses in strings.

echo ==========================================
echo   PTOS Web Server
echo ==========================================
echo.

if not exist "ptos_web.py" (
    echo ERROR: ptos_web.py not found.
    echo Run this script from the ptos folder.
    echo Or run setup_ptos_windows.bat to set up first.
    pause
    exit /b 1
)

:: Find Python
set PYTHON=
py --version >nul 2>&1
if not errorlevel 1 set PYTHON=py
if "%PYTHON%"=="" (
    python --version >nul 2>&1
    if not errorlevel 1 set PYTHON=python
)
if "%PYTHON%"=="" (
    echo ERROR: Python not found. Run setup_ptos_windows.bat first.
    pause
    exit /b 1
)

:: Kill anything on port 5000
echo Checking port 5000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Start Flask
echo.
echo Starting PTOS...
echo Open in browser: http://localhost:5000
echo Press Ctrl+C to stop.
echo.

:: Start Flask in foreground - shows output, Ctrl+C to stop
start http://localhost:5000
%PYTHON% ptos_web.py
