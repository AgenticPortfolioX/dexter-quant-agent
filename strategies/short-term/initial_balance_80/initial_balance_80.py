import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time, timedelta
import pytz
from typing import Dict, List, Optional

class InitialBalance80Strategy:
    """
    Initial Balance (IB) - "The 80% Rule" for SPY.
    Trades continuation of IB break with an 11:00 AM retrace entry.
    Optimized for SPY volatility and pricing.
    """
    def __init__(self, ticker: str = "SPY"):
        self.ticker = ticker
        self.tz = pytz.timezone('US/Eastern')
        # Ticker-specific tick size for retrace logic
        self.tick_size = 0.02 if ticker in ["SPY", "QQQ"] else 0.5

    def fetch_data(self, period: str = "20d") -> pd.DataFrame:
        """Fetch 5-minute data."""
        df = yf.download(self.ticker, period=period, interval="5m", progress=False)
        if df.empty: return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(self.tz)
        else:
            df.index = df.index.tz_convert(self.tz)
            
        return df

    def generate_signals(self, df: pd.DataFrame) -> List[Dict]:
        if df.empty: return []
        signals = []
        
        # 1. Calculate Historical IB Ranges
        days = [group for _, group in df.groupby(df.index.date)]
        if len(days) < 6: return []
        
        daily_ib_ranges = []
        for day in days:
            ib_range_data = day.between_time("09:30", "10:30")
            if not ib_range_data.empty:
                daily_ib_ranges.append(ib_range_data['High'].max() - ib_range_data['Low'].min())
            else:
                daily_ib_ranges.append(0)
        
        for i in range(5, len(days)):
            day_data = days[i]
            date = day_data.index[0].date()
            avg_ib_range = np.mean(daily_ib_ranges[i-5:i])
            
            ib_data = day_data.between_time("09:30", "10:30")
            if ib_data.empty: continue
            
            ib_high = ib_data['High'].max()
            ib_low = ib_data['Low'].min()
            ib_range = ib_high - ib_low
            
            if ib_range > avg_ib_range: continue
            
            post_ib = day_data.between_time("10:30", "15:50")
            breakout_side = None
            breakout_time = None
            
            for t, row in post_ib.iterrows():
                if row['Close'] > ib_high:
                    breakout_side = "Long"
                    breakout_time = t
                    break
                elif row['Close'] < ib_low:
                    breakout_side = "Short"
                    breakout_time = t
                    break
            
            if not breakout_side: continue
            
            retrace_window = day_data.between_time("10:45", "11:15")
            retrace_window = retrace_window[retrace_window.index > breakout_time]
            
            for entry_time, row in retrace_window.iterrows():
                hit = False
                if breakout_side == "Long":
                    if row['Low'] <= ib_high + (self.tick_size * 2):
                        hit = True
                else:
                    if row['High'] >= ib_low - (self.tick_size * 2):
                        hit = True
                
                if hit:
                    sl_dist = ib_range * 0.25
                    signals.append({
                        'date': date,
                        'time': entry_time,
                        'strategy': 'Initial Balance - 80%',
                        'side': breakout_side,
                        'ticker': self.ticker,
                        'entry': row['Close'],
                        'sl': (ib_high - sl_dist) if breakout_side == "Long" else (ib_low + sl_dist),
                        'tp_1': (ib_high + sl_dist) if breakout_side == "Long" else (ib_low - sl_dist),
                        'tp_2': 'Trailing',
                        'reason': 'IB Retrace'
                    })
                    break
                    
        return signals

if __name__ == "__main__":
    strat = InitialBalance80Strategy()
    data = strat.fetch_data(period="1mo")
    sigs = strat.generate_signals(data)
    for s in sigs:
        print(s)
