@echo off
:: PTOS Setup Script for Windows
:: Run from anywhere — clones repo, installs Python/Git via winget, sets up PTOS.

echo ==========================================
echo   PTOS Setup for Windows
echo ==========================================
echo.

:: ── Find or Install Python ────────────────────────────────────────────────────
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
    echo Python 3.11+ not found. Installing via winget...
    winget install Python.Python.3.11 --accept-package-agreements --silent --scope machine
    :: Wait for installation to complete
    echo Waiting for Python installation to complete...
    timeout /t 30 /nobreak >nul
    :: Refresh environment and find Python
    for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYSPATH=%%b"
    for /f "tokens=*" %%p in ('where python 2^>nul') do (
        if not defined PYTHON (
            %%p -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1
            if not errorlevel 1 set "PYTHON=%%~nxp"
        )
    )
    :: Fallback: use py launcher
    if "%PYTHON%"=="" set "PYTHON=py"
)

:: Verify Python is now available
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Failed to install or locate Python.
    echo Please install Python 3.11+ manually from https://python.org
    pause
    exit /b 1
)
echo Using %PYTHON% (%PYTHON% --version)

:: ── Find or Install Git ────────────────────────────────────────────────────────
git --version >nul 2>&1
if errorlevel 1 (
    echo Git not found. Installing via winget...
    winget install Git.Git --accept-package-agreements --silent --scope machine
    echo Waiting for Git installation to complete...
    timeout /t 30 /nobreak >nul
)

:: Refresh PATH for Git
set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin"

:: Verify Git is now available
git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Failed to install or locate Git.
    echo Please install Git manually from https://git-scm.com
    pause
    exit /b 1
)
echo Using Git (%git% --version)

:: ── Locate or Clone PTOS ───────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
set "PTOS_DIR=%SCRIPT_DIR%ptos"

if exist "%PTOS_DIR%\ptos.py" (
    echo.
    echo PTOS already installed in %PTOS_DIR%
    echo To update, run: update_ptos_windows.bat
    cd /d "%PTOS_DIR%"
    goto :init_ptos
)

echo.
echo Cloning PTOS repository...
git clone https://github.com/godwinburby/ptos.git "%PTOS_DIR%"
if errorlevel 1 (
    echo ERROR: Failed to clone repository. Check your internet connection.
    pause
    exit /b 1
)

cd /d "%PTOS_DIR%"

:: ── Install Dependencies ───────────────────────────────────────────────────────
:init_ptos
echo.
echo Installing Flask...
%PYTHON% -m pip install flask --quiet --break-system-packages
if errorlevel 1 (
    echo WARNING: Flask install may have failed. Retrying...
    %PYTHON% -m pip install flask
)

:: ── Initialise PTOS ───────────────────────────────────────────────────────────
if not exist "config" (
    echo.
    echo Initialising PTOS...
    %PYTHON% ptos.py --init
) else (
    echo PTOS already initialised (config/ exists).
)

:: ── Make Scripts Executable ───────────────────────────────────────────────────
echo.
echo Setting up scripts...
for %%f in (start_ptos_windows.bat update_ptos_windows.bat) do (
    if exist "%%f" echo   - %%f ready
)

:: ── Kill any process on port 5000 ───────────────────────────────────────────
echo.
echo Checking port 5000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    echo Stopping process %%a on port 5000...
    taskkill /F /PID %%a >nul 2>&1
)

:: ── Start Flask, then open browser ────────────────────────────────────────────
echo.
echo ==========================================
echo   Starting PTOS Web Server
echo ==========================================
echo.
echo Open in browser: http://localhost:5000
echo.
echo To start PTOS later: run start_ptos_windows.bat
echo To update PTOS:     run update_ptos_windows.bat
echo.
echo Press Ctrl+C to stop.
echo.

:: Start Flask in background, wait briefly, then open browser
start "" /B %PYTHON% ptos_web.py
timeout /t 2 /nobreak >nul
start http://localhost:5000

:: Keep window open so user can see output
%PYTHON% -c "import time; time.sleep(86400)" >nul 2>&1
