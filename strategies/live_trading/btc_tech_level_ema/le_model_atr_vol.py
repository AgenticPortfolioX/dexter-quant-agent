
import pandas as pd
import numpy as np

def calculate_atr_vol(df):
    """
    Refined ATR (14->10) and Stop Distance (1.5x -> 2.0x).
    Wider stops for volatile assets like NVDA/TSLA.
    """
    try:
        # ATR Calculation (Wilder's Smoothing)
        high = df['High']
        low = df['Low']
        close = df['Close']
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Reduced Period (14 -> 10) for faster reaction to volatility expansion
        df['ATR_14'] = tr.ewm(alpha=1/10, adjust=False).mean()
        
        # WIDER Stop Distance (1.5 -> 2.0)
        # Give trades more room to breathe. The 1.5x was cutting winners short.
        df['Stop_Distance'] = df['ATR_14'] * 2.0
        
        # Volume SMA
        df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
        
        return df

    except Exception as e:
        print(f"Error calculating ATR/Volume: {e}")
        return None
