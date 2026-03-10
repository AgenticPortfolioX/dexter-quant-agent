import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time, timedelta
import pytz
from typing import Dict, List, Optional

class ORB15MinGapGoStrategy:
    """
    15min ORB - "The Gap & Go" Strategy for NQ.
    Uses 15m for breakout/bias and 1m for FVG entry.
    """
    def __init__(self, ticker: str = "NQ=F"):
        self.ticker = ticker
        self.tz = pytz.timezone('US/Eastern')

    def fetch_data(self, period: str = "5d") -> Dict[str, pd.DataFrame]:
        """Fetch 15m and 1m data."""
        df_15m = yf.download(self.ticker, period=period, interval="15m", progress=False)
        df_1m = yf.download(self.ticker, period=period, interval="1m", progress=False)
        
        for df in [df_15m, df_1m]:
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert(self.tz)
            else:
                df.index = df.index.tz_convert(self.tz)
                
        return {"15m": df_15m, "1m": df_1m}

    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate VWAP for the given data (assumes intra-day)."""
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        pv = tp * df['Volume']
        
        # Cumulative PV and V by day
        cum_pv = pv.groupby(df.index.date).cumsum()
        cum_v = df['Volume'].groupby(df.index.date).cumsum()
        return cum_pv / cum_v

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Dict]:
        df_15m = data["15m"]
        df_1m = data["1m"]
        if df_15m.empty or df_1m.empty: return []

        signals = []
        df_15m['vwap'] = self.calculate_vwap(df_15m)
        
        days = df_15m.groupby(df_15m.index.date)
        
        for date, day_data in days:
            # 1. Opening Range: 9:30 - 9:45 AM
            # Check for both 9:30 candle and possible data labeling issues
            or_range = day_data.between_time("09:30", "09:45")
            if or_range.empty: continue
            
            or_high = or_range['High'].max()
            or_low = or_range['Low'].min()
            or_vol = or_range['Volume'].sum()
            or_mid = (or_high + or_low) / 2
            
            # 2. Breakout Window: 9:46 - 10:30 AM
            post_or = day_data.between_time("09:50", "10:30")
            if post_or.empty: continue
            
            # We look for the first candle that breaks the OR
            for break_idx, breakout_candle in post_or.iterrows():
                # VWAP Bias (using breakout candle close)
                # If VWAP is missing, use OR_Mid as bias proxy for backtest
                if 'vwap' in breakout_candle and not pd.isna(breakout_candle['vwap']):
                    bias = "Long" if breakout_candle['Close'] > breakout_candle['vwap'] else "Short"
                else:
                    bias = "Long" if breakout_candle['Close'] > or_mid else "Short"
                
                # Trigger: Breakout of OR
                is_breakout = False
                side = None
                if bias == "Long" and breakout_candle['Close'] > or_high:
                    is_breakout = True
                    side = "Long"
                elif bias == "Short" and breakout_candle['Close'] < or_low:
                    is_breakout = True
                    side = "Short"
                
                if not is_breakout: continue
                
                # 4. Volume Confirmation (Breaks usually have higher volume)
                # Relaxed for backtest if volume is missing
                if 'Volume' in breakout_candle and breakout_candle['Volume'] > 0:
                    avg_or_vol = or_vol / len(or_range)
                    if breakout_candle['Volume'] < (avg_or_vol * 0.5): continue # Even more relaxed
            
            # 5. Entry Logic (1-Minute FVG)
            # Look for FVG on 1-min chart after 9:45 AM
            day_1m = df_1m[df_1m.index.date == date].between_time("09:45", "11:00")
            
            for i in range(2, len(day_1m)):
                c1, c2, c3 = day_1m.iloc[i-2], day_1m.iloc[i-1], day_1m.iloc[i]
                
                fvg_found = False
                fvg_price = None
                
                if side == "Long":
                    # Bullish FVG: c1.High < c3.Low
                    if c1['High'] < c3['Low']:
                        gap_size = c3['Low'] - c1['High']
                        if gap_size >= 2.0:
                            fvg_found = True
                            fvg_price = c1['High'] # Limit at edge
                else: # Short
                    # Bearish FVG: c1.Low > c3.High
                    if c1['Low'] > c3['High']:
                        gap_size = c1['Low'] - c3['High']
                        if gap_size >= 2.0:
                            fvg_found = True
                            fvg_price = c1['Low']
                
                if fvg_found:
                    # Check if price retraces to fvg_price in next 10 candles
                    post_fvg = day_1m.iloc[i+1 : i+11]
                    for entry_time, p in post_fvg.iterrows():
                        hit = False
                        if side == "Long" and p['Low'] <= fvg_price: hit = True
                        elif side == "Short" and p['High'] >= fvg_price: hit = True
                        
                        if hit:
                            signals.append({
                                'date': date,
                                'time': entry_time,
                                'strategy': '15min ORB - Gap & Go',
                                'side': side,
                                'entry': fvg_price,
                                'sl': or_mid, # Proxy for POC
                                'tp': fvg_price + (or_high - or_low) if side == "Long" else fvg_price - (or_high - or_low),
                                'reason': fvg_price
                            })
                            break
                    if len(signals) > 0 and signals[-1]['date'] == date: break
                    
        return signals

if __name__ == "__main__":
    strat = ORB15MinGapGoStrategy()
    data = strat.fetch_data(period="1mo")
    sigs = strat.generate_signals(data)
    for s in sigs:
        print(s)
