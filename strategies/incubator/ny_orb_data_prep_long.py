
import sys
import os
import pandas as pd
import numpy as np
import pytz
from datetime import time
import yfinance as yf

def process_ny_orb_data_long(ticker="ES=F"):
    print(f"Fetching 60 days of 5-minute data for {ticker} (Max allowable intraday history)...")
    
    # yfinance limit for 5m is 60d
    df = yf.download(ticker, period="60d", interval="5m", progress=False, auto_adjust=True)
    
    if df.empty:
        print("No data fetched.")
        return

    # Handle MultiIndex if present
    # yfinance often returns MultiIndex like (Price, Ticker) or (Ticker, Price) depending on version/args
    if isinstance(df.columns, pd.MultiIndex):
        try:
            if ticker in df.columns.levels[0]:
                df = df[ticker].copy()
            elif ticker in df.columns.levels[1]:
                 df = df.xs(ticker, axis=1, level=1, drop_level=True)
            else:
                 # Fallback: Assume structure is Ticker -> OHLC but flattened?
                 # Or just try to select by level 0 name?
                 pass
        except Exception:
             # Last resort if structure is messy: flatten
             df.columns = ['_'.join(col).strip() for col in df.columns.values]
             # This might break the standard logic if it expects simple OHLC but we can adapt lower down
             pass

    print(f"Aligning {len(df)} rows to US/Eastern...")
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert('US/Eastern')

    # Add Boolean Columns
    times = df.index.time
    t_0800 = time(8, 0)
    t_0930 = time(9, 30)
    t_0945 = time(9, 45)
    t_1600 = time(16, 0)
    
    print("Adding boolean flags...")
    df['is_premarket_window'] = (times >= t_0800) & (times < t_0930)
    # Note: On 5m chart, 09:30, 09:35, 09:40 candles make up the 15m ORB
    df['is_orb_anchor'] = (times >= t_0930) & (times < t_0945)
    df['is_trading_session'] = (times >= t_0945) & (times < t_1600)

    # Clean
    df.dropna(subset=['Close'], inplace=True)
    
    output_path = "ES_5m_aligned.pkl"
    df.to_pickle(output_path)
    print(f"60-Day Data saved to {output_path}")

if __name__ == "__main__":
    process_ny_orb_data_long()
