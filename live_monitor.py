
import os
import sys
import json
import time
import subprocess
import threading
from datetime import datetime
import pytz
import yfinance as yf

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from scripts.slack_notifier import send_dexter_slack_alert

from strategies.validation.alpha_autotrader import run_alpha_autotrader, close_short_term_positions, generate_daily_pnl_report, execute_trade

# Global Lock
LOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.lock")
lock_file = None

# Configuration
INTERVAL_SECONDS = 15  # Main loop interval
BOARD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "LIVE_STRATEGY_BOARD.md")
EST = pytz.timezone('US/Eastern')

def update_board_status(status, last_error=None):
    """Updates the Status Board headline and health section only, preserving other content."""
    try:
        now_est = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")
        content = ""
        if os.path.exists(BOARD_PATH):
            with open(BOARD_PATH, "r", encoding='utf-8') as f:
                content = f.read()
        
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

        with open(BOARD_PATH, "w", encoding='utf-8') as f:
            f.write(content)
            
    except Exception as e:
        print(f"Failed to update board: {str(e)}")

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

def main(test_once=False):
    # FIX 1: Set stdout/stderr encoding to utf-8 to prevent UnicodeEncodeError on Windows cp1252 terminals
    import io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    print("--- DEXTER SUPER-MONITOR STARTED ---")
    send_dexter_slack_alert("🚀 *DEXTER SUPER-MONITOR STARTED* - Alpha Engine is now active and scanning.")
    
    # 0. Instance Lock (Port Bind Mutex - Port 5007)
    # This is the most reliable single-instance lock for Windows
    import socket
    try:
        # Create a global socket that we keep open
        global lock_socket
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.settimeout(1)
        lock_socket.bind(('127.0.0.1', 5007))
        lock_socket.listen(1) # Make it visible to netstat and truly exclusive
    except socket.error:
        # HARDENING: Add a sleep before exiting to prevent rapid-fire restart loops (especially with PM2/Watchdogs)
        print("[WARN] Another monitor instance is already running (Port 5007 Bound). Throttling exit...")
        time.sleep(5)
        os._exit(0)

    # FIX 3: Resolve explicit quant-env Python path for all subprocess calls
    # This ensures subprocesses use the correct venv regardless of how the monitor was launched.
    VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quant-env", "Scripts", "pythonw.exe")
    if not os.path.exists(VENV_PYTHON):
        VENV_PYTHON = sys.executable  # Fallback to current interpreter

    scheduler = MarketScheduler()
    
    # 0. Startup Zombie Cleansing
    # FIX 2: Pass current PID so kill_zombies.ps1 excludes THIS process from termination
#    print(f"[{datetime.now()}] Purging zombie Dexter processes (excluding self PID={os.getpid()})...")
#    cleanup_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "kill_zombies.ps1")
#    if os.path.exists(cleanup_script):
#        subprocess.run(
#            ["powershell", "-ExecutionPolicy", "Bypass", "-File", cleanup_script,
#             "-Force", "-ExcludePid", str(os.getpid())],
#            check=False, timeout=30
#        )
    time.sleep(2)

    # Start the multi-threaded heartbeat
    hb_thread = threading.Thread(target=heartbeat_thread_worker, args=(scheduler,), daemon=True)
    hb_thread.start()
    
    # 0. Launch Slack Listener on startup
    slack_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "dexter_slack_listener.py")
    if os.path.exists(slack_script):
        print(f"[{datetime.now()}] 📡 Booting Dexter Slack Listener (Windowless)...")
        # Use VENV_PYTHON (pythonw.exe) to ensure it stays in background
        subprocess.Popen([VENV_PYTHON, slack_script], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
    else:
        print(f"[{datetime.now()}] ⚠️ Slack Listener script NOT FOUND: {slack_script}")
    
    last_intel_time = 0
    last_bridge_check = 0
    total_scans = 0
    while True:
        try:
            now_est = datetime.now(EST)
            current_date = now_est.strftime("%Y-%m-%d")

            # 1. Hard Handshake (Every 5 minutes)
            # This ensures that even if heartbeat is nominal, we detect Auth/Bridge failure
            if time.time() - last_bridge_check > 300 or test_once:
                print(f"[{now_est}] Probing Robinhood Bridge authentication status...")
                import requests
                try:
                    r_health = requests.get("http://localhost:5005/health", timeout=5)
                    if r_health.status_code == 200:
                        health_data = r_health.json()
                        if not health_data.get("logged_in"):
                            print(f"[{now_est}] 🚨 AUTHENTICATION FAILURE DETECTED!")
                            update_board_status("🚨 CRITICAL: AUTHENTICATION REQUIRED")
                    else:
                        print(f"[{now_est}] ⚠️ Bridge Server error (Status {r_health.status_code})")
                        update_board_status(f"⚠️ BRIDGE ERROR {r_health.status_code}")
                except Exception as e:
                    print(f"[{now_est}] ❌ Bridge Server connection failed: {e}")
                    update_board_status("❌ BRIDGE OFFLINE (Restarting...)")
                    # Auto-Restart the Bridge (Self-Healing)
                    print(f"[{now_est}] 🩹 Attempting to restart Bridge Server...")
                    
                    # HARDENING: Kill any existing processes on Port 5005 / Dexter zombies first
                    cleanup_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "kill_zombies.ps1")
                    if os.path.exists(cleanup_script):
                        print(f"[{now_est}] 🧹 Purging zombies before bridge restart (excluding self PID={os.getpid()})...")
                        subprocess.run(
                            ["powershell", "-ExecutionPolicy", "Bypass", "-File", cleanup_script,
                             "-Force", "-ExcludePid", str(os.getpid())],
                            check=False, timeout=30
                        )
                    
                    bridge_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quant_scripts", "bridge_server.py")
                    python_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quant-env", "Scripts", "pythonw.exe")
                    if os.path.exists(bridge_script):
                        subprocess.Popen([python_exe, bridge_script], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
                        time.sleep(5)
                    
                    # Also ensure Slack Listener is running
                    slack_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "dexter_slack_listener.py")
                    if os.path.exists(slack_script):
                        print(f"[{now_est}] 📡 Booting Dexter Slack Listener...")
                        subprocess.Popen([python_exe, slack_script], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
                last_bridge_check = time.time()

            # 2. Execution Logic
            state, status_msg = scheduler.get_market_state()
            
            # 1. Heartbeat Logging (Batched helper, every 15m)
            if state not in ["DORMANT", "PAUSED"]:
                if scheduler.should_log_heartbeat() or test_once:
                    log_heartbeat(state, os.getpid())
                    print(f"[{now_est}] Heartbeat logged. State: {state}")

            # 2. Execution Logic
            if state not in ["DORMANT", "PAUSED"]:
                # Morning Report
                last_report_date = None
                report_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_report_date")
                if os.path.exists(report_file):
                    with open(report_file, "r") as f: last_report_date = f.read().strip()
                
                current_date = now_est.strftime("%Y-%m-%d")
                if now_est.hour == 9 and current_date != last_report_date:
                    print(f"[{now_est}] Triggering 9:00 AM Morning Market Report & Cache Warm-Up...")
                    
                    # 1. Morning Market Report
                    morning_report_script = r"C:\Users\jmgra\antigravityagents\.agent\skills\agentic-skills\15-morning-market-report\scripts\morning_report.py"
                    # FIX 3: Use VENV_PYTHON to ensure correct interpreter
                    subprocess.run([VENV_PYTHON, morning_report_script], check=False, timeout=600)
                    
                    # 2. Cache Warm-Up
                    warm_up_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "warm_up_agent.py")
                    subprocess.run([VENV_PYTHON, warm_up_script], check=False, timeout=600)

                    # 3. Zombie Process Extraction (9:00 AM SOP) — FIX 2: exclude self PID
                    print(f"[{now_est}] Running 9:00 AM Zombie Process Extraction...")
                    cleanup_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "kill_zombies.ps1")
                    if os.path.exists(cleanup_script):
                        subprocess.run(
                            ["powershell", "-ExecutionPolicy", "Bypass", "-File", cleanup_script,
                             "-Force", "-ExcludePid", str(os.getpid())],
                            check=False, timeout=30
                        )
                    
                    with open(report_file, "w") as f: f.write(current_date)

                # End of Day Market Close Exit (4:00 PM)
                last_exit_date = None
                exit_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_exit_date")
                if os.path.exists(exit_file):
                    with open(exit_file, "r") as f: last_exit_date = f.read().strip()
                
                if now_est.hour == 15 and now_est.minute == 50 and current_date != last_exit_date:
                    print(f"[{now_est}] Triggering 4:00 PM EOD Short-Term Position Exit...")
                    close_short_term_positions()
                    with open(exit_file, "w") as f: f.write(current_date)

                # Post-Market Session Audit & P&L Report (4:15 PM)
                last_audit_date = None
                audit_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_audit_date")
                if os.path.exists(audit_file):
                    with open(audit_file, "r") as f: last_audit_date = f.read().strip()
                
                if now_est.hour == 16 and now_est.minute == 15 and current_date != last_audit_date:
                    print(f"[{now_est}] Triggering 4:15 PM Post-Market Session Audit & Enhanced Post-Mortem...")
                    # 1. Qualitative Audit
                    audit_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "session_audit.py")
                    subprocess.run([VENV_PYTHON, audit_script], check=False, timeout=300)
                    
                    # 2. Enhanced Post-Mortem Report
                    post_mortem_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "post_mortem_report.py")
                    subprocess.run([VENV_PYTHON, post_mortem_script], check=False, timeout=300)
                    
                    with open(audit_file, "w") as f: f.write(current_date)

                # Nightly Signal Quality Analysis
                last_quality_date = None
                quality_check_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_quality_date")
                if os.path.exists(quality_check_file):
                    with open(quality_check_file, "r") as f: last_quality_date = f.read().strip()
                
                if now_est.hour == 17 and current_date != last_quality_date:
                    print(f"[{now_est}] Triggering 5:00 PM Nightly Signal Quality Feedback Loop...")
                    quality_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "signal_quality_tracker.py")
                    subprocess.run([VENV_PYTHON, quality_script], check=False, timeout=300)  # FIX 3
                    with open(quality_check_file, "w") as f: f.write(current_date)

                # 2.5 Market Intelligence (Every 15 mins during active sessions)
                if state != "DORMANT" and (time.time() - last_intel_time > 900 or test_once):
                    intel_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "market_intelligence_agent.py")
                    if os.path.exists(intel_script):
                        print(f"[{now_est}] Refreshing Market Intelligence Context...")
                        subprocess.run([VENV_PYTHON, intel_script], check=False, timeout=120)  # FIX 3
                        last_intel_time = time.time()


                # Run Alpha Engine (This can take minutes, but won't block the heartbeat thread)
                run_alpha_autotrader(mode=state)

            # 3. Command Processing
            command_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "commands")
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
                                pilot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PILOT_LIGHT.json")
                                # IMPROVEMENT: Write last_toggle timestamp so we know when it was stopped
                                toggle_ts = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")
                                with open(pilot_path, "w") as f:
                                    json.dump({"enabled": False, "last_toggle": toggle_ts}, f, indent=4)
                            
                            elif cmd_name == "CLOSE_TRADE":
                                asset = cmd_data.get("params", {}).get("asset")
                                if asset:
                                    print(f"[{datetime.now()}] Slack/Manual Command: Closing trade for {asset}")
                                    try:
                                        from strategies.validation.alpha_autotrader import get_active_positions
                                        active_positions = get_active_positions(mode=state)
                                        qty = active_positions.get(asset)
                                        if qty:
                                            hist = yf.Ticker(asset).history(period="1d")
                                            current_price = hist['Close'].iloc[-1] if not hist.empty else 0
                                            execute_trade("Manual Telegram Close", asset, "SELL", current_price, mode=state, quantity_override=qty)
                                            print(f"[{datetime.now()}] Successfully triggered trade closure for {asset} (Qty: {qty}).")
                                        else:
                                            print(f"[{datetime.now()}] No active position found for {asset}.")
                                    except Exception as trade_error:
                                        print(f"[{datetime.now()}] Failed to execute CLOSE_TRADE for {asset}: {trade_error}")

                            elif cmd_name == "CLOSE_ALL":
                                print(f"[{datetime.now()}] Slack/Manual Command: Closing ALL active trades.")
                                try:
                                    from strategies.validation.alpha_autotrader import get_active_positions
                                    active_positions = get_active_positions(mode=state)
                                    for asset, qty in active_positions.items():
                                        hist = yf.Ticker(asset).history(period="1d")
                                        current_price = hist['Close'].iloc[-1] if not hist.empty else 0
                                        execute_trade("Manual Telegram Close All", asset, "SELL", current_price, mode=state, quantity_override=qty)
                                        print(f"[{datetime.now()}] Successfully triggered trade closure for {asset} (Qty: {qty}).")
                                except Exception as trade_error:
                                    print(f"[{datetime.now()}] Failed to execute CLOSE_ALL: {trade_error}")

                            archive_path = os.path.join(archive_dir, cmd_file)
                            if os.path.exists(archive_path): os.remove(archive_path) # Prevent rename collision
                            os.rename(cmd_path, archive_path)
                        except Exception as ce:
                            print(f"Error processing command {cmd_file}: {ce}")
        except Exception as e:
            print(f"CRITICAL ERROR in Monitor: {e}")
        
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
