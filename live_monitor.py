
import os
import sys
import json
import time
import subprocess
import threading
from datetime import datetime
import pytz

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from strategies.validation.alpha_autotrader import run_alpha_autotrader

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
        if not self.is_pilot_light_on():
            return "PAUSED", "🔴 SYSTEM PAUSED (Pilot Light is RED)"

        now = datetime.now(self.EST)
        time_str = now.strftime("%H:%M")
        
        if now.weekday() >= 5:
            return "DORMANT", "🔴 OFFLINE (Weekend)"

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
    print(f"--- DEXTER SUPER-MONITOR STARTED ---")
    scheduler = MarketScheduler()
    
    # Start the multi-threaded heartbeat
    hb_thread = threading.Thread(target=heartbeat_thread_worker, args=(scheduler,), daemon=True)
    hb_thread.start()
    
    last_intel_time = 0
    while True:
        try:
            now_est = datetime.now(scheduler.EST)
            state, status_msg = scheduler.get_market_state()
            
            # 1. Heartbeat Logging (Batched helper, every 15m)
            if state != "DORMANT":
                if scheduler.should_log_heartbeat() or test_once:
                    log_heartbeat(state, os.getpid())
                    print(f"[{now_est}] Heartbeat logged. State: {state}")

            # 2. Execution Logic
            if state != "DORMANT":
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
                    subprocess.run([sys.executable, morning_report_script], check=False, timeout=600)
                    
                    # 2. Proposal 6: Cache Warm-Up
                    warm_up_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "warm_up_agent.py")
                    subprocess.run([sys.executable, warm_up_script], check=False, timeout=600)
                    
                    with open(report_file, "w") as f: f.write(current_date)

                # Post-Market Session Audit
                last_audit_date = None
                audit_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_audit_date")
                if os.path.exists(audit_file):
                    with open(audit_file, "r") as f: last_audit_date = f.read().strip()
                
                if now_est.hour == 16 and now_est.minute == 15 and current_date != last_audit_date:
                    print(f"[{now_est}] Triggering 4:15 PM Post-Market Session Audit...")
                    audit_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "session_audit.py")
                    subprocess.run([sys.executable, audit_script], check=False, timeout=300)
                    with open(audit_file, "w") as f: f.write(current_date)

                # Nightly Signal Quality Analysis
                last_quality_date = None
                quality_check_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_quality_date")
                if os.path.exists(quality_check_file):
                    with open(quality_check_file, "r") as f: last_quality_date = f.read().strip()
                
                if now_est.hour == 17 and current_date != last_quality_date:
                    print(f"[{now_est}] Triggering 5:00 PM Nightly Signal Quality Feedback Loop...")
                    quality_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "signal_quality_tracker.py")
                    subprocess.run([sys.executable, quality_script], check=False, timeout=300)
                    with open(quality_check_file, "w") as f: f.write(current_date)

                # 2.5 Market Intelligence (Every 15 mins during active sessions)
                if state != "DORMANT" and (time.time() - last_intel_time > 900 or test_once):
                    intel_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "market_intelligence_agent.py")
                    if os.path.exists(intel_script):
                        print(f"[{now_est}] Refreshing Market Intelligence Context...")
                        subprocess.run([sys.executable, intel_script], check=False, timeout=120)
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
                                with open(pilot_path, "w") as f: json.dump({"enabled": False}, f)
                            
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
