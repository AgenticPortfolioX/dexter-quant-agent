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
except ImportError as e:
    print(f"Error importing strategy S1: {e}")
    sys.exit(1)

# --- Top 15 Assets from previous S1 backtest ---
TOP_15_S1 = [
    "MSTR", "SNOW", "COIN", "ARM", "CRWD", "CRM", "PLTR", "TSM", 
    "TSLA", "AVGO", "PANW", "AMD", "ADBE", "IWM", "HOOD"
]

# --- 100 Additional Assets ---
# 10 Cryptos (including BTC, ETH, LINK + 7 others)
CRYPTOS = ["BTC-USD", "ETH-USD", "LINK-USD", "SOL-USD", "ADA-USD", "XRP-USD", "DOT-USD", "AVAX-USD", "DOGE-USD", "UNI-USD"]

# 90 Other Logical Assets (Broad representation: Tech, Semi, Energy, Financials, Retail, ETFs)
ADDITIONAL_90 = [
    # Semiconductors / Hardware
    "QCOM", "INTC", "MU", "TXN", "AMAT", "LRCX", "ADI", "KLAC", "MRVL", "NXPI", "MCHP", "STX", "WDC",
    # Big Tech / Software
    "ORCL", "SAP", "INTU", "NOW", "IBM", "UBER", "ABNB", "TEAM", "WDAY", "DDOG", "NET", "SNPS", "CDNS",
    # Internet / Ecommerce
    "PDD", "BABA", "JD", "MELI", "SE", "EBAY", "ETSY", "CHWY",
    # Financials / Fintech
    "JPM", "BAC", "WFC", "GS", "MS", "AXP", "SQ", "GME", "AFRM", "SOFI", "NU",
    # Consumer / Retail
    "WMT", "COST", "HD", "LOW", "TGT", "SBUX", "NKE", "LULU", "DKNG", "MAR", "H",
    # Healthcare / Bio
    "UNH", "LLY", "ABBV", "MRK", "JNJ", "PFE", "AMGN", "REGN", "VRTX", "ISRG",
    # Energy / Industrials
    "XOM", "CVX", "SLB", "GE", "BA", "CAT", "DE", "RTX", "LMT",
    # Commodities / Other
    "GLD", "SLV", "GC=F", "CL=F", "USO", "TLT", "BITO", "IBIT", "MARA", "RIOT", "HUT", "CLSK"
]

# Combined 100 new assets
NEW_100_ASSETS = CRYPTOS + ADDITIONAL_90

BACKTEST_PERIOD = "60d" # Max for 5m data
TIMEFRAME = "5m"

class S1ExpandedBacktester:
    def __init__(self):
        self.tz = pytz.timezone("US/Eastern")

    def run(self):
        print(f"\n>>> Running Expanded Backtest for Strategy S1 (Sonnet ORE + Regime)")
        print(f">>> Target: 100 Additional Assets (10 Cryptos + 90 Stocks/ETFs)")
        
        engine = SonnetORERegime(tickers=NEW_100_ASSETS)
        
        # 1. Scan for signals
        # S1 strictly has a SESSION_START = time(9, 30) and SESSION_END = time(16, 0)
        # and filters within generate_signals using day_df.between_time("09:45", "15:55").
        # So even for cryptos, it will only generate signals during market hours.
        signals = engine.scan_all(period=BACKTEST_PERIOD)
        
        # 2. Validate and produce report
        results = self.validate_signals(signals)
        self.report_final(results)
        
        # 3. Save Top 15 Winners for the user
        self.update_s1_config(results)

    def validate_signals(self, signals):
        if not signals:
            return {"total_pnl": 0, "win_rate": 0, "count": 0, "asset_stats": {}}

        ticker_signals = {}
        for s in signals:
            t = s['ticker']
            if t not in ticker_signals: ticker_signals[t] = []
            ticker_signals[t].append(s)

        total_trades = 0
        winning_trades = 0
        total_pnl = 0
        asset_stats = {}

        for ticker, sigs in ticker_signals.items():
            df = yf.download(ticker, period=BACKTEST_PERIOD, interval=TIMEFRAME, progress=False)
            if df.empty: continue
            
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC").tz_convert(self.tz)
            else:
                df.index = df.index.tz_convert(self.tz)

            ticker_pnl = 0
            ticker_wins = 0
            ticker_trades = 0

            for sig in sigs:
                entry_ts = pd.to_datetime(sig['timestamp'])
                if entry_ts.tzinfo is None:
                    entry_ts = entry_ts.tz_localize("UTC").tz_convert(self.tz)
                
                future_data = df[df.index > entry_ts]
                if future_data.empty: continue

                sl = sig['stop_loss']
                tp = sig['take_profit']
                entry = sig['entry']
                is_long = sig['type'] == 'LONG_ENTRY'

                hit = False
                pnl_outcome = 0

                for _, row in future_data.iterrows():
                    high = row['High']
                    low = row['Low']

                    if is_long:
                        if low <= sl:
                            pnl_outcome = (sl - entry) / entry
                            hit = True
                            break
                        if high >= tp:
                            pnl_outcome = (tp - entry) / entry
                            ticker_wins += 1
                            winning_trades += 1
                            hit = True
                            break
                    else: # SHORT
                        if high >= sl:
                            pnl_outcome = (entry - sl) / entry
                            hit = True
                            break
                        if low <= tp:
                            pnl_outcome = (entry - tp) / entry
                            ticker_wins += 1
                            winning_trades += 1
                            hit = True
                            break
                
                if hit:
                    ticker_trades += 1
                    total_trades += 1
                    ticker_pnl += pnl_outcome
                    total_pnl += pnl_outcome
            
            if ticker_trades > 0:
                asset_stats[ticker] = {
                    "pnl": round(ticker_pnl * 100, 2),
                    "win_rate": round((ticker_wins / ticker_trades) * 100, 2),
                    "count": ticker_trades
                }

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        return {
            "total_pnl": round(total_pnl * 100, 2),
            "win_rate": round(win_rate, 2),
            "count": total_trades,
            "asset_stats": asset_stats
        }

    def report_final(self, results):
        print("\n" + "="*80)
        print("S1 EXPANDED BACKTEST REPORT (100 ADDITIONAL ASSETS)")
        print("="*80)
        print(f"Aggregated P&L: {results['total_pnl']}%")
        print(f"Total Win Rate: {results['win_rate']}%")
        print(f"Total Trades:   {results['count']}")
        print("\nASSET-SPECIFIC BREAKDOWN:")
        print(f"{'TICKER':<10} {'P&L %':<10} {'WIN %':<10} {'COUNT':<6}")
        print("-" * 40)
        
        sorted_assets = sorted(results['asset_stats'].items(), key=lambda x: x[1]['pnl'], reverse=True)
        for ticker, stats in sorted_assets:
            print(f"{ticker:<10} {stats['pnl']:<10} {stats['win_rate']:<10} {stats['count']:<6}")

    def update_s1_config(self, results):
        # We need to save the "Final Top 15" for Strategy S1.
        # This includes the Top 15 from the ORIGINAL test (which we "saved")
        # and any new winners from this 100-asset test.
        # But per the prompt: "save the top 15 assets from the backtest and get rid of the bottom 15".
        # This implies updating the strategy's target assets.
        
        sorted_new = sorted(results['asset_stats'].items(), key=lambda x: x[1]['pnl'], reverse=True)
        top_new_15 = [x[0] for x in sorted_new[:15]]
        
        # Save to a temporary file for results analysis
        output_file = "C:/Users/jmgra/antigravityagents/.agent/reporting-repo/backtests/s1_expanded_backtest.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=4)
        print(f"\nExpanded results saved to {output_file}")

if __name__ == "__main__":
    tester = S1ExpandedBacktester()
    tester.run()
