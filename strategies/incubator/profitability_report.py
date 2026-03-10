import pandas as pd
import numpy as np
import yfinance as yf
import os
import sys
from datetime import datetime, timedelta, time
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

STRATEGIES = [
    {"name": "London Displacement", "class": LondonDisplacementStrategy, "assets": ["NQ=F", "ES=F", "YM=F", "GBPUSD=X", "USDJPY=X"]},
    {"name": "15min ORB", "class": ORB15MinGapGoStrategy, "assets": ["QQQ", "NVDA", "TSLA", "MSFT", "AAPL"]},
    {"name": "30min ORB", "class": ORB30MinAnchorStrategy, "assets": ["ES=F", "SPY", "AAPL", "MSFT", "NVDA"]},
    {"name": "Initial Balance", "class": InitialBalance80Strategy, "assets": ["NQ=F", "ES=F", "YM=F", "RTY=F", "QQQ"]},
    {"name": "Noon Curve", "class": NoonCurveStrategy, "assets": ["NQ=F", "ES=F"]} 
]

class ProfitabilityBacktester:
    def __init__(self, period: str = "60d"):
        self.period = period # yfinance limit for intraday
        self.results = []
        self.report_path = "incubator_profitability_report.csv"
        self.tz = pytz.timezone('US/Eastern')

    def fetch_data(self, ticker: str, interval: str) -> pd.DataFrame:
        df = yf.download(ticker, period=self.period, interval=interval, progress=False)
        if df.empty: return df
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(self.tz)
        else:
            df.index = df.index.tz_convert(self.tz)
        return df

    def simulate_trade(self, df: pd.DataFrame, signal: Dict) -> Dict:
        """Simulates a trade outcome based on SL/TP."""
        entry_time = signal['time']
        side = signal['side']
        entry_price = signal['entry']
        sl = signal['sl']
        tp = signal.get('tp', entry_price * 1.01 if side == 'Long' else entry_price * 0.99)
        
        # Look at data AFTER entry
        post_trade = df[df.index > entry_time]
        
        for t, row in post_trade.iterrows():
            if side == "Long":
                if row['Low'] <= sl: return {"result": "LOSS", "exit_time": t, "exit_price": sl}
                if row['High'] >= tp: return {"result": "WIN", "exit_time": t, "exit_price": tp}
            else: # Short
                if row['High'] >= sl: return {"result": "LOSS", "exit_time": t, "exit_price": sl}
                if row['Low'] <= tp: return {"result": "WIN", "exit_time": t, "exit_price": tp}
            
            # Time-based exit (EO Day)
            if t.time() >= time(15, 50):
                pnl = (row['Close'] - entry_price) if side == "Long" else (entry_price - row['Close'])
                return {"result": "WIN" if pnl > 0 else "LOSS", "exit_time": t, "exit_price": row['Close']}
                
        return {"result": "OPEN", "exit_time": None, "exit_price": None}

    def run(self):
        print(f"=== STARTING PROFITABILITY BACKTEST ===")
        
        for strat_info in STRATEGIES:
            print(f"\n--- Strategy: {strat_info['name']} ---")
            
            for asset in strat_info['assets']:
                try:
                    print(f"  Testing {asset}...")
                    
                    if strat_info['name'] == "London Displacement":
                        df = self.fetch_data(asset, "5m")
                        strat = strat_info['class'](ticker=asset)
                        sigs = strat.generate_signals(df)
                        sim_df = df
                        
                    elif strat_info['name'] == "15min ORB":
                        data = {
                            "15m": self.fetch_data(asset, "15m"),
                            "1m": self.fetch_data(asset, "1m")
                        }
                        strat = strat_info['class'](ticker=asset)
                        sigs = strat.generate_signals(data)
                        sim_df = data["1m"]
                        
                    elif strat_info['name'] == "30min ORB":
                        data = {
                            "30m": self.fetch_data(asset, "30m"),
                            "5m": self.fetch_data(asset, "5m")
                        }
                        strat = strat_info['class'](ticker=asset)
                        sigs = strat.generate_signals(data)
                        sim_df = data["5m"]
                        
                    elif strat_info['name'] == "Initial Balance":
                        df = self.fetch_data(asset, "5m")
                        strat = strat_info['class'](ticker=asset)
                        sigs = strat.generate_signals(df)
                        sim_df = df
                        
                    elif strat_info['name'] == "Noon Curve":
                        data = {
                            "NQ=F": self.fetch_data("NQ=F", "5m"),
                            "ES=F": self.fetch_data("ES=F", "5m")
                        }
                        strat = strat_info['class']()
                        sigs = strat.generate_signals(data)
                        sim_df = data["NQ=F"]
                    
                    if not sigs:
                        self.results.append({"Strategy": strat_info['name'], "Asset": asset, "WinRate": "0%", "Trades": 0, "Status": "NO_SIGNALS"})
                        continue

                    wins = 0
                    total = 0
                    for s in sigs:
                        res = self.simulate_trade(sim_df, s)
                        if res['result'] != "OPEN":
                            total += 1
                            if res['result'] == "WIN": wins += 1
                    
                    win_rate = (wins / total * 100) if total > 0 else 0
                    self.results.append({
                        "Strategy": strat_info['name'],
                        "Asset": asset,
                        "WinRate": f"{win_rate:.2f}%",
                        "Trades": total,
                        "Status": "COMPLETE"
                    })
                    print(f"    {win_rate:.2f}% Win Rate ({wins}/{total})")
                    
                except Exception as e:
                    print(f"    Error on {asset}: {str(e)}")
        
        self.save_report()

    def save_report(self):
        df = pd.DataFrame(self.results)
        df.to_csv(self.report_path, index=False)
        print(f"\nReport saved to {self.report_path}")

if __name__ == "__main__":
    tester = ProfitabilityBacktester()
    tester.run()
