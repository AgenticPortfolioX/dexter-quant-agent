import pandas as pd
import numpy as np
import yfinance as yf
import os
from datetime import datetime, time

class DynamicBiasMomentumStrategy:
    """
    Strategy: Dynamic Intraday Momentum + Daily Bias
    Logic:
    - Entry: Price expands beyond 14-day dynamic volatility threshold from open.
    - Filter: Price must be above/below Today's Open AND Yesterday's Midpoint.
    - Exit: Force close at end of day (15:55 EST).
    """
    def __init__(self, symbol="^SPX"):
        self.symbol = symbol
        self.active_position = None
        self.log_dir = "logs"
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def log(self, message):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

    def fetch_data(self):
        try:
            # 1h data for analysis
            df = yf.download(self.symbol, period="30d", interval="1h")
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except Exception as e:
            self.log(f"Error fetching data: {e}")
            return None

    def calculate_indicators(self, df):
        if df is None or df.empty: return None
        
        df = df.copy()
        df['Date'] = df.index.date
        df['Open_Price'] = df.groupby('Date')['Open'].transform('first')
        
        # 1. Dynamic Volatility Threshold (14-period)
        df['PctMove'] = (df['Close'] - df['Open_Price']) / df['Open_Price']
        df['Threshold'] = df['PctMove'].abs().rolling(window=14*7).mean()
        
        # 2. Daily Bias Elements
        daily_agg = df.groupby('Date').agg({'High': 'max', 'Low': 'min'})
        daily_agg['Mid'] = (daily_agg['High'] + daily_agg['Low']) / 2
        daily_agg['Prev_Mid'] = daily_agg['Mid'].shift(1)
        df = df.join(daily_agg[['Prev_Mid']], on='Date')
        
        return df

    def run_check(self):
        df = self.fetch_data()
        df = self.calculate_indicators(df)
        if df is None: return

        last_row = df.iloc[-1]
        close = last_row['Close']
        open_p = last_row['Open_Price']
        prev_mid = last_row['Prev_Mid']
        threshold = last_row['Threshold']
        
        if pd.isna(threshold) or pd.isna(prev_mid):
            return

        upper_bound = open_p * (1 + threshold)
        lower_bound = open_p * (1 - threshold)
        
        bullish_bias = (close > open_p) and (close > prev_mid)
        bearish_bias = (close < open_p) and (close < prev_mid)

        # Entry Logic
        if self.active_position is None:
            if close > upper_bound and bullish_bias:
                self.log(f"Entering LONG @ {close}")
                self.active_position = "LONG"
            elif close < lower_bound and bearish_bias:
                self.log(f"Entering SHORT @ {close}")
                self.active_position = "SHORT"
        
        # Time-based Exit
        # In a real live environment, this would be tied to a clock
        # for a backtest/active monitor, we check current time
        # self.log(f"Monitoring: {self.symbol} @ {close} (Threshold: {threshold:.4%})")

    def generate_signals(self, df):
        """
        Standard interface for signal generation.
        Scans the provided DataFrame and returns a list of signal dicts.
        """
        if df is None or df.empty:
            return []
        df_ind = self.calculate_indicators(df)
        if df_ind is None:
            return []
        signals = []
        for i in range(1, len(df_ind)):
            row = df_ind.iloc[i]
            if pd.isna(row.get('Threshold')) or pd.isna(row.get('Prev_Mid')):
                continue
            close = float(row['Close'])
            open_p = float(row['Open_Price'])
            prev_mid = float(row['Prev_Mid'])
            threshold = float(row['Threshold'])
            upper = open_p * (1 + threshold)
            lower = open_p * (1 - threshold)
            bullish_bias = (close > open_p) and (close > prev_mid)
            bearish_bias = (close < open_p) and (close < prev_mid)
            if close > upper and bullish_bias:
                signals.append({'timestamp': df_ind.index[i], 'type': 'LONG', 'price': close})
            elif close < lower and bearish_bias:
                signals.append({'timestamp': df_ind.index[i], 'type': 'SHORT', 'price': close})
        return signals

if __name__ == "__main__":
    strategy = DynamicBiasMomentumStrategy("QQQ")
    strategy.run_check()
