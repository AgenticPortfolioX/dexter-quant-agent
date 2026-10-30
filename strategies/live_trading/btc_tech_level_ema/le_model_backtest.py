
import pandas as pd
import numpy as np

def run_backtest_with_tsl(df):
    """
    Implements Trailing Stop Logic (Prompt 10) & Backtesting Engine (Prompt 11):
    - Trades Vectorized
    - Dynamic TSL: max(Initial, Close - 1.5*ATR) for longs.
    """
    try:
        trades = []
        active_trade = None
        
        # Iterate Row-by-Row
        # While pandas shift is vectorized, strict position management across candles is often cleaner iteratively for state.
        # But Prompt 11 requests vectorized if possible ("Use vectorized operations...").
        # However, Trailing Stop is a path-dependent calculation (S_t depends on S_t-1).
        # We will use numba/jit or simply iterate for path dependency (most accurate).
        # We will iterate for clarity and correctness in Python.
        
        # Pre-State Variables
        # We need sequential logic.
        
        # 1. Prepare Columns needed
        # Open, High, Low, Close, ATR_14, Stop_Distance, Long_Entry_Signal
        
        # 2. Iterate
        for i in range(len(df)):
            curr = df.iloc[i]
            timestamp = curr.name
            
            # --- Active Trade Management (Exit) ---
            if active_trade:
                trade_type = active_trade['type']
                
                exit_price = None
                exit_reason = None
                
                if trade_type == 'LONG':
                    # 1. Check Stop Loss (Intrabar Low)
                    if curr['Low'] <= active_trade['sl']:
                        exit_price = active_trade['sl']
                        exit_reason = 'Stop Loss'
                    
                    # 2. Update Trailing Stop (Dynamic)
                    if not exit_price:
                        # New Potential TSL: Close - 1.5 * ATR
                        new_tsl = curr['Close'] - (curr['ATR_14'] * 1.5)
                        # Long TSL only moves UP
                        active_trade['sl'] = max(active_trade['sl'], new_tsl)
                        
                elif trade_type == 'SHORT':
                    # 1. Check Stop Loss (Intrabar High)
                    if curr['High'] >= active_trade['sl']:
                        exit_price = active_trade['sl']
                        exit_reason = 'Stop Loss'
                        
                    # 2. Update Trailing Stop
                    if not exit_price:
                        # New Potential TSL: Close + 1.5 * ATR
                        new_tsl = curr['Close'] + (curr['ATR_14'] * 1.5)
                        # Short TSL only moves DOWN
                        active_trade['sl'] = min(active_trade['sl'], new_tsl)

                # Process Exit
                if exit_price:
                    # Calculate PnL
                    # Long: Exit - Entry
                    # Short: Entry - Exit
                    if trade_type == 'LONG':
                        pnl = exit_price - active_trade['entry']
                    else:
                        pnl = active_trade['entry'] - exit_price
                        
                    trades.append({
                        'entry_time': active_trade['entry_time'],
                        'exit_time': timestamp,
                        'type': trade_type,
                        'entry': active_trade['entry'],
                        'exit': exit_price,
                        'pnl': pnl,
                        'outcome': exit_reason,
                        'stop_distance': active_trade['initial_risk'],
                        'exit_reason': exit_reason
                    })
                    active_trade = None
                    continue # Trade closed, move to next candle to check for new entry? 
                    # Usually we don't re-enter on the same candle we stopped out on.
            
            # --- New Entry Logic ---
            if not active_trade:
                # Long
                if curr['Long_Entry_Signal']:
                    entry_price = curr['Open']
                    stop_dist = curr['Stop_Distance']
                    initial_sl = entry_price - stop_dist
                    
                    active_trade = {
                        'entry_time': timestamp,
                        'type': 'LONG',
                        'entry': entry_price,
                        'sl': initial_sl,
                        'initial_risk': stop_dist
                    }
                    
                # Short
                elif curr['Short_Entry_Signal']:
                    entry_price = curr['Open']
                    stop_dist = curr['Stop_Distance']
                    initial_sl = entry_price + stop_dist
                    
                    active_trade = {
                        'entry_time': timestamp,
                        'type': 'SHORT',
                        'entry': entry_price,
                        'sl': initial_sl,
                        'initial_risk': stop_dist
                    }

        return pd.DataFrame(trades)

    except Exception as e:
        print(f"Error Backtest Engine: {e}")
        return pd.DataFrame()
