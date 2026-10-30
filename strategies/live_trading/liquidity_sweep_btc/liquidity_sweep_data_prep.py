
import sys
import os
import pandas as pd
import yfinance as yf
from datetime import time

def fetch_liquidity_sweep_data():
    tickers = ["BTC-USD", "ETH-USD"]
    
    # We use 1h for Execution (allows 730d history on yfinance)
    # We use 4h for Context
    period = "730d"
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    for ticker in tickers:
        print(f"Fetching data for {ticker}...")
        safe_ticker = ticker.replace("=X", "").replace("-", "")
        
        # 1 Hour Data (Execution)
        try:
            df_1h = yf.download(ticker, period=period, interval="1h", progress=False, auto_adjust=True)
            if df_1h.empty:
                print(f"  No 1h data for {ticker}")
                continue
                
            # 4 Hour Data (Context) -> yfinance doesn't natively support 4h? 
            # Actually yfinance supports: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
            # It does NOT support 4h directly usually. 
            # We will fetch 1h and resample to 4h, OR use 1d for context.
            # Let's use 1d (Daily) for context pools if 4h is unavailable.
            # Actually, standard SFP is often H1 sweep of Daily levels. 
            # Let's try fetching "1d" for context.
            
            df_1d = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
            if df_1d.empty:
                print(f"  No 1d data for {ticker}")
                continue

            # Align Timezones
            if df_1h.index.tz is None: df_1h.index = df_1h.index.tz_localize('UTC')
            df_1h.index = df_1h.index.tz_convert('US/Eastern')
            
            if df_1d.index.tz is None: df_1d.index = df_1d.index.tz_localize('UTC')
            df_1d.index = df_1d.index.tz_convert('US/Eastern')
            
            # Save
            df_1h.to_pickle(os.path.join(base_path, f"{safe_ticker}_1h_sweep.pkl"))
            df_1d.to_pickle(os.path.join(base_path, f"{safe_ticker}_1d_sweep.pkl"))
            
            print(f"  Saved {safe_ticker}_1h_sweep.pkl ({len(df_1h)} rows)")
            print(f"  Saved {safe_ticker}_1d_sweep.pkl ({len(df_1d)} rows)")
            
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")

if __name__ == "__main__":
    fetch_liquidity_sweep_data()
