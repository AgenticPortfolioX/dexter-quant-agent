"""
Migration Script: Move Strategies with Profit Factor < 1.10 into strategies/meh
and Decommission from Live Trading.
"""

import os
import shutil
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(ROOT, "strategy_registry.json")
RESULTS_PATH = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\backtests\results\live_strategies_backtest_results.json"
if not os.path.exists(RESULTS_PATH):
    RESULTS_PATH = os.path.join(ROOT, "cache", "live_strategies_backtest_results.json")
MEH_DIR = os.path.join(ROOT, "strategies", "meh")

os.makedirs(MEH_DIR, exist_ok=True)

# 1. Directory and file move specifications
MOVES = [
    # Subdirectories
    ("strategies/live_trading/gemini_velocity", "strategies/meh/gemini_velocity", True),
    ("strategies/live_trading/big_d", "strategies/meh/big_d", True),
    ("strategies/live_trading/little_d", "strategies/meh/little_d", True),
    ("strategies/active_testing/volcanix_vwap_reclaim", "strategies/meh/volcanix_vwap_reclaim", True),
    # Individual files
    ("strategies/active_testing/ny_orb_strategy.py", "strategies/meh/ny_orb_strategy.py", False),
    ("strategies/active_testing/wickless_candle_strategy.py", "strategies/meh/wickless_candle_strategy.py", False),
    ("strategies/active_testing/dynamic_bias_momentum_strategy.py", "strategies/meh/dynamic_bias_momentum_strategy.py", False),
    ("strategies/active_testing/volatility_squeeze_breakout.py", "strategies/meh/volatility_squeeze_breakout.py", False),
    ("strategies/active_testing/macd_oscillator.py", "strategies/meh/macd_oscillator.py", False),
    ("strategies/active_testing/bollinger_bands.py", "strategies/meh/bollinger_bands.py", False),
    ("strategies/active_testing/shooting_star.py", "strategies/meh/shooting_star.py", False),
    ("strategies/active_testing/dual_thrust.py", "strategies/meh/dual_thrust.py", False),
    ("strategies/active_testing/heikin_ashi.py", "strategies/meh/heikin_ashi.py", False),
    ("strategies/active_testing/strategy_os.py", "strategies/meh/strategy_os.py", False),
]

def execute_moves():
    print("Moving strategy files/directories into strategies/meh/...")
    for src_rel, dest_rel, is_dir in MOVES:
        src = os.path.join(ROOT, src_rel)
        dest = os.path.join(ROOT, dest_rel)

        if not os.path.exists(src):
            print(f"  [SKIP] Source does not exist: {src_rel}")
            continue

        if is_dir:
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.move(src, dest)
            print(f"  [MOVED DIR] {src_rel} -> {dest_rel}")
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.exists(dest):
                os.remove(dest)
            shutil.move(src, dest)
            print(f"  [MOVED FILE] {src_rel} -> {dest_rel}")

def update_registry():
    print("\nUpdating strategy_registry.json...")
    with open(REGISTRY_PATH, 'r') as f:
        registry = json.load(f)

    # Names of strategies to decommission (PF < 1.10)
    DECOMMISSION_NAMES = {
        "Gemini Velocity": "strategies/meh/gemini_velocity/gemini_velocity_momentum.py",
        "BigD (PO3/AMD)": "strategies/meh/big_d/big_d.py",
        "LittleD (SFP)": "strategies/meh/little_d/little_d.py",
        "Volcanix (VWAP Reclaim)": "strategies/meh/volcanix_vwap_reclaim/vwap_reclaim_rvol.py",
        "NY ORB": "strategies/meh/ny_orb_strategy.py",
        "Wickless Candles": "strategies/meh/wickless_candle_strategy.py",
        "Dynamic + Daily Bias": "strategies/meh/dynamic_bias_momentum_strategy.py",
        "Nova (Optimized)": "strategies/meh/volatility_squeeze_breakout.py",
        "MACD Oscillator (MACD)": "strategies/meh/macd_oscillator.py",
        "Bollinger Bands (BB)": "strategies/meh/bollinger_bands.py",
        "Shooting Star (SS)": "strategies/meh/shooting_star.py",
        "Dual Thrust (DT)": "strategies/meh/dual_thrust.py",
        "Heikin Ashi (HA)": "strategies/meh/heikin_ashi.py",
        "Strategy OS": "strategies/meh/strategy_os.py",
    }

    current_live = registry.get("live_trading", [])
    new_live = []
    meh_list = registry.get("meh", [])

    for strat in current_live:
        name = strat['name']
        if name in DECOMMISSION_NAMES:
            strat['script'] = DECOMMISSION_NAMES[name]
            strat['status'] = "DECOMMISSIONED"
            strat['decommission_reason'] = "Profit Factor < 1.10 in Live Backtest Audit"
            meh_list.append(strat)
        else:
            new_live.append(strat)

    registry["live_trading"] = new_live
    registry["meh"] = meh_list

    with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=4)

    print(f"  Live Trading Strategies Remaining: {len(new_live)}")
    print(f"  Decommissioned Meh Strategies: {len(meh_list)}")

if __name__ == "__main__":
    execute_moves()
    update_registry()
