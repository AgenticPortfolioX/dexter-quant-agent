import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time, timedelta
import pytz
from typing import Dict, List, Optional

class LondonDisplacementStrategy:
    """
    London Displacement Strategy: Captures the 'Stop Run' and reversal during the London open.
    Target: NQ
    """
    def __init__(self, ticker: str = "NQ=F"):
        self.ticker = ticker
        self.tz = pytz.timezone('US/Eastern')

    def fetch_data(self, period: str = "5d") -> pd.DataFrame:
        """Fetch 5-minute data for NQ."""
        df = yf.download(self.ticker, period=period, interval="5m", progress=False)
        if df.empty: return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # Ensure index is Eastern Time
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(self.tz)
        else:
            df.index = df.index.tz_convert(self.tz)
            
        return df

    def generate_signals(self, df: pd.DataFrame) -> List[Dict]:
        """
        Generates trading signals based on London Displacement logic.
        """
        signals = []
        df = df.copy()
        
        # Group by day to process each trading day independently
        days = df.groupby(df.index.date)
        
        for date, day_data in days:
            if len(day_data) < 20: continue # Skip partial days
            
            # Identify the consolidation range from 5:00 AM to 6:00 AM ET.
            anchor_range = day_data.between_time("05:00", "06:00")
            if anchor_range.empty: continue
            
            range_high = anchor_range['High'].max()
            range_low = anchor_range['Low'].min()
            
            # Tick size awareness
            if "USD=X" in self.ticker or "/" in self.ticker:
                tick_threshold = 0.0001 # 1 pip for FX
            elif "=F" in self.ticker:
                tick_threshold = 0.25 # 1 tick for most futures
            else:
                tick_threshold = 0.01

            # 2. Trigger Window: 6:15 AM to 7:15 AM ET
            trigger_window = day_data.between_time("06:15", "07:15")
            if trigger_window.empty: continue
            
            # Average body size for displacement filter (last 5 candles before sweep window)
            # We need to find the index of the trigger window start
            try:
                window_start_idx = day_data.index.get_loc(trigger_window.index[0])
                if isinstance(window_start_idx, slice): window_start_idx = window_start_idx.start
            except: continue
            
            if window_start_idx < 5: continue
            
            prev_5_candles = day_data.iloc[window_start_idx-5:window_start_idx]
            avg_body_size = abs(prev_5_candles['Open'] - prev_5_candles['Close']).mean()
            
            # Monitor for a "Stop Run"
            sweep_occured = False
            sweep_type = None # 'UP' or 'DOWN'
            sweep_candle_idx = None
            
            for i in range(len(trigger_window)):
                candle = trigger_window.iloc[i]
                current_time = trigger_window.index[i]
                
                # Check for Sweep
                # Upward sweep (sweeping buy stops)
                if not sweep_occured and candle['High'] > (range_high + tick_threshold):
                    # Check if it closes back inside within 2 candles (including this one or next)
                    # For simplicity, we check this candle and the next 2.
                    lookahead = day_data.iloc[day_data.index.get_loc(current_time) : day_data.index.get_loc(current_time) + 3]
                    
                    for j in range(len(lookahead)):
                        reclaim_candle = lookahead.iloc[j]
                        if reclaim_candle['Close'] < range_high:
                            # 3. Displacement Filter
                            body_size = abs(reclaim_candle['Open'] - reclaim_candle['Close'])
                            if body_size >= (avg_body_size * 1.5):
                                sweep_occured = True
                                sweep_type = 'UP'
                                sweep_candle_idx = i
                                reclaim_candle_time = lookahead.index[j]
                                sweep_candle = candle
                                break
                    
                # Downward sweep (sweeping sell stops)
                elif not sweep_occured and candle['Low'] < (range_low - tick_threshold):
                    lookahead = day_data.iloc[day_data.index.get_loc(current_time) : day_data.index.get_loc(current_time) + 3]
                    
                    for j in range(len(lookahead)):
                        reclaim_candle = lookahead.iloc[j]
                        if reclaim_candle['Close'] > range_low:
                            body_size = abs(reclaim_candle['Open'] - reclaim_candle['Close'])
                            if body_size >= (avg_body_size * 1.5):
                                sweep_occured = True
                                sweep_type = 'DOWN'
                                sweep_candle_idx = i
                                reclaim_candle_time = lookahead.index[j]
                                sweep_candle = candle
                                break
                
                if sweep_occured:
                    # 4. Entry Logic (Market Structure Shift)
                    # Wait for next 5-min candle to break high/low of Sweep Candle
                    next_candles = day_data[day_data.index > reclaim_candle_time].head(5)
                    entry_found = False
                    
                    for entry_idx, entry_candle in next_candles.iterrows():
                        if sweep_type == 'UP': # Look for Short
                            if entry_candle['Low'] < sweep_candle['Low']:
                                signals.append({
                                    'date': date,
                                    'time': entry_idx,
                                    'strategy': 'London Displacement',
                                    'side': 'Short',
                                    'entry': sweep_candle['Low'],
                                    'sl': sweep_candle['High'] + 1.25, # 5 ticks
                                    'tp': range_low,
                                    'reason': 'London Swipe Reclaim'
                                })
                                entry_found = True
                                break
                        else: # Look for Long
                            if entry_candle['High'] > sweep_candle['High']:
                                signals.append({
                                    'date': date,
                                    'time': entry_idx,
                                    'strategy': 'London Displacement',
                                    'side': 'Long',
                                    'entry': sweep_candle['High'],
                                    'sl': sweep_candle['Low'] - 1.25,
                                    'tp': range_high,
                                    'reason': 'London Swipe Reclaim'
                                })
                                entry_found = True
                                break
                    if entry_found: break # Only one LD trade per day
            
        return signals

if __name__ == "__main__":
    strat = LondonDisplacementStrategy()
    data = strat.fetch_data(period="1mo")
    sigs = strat.generate_signals(data)
    for s in sigs:
        print(s)
