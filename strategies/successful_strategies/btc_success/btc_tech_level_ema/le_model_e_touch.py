
import pandas as pd

def detect_ema_touch(df, tolerance_pct=0.0125):
    """
    Refined 'E Touch' Zone:
    - Increased tolerance (0.5% -> 1.25%).
    - Allows deeper pullbacks (wicks) below the 8 EMA.
    - Still requires Close > 8 EMA (Bounce).
    - Captures "Shakeouts" into the 20 EMA area often seen on NVDA/TSLA.
    """
    try:
        ema_8 = df['EMA_8']
        
        # Buffer: Allow price to dip meaningfully below the EMA.
        # "Low <= 8 EMA + larger buffer"
        buffer_zone_high = ema_8 * (1 + tolerance_pct)
        
        # Touch Logic
        # 1. Price penetrated the EMA zone deep enough to test demand.
        # 2. Bullish Rejection/Bounce (Close > EMA) remains the core filter.
        
        df['E_Touch'] = (df['Low'] <= buffer_zone_high) & (df['Close'] > ema_8)
        
        return df

    except Exception as e:
        print(f"Error EMA touch logic: {e}")
        return None
