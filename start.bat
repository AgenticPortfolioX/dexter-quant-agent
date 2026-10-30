@echo off
echo Starting Dexter Quant Agent...
echo Activating quant-env...
call quant-env\Scripts\activate

REM Prevent UnicodeEncodeError when printing emoji chars on Windows cp1252 terminals
SET PYTHONIOENCODING=utf-8

echo Performing Pre-Flight Authentication Check...
python scripts/check_account_status.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [CRITICAL ERROR] Robinhood Authentication Failed!
    echo Please run 'python scripts/manual_login.py' to re-authenticate manually.
    echo.
    pause
    exit /b %ERRORLEVEL%
)

echo Authentication Successful.

echo Launching Live Monitor (Windowless)...
start "" "quant-env\Scripts\pythonw.exe" live_monitor.py

echo Starting Core Server...
cd dexter-core
bun run server.ts
pause
