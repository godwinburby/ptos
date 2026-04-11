@echo off
:: PTOS Update Script for Windows
:: Run from inside the ptos folder

echo ==========================================
echo   PTOS Update
echo ==========================================
echo.

:: Check if ptos_web.py exists
if not exist "ptos_web.py" (
    echo ERROR: ptos_web.py not found.
    echo Make sure you are running this from the PTOS folder.
    pause
    exit /b 1
)

:: Find Python
py --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        set "PYTHON=python"
    ) else (
        set "PYTHON=python"
    )
) else (
    set "PYTHON=py"
)

:: Kill Flask if running
echo Checking for running server...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    echo Stopping server (PID: %%a)...
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo Downloading latest PTOS...
curl -L -o ptos.zip https://github.com/godwinburby/ptos/archive/refs/heads/main.zip

echo.
echo Extracting and updating files...
tar -xf ptos.zip

:: Update Python files
xcopy /Y ptos-main\*.py . >nul 2>&1

:: Update web templates
if exist "ptos-main\web_templates" (
    xcopy /E /Y ptos-main\web_templates\* web_templates\ >nul 2>&1
)

:: Update scripts
xcopy /Y ptos-main\*_windows.bat . >nul 2>&1

:: Cleanup
rmdir /S /Q ptos-main 2>nul
del ptos.zip

echo.
echo ==========================================
echo   PTOS Updated!
echo ==========================================
echo.
echo Restart with:
echo   start_ptos_windows.bat
pause
