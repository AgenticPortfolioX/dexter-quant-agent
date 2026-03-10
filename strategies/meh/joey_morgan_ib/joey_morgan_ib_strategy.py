import pandas as pd
import numpy as np

class JoeyMorganIBStrategy:
    """
    Initial Balance (IB) Strategy based on Joey Morgan's methodology.
    Timeframe: 5-minute chart
    Initial Balance (IB): The highest High and lowest Low of the first hour 
                          of the New York session (09:30 AM - 10:30 AM EST).
    
    Optimized for QQQ and SPY.
    
    Models:
    1. Failed Auctions (Reversal to IB Mid)
    2. Break and Retest (Continuation)
    """
    
    MIN_RR = 1.5  # Minimum Risk/Reward ratio required to enter any trade

    def __init__(self, ticker: str = "QQQ", min_rr=1.5):
        self.ticker = ticker
        self.timeframe = '5m'
        self.min_rr = min_rr
        
    def calculate_ib(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Groups the 5-minute OHLC dataframe by day to find the IB_High,
        IB_Low, and calculates IB_Mid (09:30 - 10:30 market time).
        Forward-fills these levels for the rest of the trading day.
        """
        df = df.copy()
        df['Date'] = df.index.date
        df['Time'] = df.index.time
        
        # Mask for the first hour (Initial Balance)
        import datetime
        time_mask = (df['Time'] >= datetime.time(9, 30)) & (df['Time'] <= datetime.time(10, 30))
        
        # Calculate daily IB values
        ib_data = df[time_mask].groupby('Date').agg(
            IB_High=('High', 'max'),
            IB_Low=('Low', 'min')
        )
        ib_data['IB_Mid'] = (ib_data['IB_High'] + ib_data['IB_Low']) / 2.0
        
        # Merge back to the original dataframe
        df = df.merge(ib_data, left_on='Date', right_index=True, how='left')
        
        # Ensure values are strictly tied to the day (already aligned via merge)
        # Price levels are now available for all candles on that 'Date'
        # The strategy logic should strictly operate AFTER 10:30 AM.
        
        return df

    def _check_rr(self, entry, stop_loss, take_profit, trade_type):
        """Returns True if the trade meets the minimum RR ratio."""
        if trade_type == 'LONG_ENTRY':
            risk = entry - stop_loss
            reward = take_profit - entry
        else:
            risk = stop_loss - entry
            reward = entry - take_profit
        if risk <= 0:
            return False
        return (reward / risk) >= self.min_rr

    def generate_signals(self, df: pd.DataFrame) -> list:
        """
        Scans the 5-minute DataFrame containing IB_High, IB_Low, and IB_Mid.
        Generates Entry Model 1 (Failed Auction) and Model 2 (Break & Retest) signals.
        Enforces a minimum 1.5:1 RR on every trade to ensure positive expectancy.
        Returns a list of signal dictionary objects.
        """
        df = self.calculate_ib(df)
        signals = []
        
        import datetime
        post_ib_time = datetime.time(10, 35)
        model2_cutoff = datetime.time(14, 0)  # No Model 2 signals after 2 PM EST
        
        # State tracking for Break & Retest
        # To simplify, we keep track of whether the IB has been cleanly broken in the current day
        broken_above = False
        broken_below = False
        current_date = None
        
        for i in range(len(df)):
            row = df.iloc[i]
            ts = df.index[i]
            
            # Reset state on new day
            if row['Date'] != current_date:
                broken_above = False
                broken_below = False
                current_date = row['Date']
                
            if pd.isna(row['IB_High']) or row['Time'] < post_ib_time:
                continue
                
            high = row['High']
            low = row['Low']
            close = row['Close']
            
            ib_high = row['IB_High']
            ib_low = row['IB_Low']
            ib_mid = row['IB_Mid']
            
            # Tracking full candle closures for Model 2 states
            if close > ib_high:
                broken_above = True
            if close < ib_low:
                broken_below = True

            # --- MODEL 1: Failed Auctions ---
            # Short Signal: Price breaks above IB_High during candle, but closes below it.
            if high > ib_high and close < ib_high:
                sl = high + (high * 0.0005)
                # Extended TP: If close is well inside the IB, target the full opposite IB wall
                ib_range = ib_high - ib_low
                tp = ib_low if (ib_high - close) > (ib_range * 0.4) else ib_mid
                if self._check_rr(close, sl, tp, 'SHORT_ENTRY'):
                    signals.append({
                        'timestamp': ts,
                        'model': 'Model 1 (Failed Auction)',
                        'type': 'SHORT_ENTRY',
                        'entry': close,
                        'take_profit': tp,
                        'stop_loss': sl
                    })
                
            # Long Signal: Price breaks below IB_Low during candle, but closes above it.
            if low < ib_low and close > ib_low:
                sl = low - (low * 0.0005)
                ib_range = ib_high - ib_low
                tp = ib_high if (close - ib_low) > (ib_range * 0.4) else ib_mid
                if self._check_rr(close, sl, tp, 'LONG_ENTRY'):
                    signals.append({
                        'timestamp': ts,
                        'model': 'Model 1 (Failed Auction)',
                        'type': 'LONG_ENTRY',
                        'entry': close,
                        'take_profit': tp,
                        'stop_loss': sl
                    })
                
            # --- MODEL 2: Break and Retest (Continuation) ---
            # Time-restricted to before 2PM EST to avoid end-of-day noise
            if row['Time'] >= model2_cutoff:
                continue

            # Long Continuation: Already broke above IB_High. Current candle retests IB_High from above.
            if broken_above and (low <= ib_high) and (close > ib_high):
                sl = ib_high - (ib_high * 0.001)
                tp = close + abs(close - ib_high) * 2
                if self._check_rr(close, sl, tp, 'LONG_ENTRY'):
                    signals.append({
                        'timestamp': ts,
                        'model': 'Model 2 (Retest Continuation)',
                        'type': 'LONG_ENTRY',
                        'entry': close,
                        'stop_loss': sl,
                        'take_profit': tp
                    })
                
            # Short Continuation: Already broke below IB_Low. Current candle retests IB_Low from below.
            if broken_below and (high >= ib_low) and (close < ib_low):
                sl = ib_low + (ib_low * 0.001)
                tp = close - abs(close - ib_low) * 2
                if self._check_rr(close, sl, tp, 'SHORT_ENTRY'):
                    signals.append({
                        'timestamp': ts,
                        'model': 'Model 2 (Retest Continuation)',
                        'type': 'SHORT_ENTRY',
                        'entry': close,
                        'stop_loss': sl,
                        'take_profit': tp
                    })
                
        return signals

if __name__ == "__main__":
    print("Strategy Class Available: JoeyMorganIBStrategy")
    print("Method: Initial Balance (First Hour NY Session)")
    print("Timeframe: 5-minute")
    print("Models: Failed Auctions & Break/Retest Continuations")
