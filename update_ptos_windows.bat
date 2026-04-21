@echo off
:: PTOS Update Script for Windows
:: Run from inside the ptos folder.
:: Requires git (installed via setup_ptos_windows.bat)

echo ==========================================
echo   PTOS Update
echo ==========================================
echo.

:: Locate ptos_web.py
if not exist "ptos_web.py" (
    echo ERROR: ptos_web.py not found.
    echo Run this script from the ptos folder.
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

:: Check dependencies
echo Checking dependencies...
%PYTHON% -c "import flask" 2>nul
if errorlevel 1 (
    echo Installing Flask and tomli-w...
    %PYTHON% -m pip install flask tomli-w --quiet
)

:: Git pull
if exist ".git" (
    echo Pulling latest from GitHub...
    git pull
    if errorlevel 1 (
        echo ERROR: git pull failed.
        echo Check your internet connection or run setup_ptos_windows.bat.
        pause
        exit /b 1
    )
) else (
    echo ERROR: Not a git repository.
    echo Run setup_ptos_windows.bat to reinstall with git.
    pause
    exit /b 1
)

:: Restart server in background (so script returns quickly)
echo.
echo Restarting server...
(
    timeout /t 2 /nobreak >nul
    taskkill /F /IM python.exe >nul 2>&1
    timeout /t 1 /nobreak >nul
    start /B %PYTHON% ptos_web.py
    start http://localhost:5000
) &

echo.
echo ==========================================
echo   PTOS Updated!
echo ==========================================
echo Server is restarting in background...
