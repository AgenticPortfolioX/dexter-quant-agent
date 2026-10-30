import pandas as pd
import numpy as np

class MACD200BounceStrategy:
    """
    MACD + 200 SMA + Support/Resistance Bounce Strategy.
    As derived from the 2nd YouTube Strategy breakdown (86% Win Rate claim).
    
    This system requires:
    1. Trend Identification: 200 SMA acts as the ultimate bias (above = long, below = short)
                             and as the hard stop-loss wall.
    2. Price Action: Price must be bouncing off a recent Support/Resistance key level.
    3. Momentum Trigger: MACD Line must cross the Signal Line while on the OPPOSITE side
                         of the Zero Line (crosses up while below 0 for longs).
    4. Risk Management: Fixed 1:1.5 Risk-to-Reward Ratio.
    """
    
    def __init__(self, fast_ema=12, slow_ema=26, signal_ema=9, sma_period=200, key_level_lookback=20, bounce_thresh=0.005):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.signal_ema = signal_ema
        self.sma_period = sma_period
        
        # Used to identify recent "bounce" zones dynamically
        self.key_level_lookback = key_level_lookback
        # How close price needs to be to the key level to be considered a "bounce" (0.5%)
        self.bounce_thresh = bounce_thresh

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the 200 SMA, MACD (12, 26, 9), and dynamic Support/Resistance levels.
        """
        if 'Close' not in df.columns:
            raise ValueError("DataFrame must contain 'Close' price column.")
            
        df = df.copy()
        
        # 1. 200 SMA (Trend Filter & Stop Loss Wall)
        df['SMA_200'] = df['Close'].rolling(window=self.sma_period).mean()
        
        # 2. MACD Indicators
        df['EMA_Fast'] = df['Close'].ewm(span=self.fast_ema, adjust=False).mean()
        df['EMA_Slow'] = df['Close'].ewm(span=self.slow_ema, adjust=False).mean()
        df['MACD_Line'] = df['EMA_Fast'] - df['EMA_Slow']
        df['Signal_Line'] = df['MACD_Line'].ewm(span=self.signal_ema, adjust=False).mean()
        
        # 3. Dynamic Support & Resistance levels (Rolling Min/Max)
        df['Support_Level'] = df['Low'].rolling(window=self.key_level_lookback).min().shift(1)
        df['Resistance_Level'] = df['High'].rolling(window=self.key_level_lookback).max().shift(1)
        
        return df

    def generate_signals(self, df: pd.DataFrame) -> list:
        """
        Generates buy/sell signals on price bouncing off support/resistance 
        with MACD confirming the momentum shift along the 200 SMA trend.
        Return list of actionable signal dictionaries.
        """
        df = self.calculate_indicators(df)
        signals = []
        
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            ts = df.index[i]
            
            # Require 200 SMA to be populated
            if pd.isna(row['SMA_200']):
                continue
                
            close = row['Close']
            sma200 = row['SMA_200']
            
            # --- MACD Crossover Logic ---
            # Bullish Cross: MACD Line crosses ABOVE Signal Line
            bullish_cross = (prev['MACD_Line'] <= prev['Signal_Line']) and (row['MACD_Line'] > row['Signal_Line'])
            # Both lines MUST be BELOW the Zero Line for a valid long entry bounce
            macd_below_zero = (row['MACD_Line'] < 0) and (row['Signal_Line'] < 0)
            
            # Bearish Cross: MACD Line crosses BELOW Signal Line
            bearish_cross = (prev['MACD_Line'] >= prev['Signal_Line']) and (row['MACD_Line'] < row['Signal_Line'])
            # Both lines MUST be ABOVE the Zero Line for a valid short entry bounce
            macd_above_zero = (row['MACD_Line'] > 0) and (row['Signal_Line'] > 0)
            
            # --- Price Action Bounce Logic ---
            # Is price currently near the recent support floor? (Longs)
            near_support = False
            if pd.notna(row['Support_Level']):
                dist_to_support = abs(close - row['Support_Level']) / close
                near_support = dist_to_support <= self.bounce_thresh
                
            # Is price currently near the recent resistance ceiling? (Shorts)
            near_res = False
            if pd.notna(row['Resistance_Level']):
                dist_to_res = abs(row['Resistance_Level'] - close) / close
                near_res = dist_to_res <= self.bounce_thresh

            # --- LONG SIGNAL EVALUATION ---
            # 1. Price > 200 SMA (Uptrend)
            # 2. Near Support (Bounce)
            # 3. MACD crosses up while below zero
            if (close > sma200) and near_support and bullish_cross and macd_below_zero:
                entry_price = close
                # Stop Loss directly below the 200 SMA Wall
                stop_loss = sma200 - (sma200 * 0.001) 
                
                # Failsafe if 200 SMA is incredibly close/identical to entry
                risk_amt = entry_price - stop_loss
                if risk_amt <= 0: risk_amt = entry_price * 0.002
                
                # Take profit at 1.5 Risk/Reward Ratio per video instructions
                take_profit = entry_price + (risk_amt * 1.5)
                
                signals.append({
                    'timestamp': ts,
                    'type': 'LONG_ENTRY',
                    'entry': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'rr_ratio': 1.5,
                    'model': 'MACD + 200 SMA Bounce (Bullish)'
                })
                
            # --- SHORT SIGNAL EVALUATION ---
            # 1. Price < 200 SMA (Downtrend)
            # 2. Near Resistance (Bounce)
            # 3. MACD crosses down while above zero
            elif (close < sma200) and near_res and bearish_cross and macd_above_zero:
                entry_price = close
                # Stop Loss directly above the 200 SMA Wall
                stop_loss = sma200 + (sma200 * 0.001)
                
                risk_amt = stop_loss - entry_price
                if risk_amt <= 0: risk_amt = entry_price * 0.002
                
                # Take profit at 1.5 Risk/Reward Ratio
                take_profit = entry_price - (risk_amt * 1.5)
                
                signals.append({
                    'timestamp': ts,
                    'type': 'SHORT_ENTRY',
                    'entry': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'rr_ratio': 1.5,
                    'model': 'MACD + 200 SMA Bounce (Bearish)'
                })
                
        return signals

if __name__ == "__main__":
    print("Strategy Class Available: MACD200BounceStrategy")
    print("Primary Indicators: MACD (12,26,9), 200 SMA, Price Action Extrema")
    print("Fixed Risk/Reward: 1.5RR")
