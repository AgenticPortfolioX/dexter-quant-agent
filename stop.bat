@echo off
echo Stopping Dexter Quant Agent server...
taskkill /F /IM bun.exe /T >nul 2>&1
taskkill /F /IM pythonw.exe /T >nul 2>&1
echo Done.
pause
