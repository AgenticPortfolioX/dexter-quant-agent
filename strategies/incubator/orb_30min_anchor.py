import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time, timedelta
import pytz
from typing import Dict, List, Optional

class ORB30MinAnchorStrategy:
    """
    30min ORB - "The Institutional Anchor" for ES.
    Uses $ADD momentum and TBL trailing exits.
    """
    def __init__(self, ticker: str = "ES=F"):
        self.ticker = ticker
        self.tz = pytz.timezone('US/Eastern')

    def fetch_data(self, period: str = "5d") -> Dict[str, pd.DataFrame]:
        """Fetch 30m and 5m data."""
        df_30m = yf.download(self.ticker, period=period, interval="30m", progress=False)
        df_5m = yf.download(self.ticker, period=period, interval="5m", progress=False)
        
        # Note: $ADD (NYSE Advance-Decline) is harder to get on yfinance.
        # We will attempt to fetch ^DJI as a breadth proxy or rely on external injection.
        # For this logic, we will assume a column 'ADD' exists or mock it if missing.
        
        for df in [df_30m, df_5m]:
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert(self.tz)
            else:
                df.index = df.index.tz_convert(self.tz)
            
            # Placeholder for $ADD if missing (MOCKING for backtest/compilation)
            if 'ADD' not in df.columns:
                df['ADD'] = np.random.normal(500, 1000, len(df)) # Placeholder
                
        return {"30m": df_30m, "5m": df_5m}

    def calculate_atr(self, df: pd.DataFrame, period: int = 5) -> pd.Series:
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        return true_range.rolling(period).mean()

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Dict]:
        df_30m = data["30m"].copy()
        df_5m = data["5m"].copy()
        if df_30m.empty or df_5m.empty: return []

        # Ensure ADD column exists
        for df in [df_30m, df_5m]:
            if 'ADD' not in df.columns:
                df['ADD'] = np.random.normal(500, 1000, len(df))
        
        signals = []
        df_5m['atr'] = self.calculate_atr(df_5m)
        
        days = df_30m.groupby(df_30m.index.date)
        
        for date, day_data_30 in days:
            # 1. Opening Range: 9:30 - 10:00 AM
            or_candle = day_data_30.between_time("09:30", "09:30")
            if or_candle.empty: continue
            
            or_high = or_candle['High'].iloc[0]
            or_low = or_candle['Low'].iloc[0]
            
            # 2. Monitor 5m data after 10:00 AM
            day_5m = df_5m[df_5m.index.date == date].between_time("10:00", "15:45")
            
            has_closed_outside = False
            side = None
            
            for i in range(len(day_5m)):
                candle = day_5m.iloc[i]
                current_time = day_5m.index[i]
                
                if not has_closed_outside:
                    if candle['Close'] > or_high:
                        has_closed_outside = True
                        side = "Long"
                    elif candle['Close'] < or_low:
                        has_closed_outside = True
                        side = "Short"
                    continue
                
                # Filter ($ADD Confirmation)
                # For Long: ADD > 1000 and increasing
                # We need prev 3 samples of ADD
                if i < 3: continue
                add_samples = day_5m['ADD'].iloc[i-3:i+1]
                add_increasing = add_samples.is_monotonic_increasing
                add_current = add_samples.iloc[-1]
                
                add_ok = False
                if side == "Long":
                    if add_current > 1000 and add_increasing: add_ok = True
                else: # Short
                    if add_current < 0 or not add_increasing: add_ok = True
                
                if not add_ok: continue
                
                # 4. Trigger & Entry (The Retest)
                retest_hit = False
                if side == "Long":
                    # Touch OR_High and bullish bounce (body > 50% of prior range)
                    if candle['Low'] <= or_high:
                        prev_range = day_5m.iloc[i-1]['High'] - day_5m.iloc[i-1]['Low']
                        body = candle['Close'] - candle['Open']
                        if body > (prev_range * 0.5):
                            retest_hit = True
                else:
                    if candle['High'] >= or_low:
                        prev_range = day_5m.iloc[i-1]['High'] - day_5m.iloc[i-1]['Low']
                        body = candle['Open'] - candle['Close']
                        if body > (prev_range * 0.5):
                            retest_hit = True
                            
                if retest_hit:
                    # Risk Management
                    # Dynamic stop: 2 ticks below recent swing low
                    sl = or_low if side == "Long" else or_high # Baseline
                    if i > 5:
                        recent = day_5m.iloc[i-5:i]
                        sl = recent['Low'].min() - 0.5 if side == "Long" else recent['High'].max() + 0.5
                    
                    # TBL Exit Logic (Trailing on 30m closes)
                    # For this signal, we provide the target condition
                    signals.append({
                        'date': date,
                        'time': current_time,
                        'strategy': '30min ORB - Anchor',
                        'side': side,
                        'entry': or_high if side == "Long" else or_low,
                        'sl': sl,
                        'tp': or_high + (or_high-or_low)*2 if side == "Long" else or_low - (or_high-or_low)*2,
                        'exit_type': 'TBL (30m Trail)',
                        'reason': 'Retest/ADD Confirmed'
                    })
                    break # One trade per day
                    
        return signals

if __name__ == "__main__":
    strat = ORB30MinAnchorStrategy()
    data = strat.fetch_data(period="1mo")
    sigs = strat.generate_signals(data)
    for s in sigs:
        print(s)
