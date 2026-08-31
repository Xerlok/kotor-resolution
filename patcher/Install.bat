@echo off
rem K1 Area Map Fixes - installer.
rem Runs the packaged patcher if it is here, otherwise the Python source.
rem You can also drag your KOTOR folder onto this file to point it at the game.
setlocal
cd /d "%~dp0"

if exist "Patcher\K1AreaMapFixes.exe" (
    "Patcher\K1AreaMapFixes.exe" %*
) else (
    where python >nul 2>nul || (
        echo.
        echo The packaged patcher is missing, and Python was not found either.
        echo.
        echo Most likely this folder was not unzipped properly. Extract the
        echo whole download to a real folder and try again - do not run this
        echo from inside the zip.
        echo.
        pause
        exit /b 1
    )
    python "More info\source\install.py" %*
)

echo.
pause
