@echo off
rem K1 Area Map Fixes - uninstaller launcher.
setlocal
cd /d "%~dp0"

if exist "K1AreaMapFixes\K1AreaMapFixes-Revert.exe" (
    "K1AreaMapFixes\K1AreaMapFixes-Revert.exe" %*
) else (
    where python >nul 2>nul || (
        echo Python was not found, and the packaged patcher is missing.
        echo Re-download the release, or install Python 3.8+ to run the source.
        pause
        exit /b 1
    )
    python revert.py %*
)

echo.
pause
