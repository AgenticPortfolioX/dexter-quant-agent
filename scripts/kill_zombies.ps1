# kill_zombies.ps1
# Script to identify and terminate zombie Python processes for Dexter Quant Agent
# Protects core standing daemons (live_monitor.py, bridge_server.py, dexter_slack_listener.py)
# unless -KillBridgeOnly is explicitly specified.

param(
    [switch]$Force,
    [switch]$Audit,
    [switch]$KillBridgeOnly,
    [int]$ExcludePid = 0
)

$targetPath = "dexter-quant-agent"
$timestamp  = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "--- Dexter Zombie Process Audit | $timestamp ---" -ForegroundColor Cyan

if ($ExcludePid -gt 0) {
    Write-Host "Self-exclusion active: PID $ExcludePid will NOT be terminated." -ForegroundColor DarkGray
}

$processes = Get-CimInstance Win32_Process | Where-Object { $_.Name -match "python" }

if (-not $processes) {
    Write-Host "No Python processes found." -ForegroundColor Gray
    exit 0
}

$foundZombies = @()

foreach ($proc in $processes) {
    if ($proc.CommandLine -like "*$targetPath*") {
        if ($ExcludePid -gt 0 -and ($proc.ProcessId -eq $ExcludePid -or $proc.ParentProcessId -eq $ExcludePid)) {
            Write-Host "Skipping self/child (PID $($proc.ProcessId)) - protected by -ExcludePid." -ForegroundColor DarkGray
            continue
        }

        if ($KillBridgeOnly) {
            if ($proc.CommandLine -like "*bridge_server.py*") {
                Write-Host "Targeting Bridge Process for restart: PID $($proc.ProcessId)" -ForegroundColor Yellow
                $foundZombies += $proc.ProcessId
            }
            continue
        }

        # Protect core standing daemons from general zombie sweeps
        if ($proc.CommandLine -like "*live_monitor.py*") {
            Write-Host "Skipping Live Monitor (PID $($proc.ProcessId)) - protected daemon." -ForegroundColor Green
            continue
        }
        if ($proc.CommandLine -like "*bridge_server.py*") {
            Write-Host "Skipping Bridge Server (PID $($proc.ProcessId)) - protected daemon." -ForegroundColor Green
            continue
        }
        if ($proc.CommandLine -like "*dexter_slack_listener.py*") {
            Write-Host "Skipping Slack Listener (PID $($proc.ProcessId)) - protected daemon." -ForegroundColor Green
            continue
        }

        Write-Host "Found Zombie Dexter Process: PID $($proc.ProcessId)" -ForegroundColor Yellow
        Write-Host "Command: $($proc.CommandLine)" -ForegroundColor Gray
        $foundZombies += $proc.ProcessId
    }
}

if ($Audit) {
    Write-Host "Audit Mode: No processes terminated." -ForegroundColor Green
    exit 0
}

if ($foundZombies.Count -gt 0) {
    if ($Force -or (Read-Host "Terminate these $($foundZombies.Count) processes? (y/n)") -eq 'y') {
        foreach ($targetPid in $foundZombies) {
            Write-Host "Killing PID $targetPid..." -ForegroundColor Red
            try {
                Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
                Write-Host "Successfully terminated PID $targetPid." -ForegroundColor Green
            } catch {
                Write-Host "PID $targetPid already exited or inaccessible." -ForegroundColor DarkGray
            }
        }
        Write-Host "Cleanup Cycle Complete. Terminated $($foundZombies.Count) process(es). | $timestamp" -ForegroundColor Green
    }
} else {
    Write-Host "No Dexter zombie processes identified." -ForegroundColor Green
}
