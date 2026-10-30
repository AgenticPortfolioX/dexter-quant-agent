"""
Link-Pilled Scanner - Live Monitoring for High-Conviction SFP Setups
--------------------------------------------------------------------
Exclusively targets: LINK-USD, SOL-USD, CL=F
"""

from link_pilled import LinkPilledStrategy
import yfinance as yf
import pandas as pd
from datetime import datetime
import time

WATCHLIST = ['BITU', 'LINK-USD', 'SOL-USD', 'CL=F']

# 2x Leveraged Bitcoin Mapping
BTC_MAP = {
    'Long': 'BITU',   # 2x Long Bitcoin
    'Short': 'SBIT'   # 2x Short Bitcoin
}

def is_market_open(ticker: str) -> bool:
    """Checks if the market for the given ticker is currently open."""
    # Simple check: Crypto is 24/7. Forex/Gold close on weekends.
    if "-USD" in ticker or ticker in ['BTC-USD', 'ETH-USD', 'SOL-USD']:
        return True
    
    now = datetime.now()
    if now.weekday() >= 5: # Saturday or Sunday
        return False
    return True

def run_scanner():
    print(f"[{datetime.now()}] Starting SFP Watchlist Scan (BITU 2x Long / SBIT 2x Short)...")
    
    for ticker in WATCHLIST:
        if not is_market_open(ticker):
            print(f"Skipping {ticker} - Market Closed.")
            continue
            
        try:
            strategy = LinkPilledStrategy(ticker)
            df_h1 = strategy.fetch_h1_data(period="5d")
            levels = strategy.find_clean_swing_points(df_h1)
            signals = strategy.detect_sfp_candle(df_h1, levels)
            
            if signals is not None and not signals.empty:
                latest_signal = signals.iloc[-1]
                sfp_type = latest_signal.get('sfp_type', 'Long')
                exec_target = BTC_MAP.get(sfp_type, ticker) if ticker in ['BITU', 'IBIT'] else ticker
                print(f"\n🚀 LIVE SFP SIGNAL DETECTED: {ticker} ({sfp_type}) => TARGET: {exec_target} 🚀")
                print(latest_signal)
            else:
                print(f"No active SFP signals for {ticker}.")
                
        except Exception as e:
            print(f"Error scanning {ticker}: {e}")

if __name__ == "__main__":
    run_scanner()

"""
CRONTAB INSTRUCTIONS:
To run this scanner every hour:
0 * * * * C:/Users/jmgra/anaconda3/python.exe C:/Users/jmgra/antigravityagents/dexter-quant-agent/strategies/incubator/sfp_scanner.py >> sfp_scan.log 2>&1
"""
