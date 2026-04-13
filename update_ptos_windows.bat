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

echo.
echo ==========================================
echo   PTOS Updated!
echo ==========================================
echo.
echo Restart the server: python ptos_web.py
echo.
pause
