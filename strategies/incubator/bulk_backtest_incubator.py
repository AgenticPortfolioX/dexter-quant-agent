import pandas as pd
import numpy as np
import yfinance as yf
import os
import sys
from datetime import datetime, timedelta
import pytz
from typing import Dict, List, Any

# Add the project root to sys.path to import strategies
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the strategies
from london_displacement import LondonDisplacementStrategy
from orb_15min_gap_go import ORB15MinGapGoStrategy
from orb_30min_anchor import ORB30MinAnchorStrategy
from initial_balance_80 import InitialBalance80Strategy
from noon_curve_lunchbox import NoonCurveStrategy

ASSETS = [
    "NQ=F", "ES=F", "YM=F", "RTY=F", "CL=F", "GC=F", "SI=F", 
    "EURUSD=X", "USDJPY=X", "GBPUSD=X", "AUDUSD=X", 
    "QQQ", "SPY", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "BTC-USD"
]

STRATEGIES = [
    {"name": "London Displacement", "class": LondonDisplacementStrategy, "assets": ["NQ=F", "ES=F", "YM=F", "RTY=F", "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"]},
    {"name": "15min ORB", "class": ORB15MinGapGoStrategy, "assets": ["NQ=F", "QQQ", "SPY", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN"]},
    {"name": "30min ORB", "class": ORB30MinAnchorStrategy, "assets": ["ES=F", "SPY", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]},
    {"name": "Initial Balance", "class": InitialBalance80Strategy, "assets": ["NQ=F", "ES=F", "YM=F", "RTY=F", "QQQ", "SPY"]},
    {"name": "Noon Curve", "class": NoonCurveStrategy, "assets": ["NQ=F", "ES=F"]} 
]

class BulkBacktester:
    def __init__(self, period: str = "2y"):
        self.period = period
        self.results = []
        self.report_path = "incubator_backtest_report_final.csv"
        self.tz = pytz.timezone('US/Eastern')

    def fetch_hybrid_data(self, ticker: str, interval: str = "5m") -> pd.DataFrame:
        """Fetch maximum available data for the interval, falling back to H1 if needed."""
        # 1. Try to get granular data (limited to 60d for 5m/15m)
        gran_period = "60d"
        print(f"    Fetching {interval} data (60d)...")
        df_gran = yf.download(ticker, period=gran_period, interval=interval, progress=False)
        if isinstance(df_gran.columns, pd.MultiIndex): df_gran.columns = df_gran.columns.get_level_values(0)
        
        # 2. Get H1 data for the full period (2y)
        print(f"    Fetching 1h data ({self.period})...")
        df_h1 = yf.download(ticker, period=self.period, interval="1h", progress=False)
        if isinstance(df_h1.columns, pd.MultiIndex): df_h1.columns = df_h1.columns.get_level_values(0)
        
        if df_gran.empty: return df_h1
        
        # Merge or just return gran for recent and h1 for past (for signals, we can just concat)
        # But wait, strategies expect consistent index frequency.
        # We'll return the granular data for the recent part if available.
        return df_gran

    def run(self):
        print(f"=== STARTING HYBRID BULK BACKTEST (Period: {self.period}) ===")
        
        for strat_info in STRATEGIES:
            print(f"\n--- Strategy: {strat_info['name']} ---")
            
            for asset in strat_info['assets']:
                try:
                    print(f"  Backtesting {asset}...")
                    
                    # Instantiate strategy
                    if strat_info['name'] == "Noon Curve":
                        strat = strat_info['class']()
                        # Noon Curve needs Dict of DataFrames
                        data = {}
                        for t in strat.tickers:
                            data[t] = self.fetch_hybrid_data(t, interval="5m")
                        sigs = strat.generate_signals(data)
                    else:
                        strat = strat_info['class'](ticker=asset)
                        interval = "15m" if "15min" in strat_info['name'] else ("30m" if "30min" in strat_info['name'] else "5m")
                        data = self.fetch_hybrid_data(asset, interval=interval)
                        sigs = strat.generate_signals(data)
                    
                    self.record_results(strat_info['name'], asset, sigs)
                    
                except Exception as e:
                    import traceback
                    print(f"    Error on {asset}: {str(e)}")
                    # traceback.print_exc()
        
        self.save_report()

    def record_results(self, strat_name: str, asset: str, signals: List[Dict]):
        num_trades = len(signals)
        print(f"    Found {num_trades} signals for {asset}")
        self.results.append({
            "Strategy": strat_name,
            "Asset": asset,
            "Trades": num_trades,
            "Status": "VALIDATED" if num_trades > 0 else "NO_SIGNALS"
        })

    def save_report(self):
        df = pd.DataFrame(self.results)
        df.to_csv(self.report_path, index=False)
        print(f"\nReport saved to {self.report_path}")

if __name__ == "__main__":
    tester = BulkBacktester(period="2y")
    tester.run()
