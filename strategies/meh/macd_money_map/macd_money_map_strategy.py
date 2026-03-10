import pandas as pd
import numpy as np

class MACDMoneyMapStrategy:
    """
    MACD Money Map Trading Strategy.
    As derived from the '3 Ways To Use MACD' methodology.
    
    This system requires multi-timeframe alignment across Daily, 4-Hour, and 1-Hour charts.
    - System 1 (Trend): The Daily MACD relative to the Zero Line establishes directional bias.
    - System 2 (Setup): The 4-Hour MACD crossover confirms momentum direction.
    - System 3 (Confirmation): The 1-Hour MACD Histogram flipping color acts as the entry trigger.
    """
    
    def __init__(self, fast_period=12, slow_period=26, signal_period=9):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def calculate_indicators(self, data_dict: dict) -> dict:
        """
        Calculates the MACD, Signal Line, and Histogram for all provided DataFrames.
        data_dict should be structured as: {'1d': df_daily, '4h': df_4h, '1h': df_1h}
        """
        for timeframe, df in data_dict.items():
            if 'Close' not in df.columns:
                continue
                
            # Calculate standard EMAs
            df['EMA_Fast'] = df['Close'].ewm(span=self.fast_period, adjust=False).mean()
            df['EMA_Slow'] = df['Close'].ewm(span=self.slow_period, adjust=False).mean()
            
            # MACD Line = Fast EMA - Slow EMA
            df['MACD_Line'] = df['EMA_Fast'] - df['EMA_Slow']
            
            # Signal Line = 9 EMA of MACD Line
            df['Signal_Line'] = df['MACD_Line'].ewm(span=self.signal_period, adjust=False).mean()
            
            # Histogram = MACD Line - Signal Line
            df['MACD_Histogram'] = df['MACD_Line'] - df['Signal_Line']
            
            # Calculate recent Swing Highs & Lows (10-period lookback used for exits)
            df['Swing_High'] = df['High'].rolling(window=10).max()
            df['Swing_Low'] = df['Low'].rolling(window=10).min()
            
            data_dict[timeframe] = df
            
        return data_dict

    def generate_signals(self, data_dict: dict) -> list:
        """
        Iterates over the 1-Hour timeframe (trigger timeframe) and cross-references
        the 4-Hour (setup) and Daily (trend bias) timeframes to generate entry signals.
        Returns a list of signal dictionary objects.
        """
        data_dict = self.calculate_indicators(data_dict)
        
        df_1d = data_dict.get('1d')
        df_4h = data_dict.get('4h')
        df_1h = data_dict.get('1h')
        
        if df_1d is None or df_4h is None or df_1h is None:
            raise ValueError("Data dictionary must contain '1d', '4h', and '1h' DataFrames.")
            
        signals = []
        
        # We assume indices are datetime objects for alignment.
        for i in range(1, len(df_1h)):
            row_1h = df_1h.iloc[i]
            prev_1h = df_1h.iloc[i-1]
            current_time = df_1h.index[i]
            
            # Align with the most recent Daily candle
            daily_snapshot = df_1d[df_1d.index <= current_time]
            if daily_snapshot.empty:
                continue
            current_daily = daily_snapshot.iloc[-1]
            
            # Align with the most recent 4-Hour candle
            h4_snapshot = df_4h[df_4h.index <= current_time]
            if h4_snapshot.empty or len(h4_snapshot) < 4: # Need lookback for crossover
                continue
            
            # Rule 1: Daily Trend Bias
            daily_macd = current_daily['MACD_Line']
            bullish_bias = daily_macd > 0
            bearish_bias = daily_macd < 0
            
            if not (bullish_bias or bearish_bias):
                continue
                
            # Rule 2: 4-Hour Setup (Recent Crossover)
            # Check if there was a MACD crossover in the last 3 H4 candles
            h4_recent = h4_snapshot.iloc[-4:]
            
            h4_bullish_cross = False
            h4_bearish_cross = False
            
            for j in range(1, len(h4_recent)):
                prev = h4_recent.iloc[j-1]
                curr = h4_recent.iloc[j]
                
                # Bullish Crossover: MACD crosses above Signal
                if prev['MACD_Line'] <= prev['Signal_Line'] and curr['MACD_Line'] > curr['Signal_Line']:
                    h4_bullish_cross = True
                    
                # Bearish Crossover: MACD crosses below Signal
                if prev['MACD_Line'] >= prev['Signal_Line'] and curr['MACD_Line'] < curr['Signal_Line']:
                    h4_bearish_cross = True
            
            # Rule 3: 1-Hour Trigger
            hist_curr = row_1h['MACD_Histogram']
            hist_prev = prev_1h['MACD_Histogram']
            
            # 1H Histogram flips Red to Green (Negative to Positive)
            hist_bullish_flip = (hist_prev < 0) and (hist_curr > 0)
            
            # 1H Histogram flips Green to Red (Positive to Negative)
            hist_bearish_flip = (hist_prev > 0) and (hist_curr < 0)
            
            # Finalize LONG Signal Alignment
            if bullish_bias and h4_bullish_cross and hist_bullish_flip:
                entry_price = row_1h['Close']
                # Stop loss at recent 1H swing low
                stop_loss = prev_1h['Swing_Low']
                risk = entry_price - stop_loss
                if risk <= 0: risk = entry_price * 0.001
                
                # 2:1 Take Profit Ratio
                take_profit = entry_price + (risk * 2.0)
                
                signals.append({
                    'timestamp': current_time,
                    'type': 'LONG_ENTRY',
                    'entry': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'rr_ratio': 2.0,
                    'model': 'MACD Money Map (Bullish Triple Alignment)'
                })
                
            # Finalize SHORT Signal Alignment
            elif bearish_bias and h4_bearish_cross and hist_bearish_flip:
                entry_price = row_1h['Close']
                # Stop loss at recent 1H swing high
                stop_loss = prev_1h['Swing_High']
                risk = stop_loss - entry_price
                if risk <= 0: risk = entry_price * 0.001
                
                # 2:1 Take Profit Ratio
                take_profit = entry_price - (risk * 2.0)
                
                signals.append({
                    'timestamp': current_time,
                    'type': 'SHORT_ENTRY',
                    'entry': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'rr_ratio': 2.0,
                    'model': 'MACD Money Map (Bearish Triple Alignment)'
                })
                
        return signals

if __name__ == "__main__":
    print("Strategy Class Available: MACDMoneyMapStrategy")
    print("Timeframes Required: 1-Day, 4-Hour, 1-Hour")
