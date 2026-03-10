import os
import json

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_registry.json")

DEFAULT_REGISTRY = {
    "live_trading": [
        {
            "name": "SMC Focal Portfolio",
            "script": "strategies/validation/smc_live_autotrader.py",
            "assets": ["AAPL", "DIA", "JNJ", "WMT", "GS"],
            "frequency": 900
        },
        {
            "name": "Trinity Basket",
            "script": "trinity_test_scanner.py",
            "assets": ["GLD", "FXY", "FXE"],
            "frequency": 900
        }
    ],
    "active_testing": [
        {
            "name": "Volatility Contraction",
            "script": "volatility_contraction/live_monitor.py",
            "assets": ["SPY", "USO"],
            "frequency": 60
        },
        {
            "name": "NY ORB",
            "script": "strategies/active-strategies/ny_orb_strategy.py",
            "assets": ["SPY", "QQQ"],
            "frequency": 3600
        }
    ]
}

def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        save_registry(DEFAULT_REGISTRY)
        return DEFAULT_REGISTRY
    try:
        with open(REGISTRY_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        return DEFAULT_REGISTRY

def save_registry(data):
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(data, f, indent=4)

if __name__ == "__main__":
    # Test/Initialize
    reg = load_registry()
    print(f"Registry loaded with {len(reg['live_trading'])} live and {len(reg['active_testing'])} testing strategies.")
