
import os
import yfinance as yf
import pandas as pd
from datetime import datetime

def fetch_broad_basket_smc():
    # Nuanced Basket of 30 Assets
    tickers = [
        "SPY", "QQQ", "DIA", "IWM", "GLD", "USO", # Indices/Commodities
        "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", # Mag 7
        "AMD", "AVGO", "ADBE", "NFLX", # Semis/SaaS
        "JPM", "GS", "V", "MA", # Financials
        "WMT", "COST", "PG", # Retail/Consumer
        "UNH", "LLY", "JNJ", # Healthcare
        "XOM", "CVX", "CAT", # Energy/Industrial
        "BTC-USD" # Crypto
    ]
    
    # Timeframe: 1h candles for 1 Year
    period = "1y"
    interval = "1h"
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    for ticker in tickers:
        print(f"Fetching {period} of {interval} data for {ticker}...")
        safe_ticker = ticker.replace("=F", "").replace("-", "")
        
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
            
            if df.empty:
                print(f"  Failed for {ticker}")
                continue
            
            # Clean MultiIndex headers if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Save
            file_path = os.path.join(base_path, f"{safe_ticker}_1h_smc.pkl")
            df.to_pickle(file_path)
            print(f"  Saved {len(df)} bars to {file_path}")
            
        except Exception as e:
            print(f"  Error fetching {ticker}: {e}")

if __name__ == "__main__":
    fetch_broad_basket_smc()
