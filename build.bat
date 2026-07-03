@echo off
echo ===== Building PTOS Desktop App =====
echo.
pip install pystray pillow pywebview
python -m PyInstaller ptos.spec --clean --noconfirm
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Build FAILED with error code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo.
echo ===== Build complete! =====
echo Launch: dist\PTOS\PTOS.exe
echo Data: %%LOCALAPPDATA%%\ptos\
echo.
