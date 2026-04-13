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

:: Refresh Flask
echo.
echo Refreshing dependencies...
%PYTHON% -m pip install flask --quiet 2>nul

:: Restart server in background (so script returns quickly for HTTP response)
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
echo.
