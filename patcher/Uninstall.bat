@echo off
rem K1 Area Map Fixes - uninstaller. Puts your original swkotor.exe back.
setlocal
cd /d "%~dp0"

if exist "Patcher\K1AreaMapFixes-Revert.exe" (
    "Patcher\K1AreaMapFixes-Revert.exe" %*
) else (
    where python >nul 2>nul || (
        echo.
        echo The packaged patcher is missing, and Python was not found either.
        echo.
        echo Your backup is still here:
        echo   %%LOCALAPPDATA%%\K1AreaMapFixes\backup
        echo Copy swkotor.exe.original over your game's swkotor.exe by hand,
        echo renaming it to swkotor.exe.
        echo.
        pause
        exit /b 1
    )
    python "More info\source\revert.py" %*
)

echo.
pause
