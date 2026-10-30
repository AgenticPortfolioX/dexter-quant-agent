"""
LittleD Strategy (SFP / High Conviction) - Live Edition
-------------------------------------------
Classification: LIVE STRATEGY
Assigned Assets: IBIT, ETHE, CLNK
Architecture: Swing Failure Pattern (SFP) + Volume Spike
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time, timedelta
import pytz
import os
import sys
from typing import Dict, List, Optional

class LittleDStrategy:
    def __init__(self, symbol: str = "IBIT"):
        self.symbol = symbol
        self.tz = pytz.timezone('US/Eastern')
        
    def fetch_h1_data(self, period: str = "30d") -> pd.DataFrame:
        df = yf.download(self.symbol, period=period, interval="1h", progress=False)
        if df.empty: return df
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df

    def find_clean_swing_points(self, df: pd.DataFrame, X: int = 5, Y: int = 10) -> List[Dict]:
        highs = df['High']
        lows = df['Low']
        roll_high = highs.rolling(window=2*X+1, center=True).max()
        roll_low = lows.rolling(window=2*X+1, center=True).min()
        is_swing_high = (highs == roll_high)
        is_swing_low = (lows == roll_low)
        
        clean_levels = []
        high_indices = np.where(is_swing_high)[0]
        low_indices = np.where(is_swing_low)[0]
        
        for idx in high_indices:
            if idx < X or idx > len(df) - Y - 1: continue
            price = highs.iloc[idx]
            if highs.iloc[idx+1 : idx+Y+1].max() < price:
                clean_levels.append({'timestamp': df.index[idx], 'price': price, 'type': 'High'})
                
        for idx in low_indices:
            if idx < X or idx > len(df) - Y - 1: continue
            price = lows.iloc[idx]
            if lows.iloc[idx+1 : idx+Y+1].min() > price:
                clean_levels.append({'timestamp': df.index[idx], 'price': price, 'type': 'Low'})
        return clean_levels

    def scan(self, df: Optional[pd.DataFrame] = None, vol_threshold: float = 1.5) -> Optional[Dict]:
        """Main execution entry for Dexter Autotrader."""
        df = df if df is not None else self.fetch_h1_data()
        if df is None or df.empty: return None
        
        levels = self.find_clean_swing_points(df)
        if not levels: return None
        
        # --- 2x Leveraged & Inverse Mapping Config ---
        # 2x Long: BITU (ProShares Ultra Bitcoin ETF)
        # 2x Short: SBIT (ProShares UltraShort Bitcoin ETF)
        LONG_MAP = {"IBIT": "BITU", "BITU": "BITU", "BTC-USD": "BITU", "BTC": "BITU"}
        SHORT_MAP = {"IBIT": "SBIT", "BITU": "SBIT", "BTC-USD": "SBIT", "BTC": "SBIT", "ETHE": "SETH"}
        
        # Check the most recent candle for SFP
        curr = df.iloc[-1]
        prev_close = df.iloc[-2]['Close']
        vol_ma = df['Volume'].rolling(window=20).mean().iloc[-1]
        
        body = abs(curr['Open'] - curr['Close'])
        upper_wick = curr['High'] - max(curr['Open'], curr['Close'])
        lower_wick = min(curr['Open'], curr['Close']) - curr['Low']
        
        for level in levels:
            lvl_price = level['price']
            # Only consider levels from reasonably far back (not the current candle)
            if level['timestamp'] >= df.index[-2]: continue 
            
            # Short SFP: Sweep High, Close below -> Trade 2x Short (SBIT)
            if curr['High'] > lvl_price and curr['Close'] < lvl_price:
                if curr['Volume'] > (vol_ma * vol_threshold):
                    if upper_wick >= (max(body, 0.0001) * 2):
                        
                        final_symbol = self.symbol
                        final_direction = 'SELL'
                        if self.symbol in SHORT_MAP:
                            final_symbol = SHORT_MAP[self.symbol]
                            final_direction = 'BUY'
                            print(f"  [LittleD] Bearish SFP on {self.symbol} -> Trading 2x SHORT via {final_symbol}")

                        return {
                            'strategy': 'LittleD',
                            'symbol': final_symbol,
                            'direction': final_direction,
                            'entry': curr['Close'],
                            'sl': curr['High'] + (curr['High'] * 0.001),
                            'tp': lvl_price - (abs(curr['Close'] - lvl_price) * 1.5),
                            'timestamp': str(df.index[-1])
                        }
            
            # Long SFP: Sweep Low, Close above -> Trade 2x Long (BITU)
            if curr['Low'] < lvl_price and curr['Close'] > lvl_price:
                if curr['Volume'] > (vol_ma * vol_threshold):
                    if lower_wick >= (max(body, 0.0001) * 2):
                        final_symbol = self.symbol
                        if self.symbol in LONG_MAP:
                            final_symbol = LONG_MAP[self.symbol]
                            print(f"  [LittleD] Bullish SFP on {self.symbol} -> Trading 2x LONG on {final_symbol}")
                        return {
                            'strategy': 'LittleD',
                            'symbol': final_symbol,
                            'direction': 'BUY',
                            'entry': curr['Close'],
                            'sl': curr['Low'] - (curr['Low'] * 0.001),
                            'tp': lvl_price + (abs(curr['Close'] - lvl_price) * 1.5),
                            'timestamp': str(df.index[-1])
                        }
        return None

if __name__ == "__main__":
    import json
    for symbol in ["BITU", "IBIT", "ETHE", "CLNK"]:
        strat = LittleDStrategy(symbol)
        signal = strat.scan()
        if signal:
            print(json.dumps(signal, indent=2))
        else:
            print(f"No signal for {symbol}")
