import os
import sys
import requests
import json
import pandas as pd
from datetime import datetime
import pytz

# Setup Paths
DEXTER_ROOT = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
REGISTRY_PATH = os.path.join(DEXTER_ROOT, 'strategy_registry.json')
EST = pytz.timezone('US/Eastern')

def check_bridge():
    """Check if the Robinhood Bridge server is alive."""
    try:
        response = requests.get("http://localhost:5005/positions", timeout=5)
        if response.status_code == 200:
            return True, "✅ Bridge Server: Online (Connected to Robinhood)"
        return False, f"⚠️ Bridge Server: Error {response.status_code}"
    except Exception as e:
        return False, f"❌ Bridge Server: Offline (Check if bridge_server.py is running)"

def check_data_connectivity():
    """Verify market data fetching works."""
    import yfinance as yf
    try:
        ticker = yf.Ticker("SPY")
        hist = ticker.history(period="1d")
        if not hist.empty:
            return True, "✅ Market Data: Connected (yfinance active)"
        return False, "⚠️ Market Data: Empty Response"
    except Exception as e:
        return False, f"❌ Market Data: Connection Failed ({e})"

def check_registry():
    """Verify strategy registry is readable and contains assets."""
    try:
        if not os.path.exists(REGISTRY_PATH):
            return False, "❌ Registry: Missing strategy_registry.json"
        with open(REGISTRY_PATH, 'r') as f:
            data = json.load(f)
        live_count = len(data.get('live_trading', []))
        return True, f"✅ Registry: Loaded ({live_count} live strategies)"
    except Exception as e:
        return False, f"❌ Registry: Parse Error ({e})"

def run_heartbeat():
    print(f"\n--- 💓 DEXTER SYSTEM HEARTBEAT | {datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S EST')} ---")
    
    status_summary = []
    all_clear = True
    
    checks = [check_bridge(), check_data_connectivity(), check_registry()]
    
    for success, msg in checks:
        print(msg)
        status_summary.append(msg)
        if not success:
            all_clear = False
            
    print("-" * 50)
    if all_clear:
        print("✅ DEXTER IS BATTLE-READY.")
    else:
        print("🚨 ACTION REQUIRED: IMPAIRMENTS DETECTED.")
    
    return all_clear, "\n".join(status_summary)

if __name__ == "__main__":
    run_heartbeat()
