# Dexter Pre-Market Watchdog & SOP Automator
# Runs continuously (15m audit interval) without disrupting healthy daemons.

$logFile = "C:\Users\jmgra\antigravityagents\dexter-quant-agent\logs\pre_market_audit.log"
$heartbeatFile = "C:\Users\jmgra\antigravityagents\dexter-quant-agent\cache\heartbeat_status.json"
$zombieScript = "C:\Users\jmgra\antigravityagents\dexter-quant-agent\scripts\kill_zombies.ps1"
$pythonwExe = "C:\Users\jmgra\antigravityagents\dexter-quant-agent\quant-env\Scripts\pythonw.exe"
$workDir = "C:\Users\jmgra\antigravityagents\dexter-quant-agent"
$watchdogPort = 5008

# Single-Instance Watchdog Lock (Keep listener rooted in script scope so GC never collects it)
$script:watchdogListener = $null
try {
    $script:watchdogListener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $watchdogPort)
    $script:watchdogListener.Start()
} catch {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] Another Watchdog instance is already running (Port $watchdogPort Bound). Exiting." | Out-File -FilePath $logFile -Append -Encoding utf8
    exit 0
}

while ($true) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] Starting Health Audit..." | Out-File -FilePath $logFile -Append -Encoding utf8

    # 1. Audit Live Monitor (Must have active Win32_Process for live_monitor.py)
    $monitorRunning = $false
    try {
        $monProc = Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%live_monitor.py%'" -ErrorAction SilentlyContinue
        if ($monProc) {
            $monitorRunning = $true
        }
    } catch {
        $monitorRunning = $false
    }

    # 2. Audit Bridge Server via HTTP health endpoint on 127.0.0.1:5005 (with 1 retry)
    $bridgeRunning = $false
    for ($i = 0; $i -lt 2; $i++) {
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:5005/health" -Method Get -TimeoutSec 5 -ErrorAction Stop
            if ($resp.status -eq "online") {
                $bridgeRunning = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }

    # 3. Targeted Corrective Action (Never kill healthy daemons!)
    if (-not $bridgeRunning) {
        "[$timestamp] Bridge Server unreachable on 127.0.0.1:5005. Restarting Bridge only..." | Out-File -FilePath $logFile -Append -Encoding utf8
        if (Test-Path $zombieScript) {
            powershell -NoProfile -ExecutionPolicy Bypass -File $zombieScript -Force -KillBridgeOnly | Out-File -FilePath $logFile -Append -Encoding utf8
        }
        Start-Process -FilePath $pythonwExe -ArgumentList "$workDir\quant_scripts\bridge_server.py" -WorkingDirectory $workDir -WindowStyle Hidden
        Start-Sleep -Seconds 5
    }

    if (-not $monitorRunning) {
        "[$timestamp] Live Monitor offline. Launching Live Monitor..." | Out-File -FilePath $logFile -Append -Encoding utf8
        Start-Process -FilePath $pythonwExe -ArgumentList "$workDir\live_monitor.py" -WorkingDirectory $workDir -WindowStyle Hidden
    }

    # 4. Specialized Check for Slack Listener
    $slackRunning = Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%dexter_slack_listener.py%'" -ErrorAction SilentlyContinue
    if (-not $slackRunning) {
        "[$timestamp] Slack Listener Offline. Rebooting..." | Out-File -FilePath $logFile -Append -Encoding utf8
        Start-Process -FilePath $pythonwExe -ArgumentList "$workDir\scripts\dexter_slack_listener.py" -WorkingDirectory $workDir -WindowStyle Hidden
    }

    "[$timestamp] Audit Cycle Complete. Status: { Monitor:$monitorRunning, Bridge:$bridgeRunning }. Sleeping 15m." | Out-File -FilePath $logFile -Append -Encoding utf8
    Start-Sleep -Seconds 900
}
