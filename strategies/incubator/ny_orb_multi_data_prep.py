
import os
import yfinance as yf
import pandas as pd
from datetime import datetime

def fetch_multi_asset_orb_data():
    # Nuanced Basket for NY ORB (High Morning Volatility + Liquidity)
    tickers = [
        "SPY", "QQQ", # Indices
        "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD" # High Beta Tech
    ]
    
    # 5m data - yfinance limit is 60 days
    period = "60d"
    interval = "5m"
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    for ticker in tickers:
        print(f"Fetching {ticker} {interval} data for ORB (including pre-market)...")
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True, prepost=True)
            if df.empty:
                print(f"  Failed for {ticker}")
                continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Align to US/Eastern
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC')
            df.index = df.index.tz_convert('US/Eastern')
            
            # Save
            file_path = os.path.join(base_path, f"{ticker}_5m_orb.pkl")
            df.to_pickle(file_path)
            print(f"  Saved {len(df)} bars to {file_path}")
            
        except Exception as e:
            print(f"  Error fetching {ticker}: {e}")

if __name__ == "__main__":
    fetch_multi_asset_orb_data()
