@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_ptos_windows.ps1"
if errorlevel 1 pause
