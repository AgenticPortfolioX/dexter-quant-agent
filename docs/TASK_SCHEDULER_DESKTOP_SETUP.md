# Windows Task Scheduler: Dexter Desktop 24/7 Reliability Guide

This guide details the recommended Windows Task Scheduler and operating system configuration to maintain 24/7 uptime for the Dexter Live Monitor and Broker Bridge processes on a desktop workstation.

---

## 1. Desktop Operational Challenges & Solutions

Running high-frequency quant strategies on leveraged Bitcoin ETFs (**BITU** and **SBIT**) from a local desktop computer introduces specific operational risks:

| Desktop Failure Mode | Impact | Dexter Defense Mechanism |
| :--- | :--- | :--- |
| **Windows OS Sleep / Standby** | Halts polling loop and network socket connections | Windows Power Plan configured to "Never Sleep" + "Wake computer to run task" condition in Task Scheduler. |
| **Process Crash or Unhandled Error** | Monitor daemon dies silently | Task Scheduler configured with automatic 1-minute retry (up to 99 times) + isolated try/except blocks inside `live_monitor.py`. |
| **Broker Bridge Disconnect / Hang** | Orders fail or positions are unmonitored | `BrokerBridgeManager` probes `/health` every 15s, executes exponential backoff restarts, and alerts Slack if down >60s. |
| **Duplicate Process Spawning** | Multiple instances fight for broker bridge | TCP Port 5007 mutex single-instance lock cleanly terminates duplicate invocations with throttled exit. |
| **Windows Update Reboots** | Desktop restarts overnight | Task Scheduler "At system startup" trigger auto-launches Dexter on boot before or upon user login. |

---

## 2. Windows Task Scheduler Setup (Step-by-Step)

### Step 1: Open Task Scheduler
1. Press `Win + R`, type `taskschd.msc`, and press **Enter**.
2. In the right panel, click **Create Task...** (do not click *Create Basic Task*).

---

### Step 2: General Tab
- **Name**: `DexterLiveMonitor`
- **Description**: `Dexter AI Quant Engine - 24/7 Live Leveraged Bitcoin ETF Monitor & Bridge Daemon`
- **Security Options**:
  - Select **Run whether user is logged on or not** (or *Run only when user is logged on* if interactive MFA browser popups are required on your desktop).
  - Check **Run with highest privileges**.
- **Configure for**: `Windows 10` or `Windows 11`.

---

### Step 3: Triggers Tab
Create two triggers to ensure the monitor is always started:

#### Trigger A: At Log On
- **Begin the task**: `At log on`
- **Settings**: `Any user` (or specific user `jmgra`)
- **Advanced settings**:
  - Check **Repeat task every**: `5 minutes`
  - For a duration of: `Indefinitely`
  - Check **Enabled**

#### Trigger B: At Startup
- **Begin the task**: `At startup`
- **Advanced settings**:
  - Check **Delay task for**: `30 seconds` (allows network adapters to initialize)
  - Check **Repeat task every**: `5 minutes`
  - For a duration of: `Indefinitely`
  - Check **Enabled**

> [!NOTE]
> Repeating the task every 5 minutes acts as an external watchdog. Because `live_monitor.py` binds exclusive Port 5007, subsequent runs will detect the active instance and immediately exit with code 0 without disturbing the running daemon. If the process ever dies, Task Scheduler will revive it within 5 minutes.

---

### Step 4: Actions Tab
- **Action**: `Start a program`
- **Program/script**:
  ```text
  C:\Users\jmgra\antigravityagents\dexter-quant-agent\quant-env\Scripts\pythonw.exe
  ```
  *(Using `pythonw.exe` ensures the monitor runs as a background process without keeping a terminal window open).*
- **Add arguments**:
  ```text
  live_monitor.py
  ```
- **Start in (crucial)**:
  ```text
  C:\Users\jmgra\antigravityagents\dexter-quant-agent
  ```

---

### Step 5: Conditions Tab
- **Idle**: Default (unchecked).
- **Power**:
  - **UNCHECK** `Start the task only if the computer is on AC power`.
  - **UNCHECK** `Stop if the computer switches to battery power`.
  - **CHECK** `Wake the computer to run this task`.
- **Network**:
  - **CHECK** `Start only if the following network connection is available`: `Any connection`.

---

### Step 6: Settings Tab
- **CHECK** `Allow task to be run on demand`.
- **CHECK** `Run task as soon as possible after a scheduled start is missed`.
- **CHECK** `If the task fails, restart every`: `1 minute`.
- **Attempt to restart up to**: `99 times`.
- **UNCHECK** `Stop the task if it runs longer than: ...` *(Must run indefinitely)*.
- **CHECK** `If the running task does not end when requested, force it to stop`.
- **If the task is already running, then the following rule applies**:
  - Select: `Do not start a new instance`.

---

## 3. Desktop Windows Power & Sleep Configuration

To prevent Windows from suspending network activity or entering hybrid sleep during trading hours:

1. **System Sleep Settings**:
   - Open **Windows Settings** $\rightarrow$ **System** $\rightarrow$ **Power & battery**.
   - Set **"When plugged in, put my device to sleep after"**: **`Never`**.
   - Set **"When plugged in, turn off my screen after"**: `10 minutes` (turning off display saves power without suspending processes).

2. **Advanced Power Options**:
   - Press `Win + R`, type `powercfg.cpl`, press **Enter**.
   - Click **Change plan settings** next to your active power plan $\rightarrow$ **Change advanced power settings**.
   - Under **Sleep** $\rightarrow$ **Allow wake timers**: Set to **`Enable`**.
   - Under **PCI Express** $\rightarrow$ **Link State Power Management**: Set to **`Off`** (prevents network card power downs).
   - Under **Wireless Adapter Settings** / **Network**: Set to **`Maximum Performance`**.

---

## 4. Heartbeat & Live Diagnostics

### Inspecting Heartbeat File
Dexter writes an atomic heartbeat file on every 15-second cycle to:
`cache/heartbeat_status.json`

To inspect health from PowerShell at any time:
```powershell
Get-Content -Raw "C:\Users\jmgra\antigravityagents\dexter-quant-agent\cache\heartbeat_status.json" | ConvertFrom-Json | Select-Object timestamp, status, market_state, cycle_count, uptime_seconds, open_etf_positions, last_broker_response
```

### Heartbeat Status Schema
- `status`: `NOMINAL` (Healthy & connected), `DEGRADED` (Bridge reconnecting), `ALERT` (Error or Circuit Breaker tripped).
- `open_etf_positions`: Live `BITU` and `SBIT` positions with real-time price, entry price, hold minutes, and unrealized PnL %.
- `last_broker_response`: Exact HTTP status code, latency (ms), and connection health.
- `broker_connection`: Disconnect duration (s), consecutive failures, and reconnect attempt count.

---

## 5. Automated Slack Alerts Summary

The system broadcasts real-time alerts to the configured Slack channel for all critical operational events:

| Alert Trigger | Slack Message Prefix | Description |
| :--- | :--- | :--- |
| **Process Startup / Restart** | `🔄 *DEXTER MONITOR STARTED / RESTARTED*` | Broadcasts PID, EST timestamp, market session, and active ETFs. |
| **Broker Disconnect >60s** | `🚨 *BROKER BRIDGE DISCONNECTED (>60s)*` | Fires if bridge is unreachable for 60 seconds; initiates backoff restart. |
| **Broker Reconnected** | `✅ *BROKER BRIDGE RECONNECTED*` | Confirms bridge connection restored, reports downtime and latency. |
| **Stop-Loss Triggered** | `🛑 *LEVERAGED ETF STOP-LOSS HIT*` | Exit executed at $\le -2.0\%$ on 2x ETF price. |
| **Take-Profit Triggered** | `🎯 *LEVERAGED ETF TAKE-PROFIT HIT*` | Exit executed at $\ge +4.0\%$ on 2x ETF price. |
| **Max-Hold Expired** | `⏰ *LEVERAGED ETF MAX-HOLD EXIT HIT*` | Exit executed after 240 minutes holding period. |
| **Daily Circuit Breaker** | `🚨 *DAILY CIRCUIT BREAKER TRIPPED*` | Flattened all ETF positions on $\ge 4.5\%$ equity drawdown. |
