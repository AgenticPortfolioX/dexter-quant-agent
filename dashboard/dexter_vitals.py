import os
import subprocess
import json
from datetime import datetime

# Paths
ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\logs"
BOARD_PATH = os.path.join(ROOT, "LIVE_STRATEGY_BOARD.md")
HEARTBEAT_LOG = os.path.join(LOG_DIR, "heartbeat.log")
ENGINE_LOG = os.path.join(LOG_DIR, "alpha_engine.log")

def get_last_lines(filepath, n=5):
    if not os.path.exists(filepath):
        return ["File not found."]
    try:
        with open(filepath, "r", encoding='utf-8') as f:
            lines = f.readlines()
            return [l.strip() for l in lines[-n:]]
    except Exception as e:
        return [f"Error reading file: {e}"]

def check_process(name):
    try:
        output = subprocess.check_output(f'tasklist /FI "IMAGENAME eq {name}" /V', shell=True, text=True)
        if name in output:
            return "RUNNING", output.strip().split('\n')[-1]
        return "NOT RUNNING", None
    except:
        return "UNKNOWN", None

def main():
    print("="*50)
    print(f"📡 DEXTER VITALS REPORT | {datetime.now()}")
    print("="*50)

    # 1. Pilot Light
    pilot_path = os.path.join(ROOT, "..", "PILOT_LIGHT.json")
    pilot_on = "UNKNOWN"
    if os.path.exists(pilot_path):
        try:
            with open(pilot_path, 'r') as f:
                pilot_on = "🟢 GREEN (Active)" if json.load(f).get("enabled", True) else "🔴 RED (Paused)"
        except: pass
    
    # 2. Process Status
    py_status, py_details = check_process("python.exe")
    bun_status, bun_details = check_process("bun.exe")
    
    print(f"\n[SYSTEM PROCESSES]")
    print(f"Pilot Light:     {pilot_on}")
    print(f"Monitor (Python): {py_status}")
    if py_details: print(f"  > {py_details}")
    print(f"Core (Bun):      {bun_status}")
    if bun_details: print(f"  > {bun_details}")

    # 2. Board Status
    print(f"\n[STRATEGY BOARD]")
    if os.path.exists(BOARD_PATH):
        try:
            with open(BOARD_PATH, "r", encoding='utf-8') as f:
                first_line = f.readline().strip()
                print(f"Current Status: {first_line}")
        except:
            print("Status: Error reading board.")
    else:
        print("Status: Board not found.")

    # 3. Heartbeat
    print(f"\n[LAST HEARTBEATS]")
    for line in get_last_lines(HEARTBEAT_LOG, 3):
        print(f"  {line}")

    # 4. Engine Activity
    print(f"\n[RECENT ENGINE LOGS]")
    for line in get_last_lines(ENGINE_LOG, 5):
        print(f"  {line}")

    print("\n" + "="*50)

if __name__ == "__main__":
    main()
