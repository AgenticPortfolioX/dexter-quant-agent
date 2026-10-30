
import pandas as pd
import numpy as np

class InsideCandleStrategy:
    """
    Inside Candle Positional Strategy
    Based on Mother Candle & Inside Bar Logic with Trailing Stop.
    """
    def __init__(self, rr=3.0, atr_period=10, atr_multiplier=1.0, use_tsl=True):
        self.rr = rr
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.use_tsl = use_tsl

    def add_indicators(self, df):
        # ATR Calculation (Wilder's Smoothing)
        high = df['High']
        low = df['Low']
        close = df['Close']
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Pine Script ta.atr uses RMA (alpha = 1/length)
        df['ATR'] = tr.ewm(alpha=1/self.atr_period, adjust=False).mean()
        
        # Identification of Inside Bar
        # Inside Bar: High < High[1] AND Low > Low[1]
        df['prev_High'] = df['High'].shift(1)
        df['prev_Low'] = df['Low'].shift(1)
        
        df['Inside_Bar'] = (df['High'] < df['prev_High']) & (df['Low'] > df['prev_Low'])
        
        return df

    def backtest(self, df):
        trades = []
        active_trade = None
        
        # State Variables
        mother_high = np.nan
        mother_low = np.nan
        mother_active = False
        breakout_taken = False
        
        # Iterate row by row (using namedtuple for speed, or index)
        # We need sequential logic because entry depends on state from previous bars
        
        # Preparing a clean loop
        # Note: df is assumed to have datetime index
        
        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            timestamp = curr.name
            
            # 1. Manage Active Trade (Exit Logic)
            if active_trade:
                trade_type = active_trade['type']
                
                # Check Exits active from previous close status
                # In real life, stops can be hit intrabar. We will check Low/High against SL/TP.
                
                exit_price = None
                exit_reason = None
                
                if trade_type == 'LONG':
                    # Check SL (Trailing or Initial)
                    if curr['Low'] <= active_trade['sl']:
                        exit_price = active_trade['sl'] # Slippage not modeled per se, assuming stop hit
                        exit_reason = 'Stop Loss'
                    
                    # Check Target
                    elif curr['High'] >= active_trade['target']:
                        exit_price = active_trade['target']
                        exit_reason = 'Target'
                    
                    # Trailing Stop Update (End of Candle)
                    if not exit_price and self.use_tsl:
                        new_tsl = curr['Close'] - (curr['ATR'] * self.atr_multiplier)
                        # Long TSL only moves up
                        active_trade['sl'] = max(active_trade['sl'], new_tsl)

                elif trade_type == 'SHORT':
                    # Check SL
                    if curr['High'] >= active_trade['sl']:
                        exit_price = active_trade['sl']
                        exit_reason = 'Stop Loss'
                        
                    # Check Target
                    elif curr['Low'] <= active_trade['target']:
                        exit_price = active_trade['target']
                        exit_reason = 'Target'
                        
                    # Trailing Stop Update
                    if not exit_price and self.use_tsl:
                        new_tsl = curr['Close'] + (curr['ATR'] * self.atr_multiplier)
                        # Short TSL only moves down
                        active_trade['sl'] = min(active_trade['sl'], new_tsl)

                # Process Exit
                if exit_price:
                    pnl = (exit_price - active_trade['entry']) if trade_type == 'LONG' else (active_trade['entry'] - exit_price)
                    trades.append({
                        'entry_time': active_trade['entry_time'],
                        'exit_time': timestamp,
                        'ticker': active_trade.get('ticker', 'Unknown'),
                        'type': trade_type,
                        'entry': active_trade['entry'],
                        'exit': exit_price,
                        'pnl': pnl,
                        'outcome': exit_reason
                    })
                    active_trade = None
                    mother_active = False # Reset logic after trade close
                    breakout_taken = False
                    continue # Trade closed, move to next candle

            # 2. Logic Update if No Active Trade
            if not active_trade:
                # Inside Bar Logic
                if curr['Inside_Bar']:
                    # Set Mother Candle (Previous Candle)
                    mother_high = prev['High']
                    mother_low = prev['Low']
                    mother_active = True
                    breakout_taken = False
                
                # Entry Logic
                if mother_active and not breakout_taken:
                    # Long Breakout
                    if curr['Close'] > mother_high:
                        entry_price = curr['Close'] # Market Order on Close (Positional)
                        risk = entry_price - mother_low
                        target = entry_price + (risk * self.rr)
                        initial_sl = mother_low
                        
                        active_trade = {
                            'entry_time': timestamp,
                            'type': 'LONG',
                            'entry': entry_price,
                            'sl': initial_sl,
                            'target': target,
                            'initial_sl': initial_sl
                        }
                        breakout_taken = True
                    
                    # Short Breakout
                    elif curr['Close'] < mother_low:
                        entry_price = curr['Close']
                        risk = mother_high - entry_price
                        target = entry_price - (risk * self.rr)
                        initial_sl = mother_high
                        
                        active_trade = {
                            'entry_time': timestamp,
                            'type': 'SHORT',
                            'entry': entry_price,
                            'sl': initial_sl,
                            'target': target,
                            'initial_sl': initial_sl
                        }
                        breakout_taken = True

        return pd.DataFrame(trades)
