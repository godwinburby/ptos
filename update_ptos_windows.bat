@echo off
:: PTOS Update Script for Windows
:: Run from inside the ptos folder.
:: Uses git pull if installed via git, otherwise falls back to Python updater.

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

:: Stop server if running
echo Stopping server if running...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Git pull if this is a git repo
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
    :: No git -- hand off to Python updater
    echo No git repository found. Running Python updater...
    %PYTHON% update_ptos_windows.py
    if errorlevel 1 (
        echo ERROR: Update failed.
        pause
        exit /b 1
    )
    goto :done
)

:: Refresh Flask
echo.
echo Refreshing dependencies...
%PYTHON% -m pip install flask --quiet 2>nul

echo.
echo ==========================================
echo   PTOS Updated!
echo ==========================================
echo.
echo Run start_ptos_windows.bat to restart.
echo.

:done
pause
