@echo off
:: PTOS Setup Script for Windows
:: Run from anywhere - will install PTOS in a 'ptos' subfolder

echo ==========================================
echo   PTOS Setup for Windows
echo ==========================================
echo.

:: Check if already installed
if exist "ptos\ptos.py" (
    echo PTOS is already installed in ptos folder.
    echo Skipping download...
    set "PTOS_EXISTS=1"
) else (
    set "PTOS_EXISTS=0"
)

:: Download and install if not exists
if "%PTOS_EXISTS%"=="0" (
    echo ==========================================
    echo   Downloading and Installing PTOS
    echo ==========================================
    echo.

    :: Check for Python
    py --version >nul 2>&1
    if errorlevel 1 (
        python --version >nul 2>&1
        if errorlevel 1 (
            echo ERROR: Python is not installed.
            echo Please install Python from https://python.org
            echo Make sure to check "Add Python to PATH"
            pause
            exit /b 1
        )
        set "PYTHON=python"
    ) else (
        set "PYTHON=py"
    )

    echo Downloading PTOS...
    curl -L -o ptos.zip https://github.com/godwinburby/ptos/archive/refs/heads/main.zip

    echo.
    echo Extracting files...
    tar -xf ptos.zip

    :: Create ptos folder and move files
    if not exist "ptos" mkdir ptos
    xcopy /E /Y ptos-main\* ptos\ >nul
    rmdir /S /Q ptos-main 2>nul
    del ptos.zip

    echo PTOS downloaded and extracted!
)

cd ptos

:: Install Flask
echo.
echo Installing Flask...
%PYTHON% -m pip install flask --break-system-packages >nul 2>&1

:: Initialize PTOS
if "%PTOS_EXISTS%"=="0" (
    echo.
    echo Initializing PTOS...
    %PYTHON% ptos.py --init >nul 2>&1
)

echo.
echo ==========================================
echo   PTOS is ready!
echo ==========================================
echo.
echo Starting PTOS Web Server...
echo Open your browser to: http://localhost:5000
echo Press Ctrl+C to stop the server.
echo.

:: Start server
%PYTHON% ptos_web.py
