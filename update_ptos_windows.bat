@echo off
:: PTOS Update Script for Windows
:: Run from the ptos folder, or from the parent folder (will cd into ptos).

echo ==========================================
echo   PTOS Update
echo ==========================================
echo.

:: ── Locate PTOS directory ─────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%ptos_web.py" (
    set "PTOS_DIR=%SCRIPT_DIR%"
) else if exist "%SCRIPT_DIR%ptos\ptos_web.py" (
    set "PTOS_DIR=%SCRIPT_DIR%ptos"
) else (
    echo ERROR: ptos_web.py not found.
    echo Run this script from the ptos folder, or from the folder containing ptos.
    pause
    exit /b 1
)

cd /d "%PTOS_DIR%"

:: ── Check Git ─────────────────────────────────────────────────────────────────
git --version >nul 2>&1
if errorlevel 1 (
    :: Refresh PATH for Git
    set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin"
)
git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git not found. Please install Git.
    echo Run setup_ptos_windows.bat to reinstall with Git.
    pause
    exit /b 1
)

:: ── Check if Git Repo ─────────────────────────────────────────────────────────
if not exist ".git" (
    echo ERROR: Not a git repository.
    echo PTOS was not installed via git clone. Cannot update.
    echo Run setup_ptos_windows.bat to reinstall with git.
    pause
    exit /b 1
)

:: ── Find Python ───────────────────────────────────────────────────────────────
set "PYTHON="
py --version >nul 2>&1
if not errorlevel 1 ( set "PYTHON=py" ) else (
    python --version >nul 2>&1
    if not errorlevel 1 ( set "PYTHON=python" )
)
if "%PYTHON%"=="" (
    echo ERROR: Python not found. Run setup_ptos_windows.bat first.
    pause
    exit /b 1
)

:: ── Git Pull ─────────────────────────────────────────────────────────────────
echo.
echo Pulling latest changes from GitHub...
git pull
if errorlevel 1 (
    echo ERROR: Git pull failed. You may have uncommitted changes.
    pause
    exit /b 1
)
echo Update downloaded.

:: ── Update .version file ──────────────────────────────────────────────────────
for /f %%i in ('git rev-parse HEAD') do echo %%i > .version
echo Updated version file.

:: ── Install Any New Dependencies ─────────────────────────────────────────────
echo.
echo Checking dependencies...
%PYTHON% -m pip install flask --quiet --break-system-packages 2>nul

:: ── Background Restart (allows Flask to return response) ─────────────────────
echo.
echo Stopping server on port 5000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Background restart - script exits quickly so Flask can respond
echo Starting server...
start http://localhost:5000
start /B cmd /c "timeout /t 2 /nobreak >nul && %PYTHON% ptos_web.py"

echo.
echo ==========================================
echo   PTOS Updated!
echo ==========================================
echo.
echo Restart your browser to see changes.
