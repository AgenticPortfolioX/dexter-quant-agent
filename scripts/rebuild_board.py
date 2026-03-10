import json
import os
from datetime import datetime
import pytz

ROOT = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(ROOT, "..", "strategy_registry.json")
BOARD_PATH = os.path.join(ROOT, "..", "dashboard", "LIVE_STRATEGY_BOARD.md")
EST = pytz.timezone('US/Eastern')

def rebuild():
    if not os.path.exists(REGISTRY_PATH):
        print(f"Registry not found at {REGISTRY_PATH}")
        return

    with open(REGISTRY_PATH, 'r') as f:
        registry = json.load(f)

    pilot_path = os.path.join(ROOT, "..", "PILOT_LIGHT.json")
    pilot_on = True
    if os.path.exists(pilot_path):
        try:
            with open(pilot_path, 'r') as f:
                pilot_on = json.load(f).get("enabled", True)
        except: pass
    
    light = "🟢" if pilot_on else "🔴"
    now_est = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")
    
    lines = [
        "# 🏦 ALPHA COMMAND CENTER: LIVE STRATEGY BOARD\n",
        f"**PILOT LIGHT: {light}** | **Status: INITIALIZING...** (Last Heartbeat: {now_est})\n\n",
        "## 🟢 LIVE TRADING\n",
        "| Strategy Name | Active Assets | Status | Latest Signal |\n",
        "| :--- | :--- | :--- | :--- |\n"
    ]

    for strat in registry.get('live_trading', []):
        name = strat['name']
        assets = ", ".join(strat['assets'])
        lines.append(f"| **{name}** | {assets} | Active | None |\n")

    lines.append("\n## 🧪 ACTIVE TESTING\n")
    lines.append("| Strategy Name | Active Assets | Status | Latest Signal |\n")
    lines.append("| :--- | :--- | :--- | :--- |\n")

    for strat in registry.get('active_testing', []):
        name = strat['name']
        assets = ", ".join(strat['assets'])
        lines.append(f"| **{name}** | {assets} | Testing | None |\n")

    lines.append("\n## 🔋 MONITOR HEALTH\n")
    lines.append(f"- **Last Active Scan**: {now_est}\n")
    lines.append("- **System Status**: NOMINAL\n")

    with open(BOARD_PATH, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"Successfully rebuilt board at {BOARD_PATH}")

if __name__ == "__main__":
    rebuild()
