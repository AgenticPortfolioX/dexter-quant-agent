"""
Link-Pilled Scanner - Live Monitoring for High-Conviction SFP Setups
--------------------------------------------------------------------
Exclusively targets: LINK-USD, SOL-USD, CL=F
"""

from strategies.successful_strategies.link_pilled import LinkPilledStrategy
import yfinance as yf
import pandas as pd
from datetime import datetime
import time

WATCHLIST = ['LINK-USD', 'SOL-USD', 'CL=F']

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
    print(f"[{datetime.now()}] Starting SFP Watchlist Scan...")
    
    for ticker in WATCHLIST:
        if not is_market_open(ticker):
            print(f"Skipping {ticker} - Market Closed.")
            continue
            
        try:
            strategy = SFPStrategy(ticker)
            signals = strategy.generate_sfp_trade_signal(ticker)
            
            if signals is not None and not signals.empty:
                # We only care about the MOST RECENT signal for the scanner (live alert)
                latest_signal = signals.iloc[-1]
                # Check if it happened within the last 2 hours (to avoid stale alerts)
                # sfp_time = latest_signal['SFP_Time']
                # if (pd.Timestamp.now(tz=sfp_time.tz) - sfp_time).total_seconds() < 7200:
                print(f"\n🚀 LIVE SFP SIGNAL DETECTED: {ticker} 🚀")
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
