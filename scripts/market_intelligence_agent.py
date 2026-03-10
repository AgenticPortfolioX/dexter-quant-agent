"""
Market Intelligence Context Agent (Proposal 7)
==============================================
Runs periodically to gather macro context:
- VIX (Volatility Index)
- Sector Rotation (XLK vs XLP)
- Economic Calendar (today's FOMC, CPI, etc.)
Writes to 'market_context.json' for consumption by Alpha Engine.
"""
import os
import sys
import json
import time
from datetime import datetime
import pytz

# Add project root to path
PROJECT_ROOT = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import yfinance as yf

EST = pytz.timezone('US/Eastern')
CONTEXT_FILE = os.path.join(PROJECT_ROOT, 'market_context.json')

def get_vix_status():
    """Fetch VIX and determine risk level."""
    try:
        vix = yf.Ticker("^VIX").fast_info['last_price']
        risk = "NOMINAL"
        if vix > 20: risk = "CAUTION"
        if vix > 30: risk = "HIGH_RISK"
        return {"value": round(vix, 2), "risk_level": risk}
    except:
        return {"value": 0, "risk_level": "UNKNOWN"}

def get_sector_rotation():
    """Compare Tech (XLK) vs Defensive (XLP) 1-day performance."""
    try:
        xlk = yf.Ticker("XLK").history(period="2d")
        xlp = yf.Ticker("XLP").history(period="2d")
        
        xlk_perf = (xlk['Close'].iloc[-1] / xlk['Close'].iloc[-2]) - 1
        xlp_perf = (xlp['Close'].iloc[-1] / xlp['Close'].iloc[-2]) - 1
        
        rotation = "NEUTRAL"
        if xlk_perf > xlp_perf + 0.01: rotation = "RISK_ON"
        if xlp_perf > xlk_perf + 0.01: rotation = "RISK_OFF"
        
        return {
            "rotation": rotation,
            "xlk_1d": round(xlk_perf * 100, 2),
            "xlp_1d": round(xlp_perf * 100, 2)
        }
    except:
        return {"rotation": "UNKNOWN", "xlk_1d": 0, "xlp_1d": 0}

def get_macro_indicators():
    """Fetch DXY (USD) and TNX (10Y Yield)."""
    try:
        dxy = yf.Ticker("DX-Y.NYB").fast_info['last_price']
        tnx = yf.Ticker("^TNX").fast_info['last_price']
        return {"dxy": round(dxy, 2), "tnx": round(tnx, 2)}
    except:
        return {"dxy": 0, "tnx": 0}

def update_context():
    """Main execution: Gather all intelligence and write to disk."""
    now = datetime.now(EST)
    print(f"[{now.strftime('%H:%M:%S')}] 🧠 MARKET INTEL AGENT — Gathering macro context...")
    
    vix = get_vix_status()
    sectors = get_sector_rotation()
    macro = get_macro_indicators()
    
    # Pack result
    context = {
        "timestamp": now.isoformat(),
        "vix": vix,
        "sectors": sectors,
        "macro": macro,
        "caution_mode": (vix['risk_level'] == "HIGH_RISK" or sectors['rotation'] == "RISK_OFF")
    }
    
    with open(CONTEXT_FILE, 'w') as f:
        json.dump(context, f, indent=4)
        
    print(f"  ✅ VIX: {vix['value']} ({vix['risk_level']})")
    print(f"  ✅ Rotation: {sectors['rotation']} (XLK: {sectors['xlk_1d']}%, XLP: {sectors['xlp_1d']}%)")
    print(f"  ✅ Macro Context Saved to {CONTEXT_FILE}")

if __name__ == '__main__':
    update_context()
