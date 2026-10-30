
import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import time

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from strategies.incubator.smc_btc_plus import SmartMoneyStrategy

def smc_realtime_scanner():
    # Focal Portfolio (Top 5 Performers)
    tickers = ["AAPL", "DIA", "JNJ", "WMT", "GS"]
    
    strategy = SmartMoneyStrategy()
    
    print(f"--- SMC REAL-TIME SCANNER STARTED [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ---")
    print(f"Monitoring: {', '.join(tickers)}\n")
    
    all_alerts = []

    for ticker in tickers:
        try:
            # Fetch latest data (1h timeframe, 7d lookback for context)
            df = yf.download(ticker, period="7d", interval="1h", progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            if df.empty: continue
            
            # Run Strategy
            df = strategy.add_indicators(df)
            df = strategy.process_logic(df)
            
            # Check last 3 candles for signals (to avoid missing one that just closed)
            last_signals = df.tail(3)
            
            for idx, row in last_signals.iterrows():
                sig = row['entry_signal']
                mss = row['mss_signal']
                
                if sig in ['BUY', 'SELL']:
                    alert = f"[{idx}] ALERT: {ticker} -> {sig} Signal Detected!"
                    if sig == 'BUY':
                        alert += f" | FVG Top: {row['bullish_fvg_top']:.2f}"
                    else:
                        alert += f" | FVG Bot: {row['bearish_fvg_bottom']:.2f}"
                    
                    all_alerts.append(alert)
                    print(alert)
                
                elif mss:
                    print(f"[{idx}] INFO: {ticker} -> {mss} Formed. Watching for retrace...")

        except Exception as e:
            print(f"Error scanning {ticker}: {e}")

    # Save alerts to a log file
    log_dir = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\alerts"
    if not os.path.exists(log_dir): os.makedirs(log_dir)
    
    log_file = os.path.join(log_dir, f"smc_alerts_{datetime.now().strftime('%Y%m%d')}.txt")
    with open(log_file, 'a') as f:
        if all_alerts:
            f.write(f"--- SCAN AT {datetime.now()} ---\n")
            for a in all_alerts: f.write(a + "\n")
            f.write("\n")
        else:
            f.write(f"[{datetime.now()}] Scan complete: No new signals.\n")
            
    print(f"\nScan Complete. Alerts logged to {log_file}")

if __name__ == "__main__":
    smc_realtime_scanner()
