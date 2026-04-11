@echo off
:: PTOS Setup Script for Windows
:: Run from anywhere — installs PTOS in a 'ptos' subfolder if not present.

echo ==========================================
echo   PTOS Setup for Windows
echo ==========================================
echo.

:: ── Find Python ───────────────────────────────────────────────────────────────
set "PYTHON="
py --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py"
    goto :python_found
)
python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=python"
    goto :python_found
)
echo ERROR: Python is not installed or not on PATH.
echo Download from https://python.org — check "Add Python to PATH".
pause
exit /b 1

:python_found
:: Verify Python 3.11+
%PYTHON% -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.11 or higher is required.
    for /f "tokens=*" %%v in ('%PYTHON% --version') do echo Installed: %%v
    echo Download Python 3.11+ from https://python.org
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('%PYTHON% --version') do echo Using %%v

:: ── Download PTOS if not present ─────────────────────────────────────────────
if exist "ptos\ptos.py" (
    echo PTOS already installed in .\ptos
    set "PTOS_EXISTS=1"
) else (
    set "PTOS_EXISTS=0"
)

if "%PTOS_EXISTS%"=="0" (
    echo.
    echo Downloading PTOS...
    curl -L -o ptos.zip https://github.com/godwinburby/ptos/archive/refs/heads/main.zip
    if errorlevel 1 (
        echo ERROR: Download failed. Check your internet connection.
        pause
        exit /b 1
    )

    echo Extracting...
    tar -xf ptos.zip
    if errorlevel 1 (
        echo ERROR: Extraction failed.
        del ptos.zip 2>nul
        pause
        exit /b 1
    )

    if not exist "ptos" mkdir ptos
    xcopy /E /Y ptos-main\* ptos\ >nul
    rmdir /S /Q ptos-main 2>nul
    del ptos.zip 2>nul
    echo Download complete.
)

cd ptos

:: ── Install Flask ─────────────────────────────────────────────────────────────
echo.
echo Installing Flask...
%PYTHON% -m pip install flask --quiet
if errorlevel 1 (
    echo WARNING: Flask install may have failed. Check pip is working.
)

:: ── Initialise PTOS ──────────────────────────────────────────────────────────
if "%PTOS_EXISTS%"=="0" (
    echo.
    echo Initialising PTOS...
    %PYTHON% ptos.py --init
)

:: ── Kill any process on port 5000 ────────────────────────────────────────────
echo.
echo Checking port 5000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    echo Stopping process %%a on port 5000...
    taskkill /F /PID %%a >nul 2>&1
)

:: ── Start Flask, then open browser ───────────────────────────────────────────
echo.
echo ==========================================
echo   Starting PTOS Web Server
echo ==========================================
echo.
echo Open in browser: http://localhost:5000
echo Press Ctrl+C to stop.
echo.

:: Start Flask in background, wait briefly, then open browser
start "" /B %PYTHON% ptos_web.py
timeout /t 2 /nobreak >nul
start http://localhost:5000

:: Keep window open so user can see output / errors
%PYTHON% -c "import time; time.sleep(86400)" >nul 2>&1
