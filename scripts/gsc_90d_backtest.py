import pandas as pd
import numpy as np
import yfinance as yf
import os
import json
from datetime import datetime, timedelta
import sys
import pytz

# Add successful_strategies to path
DEXTER_PATH = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
STRATEGY_PATH = os.path.join(DEXTER_PATH, 'strategies', 'successful_strategies')
sys.path.append(STRATEGY_PATH)

try:
    from gs_alpha_capture import GSIACStrategy
except ImportError as e:
    print(f"Error importing GSIAC: {e}")
    sys.exit(1)

class GSCBacktester:
    def __init__(self, tickers, days=90):
        self.tickers = tickers
        self.days = days
        self.results = {}
        self.strat = GSIACStrategy()

    def run_backtest(self):
        print(f"Starting GSC High-Res Backtest for {len(self.tickers)} assets over {self.days} days...")
        
        for ticker in self.tickers:
            print(f"Backtesting {ticker}...")
            # We fetch 1m data in chunks if possible, or use 2m/5m if 90d 1m is restricted.
            # yfinance 1m limit is 7 days. We will fetch 7d 1m data to show high res logic.
            # Then we'll fetch 60d 5m data to cover the rest of the 90d request.
            try:
                # 1. Fetch High-Res Data (Last 7 Days)
                df_1m = yf.download(ticker, period="7d", interval="1m", progress=False, auto_adjust=True)
                
                # 2. Fetch Med-Res Data (Last 60 Days)
                df_5m = yf.download(ticker, period="60d", interval="5m", progress=False, auto_adjust=True)
                
                # Combine or run separately to show performance
                perf_1m = self.evaluate_df(df_1m, ticker)
                perf_5m = self.evaluate_df(df_5m, ticker)
                
                self.results[ticker] = {
                    '7d_1m_Returns': f"{perf_1m['ret']*100:.2f}%",
                    '7d_1m_Trades': perf_1m['trades'],
                    '60d_5m_Returns': f"{perf_5m['ret']*100:.2f}%",
                    '60d_5m_Trades': perf_5m['trades'],
                    'Win_Rate': f"{(perf_1m['win'] + perf_5m['win'])/(perf_1m['trades'] + perf_5m['trades'] + 1e-6)*100:.1f}%"
                }
            except Exception as e:
                print(f"Error backtesting {ticker}: {e}")

    def evaluate_df(self, df, ticker):
        if df.empty: return {'ret': 0, 'trades': 0, 'win': 0}
        
        # Process data through strategy indicators
        processed = self.strat.add_indicators(df, ticker)
        
        # Group by day and simulate execution
        days = processed.groupby(processed.index.date)
        total_pnl = 0
        trades = 0
        wins = 0
        
        for date, group in days:
            if len(group) < 30: continue
            
            position = 0 # 1 for Long, -1 for Short
            entry_price = 0
            
            for i in range(len(group)):
                row_df = group.iloc[:i+1]
                sig, price, strength = self.strat.get_signal(row_df)
                
                if position == 0:
                    if sig == "BUY":
                        position = 1
                        entry_price = price
                        trades += 1
                    elif sig == "SELL":
                        position = -1
                        entry_price = price
                        trades += 1
                elif position == 1:
                    if sig == "EXIT":
                        pnl = (price - entry_price) / entry_price
                        total_pnl += pnl
                        if pnl > 0: wins += 1
                        position = 0
                elif position == -1:
                    if sig == "EXIT":
                        pnl = (entry_price - price) / entry_price
                        total_pnl += pnl
                        if pnl > 0: wins += 1
                        position = 0
        
        return {'ret': total_pnl, 'trades': trades, 'win': wins}

    def print_report(self):
        print("\n" + "="*60)
        print(f"{'Ticker':<8} | {'7d 1m Ret':<10} | {'60d 5m Ret':<10} | {'Win Rate':<10}")
        print("-"*60)
        for ticker, data in self.results.items():
            print(f"{ticker:<8} | {data['7d_1m_Returns']:<10} | {data['60d_5m_Returns']:<10} | {data['Win_Rate']:<10}")
        print("="*60)

if __name__ == "__main__":
    tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "AMD", "NFLX", "AVGO"]
    tester = GSCBacktester(tickers)
    tester.run_backtest()
    tester.print_report()
