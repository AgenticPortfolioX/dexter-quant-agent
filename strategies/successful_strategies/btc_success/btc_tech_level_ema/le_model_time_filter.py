
import pandas as pd
from datetime import time

def apply_time_filter(df):
    """
    Implements Time Filter (Prompt 9):
    - Trade_Allowed: False during 09:30-09:45 (Vol) and 11:30-14:30 (Lunch Chop).
    - Requires index localized to US/Eastern.
    """
    try:
        # 1. Define Filter
        df['Trade_Allowed'] = True
        
        # Opening Chop (09:30 - 09:45)
        start_scan = time(9, 45) # Backtest usually starts at 9:30.
        
        # Lunch Chop (11:30 - 14:30)
        lunch_start = time(11, 30)
        lunch_end = time(14, 30)
        
        # 2. Iterate Timestamps (Vectorized)
        times = df.index.time
        
        # 1. Opening Chop
        df.loc[times < start_scan, 'Trade_Allowed'] = False
        
        # 2. Lunch Chop
        # 11:30 <= T < 14:30
        is_lunch = (times >= lunch_start) & (times < lunch_end)
        df.loc[is_lunch, 'Trade_Allowed'] = False
        
        # 3. Modify Signals
        # Only allow entry if Trade_Allowed is True on the signal candle (T)
        # Remember: Signal happens at Open of T. Valid_Touch happened at T-1.
        # We check if T is allowed.
        
        df.loc[~df['Trade_Allowed'], 'Long_Entry_Signal'] = False
        df.loc[~df['Trade_Allowed'], 'Short_Entry_Signal'] = False
        
        return df

    except Exception as e:
        print(f"Error Time Filter: {e}")
        # If timezone fails, default to True but warn?
        # Assuming index is already localized.
        return df # Return unmodified if error
