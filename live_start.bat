@echo off
echo Launching Dexter Live Monitor in Background...
cd /d "C:\Users\jmgra\antigravityagents\dexter-quant-agent"
start "" "C:\Users\jmgra\antigravityagents\dexter-quant-agent\quant-env\Scripts\pythonw.exe" live_monitor.py
echo Monitor launched with pythonw.


timeout /t 2 > nul
