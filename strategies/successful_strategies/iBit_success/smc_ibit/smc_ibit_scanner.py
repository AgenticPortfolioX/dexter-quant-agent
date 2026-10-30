
import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from smc_strategy import SmartMoneyStrategy

def btc_2x_smc_scanner(ticker: str = "BITU"):
    strategy = SmartMoneyStrategy()
    
    print(f"--- BITCOIN 2x LEVERAGED SMC SCANNER (BITU/SBIT) [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ---")
    
    try:
        # Fetch latest data
        df = yf.download(ticker, period="7d", interval="1h", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        if df.empty:
            print(f"No data found for {ticker}.")
            return
            
        # Run Strategy
        df = strategy.add_indicators(df)
        df = strategy.process_logic(df)
        
        # Check last candle
        last_row = df.iloc[-1]
        sig = last_row['entry_signal']
        mss = last_row['mss_signal']
        
        if sig in ['BUY', 'SELL']:
            target_symbol = "BITU" if sig == 'BUY' else "SBIT"
            action_desc = "2x LONG (Open BITU)" if sig == 'BUY' else "2x SHORT (Open SBIT)"
            price_level = last_row['bullish_fvg_top'] if sig == 'BUY' else last_row['bearish_fvg_bottom']
            print(f"!!! SIGNAL DETECTED: {ticker} -> {sig} => EXECUTING {action_desc} @ {price_level:.2f} !!!")
        elif mss:
            print(f"Structure Shift Detected: {mss}. Watching for retrace.")
        else:
            print(f"No active signals for {ticker}.")

    except Exception as e:
        print(f"Error scanning {ticker}: {e}")

if __name__ == "__main__":
    btc_2x_smc_scanner("BITU")
