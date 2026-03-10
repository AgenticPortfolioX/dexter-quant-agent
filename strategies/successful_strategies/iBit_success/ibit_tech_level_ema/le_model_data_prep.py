
import yfinance as yf
import pandas as pd
from datetime import timedelta

def fetch_multi_timeframe_data(ticker, period="60d"):
    """
    Fetches 1h and 10m data for a ticker with buffering shifted 1h data.
    """
    try:
        # 1. Fetch Data
        print(f"Fetching {ticker} data (10m & 1h)...")
        
        # 10m data (Primary)
        df_10m = yf.download(ticker, period=period, interval="5m", progress=False, auto_adjust=True)
        
        if df_10m.empty:
            raise ValueError(f"No 5m data found for {ticker}")
            
        # Resampling 5m -> 10m
        # yf returns MultiIndex columns sometimes (Ticker, OHLCV). Flatten if needed.
        if isinstance(df_10m.columns, pd.MultiIndex):
            df_10m.columns = df_10m.columns.get_level_values(0)
            
        agg_dict = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }
        # Resample logic
        df_10m = df_10m.resample('10min').agg(agg_dict).dropna()
        
        # 1h data (Anchor)
        df_1h = yf.download(ticker, period=period, interval="1h", progress=False, auto_adjust=True)
        
        if df_1h.empty:
            raise ValueError(f"No 1h data found for {ticker}")

        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = df_1h.columns.get_level_values(0)

        # 2. Process Index (Timezone)
        # Check if tz-aware. If NO, localize to UTC first (yf default).
        if df_10m.index.tz is None:
            df_10m = df_10m.tz_localize('UTC')
        else:
            df_10m = df_10m.tz_convert('UTC')
            
        if df_1h.index.tz is None:
            df_1h = df_1h.tz_localize('UTC')
        else:
            df_1h = df_1h.tz_convert('UTC')
            
        # Convert to US/Eastern
        df_10m = df_10m.tz_convert('US/Eastern')
        df_1h = df_1h.tz_convert('US/Eastern')
        
        # 3. Handle 1h Shift (The "Buffer")
        # We want the 1h data available at 10:00 to be the data from 09:00-10:00.
        # So we shift the 1h data forward by 1 hour (or 1 row if index is hourly)
        # This prevents lookahead bias. We only know the 9-10am candle contents AFTER 10am.
        
        df_1h_shifted = df_1h.shift(1)
        
        return {
            'data_10m': df_10m,
            'data_1h': df_1h_shifted
        }

    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None
