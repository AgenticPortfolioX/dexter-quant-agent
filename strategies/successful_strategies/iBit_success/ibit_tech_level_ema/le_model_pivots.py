
import pandas as pd
import numpy as np

def detect_pivot_levels(df):
    """
    Implements 'The Gulag' - Major levels logic based on Pivot Highs/Lows.
    - Pivot High: High > T-1, T-2, T+1, T+2
    - Pivot Low: Low < T-1, T-2, T+1, T+2
    - Touch Check: Close > Pivot_Low (Support Hold) OR Close < Pivot_High (Resist Hold)
    """
    try:
        # 1. Identify Pivots (Lookahead 2 is fine for HISTORICAL backtest if we adjust index)
        # However, for LIVE or Backtest Engine, we can only know it's a pivot 2 bars LATER.
        # This implementation assumes we confirm the pivot AFTER it happens.
        # BUT the task says "identify pivot highs... over the last 10 trading days".
        # This usually implies looking back at historical pivots already formed.
        
        # We will use rolling windows to find local min/max, centered=True if possible, But need to avoid forward looking.
        # A pivot formed at T-2 is confirmed at T. So at time T, we can use pivots from T-2 backwards.
        
        # Let's simple check: Is T-2 a pivot?
        # High[T-2] > High[T-3], High[T-4], High[T-1], High[T]
        
        highs = df['High']
        lows = df['Low']
        
        # Shifted comparison for vectorized speed
        # Pivot Low Check at time i-2
        is_pivot_low = (lows.shift(2) < lows.shift(3)) & \
                       (lows.shift(2) < lows.shift(4)) & \
                       (lows.shift(2) < lows.shift(1)) & \
                       (lows.shift(2) < lows)
                       
        is_pivot_high = (highs.shift(2) > highs.shift(3)) & \
                        (highs.shift(2) > highs.shift(4)) & \
                        (highs.shift(2) > highs.shift(1)) & \
                        (highs.shift(2) > highs)
                        
        # We need to propagate the "Last Known Pivot" forward.
        # Create series of NaN, fill with pivot value where True, then ffill.
        
        last_pivot_low = pd.Series(np.nan, index=df.index)
        last_pivot_low[is_pivot_low] = lows.shift(2)
        last_pivot_low = last_pivot_low.ffill()
        
        last_pivot_high = pd.Series(np.nan, index=df.index)
        last_pivot_high[is_pivot_high] = highs.shift(2)
        last_pivot_high = last_pivot_high.ffill()
        
        df['Last_Pivot_Low'] = last_pivot_low
        df['Last_Pivot_High'] = last_pivot_high
        
        # 2. Touch Logic (L_Touch)
        # Long: Price touches pivot low and closes above it (Support Bounce)
        # Short: Price touches pivot high and closes below it (Resistance Reject)
        
        tolerance = 0.002 # Small wiggle room for exact touch? The prompt implies meaningful interaction.
        # "touches a pivot low with a close above it"
        # We'll check if Low <= Pivot Low <= High (Price crossed the level)
        # OR simply Low <= Pivot * (1+tol)
        
        # L_Touch_Long
        # Touching support: Low dipped to/below the support level.
        # Holding support: Close is above the support level.
        # Filter: Only care if the support level is reasonably close (e.g., within 1.5 ATR?)
        # For now, simplistic touch: Low <= Last_Pivot_Low
        
        df['L_Touch_Long'] = (df['Low'] <= df['Last_Pivot_Low'] * 1.001) & (df['Close'] > df['Last_Pivot_Low'])
        
        # L_Touch_Short
        # Touching resistance: High rose to/above resistance
        # Holding resistance: Close is below resistance
        df['L_Touch_Short'] = (df['High'] >= df['Last_Pivot_High'] * 0.999) & (df['Close'] < df['Last_Pivot_High'])
        
        return df

    except Exception as e:
        print(f"Error Pivot Logic: {e}")
        return None
