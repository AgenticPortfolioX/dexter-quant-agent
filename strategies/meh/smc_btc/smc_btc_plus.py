
import pandas as pd
import numpy as np
import os

class SmartMoneyStrategy:
    def __init__(self, atr_period=20, displacement_mult=1.5):
        self.atr_period = atr_period
        self.displacement_mult = displacement_mult

    def add_indicators(self, df_5m):
        df = df_5m.copy()
        
        # --- ATR Calculation ---
        high = df['High']
        low = df['Low']
        close = df['Close']
        prev_close = close.shift(1)
        
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        
        df['ATR'] = tr.rolling(window=self.atr_period).mean()
        
        # --- Step 3: Displacement ---
        df['is_displacement'] = (df['High'] - df['Low']) > (self.displacement_mult * df['ATR'])
        
        # --- Step 2: Swing Points (Confirmed at i+2) ---
        df['swing_high'] = np.nan
        df['swing_low'] = np.nan
        
        # Vectorized candidate checking (i is peak)
        # High[i] > High[i-1] High [i-2] High[i+1] High[i+2]
        is_swing_high_candidate = (
            (df['High'] > df['High'].shift(1)) & 
            (df['High'] > df['High'].shift(2)) & 
            (df['High'] > df['High'].shift(-1)) & 
            (df['High'] > df['High'].shift(-2))
        )
        
        is_swing_low_candidate = (
            (df['Low'] < df['Low'].shift(1)) & 
            (df['Low'] < df['Low'].shift(2)) & 
            (df['Low'] < df['Low'].shift(-1)) & 
            (df['Low'] < df['Low'].shift(-2))
        )
        
        # CONFIRMATION at i+2:
        # We assign the value of df['High'].iloc[i] TO df['swing_high'].iloc[i+2]
        # To do this safely/vectorized, we shift the boolean mask +2
        df.loc[is_swing_high_candidate.shift(2).fillna(False), 'swing_high'] = df['High'].shift(2)
        df.loc[is_swing_low_candidate.shift(2).fillna(False), 'swing_low'] = df['Low'].shift(2)
        
        return df

    def process_logic(self, df):
        # Step 4, 5, 6 combined for flow
        df = self.detect_mss_fvg(df)
        
        df['entry_signal'] = ""
        
        # Track setups
        setup = None # To store active displacement + FVG context
        
        for i in range(10, len(df)):
            row = df.iloc[i]
            
            # --- Capture Displacement Setup ---
            if row['is_displacement']:
                # Find most recent confirmed swing points BEFORE this candle
                prev_sw_highs = df.iloc[:i]['swing_high'].dropna()
                prev_sw_lows = df.iloc[:i]['swing_low'].dropna()
                
                if not prev_sw_highs.empty or not prev_sw_lows.empty:
                    setup = {
                        'idx': i,
                        'bull_fvg_top': row['bullish_fvg_top'],
                        'bear_fvg_bot': row['bearish_fvg_bottom'],
                        'prev_sw_high': prev_sw_highs.iloc[-1] if not prev_sw_highs.empty else None,
                        'prev_sw_low': prev_sw_lows.iloc[-1] if not prev_sw_lows.empty else None,
                        'mss_found': False,
                        'entry_triggered': False
                    }
            
            # --- Check MSS within 10 candles of setup ---
            if setup and not setup['mss_found']:
                if (i - setup['idx']) <= 10:
                    # Bullish MSS: Close > setup swing high
                    if not np.isnan(setup['bull_fvg_top']) and setup['prev_sw_high']:
                        if row['Close'] > setup['prev_sw_high']:
                            setup['mss_found'] = True
                            df.at[df.index[i], 'mss_signal'] = "Bullish MSS"
                    # Bearish MSS: Close < setup swing low
                    elif not np.isnan(setup['bear_fvg_bot']) and setup['prev_sw_low']:
                        if row['Close'] < setup['prev_sw_low']:
                            setup['mss_found'] = True
                            df.at[df.index[i], 'mss_signal'] = "Bearish MSS"
                else:
                    setup = None # Window expired
            
            # --- Check Entry Signal (Retrace) ---
            if setup and setup['mss_found'] and not setup['entry_triggered']:
                # Bullish Retrace
                if not np.isnan(setup['bull_fvg_top']):
                    if row['Low'] <= setup['bull_fvg_top']:
                        df.at[df.index[i], 'entry_signal'] = "BUY"
                        setup['entry_triggered'] = True
                # Bearish Retrace
                elif not np.isnan(setup['bear_fvg_bot']):
                    if row['High'] >= setup['bear_fvg_bot']:
                        df.at[df.index[i], 'entry_signal'] = "SELL"
                        setup['entry_triggered'] = True
                        
        return df

    def detect_mss_fvg(self, df):
        # Step 5: FVG Detection at Displacement i
        df['mss_signal'] = ""
        df['bullish_fvg_top'] = np.nan
        df['bearish_fvg_bottom'] = np.nan
        
        # We need check forward i+1 for FVG, so loop to len-1
        for i in range(1, len(df)-1):
            if df.iloc[i]['is_displacement']:
                # Bullish FVG
                if df.iloc[i+1]['Low'] > df.iloc[i-1]['High']:
                    df.at[df.index[i], 'bullish_fvg_top'] = df.iloc[i-1]['High']
                # Bearish FVG
                if df.iloc[i+1]['High'] < df.iloc[i-1]['Low']:
                    df.at[df.index[i], 'bearish_fvg_bottom'] = df.iloc[i-1]['Low']
            
        return df
