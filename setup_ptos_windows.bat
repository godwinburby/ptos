@echo off
:: PTOS Setup for Windows
:: Finds Python, then hands all real work to setup_ptos_windows.py
:: Kept deliberately simple -- no parentheses, pipes, or complex bat syntax.

echo ==========================================
echo   PTOS Setup for Windows
echo ==========================================
echo.

set PYTHON=
py --version >nul 2>&1
if not errorlevel 1 set PYTHON=py

if "%PYTHON%"=="" (
    python --version >nul 2>&1
    if not errorlevel 1 set PYTHON=python
)

if "%PYTHON%"=="" (
    echo ERROR: Python is not installed or not on PATH.
    echo.
    echo Install Python 3.11 or later from:  https://python.org/downloads
    echo During install, tick "Add Python to PATH"
    echo Then run this script again.
    echo.
    pause
    exit /b 1
)

%PYTHON% "%~dp0setup_ptos_windows.py"
if errorlevel 1 pause
