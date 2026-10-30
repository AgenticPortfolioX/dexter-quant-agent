
import os
import sys
import json
import time
import subprocess
import threading
from datetime import datetime
import pytz
import yfinance as yf

import traceback
import signal

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from scripts.slack_notifier import send_dexter_slack_alert
from scripts.board_io import read_text, write_text_atomic

from strategies.validation.alpha_autotrader import (
    run_alpha_autotrader,
    close_short_term_positions,
    generate_daily_pnl_report,
    execute_trade,
    evaluate_etf_exits_and_circuit_breaker,
    load_etf_positions,
    get_etf_realtime_price,
    load_circuit_breaker_state,
    LEVERAGED_BTC_ETFS
)

# Global Lock & Paths
DEXTER_ROOT = os.path.dirname(os.path.abspath(__file__))
HEARTBEAT_STATUS_FILE = os.path.join(DEXTER_ROOT, "cache", "heartbeat_status.json")
LOCK_PATH = os.path.join(DEXTER_ROOT, "monitor.lock")
lock_file = None

# Configuration
INTERVAL_SECONDS = 15  # Main loop interval
BOARD_PATH = os.path.join(DEXTER_ROOT, "dashboard", "LIVE_STRATEGY_BOARD.md")
EST = pytz.timezone('US/Eastern')

def update_board_status(status, last_error=None, persistent=False):
    """Updates the Status Board headline and health section only, preserving other content.

    `persistent` is accepted for API compatibility with the alpha engine's
    critical-alert path; status is always persisted to disk here.
    """
    try:
        now_est = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")
        content = read_text(BOARD_PATH)
        
        # 1. Update Status Line
        import re
        if "**Status:" in content:
            content = re.sub(r"\*\*Status:.*$", f"**Status: {status}** (Last Heartbeat: {now_est})", content, flags=re.MULTILINE)
        else:
            # Prefix if missing or dashboard is empty
            header = f"# 🏦 ALPHA COMMAND CENTER: LIVE STRATEGY BOARD\n**Status: {status}** (Last Heartbeat: {now_est})\n\n"
            if not content.strip():
                content = header
            else:
                if "#" in content:
                    parts = content.split("\n", 1)
                    content = parts[0] + "\n" + f"**Status: {status}** (Last Heartbeat: {now_est})\n" + (parts[1] if len(parts) > 1 else "")
                else:
                    content = header + content
        
        # 2. Update Monitor Health section
        health_header = "## 🔋 MONITOR HEALTH"
        health_text = f"{health_header}\n- **Last Active Scan**: {now_est}\n- **System Status**: {'NOMINAL' if not last_error else 'ALERT'}\n"
        if last_error: health_text += f"- **Last Error**: {last_error}\n"
        
        if health_header in content:
            # Replace exactly the health section (from header to next header or end)
            pattern = re.escape(health_header) + r"[\s\S]*?(?=\n##|$)"
            content = re.sub(pattern, health_text, content)
        else:
            content = content.rstrip() + "\n\n" + health_text

        write_text_atomic(BOARD_PATH, content)

    except Exception as e:
        print(f"Failed to update board: {str(e)}")

# --- Scheduled-task helpers -------------------------------------------------
# A task is "due" if its clock threshold has passed and it has not run for the
# current date.  Exact-minute equality (the old behaviour) silently skipped
# tasks whenever a 15s cycle straddled the minute.

def read_last_run_date(path):
    return read_text(path).strip()


def mark_run_date(path, current_date):
    write_text_atomic(path, current_date)


def is_due(now_est, threshold_hhmm, last_run_date, current_date, end_hhmm=None):
    now_hhmm = now_est.strftime("%H:%M")
    if now_hhmm < threshold_hhmm:
        return False
    if end_hhmm is not None and now_hhmm >= end_hhmm:
        return False
    return current_date != last_run_date


_RUNNING_TASKS = set()
_RUNNING_TASKS_LOCK = threading.Lock()


def run_detached(name, cmd, timeout=600):
    """Run a blocking script in a daemon thread so the 15s trading loop never
    stalls behind yfinance or report generation.  Overlapping runs of the same
    task are skipped."""
    with _RUNNING_TASKS_LOCK:
        if name in _RUNNING_TASKS:
            print(f"[TASK] {name} already running — skipping this trigger.")
            return False
        _RUNNING_TASKS.add(name)

    def _runner():
        try:
            print(f"[TASK] {name} started.")
            subprocess.run(cmd, check=False, timeout=timeout)
            print(f"[TASK] {name} finished.")
        except Exception as exc:
            print(f"[TASK] {name} failed: {exc}")
        finally:
            with _RUNNING_TASKS_LOCK:
                _RUNNING_TASKS.discard(name)

    threading.Thread(target=_runner, daemon=True, name=f"task-{name}").start()
    return True

class MarketScheduler:
    def __init__(self):
        self.EST = pytz.timezone('US/Eastern')
        self.last_heartbeat = 0.0
        self.heartbeat_interval = 900  # 15 minutes for log file

    def is_pilot_light_on(self):
        pilot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PILOT_LIGHT.json")
        if not os.path.exists(pilot_path):
            return True 
        try:
            with open(pilot_path, 'r') as f:
                state = json.load(f)
                return state.get("enabled", True)
        except:
            return True

    def get_market_state(self):
        now = datetime.now(self.EST)
        time_str = now.strftime("%H:%M")
        
        # Priority 1: Weekend Check (Overrides everything)
        if now.weekday() >= 5:
            return "DORMANT", "🔴 OFFLINE (Weekend)"

        # Priority 2: Pilot Light Check
        if not self.is_pilot_light_on():
            return "PAUSED", "🔴 SYSTEM PAUSED (Pilot Light is RED)"

        if "08:00" <= time_str < "09:30":
            return "PRE_MARKET", "🟢 SCANNING (Warm-up Mode)"
        elif "09:30" <= time_str < "16:00":
            return "LIVE_MARKET", "🚀 TRADING (Full Alpha Mode)"
        elif "16:00" <= time_str < "16:15":
            return "POST_MARKET", "🟡 SCANNING (Cool-down Mode)"
        else:
            return "DORMANT", "🔴 OFFLINE (Non-Market Hours)"

    def should_log_heartbeat(self):
        now_ts = time.time()
        if now_ts - self.last_heartbeat >= self.heartbeat_interval:
            self.last_heartbeat = now_ts
            return True
        return False

def log_heartbeat(state, pid):
    """Performs a single, batched heartbeat write to disk."""
    heartbeat_path = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\logs\heartbeat.log"
    try:
        os.makedirs(os.path.dirname(heartbeat_path), exist_ok=True)
        now_est = datetime.now(pytz.timezone('US/Eastern'))
        entry = f"[HEARTBEAT] {now_est.strftime('%Y-%m-%d %H:%M:%S EST')} | State: {state} | PID: {pid}\n"
        with open(heartbeat_path, "a", encoding='utf-8') as f:
            f.write(entry)
    except Exception as e:
        print(f"[HEARTBEAT ERROR] Could not write heartbeat: {e}")

def heartbeat_thread_worker(scheduler):
    """Background thread that updates the board every 60 seconds exactly."""
    print("[THREAD] Heartbeat background thread started.")
    while True:
        try:
            state, status_msg = scheduler.get_market_state()
            update_board_status(f"{state}: {status_msg}")
        except Exception as e:
            print(f"[THREAD ERROR] Heartbeat failed: {e}")
        time.sleep(60)

class BrokerBridgeManager:
    """Manages connection, health probing, and exponential backoff restarts for the broker bridge."""
    def __init__(self, port=5005, venv_python=None):
        self.port = port
        self.venv_python = venv_python
        self.last_contact_ts = time.time()
        self.first_failure_ts = None
        self.is_connected = False
        self.consecutive_failures = 0
        self.reconnect_attempts = 0
        self.next_restart_ts = 0.0
        self.last_alert_ts = 0.0
        self.was_disconnected_alerted = False
        self.last_response = {
            "timestamp": None,
            "status": "INITIALIZING",
            "http_code": None,
            "latency_ms": 0.0,
            "logged_in": False,
            "error": None
        }

    def check_health(self):
        """Probes the broker bridge health endpoint over IPv4 127.0.0.1 with 1 immediate retry."""
        import requests
        now_ts = time.time()
        now_est_str = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")
        last_exc = None
        resp = None
        latency_ms = 0.0

        for attempt in range(2):
            t0 = time.time()
            try:
                resp = requests.get(f"http://127.0.0.1:{self.port}/health", timeout=5.0)
                latency_ms = round((time.time() - t0) * 1000, 1)
                if resp.status_code == 200:
                    break
            except Exception as exc:
                latency_ms = round((time.time() - t0) * 1000, 1)
                last_exc = exc
                if attempt == 0:
                    time.sleep(1.5)

        if resp is not None and resp.status_code == 200:
            data = resp.json()
            logged_in = bool(data.get("logged_in", False))
            self.last_response = {
                "timestamp": now_est_str,
                "status": "ONLINE" if logged_in else "AUTH_REQUIRED",
                "http_code": 200,
                "latency_ms": latency_ms,
                "logged_in": logged_in,
                "error": None if logged_in else "Session expired or authentication required on Robinhood app"
            }

            if logged_in:
                disconnect_dur = (now_ts - self.first_failure_ts) if self.first_failure_ts else 0.0
                self.last_contact_ts = now_ts
                self.first_failure_ts = None
                self.is_connected = True

                if self.was_disconnected_alerted:
                    send_dexter_slack_alert(
                        f"BROKER BRIDGE RECONNECTED\n"
                        f"Port: {self.port} | Latency: {latency_ms}ms\n"
                        f"Downtime: {disconnect_dur:.0f}s\n"
                        f"Timestamp: {now_est_str}",
                        is_error=True
                    )
                    self.was_disconnected_alerted = False

                self.consecutive_failures = 0
                return True, "ONLINE"
            else:
                self.is_connected = False
                return False, "AUTH_REQUIRED"
        elif resp is not None:
            self.last_response = {
                "timestamp": now_est_str,
                "status": "HTTP_ERROR",
                "http_code": resp.status_code,
                "latency_ms": latency_ms,
                "logged_in": False,
                "error": f"HTTP {resp.status_code}: {resp.text[:100]}"
            }
            self.is_connected = False
            self._handle_failure(now_ts, now_est_str, f"HTTP {resp.status_code}")
            return False, f"HTTP_{resp.status_code}"
        else:
            err_msg = str(last_exc) if last_exc else "Unknown connection failure"
            self.last_response = {
                "timestamp": now_est_str,
                "status": "OFFLINE",
                "http_code": None,
                "latency_ms": latency_ms,
                "logged_in": False,
                "error": err_msg[:120]
            }
            self.is_connected = False
            self._handle_failure(now_ts, now_est_str, err_msg)
            return False, "OFFLINE"

    def _handle_failure(self, now_ts, now_est_str, error_detail):
        if self.first_failure_ts is None:
            self.first_failure_ts = now_ts
        self.consecutive_failures += 1
        disconnect_dur = now_ts - self.first_failure_ts

        # Trigger disconnect alert to #Triage ONLY if genuinely down > 60s across >= 2 consecutive checks
        if self.consecutive_failures >= 2 and disconnect_dur > 60 and (now_ts - self.last_alert_ts > 300):
            self.last_alert_ts = now_ts
            self.was_disconnected_alerted = True
            send_dexter_slack_alert(
                f"BROKER BRIDGE DISCONNECTED (>60s)\n"
                f"Status: Bridge on port {self.port} unreachable.\n"
                f"Duration: {disconnect_dur:.0f}s | Consecutive Failures: {self.consecutive_failures}\n"
                f"Last Error: {error_detail[:100]}\n"
                f"Action: Initiating automatic restart with exponential backoff.\n"
                f"Timestamp: {now_est_str}",
                is_error=True
            )

        # Exponential backoff restart logic
        if now_ts >= self.next_restart_ts:
            backoff_seconds = min(60, 5 * (2 ** min(self.consecutive_failures - 1, 4)))
            self.next_restart_ts = now_ts + backoff_seconds
            self.reconnect_attempts += 1
            print(f"[{now_est_str}] Attempting Bridge Restart #{self.reconnect_attempts} (Next backoff: {backoff_seconds}s)...")
            self._restart_bridge()

    def _restart_bridge(self):
        try:
            # Purge ONLY stale bridge_server.py processes
            cleanup_script = os.path.join(DEXTER_ROOT, "scripts", "kill_zombies.ps1")
            if os.path.exists(cleanup_script):
                subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", cleanup_script,
                     "-Force", "-KillBridgeOnly", "-ExcludePid", str(os.getpid())],
                    check=False, timeout=20
                )

            bridge_script = os.path.join(DEXTER_ROOT, "quant_scripts", "bridge_server.py")
            python_exe = self.venv_python or os.path.join(DEXTER_ROOT, "quant-env", "Scripts", "pythonw.exe")
            if os.path.exists(bridge_script):
                subprocess.Popen(
                    [python_exe, bridge_script],
                    cwd=DEXTER_ROOT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                )
                print(f"[BRIDGE] bridge_server.py launched in background.")
        except Exception as e:
            print(f"[BRIDGE ERROR] Failed to restart bridge: {e}")

def write_heartbeat_status(state, status_msg, cycle_count, start_time, bridge_mgr, last_error=None, cycle_duration=0.0):
    """
    Task 1: Updates heartbeat file every cycle with:
    - timestamp (EST & ISO)
    - open ETF positions (from load_etf_positions with realtime prices & unrealized PnL %)
    - last broker response (status, latency, code, error)
    - process metrics (PID, uptime, cycle count)
    """
    now_est = datetime.now(EST)
    now_ts = time.time()
    
    # Load open ETF positions and enrich with current prices
    raw_positions = load_etf_positions()
    enriched_etf_positions = {}
    for sym, pos in raw_positions.items():
        if sym in LEVERAGED_BTC_ETFS:
            entry_px = float(pos.get("entry_price", 0))
            curr_px = get_etf_realtime_price(sym) or entry_px
            pnl_pct = ((curr_px - entry_px) / entry_px * 100.0) if entry_px > 0 else 0.0
            entry_ts = pos.get("entry_timestamp", now_ts)
            hold_mins = round((now_ts - entry_ts) / 60.0, 1)
            
            enriched_etf_positions[sym] = {
                "symbol": sym,
                "side": pos.get("side", "LONG"),
                "quantity": pos.get("quantity", 0.0),
                "entry_price": entry_px,
                "current_price": curr_px,
                "unrealized_pnl_pct": round(pnl_pct, 2),
                "entry_time": pos.get("entry_time"),
                "hold_minutes": hold_mins,
                "strategy_name": pos.get("strategy_name")
            }

    cb_state = load_circuit_breaker_state()

    status_eval = "NOMINAL"
    if last_error:
        status_eval = "ALERT"
    elif cb_state.get("tripped", False):
        status_eval = "CIRCUIT_BREAKER_ACTIVE"
    elif not bridge_mgr.is_connected:
        status_eval = "DEGRADED"

    heartbeat_data = {
        "timestamp": now_est.strftime("%Y-%m-%d %H:%M:%S EST"),
        "timestamp_iso": now_est.isoformat(),
        "timestamp_epoch": now_ts,
        "pid": os.getpid(),
        "status": status_eval,
        "market_state": state,
        "market_status_text": status_msg,
        "uptime_seconds": round(now_ts - start_time, 1),
        "cycle_count": cycle_count,
        "last_cycle_duration_seconds": round(cycle_duration, 3),
        "open_etf_positions": enriched_etf_positions,
        "last_broker_response": bridge_mgr.last_response,
        "broker_connection": {
            "is_connected": bridge_mgr.is_connected,
            "disconnect_duration_seconds": round(now_ts - bridge_mgr.last_contact_ts, 1) if not bridge_mgr.is_connected else 0.0,
            "consecutive_failures": bridge_mgr.consecutive_failures,
            "reconnect_attempts": bridge_mgr.reconnect_attempts
        },
        "circuit_breaker": {
            "tripped": cb_state.get("tripped", False),
            "drawdown_pct": cb_state.get("drawdown_pct", 0.0),
            "trip_time": cb_state.get("trip_time")
        },
        "last_error": str(last_error) if last_error else None
    }

    try:
        os.makedirs(os.path.dirname(HEARTBEAT_STATUS_FILE), exist_ok=True)
        temp_file = HEARTBEAT_STATUS_FILE + f".tmp.{os.getpid()}"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(heartbeat_data, f, indent=4)
        if os.path.exists(HEARTBEAT_STATUS_FILE):
            os.remove(HEARTBEAT_STATUS_FILE)
        os.rename(temp_file, HEARTBEAT_STATUS_FILE)
    except Exception as e:
        print(f"[HEARTBEAT ERROR] Could not save heartbeat status file: {e}")

def main(test_once=False):
    # Set stdout/stderr encoding to utf-8 to prevent UnicodeEncodeError on Windows cp1252 terminals
    import io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ["PYTHONIOENCODING"] = "utf-8"

    print("--- DEXTER SUPER-MONITOR STARTED ---")
    
    # 0. Instance Lock (Port Bind Mutex - Port 5007)
    import socket
    try:
        global lock_socket
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.settimeout(1)
        lock_socket.bind(('127.0.0.1', 5007))
        lock_socket.listen(1)
    except socket.error:
        print("[WARN] Another monitor instance is already running (Port 5007 Bound). Throttling exit...")
        time.sleep(5)
        os._exit(0)

    VENV_PYTHON = os.path.join(DEXTER_ROOT, "quant-env", "Scripts", "pythonw.exe")
    if not os.path.exists(VENV_PYTHON):
        VENV_PYTHON = sys.executable

    scheduler = MarketScheduler()
    start_time = time.time()
    cycle_count = 0
    bridge_mgr = BrokerBridgeManager(port=5005, venv_python=VENV_PYTHON)

    # Signal handlers for clean shutdown
    def handle_exit(signum, frame):
        print(f"\n[SHUTDOWN] Signal {signum} received. Updating heartbeat and exiting cleanly...")
        try:
            write_heartbeat_status("STOPPED", "Shutdown by signal", cycle_count, start_time, bridge_mgr)
        except Exception:
            pass
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)
    except Exception:
        pass

    # Start the multi-threaded heartbeat for status board
    hb_thread = threading.Thread(target=heartbeat_thread_worker, args=(scheduler,), daemon=True)
    hb_thread.start()
    
    # Launch Slack Listener on startup
    slack_script = os.path.join(DEXTER_ROOT, "scripts", "dexter_slack_listener.py")
    if os.path.exists(slack_script):
        print(f"[{datetime.now()}] 📡 Booting Dexter Slack Listener (Windowless)...")
        subprocess.Popen([VENV_PYTHON, slack_script], cwd=DEXTER_ROOT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
    else:
        print(f"[{datetime.now()}] ⚠️ Slack Listener script NOT FOUND: {slack_script}")

    # Process Start / Restart Alert (Task 3)
    init_state, init_status = scheduler.get_market_state()
    send_dexter_slack_alert(
        f"DEXTER MONITOR STARTED / RESTARTED\n"
        f"Host: Windows Desktop | PID: {os.getpid()}\n"
        f"EST: {datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S EST')}\n"
        f"Market State: {init_state} ({init_status})\n"
        f"Active ETFs: BITU (2x Long) / SBIT (2x Short)\n"
        f"Polling Interval: {INTERVAL_SECONDS}s",
        is_error=True
    )

    last_intel_time = 0
    while True:
        cycle_start_ts = time.time()
        cycle_count += 1
        last_cycle_error = None
        state, status_msg = "UNKNOWN", "Initializing"

        try:
            now_est = datetime.now(EST)
            current_date = now_est.strftime("%Y-%m-%d")

            # 1. Proactive Broker Bridge Probe & Backoff Recovery (Task 2)
            try:
                bridge_mgr.check_health()
            except Exception as be:
                print(f"[{now_est}] Bridge Check Exception: {be}")

            # 2. Market State
            state, status_msg = scheduler.get_market_state()

            # 3. Scheduled Daily Tasks (isolated in try/except, weekday-only)
            # These are deliberately OUTSIDE the DORMANT/PAUSED guard: the 16:05
            # audit and 17:00 quality pass happen after the close, when the
            # market state is DORMANT, and used to never run at all.
            if now_est.weekday() < 5 and not os.environ.get("DEXTER_SKIP_SCHEDULER"):
                try:
                    report_file = os.path.join(DEXTER_ROOT, ".last_report_date")
                    if is_due(now_est, "09:00",
                              read_last_run_date(report_file), current_date,
                              end_hhmm="09:30"):
                        print(f"[{now_est}] Triggering 9:00 AM Morning Market Report & Cache Warm-Up...")
                        morning_report_script = r"C:\Users\jmgra\antigravityagents\.agent\skills\agentic-skills\15-morning-market-report\scripts\morning_report.py"
                        if os.path.exists(morning_report_script):
                            run_detached("morning_report", [VENV_PYTHON, morning_report_script], timeout=600)

                        warm_up_script = os.path.join(DEXTER_ROOT, "scripts", "warm_up_agent.py")
                        if os.path.exists(warm_up_script):
                            run_detached("warm_up", [VENV_PYTHON, warm_up_script], timeout=600)

                        cleanup_script = os.path.join(DEXTER_ROOT, "scripts", "kill_zombies.ps1")
                        if os.path.exists(cleanup_script):
                            run_detached("kill_zombies",
                                         ["powershell", "-ExecutionPolicy", "Bypass", "-File",
                                          cleanup_script, "-Force", "-ExcludePid", str(os.getpid())],
                                         timeout=30)
                        mark_run_date(report_file, current_date)

                    # 09:15 PEAD candidate scan (must finish before the open)
                    pead_file = os.path.join(DEXTER_ROOT, ".last_pead_scan_date")
                    pead_script = os.path.join(DEXTER_ROOT, "scripts", "pead_scanner.py")
                    if (os.path.exists(pead_script)
                            and is_due(now_est, "09:15", read_last_run_date(pead_file),
                                       current_date, end_hhmm="09:45")):
                        run_detached("pead_scanner", [VENV_PYTHON, pead_script], timeout=900)
                        mark_run_date(pead_file, current_date)

                    # 15:50 EOD Short-Term Position Exit (windowed, not exact-minute)
                    exit_file = os.path.join(DEXTER_ROOT, ".last_exit_date")
                    if is_due(now_est, "15:50", read_last_run_date(exit_file),
                              current_date, end_hhmm="16:00"):
                        print(f"[{now_est}] Triggering 3:50 PM EOD Short-Term Position Exit...")
                        try:
                            close_short_term_positions()
                        finally:
                            # Mark regardless: a failed sweep must not retry every
                            # 15 seconds into the closing auction.
                            mark_run_date(exit_file, current_date)

                    # 16:05 Post-Market Session Audit & P&L Report (runs when DORMANT)
                    audit_file = os.path.join(DEXTER_ROOT, ".last_audit_date")
                    if is_due(now_est, "16:05", read_last_run_date(audit_file), current_date):
                        print(f"[{now_est}] Triggering Post-Market Session Audit & Post-Mortem...")
                        audit_script = os.path.join(DEXTER_ROOT, "scripts", "session_audit.py")
                        if os.path.exists(audit_script):
                            run_detached("session_audit", [VENV_PYTHON, audit_script], timeout=300)
                        post_mortem_script = os.path.join(DEXTER_ROOT, "scripts", "post_mortem_report.py")
                        if os.path.exists(post_mortem_script):
                            run_detached("post_mortem", [VENV_PYTHON, post_mortem_script], timeout=300)
                        # Refresh post-close marks in the systematic position book
                        run_detached("systematic_exits",
                                     [VENV_PYTHON, os.path.join(DEXTER_ROOT, "scripts", "run_systematic_exits.py")],
                                     timeout=120)
                        mark_run_date(audit_file, current_date)

                    # 17:00 Nightly Signal Quality Feedback Loop (runs when DORMANT)
                    quality_check_file = os.path.join(DEXTER_ROOT, ".last_quality_date")
                    if is_due(now_est, "17:00", read_last_run_date(quality_check_file), current_date):
                        print(f"[{now_est}] Triggering 5:00 PM Nightly Signal Quality Feedback Loop...")
                        quality_script = os.path.join(DEXTER_ROOT, "scripts", "signal_quality_tracker.py")
                        if os.path.exists(quality_script):
                            run_detached("signal_quality", [VENV_PYTHON, quality_script], timeout=300)
                        mark_run_date(quality_check_file, current_date)

                    # Market Intelligence (every 15m, only while the market is awake)
                    if (state not in ["DORMANT", "PAUSED"]
                            and (time.time() - last_intel_time > 900 or test_once)):
                        intel_script = os.path.join(DEXTER_ROOT, "scripts", "market_intelligence_agent.py")
                        if os.path.exists(intel_script):
                            print(f"[{now_est}] Refreshing Market Intelligence Context...")
                            if run_detached("market_intel", [VENV_PYTHON, intel_script], timeout=120):
                                last_intel_time = time.time()

                except Exception as sched_err:
                    print(f"[{now_est}] Scheduled task error: {sched_err}")
                    last_cycle_error = f"Scheduled task error: {sched_err}"

            if state not in ["DORMANT", "PAUSED"]:
                # 4. Evaluate Leveraged ETF Bracket Exits (2% SL / 4% TP / Max Hold) & Circuit Breaker (Task 3)
                try:
                    evaluate_etf_exits_and_circuit_breaker(mode=state)
                except Exception as exit_err:
                    print(f"[{now_est}] Error in ETF Exit / Circuit Breaker loop: {exit_err}")
                    last_cycle_error = f"ETF Exit Error: {exit_err}"

                # 5. Run Alpha Engine
                try:
                    run_alpha_autotrader(mode=state)
                except Exception as alpha_err:
                    print(f"[{now_est}] Error running Alpha Autotrader: {alpha_err}")
                    last_cycle_error = f"Alpha Engine Error: {alpha_err}"

            # 6. Command Processing (cmd_*.json)
            try:
                command_dir = os.path.join(DEXTER_ROOT, "commands")
                if os.path.exists(command_dir):
                    archive_dir = os.path.join(command_dir, "archive")
                    if not os.path.exists(archive_dir): os.makedirs(archive_dir, exist_ok=True)

                    for cmd_file in list(os.listdir(command_dir)):
                        if cmd_file.endswith(".json") and cmd_file.startswith("cmd_"):
                            cmd_path = os.path.join(command_dir, cmd_file)
                            try:
                                with open(cmd_path, "r") as f:
                                    cmd_data = json.load(f)
                                
                                cmd_name = cmd_data.get("command")
                                print(f"[{datetime.now()}] EXECUTING COMMAND: {cmd_name}")
                                
                                if cmd_name == "STOP_ALL":
                                    pilot_path = os.path.join(DEXTER_ROOT, "PILOT_LIGHT.json")
                                    toggle_ts = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")
                                    with open(pilot_path, "w") as f:
                                        json.dump({"enabled": False, "last_toggle": toggle_ts}, f, indent=4)
                                
                                elif cmd_name == "CLOSE_TRADE":
                                    asset = cmd_data.get("params", {}).get("asset")
                                    if asset:
                                        from strategies.validation.alpha_autotrader import get_active_positions
                                        active_positions = get_active_positions(mode=state)
                                        qty = active_positions.get(asset)
                                        if qty:
                                            hist = yf.Ticker(asset).history(period="1d")
                                            current_price = hist['Close'].iloc[-1] if not hist.empty else 0
                                            execute_trade("Manual Telegram Close", asset, "SELL", current_price, mode=state, quantity_override=qty)
                                
                                elif cmd_name == "CLOSE_ALL":
                                    from strategies.validation.alpha_autotrader import get_active_positions
                                    active_positions = get_active_positions(mode=state)
                                    for asset, qty in active_positions.items():
                                        hist = yf.Ticker(asset).history(period="1d")
                                        current_price = hist['Close'].iloc[-1] if not hist.empty else 0
                                        execute_trade("Manual Telegram Close All", asset, "SELL", current_price, mode=state, quantity_override=qty)

                                archive_path = os.path.join(archive_dir, cmd_file)
                                if os.path.exists(archive_path): os.remove(archive_path)
                                os.rename(cmd_path, archive_path)
                            except Exception as ce:
                                print(f"Error processing command {cmd_file}: {ce}")
            except Exception as cmd_err:
                print(f"Command processing error: {cmd_err}")

        except Exception as main_loop_err:
            # Task 4: Catch outer exceptions so the main loop NEVER dies
            err_trace = traceback.format_exc()
            print(f"[{datetime.now(EST)}] CRITICAL LOOP EXCEPTION (Resilient Handled): {main_loop_err}\n{err_trace}")
            last_cycle_error = f"CRITICAL LOOP EXCEPTION: {main_loop_err}"

        # Calculate cycle duration and write heartbeat file (Task 1)
        cycle_dur = time.time() - cycle_start_ts
        try:
            write_heartbeat_status(
                state=state,
                status_msg=status_msg,
                cycle_count=cycle_count,
                start_time=start_time,
                bridge_mgr=bridge_mgr,
                last_error=last_cycle_error,
                cycle_duration=cycle_dur
            )
            update_board_status(
                f"{state}: {status_msg}",
                last_error=last_cycle_error
            )
            if scheduler.should_log_heartbeat():
                log_heartbeat(state, os.getpid())
        except Exception as hb_err:
            print(f"Heartbeat write exception: {hb_err}")

        if test_once:
            break

        # Small sleep in main loop to prevent CPU spin
        time.sleep(INTERVAL_SECONDS) 

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run once and exit")
    args = parser.parse_args()
    
    main(test_once=args.test)
