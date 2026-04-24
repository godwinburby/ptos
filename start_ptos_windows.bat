@echo off
:: PTOS Start Script for Windows
:: Run from inside the ptos folder.
:: Automatically updates from git if available, then starts the server.

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

:: Check for updates (if git repo)
if exist ".git" (
    echo Checking for updates...
    git pull >nul 2>&1
    if not errorlevel 1 (
        echo Updated from GitHub.
    ) else (
        echo Could not reach GitHub - continuing with local version.
    )
) else (
    echo Not a git repo - skipping update check.
)

:: Check/install dependencies
%PYTHON% -c "import flask" 2>nul
if errorlevel 1 (
    echo Installing Flask and tomli-w...
    %PYTHON% -m pip install flask tomli-w --quiet
)

:: Kill anything on port 5000
echo.
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
timeout /t 2 /nobreak >nul
start http://localhost:5000
%PYTHON% ptos_web.py
