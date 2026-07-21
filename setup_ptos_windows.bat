@echo off
setlocal
set PS1_PATH=%~dp0setup_ptos_windows.ps1
set PS1_URL=https://raw.githubusercontent.com/godwinburby/ptos/main/setup_ptos_windows.ps1

if not exist "%PS1_PATH%" (
    echo Downloading setup script...
    powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PS1_URL%' -OutFile '%PS1_PATH%'"
    if errorlevel 1 (
        echo ERROR: Could not download setup script. Check your internet connection.
        pause
        exit /b 1
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1_PATH%"
if errorlevel 1 pause
