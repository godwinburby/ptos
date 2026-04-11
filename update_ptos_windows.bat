@echo off
:: PTOS Update Script for Windows
:: Run from inside the ptos folder.

echo ==========================================
echo   PTOS Update
echo ==========================================
echo.

if not exist "ptos_web.py" (
    echo ERROR: ptos_web.py not found.
    echo Run this script from the ptos folder.
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
    echo ERROR: Python not found.
    pause
    exit /b 1
)

:: ── Stop Flask if running ─────────────────────────────────────────────────────
echo Checking for running server...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    echo Stopping server (PID %%a)...
    taskkill /F /PID %%a >nul 2>&1
)

:: ── Download latest zip ───────────────────────────────────────────────────────
echo.
echo Downloading latest PTOS...
curl -L -o ptos_update.zip https://github.com/godwinburby/ptos/archive/refs/heads/main.zip
if errorlevel 1 (
    echo ERROR: Download failed. Check your internet connection.
    pause
    exit /b 1
)

echo Extracting...
tar -xf ptos_update.zip
if errorlevel 1 (
    echo ERROR: Extraction failed.
    del ptos_update.zip 2>nul
    pause
    exit /b 1
)

:: ── Copy updated files (preserve config/, records/, journal/) ────────────────
echo Updating Python files...
xcopy /Y ptos-main\*.py . >nul 2>&1

echo Updating web templates...
if exist "ptos-main\web_templates" (
    if not exist "web_templates" mkdir web_templates
    xcopy /E /Y ptos-main\web_templates\* web_templates\ >nul 2>&1
)

echo Updating scripts...
xcopy /Y ptos-main\*_windows.bat . >nul 2>&1

:: ── Cleanup ───────────────────────────────────────────────────────────────────
rmdir /S /Q ptos-main 2>nul
del ptos_update.zip 2>nul

echo.
echo ==========================================
echo   PTOS Updated!
echo ==========================================
echo.
echo Restart the server with:  start_ptos_windows.bat
echo.
pause
