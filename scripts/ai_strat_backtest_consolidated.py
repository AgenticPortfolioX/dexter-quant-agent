import pandas as pd
import numpy as np
import yfinance as yf
import os
import sys
import json
from datetime import datetime, timedelta
import pytz

# Add strategy path
sys.path.append(os.path.join(os.getcwd(), 'strategies', 'Ai-strats'))

try:
    from sonnet_ore_regime import SonnetORERegime
    from opus_keltner_exhaust import OpusKeltnerExhaust
    from gemini_vortex_squeeze import GeminiVortexSqueeze
except ImportError as e:
    print(f"Error importing strategies: {e}")
    sys.exit(1)

# 30 Logical Assets
TICKERS = [
    "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD", "SMCI", "AVGO",
    "NFLX", "ADBE", "CRM", "PANW", "CRWD", "MSTR", "COIN", "HOOD", "PYPL", "PLTR",
    "ROKU", "TSM", "ARM", "SHOP", "SNOW", "SQ", "U", "QQQ", "IWM", "SPY"
]

BACKTEST_PERIOD = "60d" # Max for 5m data
TIMEFRAME = "5m"

class AIStratBacktester:
    def __init__(self):
        self.results = {}
        self.tz = pytz.timezone("US/Eastern")

    def run_backtest(self):
        strategies = {
            "S1": SonnetORERegime(tickers=TICKERS),
            "O1": OpusKeltnerExhaust(tickers=TICKERS),
            "G1": GeminiVortexSqueeze(tickers=TICKERS)
        }

        consolidated_results = {}

        for label, engine in strategies.items():
            print(f"\n>>> Backtesting Strategy: {label} ({engine.__class__.__name__})")
            signals = engine.scan_all(period=BACKTEST_PERIOD)
            
            strat_results = self.validate_signals(signals)
            consolidated_results[label] = strat_results

        self.report_final(consolidated_results)

    def validate_signals(self, signals):
        if not signals:
            return {"total_pnl": 0, "win_rate": 0, "count": 0, "asset_pnl": {}}

        # Group signals by ticker to fetch data once
        ticker_signals = {}
        for s in signals:
            t = s['ticker']
            if t not in ticker_signals: ticker_signals[t] = []
            ticker_signals[t].append(s)

        total_trades = 0
        winning_trades = 0
        total_pnl = 0
        asset_pnl = {}

        for ticker, sigs in ticker_signals.items():
            print(f"  Validating {len(sigs)} signals for {ticker}...")
            # Fetch 60d 5m data to check outcomes
            df = yf.download(ticker, period=BACKTEST_PERIOD, interval=TIMEFRAME, progress=False)
            if df.empty: continue
            
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC").tz_convert(self.tz)
            else:
                df.index = df.index.tz_convert(self.tz)

            ticker_pnl = 0
            for sig in sigs:
                entry_ts = pd.to_datetime(sig['timestamp'])
                # If timestamp is naive or string with Z, ensure proper conversion
                if entry_ts.tzinfo is None:
                    entry_ts = entry_ts.tz_localize("UTC").tz_convert(self.tz)
                
                # Check data AFTER entry_ts
                future_data = df[df.index > entry_ts]
                if future_data.empty: continue

                sl = sig['stop_loss']
                tp = sig['take_profit']
                entry = sig['entry']
                is_long = sig['type'] == 'LONG_ENTRY'

                trade_outcome = 0
                hit = False

                for _, row in future_data.iterrows():
                    high = row['High']
                    low = row['Low']

                    if is_long:
                        if low <= sl:
                            trade_outcome = (sl - entry) / entry
                            hit = True
                            break
                        if high >= tp:
                            trade_outcome = (tp - entry) / entry
                            winning_trades += 1
                            hit = True
                            break
                    else: # SHORT
                        if high >= sl:
                            trade_outcome = (entry - sl) / entry
                            hit = True
                            break
                        if low <= tp:
                            trade_outcome = (entry - tp) / entry
                            winning_trades += 1
                            hit = True
                            break
                
                if hit:
                    total_trades += 1
                    total_pnl += trade_outcome
                    ticker_pnl += trade_outcome
            
            asset_pnl[ticker] = round(ticker_pnl * 100, 2)

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        return {
            "total_pnl": round(total_pnl * 100, 2),
            "win_rate": round(win_rate, 2),
            "count": total_trades,
            "asset_pnl": asset_pnl
        }

    def report_final(self, results):
        report_path = "C:/Users/jmgra/antigravityagents/.agent/reporting-repo/backtests/backtest_results_ai_strats.json"
        with open(report_path, "w") as f:
            json.dump(results, f, indent=4)
        
        print("\n" + "="*80)
        print("FINAL AI-STRATS BACKTEST REPORT (S1, O1, G1)")
        print("="*80)
        
        for label, res in results.items():
            print(f"\n--- Strategy {label} Results ---")
            print(f"Aggregated P&L: {res['total_pnl']}%")
            print(f"Win Rate %:     {res['win_rate']}%")
            print(f"Signal Count:   {res['count']}")
            print(f"Length:         {BACKTEST_PERIOD}")
            
            # Top 3 Assets
            sorted_assets = sorted(res['asset_pnl'].items(), key=lambda x: x[1], reverse=True)
            print(f"Top 3 Assets P&L: {', '.join([f'{k}: {v}%' for k, v in sorted_assets[:3]])}")
            print(f"Full Asset P&L: {res['asset_pnl']}")
            print("-" * 40)
        
        print(f"\nFull results saved to {report_path}")

if __name__ == "__main__":
    tester = AIStratBacktester()
    tester.run_backtest()
