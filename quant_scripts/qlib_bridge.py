
import pandas as pd
import yfinance as yf
import argparse
import sys
import datetime
from datetime import datetime, timedelta, date, time
import pytz

def ensure_list(x):
    if isinstance(x, list):
        return x
    return [x]

def fetch_historical_data(tickers, interval='1m', period='30d'):
    """
    Simulates bridging to Qlib by fetching raw data via yfinance for this PoC.
    Returns: pandas DataFrame aligned to EST.
    """
    tickers = ensure_list(tickers)
    
    # Try fetching up to 30 days if possible, or fallback to 7 days for 1m
    # yfinance often limits 1m to 7 days
    try:
        data = yf.download(tickers, period=period, interval=interval, group_by='ticker', auto_adjust=True, progress=False)
        
        # If MultiIndex columns (multiple tickers), flatten or handle
        if isinstance(data.columns, pd.MultiIndex):
            # For simplicity, extract just the first ticker for this bridge
            ticker = tickers[0]
            if ticker in data.columns.levels[0]:
                data = data[ticker].copy()
            else:
                # Flat structure if just one ticker?
                pass 
                # Check structure
        
        if data.empty:
            print(f"Warning: No data fetched for {tickers} with period {period}. Trying 7d...")
            data = yf.download(tickers, period='7d', interval=interval, group_by='ticker', auto_adjust=True, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                ticker = tickers[0]
                if ticker in data.columns.levels[0]:
                    data = data[ticker].copy()

        if data.empty:
            raise ValueError(f"Failed to fetch data for {tickers}")

        # Ensure index is datetime with timezone
        if data.index.tz is None:
             # Assume UTC if not set by yfinance (yfinance usually returns localized or UTC)
             # Actually yfinance returns localized to exchange time or UTC. 
             # For forex, it's usually UTC.
             data.index = data.index.tz_localize('UTC')
        
        # Convert to US/Eastern
        est = pytz.timezone('US/Eastern')
        data.index = data.index.tz_convert(est)
        
        return data

    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame()

def sanity_check_asian_range(df):
    """
    Verifies that we can identify 19:00 - 02:00 EST blocks in the data.
    Prints the High/Low for each identified session.
    """
    if df.empty:
        print("Data is empty. Cannot run sanity check.")
        return

    print("\n--- Sanity Check: Asian Range Identification (19:00 - 02:00 EST) ---")
    
    # Group by trading day. 
    # Asian range (19:00 prev day to 02:00 current day) belongs to 'Current Day' session logically.
    # We can iterate through days and find the range.
    
    # Get unique dates in dataset
    unique_dates = pd.unique(df.index.date)
    unique_dates.sort()
    
    for current_date in unique_dates:
        # Define the window:
        # Start: Previous day 19:00
        # End: Current day 02:00
        
        prev_date = current_date - timedelta(days=1)
        
        start_dt = pd.Timestamp.combine(prev_date, time(19, 0)).tz_localize('US/Eastern')
        end_dt = pd.Timestamp.combine(current_date, time(2, 0)).tz_localize('US/Eastern')
        
        # Slice
        mask = (df.index >= start_dt) & (df.index <= end_dt)
        session_data = df.loc[mask]
        
        if not session_data.empty:
             high = session_data['High'].max()
             low = session_data['Low'].min()
             count = len(session_data)
             print(f"Date: {current_date} | Range Found: Yes | Records: {count} | High: {high:.5f} | Low: {low:.5f}")
        else:
             # Check if it's a weekend or missing data
             # print(f"Date: {current_date} | Range Found: No (Weekend/Missing)")
             pass

def main():
    parser = argparse.ArgumentParser(description='QLib Bridge for Data Fetching')
    parser.add_argument('--ticker', type=str, default='GBPUSD=X', help='Ticker symbol (default: GBPUSD=X)')
    parser.add_argument('--period', type=str, default='30d', help='Data period (default: 30d)')
    parser.add_argument('--sanity_check', action='store_true', help='Run sanity check logic')
    
    args = parser.parse_args()
    
    print(f"Fetching data for {args.ticker}...")
    df = fetch_historical_data(args.ticker, period=args.period)
    
    print(f"Data fetched: {len(df)} rows.")
    if not df.empty:
        print(f"Timezone: {df.index.tz}")
        print(f"First timestamp: {df.index[0]}")
        print(f"Last timestamp: {df.index[-1]}")
    
    if args.sanity_check:
        sanity_check_asian_range(df)

if __name__ == "__main__":
    main()
