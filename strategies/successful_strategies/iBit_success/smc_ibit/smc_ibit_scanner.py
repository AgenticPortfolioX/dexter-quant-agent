
import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from smc_strategy import SmartMoneyStrategy

def ibit_smc_scanner():
    ticker = "IBIT"
    strategy = SmartMoneyStrategy()
    
    print(f"--- IBIT SMART MONEY STRATEGY SCANNER [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ---")
    
    try:
        # Fetch latest data
        df = yf.download(ticker, period="7d", interval="1h", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        if df.empty:
            print("No data found for IBIT.")
            return
            
        # Run Strategy
        df = strategy.add_indicators(df)
        df = strategy.process_logic(df)
        
        # Check last candle
        last_row = df.iloc[-1]
        sig = last_row['entry_signal']
        mss = last_row['mss_signal']
        
        if sig in ['BUY', 'SELL']:
            print(f"!!! SIGNAL DETECTED: IBIT -> {sig} !!!")
            if sig == 'BUY':
                print(f"Level: {last_row['bullish_fvg_top']}")
            else:
                print(f"Level: {last_row['bearish_fvg_bottom']}")
        elif mss:
            print(f"Structure Shift Detected: {mss}. Watching for retrace.")
        else:
            print("No active signals for IBIT.")

    except Exception as e:
        print(f"Error scanning IBIT: {e}")

if __name__ == "__main__":
    ibit_smc_scanner()
