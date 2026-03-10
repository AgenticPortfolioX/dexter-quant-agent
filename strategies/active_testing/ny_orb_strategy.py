
import pandas as pd
import numpy as np
import os
from datetime import time, timedelta

class NYOrbStrategy:
    """
    Implements the NY 15min ORB Strategy with specific 'No-Trade' filters and execution logic.
    """
    
    def __init__(self, volatility_threshold_pct=0.3):
        # volatility_threshold_pct: max shield range as % of price (default 0.3%)
        self.vol_threshold_pct = volatility_threshold_pct

    def get_orb_candidate_data(self, df):
        grouped = df.groupby(df.index.date)
        return grouped

    def apply_filters(self, day_data, date):
        reasons = []
        trade_allowed = True
        
        t_0800 = time(8, 0)
        t_0815 = time(8, 15)
        t_0930 = time(9, 30)
        
        # 1. Identify 08:00 - 08:15 Range (The "Shield")
        mask_shield = (day_data.index.time >= t_0800) & (day_data.index.time < t_0815)
        shield_data = day_data[mask_shield]
        
        if shield_data.empty:
            return {'trade_allowed': False, 'reasons': ['No 08:00-08:15 Data'], 'metrics': {}}

        shield_high = shield_data['High'].max()
        shield_low = shield_data['Low'].min()
        shield_mean = (shield_high + shield_low) / 2
        shield_range = shield_high - shield_low
        
        # Dynamic Threshold calculation
        current_threshold = (self.vol_threshold_pct / 100) * shield_mean
        
        metrics = {
            'shield_high': shield_high,
            'shield_low': shield_low,
            'shield_range': shield_range,
            'threshold_value': current_threshold
        }

        # --- Filter A: Volatility ---
        if shield_range > current_threshold:
            reasons.append(f"FILTER A: Volatility > {self.vol_threshold_pct}% (${current_threshold:.2f})")
            trade_allowed = False

        # Prepare Pre-Market Data (08:15 - 09:30)
        # 09:30 is essentially the open, so we check up to 09:29 bar
        mask_pre = (day_data.index.time >= t_0815) & (day_data.index.time < t_0930)
        pre_market_data = day_data[mask_pre]
        
        if pre_market_data.empty:
             # If no pre-market data, can't check B or C, but if A passed maybe ok? 
             # Safety says fail.
             if trade_allowed: # Only add if not already failed
                 reasons.append("No Pre-Market Data (08:15-09:30)")
                 trade_allowed = False
             return {'trade_allowed': trade_allowed, 'reasons': reasons, 'metrics': metrics}

        # --- Filter B: The Expansion Trap ---
        # Did price touch BOTH levels?
        touched_high = pre_market_data['High'].max() >= shield_high
        touched_low = pre_market_data['Low'].min() <= shield_low
        
        if touched_high and touched_low:
            reasons.append("FILTER B: Expansion Trap (Touched Both High & Low)")
            trade_allowed = False

        # --- Filter C: Pre-9:30 Break/Retest ---
        # Logic: Close outside range -> Touch boundary again
        
        break_occurred = False
        break_direction = None # 'up' or 'down'
        break_index = -1
        
        # Iterate through pre-market bars to find first break
        # We iterate by integer location
        for i in range(len(pre_market_data)):
            row = pre_market_data.iloc[i]
            if row['Close'] > shield_high:
                break_occurred = True
                break_direction = 'up'
                break_index = i
                break
            elif row['Close'] < shield_low:
                break_occurred = True
                break_direction = 'down'
                break_index = i
                break
        
        if break_occurred and trade_allowed: # Only check if not already dead
            # Check for retest in SUBSEQUENT bars
            # Slice from break_index + 1 to end
            remaining_bars = pre_market_data.iloc[break_index+1:]
            
            if not remaining_bars.empty:
                if break_direction == 'up':
                    # Retest means coming back down to touch shield_high
                    # Low of any subsequent bar <= shield_high
                    if remaining_bars['Low'].min() <= shield_high:
                         reasons.append("FILTER C: Break & Retest (Bullish Break -> Retest High)")
                         trade_allowed = False
                         
                elif break_direction == 'down':
                    # Retest means coming back up to touch shield_low
                    # High of any subsequent bar >= shield_low
                    if remaining_bars['High'].max() >= shield_low:
                         reasons.append("FILTER C: Break & Retest (Bearish Break -> Retest Low)")
                         trade_allowed = False

        return {
            'trade_allowed': trade_allowed,
            'reasons': reasons,
            'metrics': metrics
        }

    def execute_trade(self, day_data, metrics, prev_day_data=None):
        """
        Simulates execution of the ORB strategy for a single day.
        Assumes filters have passed.
        """
        # Time Management
        t_0930 = time(9, 30)
        t_0945 = time(9, 45)
        t_1600 = time(16, 0)
        
        # 1. Anchor: ORB (09:30-09:45)
        mask_orb = (day_data.index.time >= t_0930) & (day_data.index.time < t_0945)
        orb_data = day_data[mask_orb]
        
        if orb_data.empty:
             return {'result': 'No Trade', 'pnl': 0, 'reason': 'No ORB Data'}
             
        orb_high = orb_data['High'].max()
        orb_low = orb_data['Low'].min()
        orb_range = orb_high - orb_low
        midpoint = (orb_high + orb_low) / 2
        
        # 2. Targets & Stops
        # Risk = Entry - Stop.
        # Stop is at Midpoint.
        # Long Entry: ORB High + Tick (Simplify to ORB High)
        # Short Entry: ORB Low - Tick (Simplify to ORB Low)
        
        # Risk Per Share
        risk_long = orb_high - midpoint
        risk_short = midpoint - orb_low
        
        target1_dist_long = 1.5 * risk_long
        target1_dist_short = 1.5 * risk_short
        
        target1_long = orb_high + target1_dist_long
        target1_short = orb_low - target1_dist_short
        
        # Target 2: Previous Day High/Low
        pdh = None
        pdl = None
        if prev_day_data is not None and not prev_day_data.empty:
            pdh = prev_day_data['High'].max()
            pdl = prev_day_data['Low'].min()
            
        target2_long = pdh if pdh and pdh > orb_high else (orb_high + 3 * risk_long) # Fallback to 3R if no PDH
        target2_short = pdl if pdl and pdl < orb_low else (orb_low - 3 * risk_short) # Fallback to 3R if no PDL
        
        # 3. Execution Loop (09:45 - 16:00)
        mask_session = (day_data.index.time >= t_0945) & (day_data.index.time < t_1600)
        session_data = day_data[mask_session]
        
        if session_data.empty:
            return {'result': 'No Trade', 'pnl': 0, 'reason': 'No Session Data'}
        
        position = None # 'long', 'short', None
        entry_price = 0
        stop_loss = 0
        
        result = {'result': 'No Trigger', 'pnl': 0, 'reason': 'No Breakout'}
        
        # Iterate candle by candle
        for i in range(len(session_data)):
            candle = session_data.iloc[i]
            curr_time = candle.name
            
            # Check Trigger (1m Close outside range)
            if position is None:
                if candle['Close'] > orb_high:
                    position = 'long'
                    entry_price = orb_high # Slippage ignored for Logic test
                    stop_loss = midpoint
                    result['entry_time'] = curr_time
                    result['type'] = 'Long'
                    # print(f"Long Entry at {curr_time} @ {entry_price}")
                elif candle['Close'] < orb_low:
                    position = 'short'
                    entry_price = orb_low
                    stop_loss = midpoint
                    result['entry_time'] = curr_time
                    result['type'] = 'Short'
                    # print(f"Short Entry at {curr_time} @ {entry_price}")
            
            # Manage Open Position
            else:
                # Check Stop Loss
                if position == 'long':
                    if candle['Low'] <= stop_loss:
                         result['exit_time'] = curr_time
                         result['exit_price'] = stop_loss
                         result['pnl'] = stop_loss - entry_price
                         result['result'] = 'Stop Loss'
                         return result
                    
                    # Check Target 1 (Partial? Let's just track full exit for now or simple strategy)
                    # Use Target 1 as main target for simplicity or blend?
                    # Request said "Set Target 1... Set Target 2... Hard exit at 16:00"
                    # Let's assume full exit at Target 1 for simplicity of this verification step
                    # OR split position? "Set Target 1... Target 2" implies dynamic exit.
                    # Let's track if T1 hit, then aim for T2. 
                    
                    if candle['High'] >= target1_long:
                        # T1 Hit. Move Stop to Breakeven? Usually standard practice.
                        stop_loss = entry_price 
                        
                    if candle['High'] >= target2_long:
                        # T2 Hit (Full Exit)
                         result['exit_time'] = curr_time
                         result['exit_price'] = target2_long
                         # Simplified: Average of T1 and T2? Or just T2? 
                         # Let's assume held for swing to T2 if T1 passed.
                         result['pnl'] = target2_long - entry_price
                         result['result'] = 'Target 2'
                         return result

                elif position == 'short':
                    if candle['High'] >= stop_loss:
                         result['exit_time'] = curr_time
                         result['exit_price'] = stop_loss
                         result['pnl'] = entry_price - stop_loss
                         result['result'] = 'Stop Loss'
                         return result
                         
                    if candle['Low'] <= target1_short:
                        stop_loss = entry_price
                        
                    if candle['Low'] <= target2_short:
                         result['exit_time'] = curr_time
                         result['exit_price'] = target2_short
                         result['pnl'] = entry_price - target2_short
                         result['result'] = 'Target 2'
                         return result

        # Hard Exit at 16:00 (End of data)
        if position is not None:
             last_candle = session_data.iloc[-1]
             result['exit_time'] = last_candle.name
             result['exit_price'] = last_candle['Close']
             if position == 'long':
                 result['pnl'] = last_candle['Close'] - entry_price
             else:
                 result['pnl'] = entry_price - last_candle['Close']
             result['result'] = 'Hard Exit (16:00)'
             
        return result

    def run_analysis(self, file_path):
        """
        Loads data, runs filters AND execution, returns results summary.
        """
        try:
            df = pd.read_pickle(file_path)
        except Exception as e:
            return f"Error loading data: {e}"

        grouped = self.get_orb_candidate_data(df)
        results = []

        print(f"Analyzing {len(grouped)} trading days...")
        
        prev_group = None

        for date, group in grouped:
            # We only care if we have data for the setup times
            # Filter logic handles missing data checks
            res = self.apply_filters(group, date)
            
            # If Allowed, Execute
            exec_res = {'pnl': 0, 'result': 'Filtered'}
            if res['trade_allowed']:
                exec_res = self.execute_trade(group, res['metrics'], prev_group)
            
            results.append({
                'date': date,
                'trade_allowed': res['trade_allowed'],
                'reasons': "; ".join(res['reasons']),
                'range': res['metrics'].get('shield_range', 0),
                'pnl': exec_res['pnl'],
                'outcome': exec_res['result']
            })
            
            prev_group = group # Store for PDH/PDL next loop
            
        return pd.DataFrame(results)

if __name__ == "__main__":
    # Test run
    strategy = NYOrbStrategy()
    data_path = "ES_1m_aligned.pkl"
    if os.path.exists(data_path):
        results_df = strategy.run_analysis(data_path)
        print(results_df.head(10))
        
        # Quick stats
        allowed = results_df[results_df['trade_allowed']]
        denied = results_df[~results_df['trade_allowed']]
        print(f"\nTotal Days: {len(results_df)}")
        print(f"Allowed: {len(allowed)}")
        print(f"Denied: {len(denied)}")
        
        print("\nPnL Summary:")
        print(f"Total PnL: {results_df['pnl'].sum():.2f}")
        
    else:
        print("Data file not found. Run Step 1 first.")
