import pandas as pd
import numpy as np

class MACDRefinedFrequency:
    """
    Relaxed MACD Bounce Strategy.
    Focus: Increase trigger frequency by loosening constraints and adding 50 EMA.
    """
    def __init__(self, fast_ema=12, slow_ema=26, signal_ema=9, sma_period=200, intermediate_ema=50, key_level_lookback=30, bounce_thresh=0.015):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.signal_ema = signal_ema
        self.sma_period = sma_period
        self.intermediate_ema = intermediate_ema
        self.key_level_lookback = key_level_lookback
        self.bounce_thresh = bounce_thresh

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # 1. EMAs & SMAs
        df['SMA_200'] = df['Close'].rolling(window=self.sma_period).mean()
        df['EMA_50'] = df['Close'].ewm(span=self.intermediate_ema, adjust=False).mean()
        
        # 2. MACD
        df['EMA_Fast'] = df['Close'].ewm(span=self.fast_ema, adjust=False).mean()
        df['EMA_Slow'] = df['Close'].ewm(span=self.slow_ema, adjust=False).mean()
        df['MACD_Line'] = df['EMA_Fast'] - df['EMA_Slow']
        df['Signal_Line'] = df['MACD_Line'].ewm(span=self.signal_ema, adjust=False).mean()
        df['Histogram'] = df['MACD_Line'] - df['Signal_Line']
        
        # 3. Dynamic Levels (Increased lookback for more targets)
        df['Support_Level'] = df['Low'].rolling(window=self.key_level_lookback).min().shift(1)
        df['Resistance_Level'] = df['High'].rolling(window=self.key_level_lookback).max().shift(1)
        
        return df

    def generate_signals(self, df: pd.DataFrame) -> list:
        df = self.calculate_indicators(df)
        signals = []
        
        # ONLY process closed candles to prevent flicker-spamming
        for i in range(1, len(df) - 1): 
            row = df.iloc[i]
            prev = df.iloc[i-1]
            ts = df.index[i]
            
            if pd.isna(row['SMA_200']): continue
                
            close = row['Close']
            sma200 = row['SMA_200']
            ema50 = row['EMA_50']
            
            # --- RELAXED MACD Crossover ---
            # Bullish Cross
            bullish_cross = (prev['MACD_Line'] <= prev['Signal_Line']) and (row['MACD_Line'] > row['Signal_Line'])
            # Relaxed: Allow cross below zero OR "Histogram Flip" (Zero Line Rejection)
            valid_bullish_macd = (row['MACD_Line'] < 0) or (prev['Histogram'] < 0 and row['Histogram'] > 0)
            
            # Bearish Cross
            bearish_cross = (prev['MACD_Line'] >= prev['Signal_Line']) and (row['MACD_Line'] < row['Signal_Line'])
            valid_bearish_macd = (row['MACD_Line'] > 0) or (prev['Histogram'] > 0 and row['Histogram'] < 0)
            
            # --- RELAXED Price Action Bounce ---
            # Distance to Support OR EMA 50 OR SMA 200
            dist_to_sup = abs(close - row['Support_Level']) / close if pd.notna(row['Support_Level']) else 1.0
            dist_to_ema50 = abs(close - ema50) / close
            
            near_support = (dist_to_sup <= self.bounce_thresh) or (dist_to_ema50 <= (self.bounce_thresh * 0.5))
                
            dist_to_res = abs(row['Resistance_Level'] - close) / close if pd.notna(row['Resistance_Level']) else 1.0
            near_res = (dist_to_res <= self.bounce_thresh) or (dist_to_ema50 <= (self.bounce_thresh * 0.5))

            # --- LONG ---
            if (close > sma200) and near_support and bullish_cross and valid_bullish_macd:
                stop_loss = min(row['Support_Level'], sma200, ema50) * 0.998
                risk = close - stop_loss
                if risk <= 0: risk = close * 0.005
                signals.append({
                    'timestamp': ts, 'type': 'LONG_ENTRY', 'entry': close,
                    'stop_loss': stop_loss, 'take_profit': close + (risk * 2.0), # Increased RR to 2.0
                    'model': 'Refined MACD Flush'
                })
                
            # --- SHORT ---
            elif (close < sma200) and near_res and bearish_cross and valid_bearish_macd:
                stop_loss = max(row['Resistance_Level'], sma200, ema50) * 1.002
                risk = stop_loss - close
                if risk <= 0: risk = close * 0.005
                signals.append({
                    'timestamp': ts, 'type': 'SHORT_ENTRY', 'entry': close,
                    'stop_loss': stop_loss, 'take_profit': close - (risk * 2.0),
                    'model': 'Refined MACD Flush'
                })
                
        return signals
