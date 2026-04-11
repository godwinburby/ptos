@echo off
:: PTOS Start Script for Windows
:: Run from inside the ptos folder

echo ==========================================
echo   PTOS Web Server
echo ==========================================
echo.

:: Check if ptos_web.py exists
if not exist "ptos_web.py" (
    echo ERROR: ptos_web.py not found.
    echo Make sure you are running this from the PTOS folder.
    pause
    exit /b 1
)

:: Find Python
py --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python is not installed.
        pause
        exit /b 1
    )
    set "PYTHON=python"
) else (
    set "PYTHON=py"
)

:: Kill any process on port 5000
echo Checking for existing server on port 5000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    echo Killing process %%a on port 5000...
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo Starting PTOS Web Server...
echo Open in browser: http://localhost:5000
echo Press Ctrl+C to stop.
echo.

:: Open browser
start http://localhost:5000

:: Start Flask server
%PYTHON% ptos_web.py
