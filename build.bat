@echo off
echo ===== Building PTOS Desktop App =====
echo.

pyinstaller ptos.spec --clean --noconfirm

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Build FAILED with error code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo.
echo ===== Build complete! =====
echo Output: dist\PTOS\PTOS.exe
echo.
echo To run, double-click dist\PTOS\PTOS.exe
echo or launch: dist\PTOS\PTOS.exe
echo.
