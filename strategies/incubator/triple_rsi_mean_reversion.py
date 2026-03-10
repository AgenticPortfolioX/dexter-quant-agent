import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime

class TripleRSIStrategy:
    def __init__(self, period=5, sma_period=200):
        self.period = period
        self.sma_period = sma_period

    def calculate_rsi(self, series):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def add_indicators(self, df):
        df = df.copy()
        df['SMA_200'] = df['Close'].rolling(window=self.sma_period).mean()
        df['RSI_5'] = self.calculate_rsi(df['Close'])
        return df

    def get_signal(self, df):
        if len(df) < (self.sma_period + 5):
            return "NONE", None

        curr_price = df['Close'].iloc[-1]
        curr_sma = df['SMA_200'].iloc[-1]
        rsi_series = df['RSI_5']
        
        # Check last 4 RSI values (consecutive decrease)
        # We need [t, t-1, t-2, t-3]
        if len(rsi_series) < 4: return "NONE", None
        
        rsi_vals = rsi_series.iloc[-4:].values # [t-3, t-2, t-1, t]
        
        current_rsi = rsi_vals[3]
        bullish_trend = curr_price > curr_sma
        consecutive_decrease = (rsi_vals[3] < rsi_vals[2] < rsi_vals[1] < rsi_vals[0])
        rsi_3_days_ago_clean = rsi_vals[0] < 60
        oversold = current_rsi < 30
        
        if bullish_trend and oversold and consecutive_decrease and rsi_3_days_ago_clean:
            return "BUY", curr_price
        elif current_rsi >= 50:
            return "EXIT", curr_price
            
        return "NONE", None

if __name__ == "__main__":
    # Test logic
    ticker = "QQQ"
    df = yf.download(ticker, period="1y", interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    strat = TripleRSIStrategy()
    df = strat.add_indicators(df)
    signal, price = strat.get_signal(df)
    print(f"Ticker: {ticker} | Signal: {signal} | Price: {price}")

