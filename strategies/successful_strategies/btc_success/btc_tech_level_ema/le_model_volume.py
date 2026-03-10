
import pandas as pd

def check_volume_confirmation(df):
    """
    Implements Volume Confirmation (Prompt 7):
    - Volume Breakout: Vol > 1.5 * SMA(20) at new highs.
    - Volume Dryup: Pullback_Volume < 0.7 * SMA(20). 
    - Valid_Long_Touch: (E_Touch OR L_Touch_Long) AND Anchor_Up AND Pullback_Volume_Dry.
    """
    try:
        # 1. High Volume Breakout (Condition Only - Not Entry)
        new_high_5 = df['High'].rolling(5).max() == df['High']
        new_low_5 = df['Low'].rolling(5).min() == df['Low']
        
        df['Vol_Breakout'] = (df['Volume'] > df['Volume_SMA_20'] * 1.5) & (new_high_5 | new_low_5)
        
        # 2. Pullback Volume Dry
        df['Vol_Dry'] = df['Volume'] < (df['Volume_SMA_20'] * 0.7)
        
        # 3. Valid Long Touch (Signal Prep)
        # Condition: Touch Occurred + Volume was Dry (Weak Sellers) + Trend is Up
        df['Valid_Long_Touch'] = (df['E_Touch'] | df['L_Touch_Long']) & \
                                 df['Anchor_Up'] & \
                                 df['Vol_Dry']
                                 
        # Valid Short Touch (Symmetrical)
        df['Valid_Short_Touch'] = (df['E_Touch'] | df['L_Touch_Short']) & \
                                  df['Anchor_Down'] & \
                                  df['Vol_Dry']
                                 
        return df

    except Exception as e:
        print(f"Error Volume Logic: {e}")
        return None
