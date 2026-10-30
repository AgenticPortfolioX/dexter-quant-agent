"""
Decommission Sonnet (ORE + Regime) and Awesome Oscillator (AO)
Move scripts to strategies/meh/ and update strategy_registry.json.
"""

import os
import shutil
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(ROOT, "strategy_registry.json")
MEH_DIR = os.path.join(ROOT, "strategies", "meh")

os.makedirs(MEH_DIR, exist_ok=True)

MOVES = [
    ("strategies/Ai-strats/sonnet_ore_regime.py", "strategies/meh/sonnet_ore_regime.py"),
    ("strategies/active_testing/awesome_oscillator.py", "strategies/meh/awesome_oscillator.py"),
]

def execute_moves():
    print("Moving Sonnet and AO scripts to strategies/meh/...")
    for src_rel, dest_rel in MOVES:
        src = os.path.join(ROOT, src_rel)
        dest = os.path.join(ROOT, dest_rel)

        if not os.path.exists(src):
            print(f"  [SKIP] Source does not exist: {src_rel}")
            continue

        if os.path.exists(dest):
            os.remove(dest)
        shutil.move(src, dest)
        print(f"  [MOVED] {src_rel} -> {dest_rel}")

def update_registry():
    print("\nUpdating strategy_registry.json...")
    with open(REGISTRY_PATH, 'r') as f:
        registry = json.load(f)

    TARGET_NAMES = {
        "Sonnet (ORE + Regime)": "strategies/meh/sonnet_ore_regime.py",
        "Awesome Oscillator (AO)": "strategies/meh/awesome_oscillator.py"
    }

    current_live = registry.get("live_trading", [])
    new_live = []
    meh_list = registry.get("meh", [])

    for strat in current_live:
        name = strat['name']
        if name in TARGET_NAMES:
            strat['script'] = TARGET_NAMES[name]
            strat['status'] = "DECOMMISSIONED"
            strat['decommission_reason'] = "Decommissioned by User Request"
            meh_list.append(strat)
            print(f"  [DECOMMISSIONED] {name}")
        else:
            new_live.append(strat)

    registry["live_trading"] = new_live
    registry["meh"] = meh_list

    with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=4)

    print(f"\nRemaining Live Trading Strategies: {len(new_live)}")
    for s in new_live:
        print(f"  - {s['name']}")
    print(f"Total Decommissioned Meh Strategies: {len(meh_list)}")

if __name__ == "__main__":
    execute_moves()
    update_registry()
