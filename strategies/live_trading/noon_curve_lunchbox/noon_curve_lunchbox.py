import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time, timedelta
import pytz
from typing import Dict, List, Optional

class NoonCurveStrategy:
    """
    Noon Curve - "The Lunchbox Reclaim" for QQQ.
    Uses intermarket divergence (QQQ/SPY) to catch lunchtime reversals.
    Optimized for QQQ volatility profile.
    """
    def __init__(self, tickers: List[str] = ["QQQ", "SPY"]):
        self.tickers = tickers
        self.tz = pytz.timezone('US/Eastern')

    def fetch_data(self, period: str = "5d") -> Dict[str, pd.DataFrame]:
        """Fetch 5-minute data."""
        data = {}
        for ticker in self.tickers:
            df = yf.download(ticker, period=period, interval="5m", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert(self.tz)
            else:
                df.index = df.index.tz_convert(self.tz)
            
            # Removed random placeholder to prevent flicker
            if 'TICK' not in df.columns:
                df['TICK'] = 0 
            
            data[ticker] = df
        return data

    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        pv = tp * df['Volume']
        cum_pv = pv.groupby(df.index.date).cumsum()
        cum_v = df['Volume'].groupby(df.index.date).cumsum()
        return cum_pv / cum_v

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Dict]:
        if len(self.tickers) < 2: return []
        t1, t2 = self.tickers[0], self.tickers[1]
        if t1 not in data or t2 not in data: return []
        
        df_t1 = data[t1].copy()
        df_t2 = data[t2].copy()
        
        df_t1['vwap'] = self.calculate_vwap(df_t1)
        df_t2['vwap'] = self.calculate_vwap(df_t2)
        
        signals = []
        days = df_t1.groupby(df_t1.index.date)
        
        for date, t1_day in days:
            t2_day = df_t2[df_t2.index.date == date]
            if t1_day.empty or t2_day.empty: continue
            
            # Lunchbox Range: 12:00 - 12:30 PM
            t1_lunchbox = t1_day.between_time("12:00", "12:30")
            t2_lunchbox = t2_day.between_time("12:00", "12:30")
            if t1_lunchbox.empty or t2_lunchbox.empty: continue
            
            t1_l_high, t1_l_low = t1_lunchbox['High'].max(), t1_lunchbox['Low'].min()
            t2_l_high, t2_l_low = t2_lunchbox['High'].max(), t2_lunchbox['Low'].min()
            
            # Trigger Window: 12:30 - 13:30 PM
            trigger_window_t1 = t1_day.between_time("12:30", "13:30")
            trigger_window_t2 = t2_day.between_time("12:30", "13:30")
            
            for i in range(len(trigger_window_t1)):
                if i >= len(trigger_window_t2): break
                t1_candle = trigger_window_t1.iloc[i]
                t2_candle = trigger_window_t2.iloc[i]
                t = trigger_window_t1.index[i]
                
                # Short Attempt (Sweep High)
                hit_short = False
                if t1_candle['High'] > t1_l_high or t2_candle['High'] > t2_l_high:
                    div = False
                    if t2_candle['High'] > t2_l_high and t1_candle['High'] <= t1_l_high: div = True
                    elif t1_candle['High'] > t1_l_high and t2_candle['High'] <= t2_l_high: div = True
                    
                    if div:
                        lookhead = t1_day[t1_day.index >= t].head(3)
                        for _, next_t1 in lookhead.iterrows():
                            if next_t1['Close'] < t1_l_high:
                                if t1_candle['TICK'] < 500:
                                    hit_short = True
                                    break
                
                if hit_short:
                    signals.append({
                        'date': date,
                        'time': t,
                        'strategy': 'Noon Curve - Lunchbox',
                        'side': 'Short',
                        'ticker': t1,
                        'entry': t1_candle['Close'],
                        'sl': max(t1_candle['High'], t2_candle['High'] * (t1_l_high/t2_l_high)),
                        'tp': t1_candle['vwap'],
                        'reason': 'Intermarket Lunch Divergence'
                    })
                    break

                # Long Attempt (Sweep Low)
                hit_long = False
                if t1_candle['Low'] < t1_l_low or t2_candle['Low'] < t2_l_low:
                    div = False
                    if t2_candle['Low'] < t2_l_low and t1_candle['Low'] >= t1_l_low: div = True
                    elif t1_candle['Low'] < t1_l_low and t2_candle['Low'] >= t2_l_low: div = True
                    
                    if div:
                        lookhead = t1_day[t1_day.index >= t].head(3)
                        for _, next_t1 in lookhead.iterrows():
                            if next_t1['Close'] > t1_l_low:
                                if t1_candle['TICK'] > -500:
                                    hit_long = True
                                    break
                
                if hit_long:
                    signals.append({
                        'date': date,
                        'time': t,
                        'strategy': 'Noon Curve - Lunchbox',
                        'side': 'Long',
                        'ticker': t1,
                        'entry': t1_candle['Close'],
                        'sl': min(t1_candle['Low'], t2_candle['Low'] * (t1_l_low/t2_l_low)),
                        'tp': t1_candle['vwap'],
                        'reason': 'Intermarket Lunch Divergence'
                    })
                    break
                    
        return signals

if __name__ == "__main__":
    strat = NoonCurveStrategy()
    data = strat.fetch_data(period="1mo")
    sigs = strat.generate_signals(data)
    for s in sigs:
        print(s)
