
import pandas as pd
import numpy as np
from datetime import timedelta

class LiquiditySweepStrategy:
    """
    Implements the Liquidity Sweep + MSS + FVG Scalping Strategy.
    """
    
    def __init__(self, atr_period=14, lookback_15m=48):
        self.atr_period = atr_period
        self.lookback_15m = lookback_15m # Bars to define significant swing

    def calculate_atr(self, df):
        """ Calculates ATR(14). """
        # Ensure unique columns
        df = df.loc[:, ~df.columns.duplicated()]
        
        if len(df) < self.atr_period: return df
        
        # Force Series extraction
        h = df['High']
        l = df['Low']
        c = df['Close']
        if isinstance(h, pd.DataFrame): h = h.iloc[:, 0]
        if isinstance(l, pd.DataFrame): l = l.iloc[:, 0]
        if isinstance(c, pd.DataFrame): c = c.iloc[:, 0]
        
        high_low = h - l
        high_close = np.abs(h - c.shift())
        low_close = np.abs(l - c.shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        
        df['ATR'] = true_range.rolling(self.atr_period).mean()
        return df

    def find_liquidity_pools(self, df_15m):
        """
        Identifies significant Swing Highs/Lows on 15m chart.
        Pool is valid if it was the highest/lowest in 'lookback_15m' bars.
        Returns: DataFrame of pools (time, price, type, intact=True)
        """
        pools = []
        # Iterate through 15m data (avoiding lookahead - check past N bars)
        # Optimized: Rolling Max/Min
        
        # We need to know if a specific bar WAS a swing high/low at that time.
        # A bar at index i is a Swing High if High[i] == max(High[i-N:i+1])? No, +1 is lookahead.
        # Standard definition: High[i] > all Highs in [i-N, i-1] (Verified High).
        # But prompts say "highest point in the last 48 bars".
        
        roll_high = df_15m['High'].rolling(window=self.lookback_15m).max()
        roll_low = df_15m['Low'].rolling(window=self.lookback_15m).min()
        
        # Identify points where High == rolling max
        # This marks them as potential pools as of that moment.
        # We store them.
        
        # A better approach for "Pools" that stick around:
        # A pool is created at a Pivot. It remains valid until Swept.
        # Let's use Fractal Logic (Pivot) to create, and Rolling Low/High to validate significance?
        # Prompt: "Level is significant if it was the highest/lowest point in the last 48 bars".
        
        for i in range(self.lookback_15m, len(df_15m)):
            # Check if i-1 was a local extreme in the window
            # Actually, we just need the levels existing *before* the 1m execution time.
            # So, at any 1m timestamp, we look at the last completed 15m candle.
            # And finding the "Highest High of last 48 15m bars".
            pass
            
        return df_15m # We will handle lookup dynamically contextually

    def backtest(self, df_1m, df_15m):
        """
        Main execution Engine.
        Iterates 1m bars.
        1. Context: Updates Liquidity Pools from 15m data (up to current time).
        2. Trigger: Checks for Sweep on 1m.
        3. Confirmation: Checks for MSS + FVG.
        4. Management: Enters & Manages Trade.
        """
        
        # Prepare 15m Data
        # We assume df_15m is indexed by time.
        # We calculate rolling max/min on 15m beforehand to speed up.
        df_15m = self.calculate_atr(df_15m) # ATR needed for sweep definition? 
        # Prompt 3 says: Sweep aggressive if wick > 0.5 * ATR(14) on ENTRY timeframe (1m).
        # Prompt 2 says: Pool intact if not exceeded by 0.5 * ATR(14) on 15m.
        
        df_1m = self.calculate_atr(df_1m)
        
        # Execution State
        active_trade = None
        trades = []
        pending_order = None # Limit order waiting for FVG fill
        
        # Variables to track Setup State
        recent_sweeps = [] 
        
        # Data Cleanup: Deduplicate columns to prevent Series ambiguity on row access
        df_1m = df_1m.loc[:, ~df_1m.columns.duplicated()]
        df_15m = df_15m.loc[:, ~df_15m.columns.duplicated()]
        
        print(f"Backtesting {len(df_1m)} bars against {len(df_15m)} context bars...")
        
        # Main Loop
        try:
            for i in range(100, len(df_1m)):
                curr_1m = df_1m.iloc[i]
                prev_1m = df_1m.iloc[i-1]
                curr_time = curr_1m.name
                
                # --- 0. Manage Active Trade ---
                if active_trade:
                    # Helper for scalar extraction from row
                    # curr_1m might have duplicates, so force scalar
                    c_low = curr_1m['Low']; c_high = curr_1m['High']
                    if isinstance(c_low, pd.Series): c_low = c_low.iloc[0]
                    if isinstance(c_high, pd.Series): c_high = c_high.iloc[0]
                    c_low = float(c_low); c_high = float(c_high)
                    
                    # Check Exit
                    res = None
                    pnl = 0
                    
                    if active_trade['direction'] == 'long':
                        # Stop Loss
                        if c_low <= active_trade['sl']:
                            res = 'Stop Loss'
                            pnl = active_trade['sl'] - active_trade['entry']
                        # TP1 (Scale Out / BE)
                        elif not active_trade['tp1_hit'] and c_high >= active_trade['tp1']:
                            # Hit TP1
                            active_trade['tp1_hit'] = True
                            active_trade['sl'] = active_trade['entry'] # Move to BE
                            
                        # TP2 (Final Target)
                        elif c_high >= active_trade['tp2']:
                            res = 'Target 2'
                            pnl = active_trade['tp2'] - active_trade['entry']
                    
                    else: # short
                        if c_high >= active_trade['sl']:
                            res = 'Stop Loss'
                            pnl = active_trade['entry'] - active_trade['sl']
                        elif not active_trade['tp1_hit'] and c_low <= active_trade['tp1']:
                            active_trade['tp1_hit'] = True
                            active_trade['sl'] = active_trade['entry']
                        elif c_low <= active_trade['tp2']:
                             res = 'Target 2'
                             pnl = active_trade['entry'] - active_trade['tp2']

                    if res:
                        trades.append({
                            'entry_time': active_trade['entry_time'],
                            'exit_time': curr_time,
                            'type': active_trade['direction'],
                            'entry': active_trade['entry'],
                            'exit': active_trade['sl'] if res == 'Stop Loss' else active_trade['tp2'],
                            'pnl': pnl,
                            'outcome': res
                        })
                        active_trade = None
                    continue

                # --- 0.5 Manage Pending Order ---
                if pending_order:
                    # Helper for scalar
                    c_low = curr_1m['Low']; c_high = curr_1m['High']
                    if isinstance(c_low, pd.Series): c_low = c_low.iloc[0]
                    if isinstance(c_high, pd.Series): c_high = c_high.iloc[0]
                    c_low = float(c_low); c_high = float(c_high)

                    # Check Fill
                    # Timeout
                    if (i - pending_order['candle_idx']) > 5:
                        pending_order = None # Expired
                    else:
                        if pending_order['direction'] == 'long':
                            if c_low <= pending_order['limit_price']:
                                # FILLED
                                entry_price = pending_order['limit_price']
                                sl = pending_order['sweep_level'] - (2 * 0.0001) # 2 pips
                                risk = entry_price - sl
                                tp1 = entry_price + risk 
                                tp2 = entry_price + (2.5 * risk)
                                
                                active_trade = {
                                    'direction': 'long',
                                    'entry_time': curr_time,
                                    'entry': entry_price,
                                    'sl': sl,
                                    'tp1': tp1,
                                    'tp1_hit': False,
                                    'tp2': tp2
                                }
                                pending_order = None
                                continue
                        else: # Short
                            if c_high >= pending_order['limit_price']:
                                # FILLED
                                entry_price = pending_order['limit_price']
                                sl = pending_order['sweep_level'] + (2 * 0.0001)
                                risk = sl - entry_price
                                tp1 = entry_price - risk
                                tp2 = entry_price - (2.5 * risk)
                                
                                active_trade = {
                                    'direction': 'short',
                                    'entry_time': curr_time,
                                    'entry': entry_price,
                                    'sl': sl,
                                    'tp1': tp1,
                                    'tp1_hit': False,
                                    'tp2': tp2
                                }
                                pending_order = None
                                continue


                # --- 1. Identify Context (15m Liquidity Pools) ---
                relevant_15m = df_15m[:curr_time]
                if len(relevant_15m) < (self.lookback_15m + 1): continue
                
                recent_48 = relevant_15m.iloc[-(self.lookback_15m+1):-1] # last N closed candles
                
                # Define Pools
                pool_high = recent_48['High'].max()
                if isinstance(pool_high, pd.Series): pool_high = pool_high.iloc[0]
                pool_high = float(pool_high)
                
                pool_low = recent_48['Low'].min()
                if isinstance(pool_low, pd.Series): pool_low = pool_low.iloc[0]
                pool_low = float(pool_low)
                
                # --- 2. Check Trigger: Sweep on 1m ---
                
                atr = curr_1m.get('ATR', 0.0005)
                if isinstance(atr, pd.Series): atr = atr.iloc[0]
                if pd.isna(atr): atr = 0.0005
                atr = float(atr)
                
                # Helper for scalar value
                c_high = curr_1m['High']; c_low = curr_1m['Low']; c_close = curr_1m['Close']
                if isinstance(c_high, pd.Series): c_high = c_high.iloc[0]
                if isinstance(c_low, pd.Series): c_low = c_low.iloc[0]
                if isinstance(c_close, pd.Series): c_close = c_close.iloc[0]
                c_high = float(c_high); c_low = float(c_low); c_close = float(c_close)
                
                is_valid_Short_Sweep = False
                # Check current bar sweep
                if c_high > pool_high and c_close < pool_high:
                    wick_extent = c_high - pool_high
                    if wick_extent >= (0.5 * atr):
                        is_valid_Short_Sweep = True
                        # Store sweep event
                        recent_sweeps.append({'type': 'short', 'time': curr_time, 'level': pool_high, 'idx': i})

                # Check Long Sweep
                is_valid_Long_Sweep = False
                if c_low < pool_low and c_close > pool_low:
                    wick_extent = pool_low - c_low
                    if wick_extent >= (0.5 * atr):
                        is_valid_Long_Sweep = True
                        recent_sweeps.append({'type': 'long', 'time': curr_time, 'level': pool_low, 'idx': i})
                
                # Cleanup old sweeps (valid for 5 mins?)
                recent_sweeps = [s for s in recent_sweeps if (i - s['idx']) <= 3]
                
                # --- 3. Confirm MSS ---
                for sweep in recent_sweeps:
                    # Short Setup: Sweep High -> Break recent Higher Low
                    if sweep['type'] == 'short':
                        lookback_idx = sweep['idx'] - 1
                        # range [lookback_idx-5 : lookback_idx]
                        
                        # Fix slice scalar extraction
                        slice_lows = df_1m.iloc[lookback_idx-5 : lookback_idx]['Low']
                        if isinstance(slice_lows, pd.DataFrame): slice_lows = slice_lows.iloc[:, 0]
                        
                        if slice_lows.empty: continue
                        minor_low = float(slice_lows.min())
                        
                        if c_close < minor_low:
                            # MSS CONFIRMED!
                            # --- 4. Detect FVG ---
                            
                            found_fvg = False
                            for f in range(i, i-3, -1): # Check recently formed FVGs
                                # Scalar extraction for candles f, f-1, f-2
                                row3 = df_1m.iloc[f]; row1 = df_1m.iloc[f-2]
                                
                                c3_high = row3['High']; c1_low = row1['Low']
                                if isinstance(c3_high, pd.Series): c3_high = c3_high.iloc[0]
                                if isinstance(c1_low, pd.Series): c1_low = c1_low.iloc[0]
                                c3_high = float(c3_high); c1_low = float(c1_low)
                                
                                # Bearish FVG: Low of C1 > High of C3
                                if c1_low > c3_high:
                                    # GAP found
                                    gap_low = c3_high
                                    gap_high = c1_low
                                    limit_price = (gap_low + gap_high) / 2
                                    
                                    pending_order = {
                                        'direction': 'short',
                                        'limit_price': limit_price,
                                        'candle_idx': i,
                                        'sweep_level': sweep['level']
                                    }
                                    found_fvg = True
                                    break # Stop looking
                            if found_fvg: break # Stop checking other sweeps
                    
                    # Long Setup: Sweep Low -> Break recent Lower High
                    elif sweep['type'] == 'long':
                         lookback_idx = sweep['idx'] - 1
                         start_idx = max(0, lookback_idx-5)
                         
                         slice_highs = df_1m.iloc[start_idx : lookback_idx]['High']
                         if isinstance(slice_highs, pd.DataFrame): slice_highs = slice_highs.iloc[:, 0]
                         
                         if slice_highs.empty: continue
                         minor_high = float(slice_highs.max())
                         
                         if c_close > minor_high:
                             # MSS Confirmed
                             # Scan for Bullish FVG
                             for f in range(i, i-3, -1):
                                 row3 = df_1m.iloc[f]; row1 = df_1m.iloc[f-2]
                                 
                                 c3_low = row3['Low']; c1_high = row1['High']
                                 if isinstance(c3_low, pd.Series): c3_low = c3_low.iloc[0]
                                 if isinstance(c1_high, pd.Series): c1_high = c1_high.iloc[0]
                                 c3_low = float(c3_low); c1_high = float(c1_high)
                                 
                                 if c1_high < c3_low:
                                     gap_high = c3_low
                                     gap_low = c1_high
                                     limit_price = (gap_high + gap_low) / 2
                                     
                                     pending_order = {
                                         'direction': 'long',
                                         'limit_price': limit_price,
                                         'candle_idx': i,
                                         'sweep_level': sweep['level']
                                     }
                                     break
                                     
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error at index {i}: {e}")
            raise e
            
        return pd.DataFrame(trades)

        return pd.DataFrame(trades)

