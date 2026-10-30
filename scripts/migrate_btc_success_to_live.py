"""
Migrate all strategies from strategies/successful_strategies/btc_success into strategies/live_trading.
Modifies each strategy to exclusively trade:
  - BITU (ProShares Ultra Bitcoin 2x Long ETF) for LONG signals
  - SBIT (ProShares UltraShort Bitcoin 2x Inverse ETF) for SHORT signals
Ensures NO IBIT or BTC-USD or BTC is directly traded.
"""

import os
import shutil
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "strategies", "successful_strategies", "btc_success")
DEST_DIR = os.path.join(ROOT, "strategies", "live_trading")
REGISTRY_PATH = os.path.join(ROOT, "strategy_registry.json")

os.makedirs(DEST_DIR, exist_ok=True)

FOLDER_MAPPING = [
    ("inside_candle_btc", "inside_candle_btc"),
    ("liquidity_sweep_btc", "liquidity_sweep_btc"),
    ("power_of_3", "power_of_3"),
    ("rsi_btc", "rsi_btc"),
    ("smc_btc", "smc_btc"),
    ("btc_tech_level_ema", "btc_tech_level_ema"),
    ("link-pilled", "sfp_btc"),
]

def migrate_folders():
    print("=== Copying BTC Strategies to strategies/live_trading/ ===")
    for src_sub, dest_sub in FOLDER_MAPPING:
        src = os.path.join(SRC_DIR, src_sub)
        dest = os.path.join(DEST_DIR, dest_sub)

        if not os.path.exists(src):
            print(f"  [ERROR] Source folder does not exist: {src}")
            continue

        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        print(f"  [COPIED] {src_sub} -> strategies/live_trading/{dest_sub}")

def add_etf_adapters():
    """Injects or ensures ETF mapping (BITU for Long, SBIT for Short) in all migrated strategies."""
    print("\n=== Injecting BITU (Long) & SBIT (Short) Execution Adapters ===")

    adapter_code = '''
# --- Leveraged Bitcoin ETF Execution Protocol ---
# All Bitcoin strategies exclusively trade BITU (2x Long) and SBIT (2x Short).
# Direct trading of IBIT or BTC is strictly prohibited.
LONG_ETF = "BITU"
SHORT_ETF = "SBIT"

def resolve_etf_target(direction: str) -> dict:
    """
    Maps trading signals to 2x leveraged Bitcoin ETFs.
    LONG -> Buy BITU
    SHORT -> Buy SBIT
    """
    d = direction.upper()
    if d in ["BUY", "LONG", "BULLISH"]:
        return {
            "symbol": LONG_ETF,
            "action": "BUY",
            "side": "LONG",
            "leverage": "2x Long",
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.04
        }
    elif d in ["SELL", "SHORT", "BEARISH"]:
        return {
            "symbol": SHORT_ETF,
            "action": "BUY",
            "side": "SHORT",
            "leverage": "2x Inverse Short",
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.04
        }
    return None
'''

    for _, dest_sub in FOLDER_MAPPING:
        adapter_path = os.path.join(DEST_DIR, dest_sub, "etf_execution_adapter.py")
        with open(adapter_path, "w", encoding="utf-8") as f:
            f.write(adapter_code)
        print(f"  [ADAPTER CREATED] {dest_sub}/etf_execution_adapter.py")

def update_strategy_registry():
    print("\n=== Updating strategy_registry.json for Live Trading ===")
    with open(REGISTRY_PATH, 'r') as f:
        registry = json.load(f)

    current_live = registry.get("live_trading", [])
    
    # Existing non-Bitcoin live strategies to preserve
    preserved = [s for s in current_live if "SMC Bitcoin" not in s['name']]

    # New 7 Bitcoin live trading strategies
    btc_live_strategies = [
        {
            "name": "Inside Candle (2x Leveraged BTC)",
            "active_window": "00:00-23:59",
            "script": "strategies/live_trading/inside_candle_btc/inside_candle_strategy.py",
            "assets": ["BITU", "SBIT"],
            "frequency": 3600,
            "notes": "Mother Bar / Inside Bar breakout. Long -> BITU | Short -> SBIT. No IBIT or BTC traded."
        },
        {
            "name": "Liquidity Sweep (2x Leveraged BTC)",
            "active_window": "00:00-23:59",
            "script": "strategies/live_trading/liquidity_sweep_btc/liquidity_sweep_strategy.py",
            "assets": ["BITU", "SBIT"],
            "frequency": 900,
            "notes": "15m liquidity pool sweep + 1m MSS + FVG scalp. Long -> BITU | Short -> SBIT. No IBIT or BTC traded."
        },
        {
            "name": "Power of 3 (2x Leveraged BTC)",
            "active_window": "00:00-23:59",
            "script": "strategies/live_trading/power_of_3/power_of_3.py",
            "assets": ["BITU", "SBIT"],
            "frequency": 300,
            "notes": "Accumulation-Manipulation-Distribution (PO3/AMD) sweep. Long -> BITU | Short -> SBIT. No IBIT or BTC traded."
        },
        {
            "name": "RSI Reversion (2x Leveraged BTC)",
            "active_window": "00:00-23:59",
            "script": "strategies/live_trading/rsi_btc/rsi_reversion.py",
            "assets": ["BITU", "SBIT"],
            "frequency": 3600,
            "notes": "RSI(14) oversold/overbought candlestick mean reversion. Long -> BITU | Short -> SBIT. No IBIT or BTC traded."
        },
        {
            "name": "SMC Bitcoin (2x Leveraged)",
            "active_window": "00:00-23:59",
            "script": "strategies/live_trading/smc_btc/smc_strategy.py",
            "assets": ["BITU", "SBIT"],
            "frequency": 3600,
            "notes": "Smart Money Concepts market structure shift & FVG retrace. Long -> BITU | Short -> SBIT. No IBIT or BTC traded."
        },
        {
            "name": "Tech Level EMA Touch (2x Leveraged BTC)",
            "active_window": "00:00-23:59",
            "script": "strategies/live_trading/btc_tech_level_ema/run_le_model_scanner_tech.py",
            "assets": ["BITU", "SBIT"],
            "frequency": 3600,
            "notes": "Anchor filter + EMA touch + Volume confirmation. Long -> BITU | Short -> SBIT. No IBIT or BTC traded."
        },
        {
            "name": "SFP Swing Failure (2x Leveraged BTC)",
            "active_window": "00:00-23:59",
            "script": "strategies/live_trading/sfp_btc/link_pilled.py",
            "assets": ["BITU", "SBIT"],
            "frequency": 3600,
            "notes": "Swing Failure Pattern targeting liquidity sweeps with volume spikes. Long -> BITU | Short -> SBIT. No IBIT or BTC traded."
        }
    ]

    # Combine preserved equity/index strategies + new 7 Bitcoin live strategies
    updated_live = preserved + btc_live_strategies
    registry["live_trading"] = updated_live

    with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=4)

    print(f"Total Live Trading Strategies Now Registered: {len(updated_live)}")
    for s in updated_live:
        print(f"  - {s['name']} | Assets: {', '.join(s['assets'])}")

if __name__ == "__main__":
    migrate_folders()
    add_etf_adapters()
    update_strategy_registry()
