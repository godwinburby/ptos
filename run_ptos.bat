@echo off
setlocal
set PS1_PATH=%~dp0run_ptos.ps1
set PS1_URL=https://raw.githubusercontent.com/godwinburby/ptos/main/run_ptos.ps1

if not exist "%PS1_PATH%" (
    echo Downloading PTOS launcher...
    curl.exe -sL --ssl-no-revoke -o "%PS1_PATH%" "%PS1_URL%"
    if errorlevel 1 (
        echo ERROR: Could not download launcher. Check your internet connection.
        pause
        exit /b 1
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1_PATH%"
if errorlevel 1 pause
