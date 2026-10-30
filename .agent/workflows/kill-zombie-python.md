---
description: Check for and terminate zombie python.exe processes stalling Dexter.
---

This workflow helps identify and kill orphan Python processes that lock files or prevent the Bridge/Monitor from starting.

// turbo
1. Run the audit script to see what's running:
```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\jmgra\antigravityagents\dexter-quant-agent\scripts\kill_zombies.ps1 -Audit
```

// turbo
2. Terminate all Dexter-related Python processes:
```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\jmgra\antigravityagents\dexter-quant-agent\scripts\kill_zombies.ps1 -Force
```

3. Verify the process list is clean:
```powershell
tasklist /FI "IMAGENAME eq python.exe" /V
```
