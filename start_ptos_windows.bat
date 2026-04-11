@echo off
:: PTOS Start Script for Windows
:: Run from inside the ptos folder.

echo ==========================================
echo   PTOS Web Server
echo ==========================================
echo.

if not exist "ptos_web.py" (
    echo ERROR: ptos_web.py not found.
    echo Run this script from the ptos folder, or run setup_ptos_windows.bat first.
    pause
    exit /b 1
)

:: ── Find Python 3.11+ ─────────────────────────────────────────────────────────
set "PYTHON="
py --version >nul 2>&1
if not errorlevel 1 (
    py -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON=py"
)
if "%PYTHON%"=="" (
    python --version >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYTHON=python"
    )
)
if "%PYTHON%"=="" (
    echo ERROR: Python 3.11+ not found. Run setup_ptos_windows.bat first.
    pause
    exit /b 1
)

:: ── Kill any process on port 5000 ────────────────────────────────────────────
echo Checking port 5000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    echo Stopping process %%a on port 5000...
    taskkill /F /PID %%a >nul 2>&1
)

:: ── Start Flask, then open browser ───────────────────────────────────────────
echo.
echo Starting PTOS...
echo Open in browser: http://localhost:5000
echo Press Ctrl+C to stop.
echo.

start "" /B %PYTHON% ptos_web.py
timeout /t 2 /nobreak >nul
start http://localhost:5000

:: Keep window open
%PYTHON% ptos_web.py
