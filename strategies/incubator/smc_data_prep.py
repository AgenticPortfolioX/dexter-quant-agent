
import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def fetch_smc_data():
    # Assets: SPY, Tesla, BTC, Nasdaq
    tickers = ["SPY", "TSLA", "BTC-USD", "NQ=F"]
    
    # 5m data allows 60 days limit
    # 1m data allows 7 days limit
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    for ticker in tickers:
        print(f"Fetching data for {ticker}...")
        safe_ticker = ticker.replace("=F", "").replace("-", "")
        
        try:
            # 5m Data (60 Days)
            print(f"  Downloading 60d of 5m data for {ticker}...")
            df_5m = yf.download(ticker, period="60d", interval="5m", progress=False, auto_adjust=True)
            if isinstance(df_5m.columns, pd.MultiIndex):
                df_5m.columns = df_5m.columns.get_level_values(0)
            
            # 1m Data (Max 7 Days)
            print(f"  Downloading 7d of 1m data for {ticker}...")
            df_1m = yf.download(ticker, period="7d", interval="1m", progress=False, auto_adjust=True)
            if isinstance(df_1m.columns, pd.MultiIndex):
                df_1m.columns = df_1m.columns.get_level_values(0)
                
            if not df_5m.empty:
                df_5m.to_pickle(os.path.join(base_path, f"{safe_ticker}_5m_smc.pkl"))
                print(f"  Saved {len(df_5m)} bars of 5m data.")
            
            if not df_1m.empty:
                df_1m.to_pickle(os.path.join(base_path, f"{safe_ticker}_1m_smc.pkl"))
                print(f"  Saved {len(df_1m)} bars of 1m data.")
                
        except Exception as e:
            print(f"  Error fetching {ticker}: {e}")

if __name__ == "__main__":
    fetch_smc_data()
