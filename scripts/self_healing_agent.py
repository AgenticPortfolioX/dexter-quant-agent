
import os
import sys
import subprocess
import json
import socket
import time
from datetime import datetime
import pytz

EST = pytz.timezone('US/Eastern')
DEXTER_ROOT = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
BRIDGE_SCRIPT = os.path.join(DEXTER_ROOT, "quant_scripts", "bridge_server.py")
MONITOR_SCRIPT = os.path.join(DEXTER_ROOT, "live_monitor.py")
ENV_PATH = os.path.join(DEXTER_ROOT, "quant-env", "Scripts", "python.exe")
PYTHONW_PATH = os.path.join(DEXTER_ROOT, "quant-env", "Scripts", "pythonw.exe")

def log_healing(message):
    print(f"[{datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S')}] [HEALER] {message}")

def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def check_bridge():
    """Ensures Robinhood Bridge is online and authenticated on port 5005."""
    import requests
    try:
        r = requests.get("http://127.0.0.1:5005/health", timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get("logged_in"):
                log_healing("OK: Robinhood Bridge is online and authenticated.")
                return True, "Authenticated"
            else:
                log_healing("FAIL: Bridge is online but NOT authenticated (MFA/Logic Error).")
                return False, "Not Authenticated"
    except Exception:
        pass
    
    log_healing("CHECK: Robinhood Bridge is offline or unreachable. Attempting restart...")
    try:
        # Start in background with pythonw
        subprocess.Popen(
            [PYTHONW_PATH, BRIDGE_SCRIPT],
            cwd=DEXTER_ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        time.sleep(10) # Wait for spin up and login attempt
        
        # Verify post-restart
        try:
            r = requests.get("http://127.0.0.1:5005/health", timeout=5)
            if r.status_code == 200 and r.json().get("logged_in"):
                log_healing("OK: Bridge successfully restarted and authenticated.")
                return True, "Restarted & Authenticated"
        except:
            pass
            
        log_healing("FAIL: Bridge restart failed to achieve authentication.")
        return False, "Failed to Authenticate"
    except Exception as e:
        log_healing(f"ERROR: Bridge restart error: {e}")
        return False, f"Error: {e}"

def check_monitor():
    """Ensures Live Monitor is running."""
    try:
        result = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq pythonw.exe", "/FO", "CSV"], capture_output=True, text=True)
        # We can't easily tell which pythonw.exe is the monitor without more complex checks, 
        # but we can check the heartbeat file to see if it's updated.
        heartbeat_file = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\logs\heartbeat.log"
        if os.path.exists(heartbeat_file):
            mtime = os.path.getmtime(heartbeat_file)
            age = (time.time() - mtime) / 60
            if age < 20:
                log_healing(f"OK: Live Monitor heartbeat is fresh ({int(age)} min old).")
                return True, "Responsive"
            else:
                log_healing(f"STALE: Live Monitor heartbeat is STALE ({int(age)} min old). Restarting...")
        else:
            log_healing("NOT_FOUND: No Live Monitor heartbeat found. Attempting start...")

        # Restart attempt
        subprocess.Popen(
            [PYTHONW_PATH, MONITOR_SCRIPT],
            cwd=DEXTER_ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return True, "Restarted"
    except Exception as e:
        log_healing(f"❌ Monitor check error: {e}")
        return False, f"Error: {e}"

def check_alpha_drift():
    """Checks if the alpha engine is persistently failing or skipping."""
    alpha_log = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\logs\live_trading\alpha_engine.log"
    if not os.path.exists(alpha_log):
        return True, "No Log Yet"
    
    try:
        with open(alpha_log, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-50:]
            warnings = [l for l in lines if "[WARNING]" in l and "Unknown strat_type" in l]
            if len(warnings) > 10:
                log_healing("DRIFT: High volume of Alpha warnings detected. Drifting?")
                return False, f"Drifting ({len(warnings)} warnings)"
        return True, "Nominal"
    except:
        return True, "Check Failed"

def run_self_healing():
    log_healing("--- DEXTER SELF-HEALING PROTOCOL INITIATED ---")
    actions = []
    
    # 1. Bridge
    b_success, b_note = check_bridge()
    actions.append(f"Bridge Integrity: {b_note}")
    
    # 2. Monitor
    m_success, m_note = check_monitor()
    actions.append(f"Monitor Integrity: {m_note}")
    
    # 3. Alpha Drift
    a_success, a_note = check_alpha_drift()
    actions.append(f"Alpha Strategy Sync: {a_note}")
    
    log_healing("--- HEALING COMPLETE ---")
    return {
        "success": b_success and m_success and a_success,
        "actions": actions
    }

if __name__ == "__main__":
    run_self_healing()
