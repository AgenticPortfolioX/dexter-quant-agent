import pandas as pd
from sfp import SFPStrategy
import time

# 25 Logical Assets covering Crypto, Forex, Indices, Metals
ASSETS = [
    # Crypto (High Volatility)
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "LTC-USD",
    # Forex Majors (Mean Reverting)
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X",
    # Commodities (Trend/Sweep)
    "GC=F", "SI=F", "CL=F",
    # Indices (Structural)
    "^GSPC", "^NDX", "^DJI", "^RUT", "^IXIC"
]

def run_bulk_backtest():
    results = []
    print(f"Starting Bulk 2-Year SFP Backtest on {len(ASSETS)} assets...")
    print("-" * 60)
    
    for ticker in ASSETS:
        try:
            print(f"Testing {ticker}...", end=" ", flush=True)
            strategy = SFPStrategy(ticker)
            # Use optimized parameters from Step 8: Vol=2.0, Retrace=0.618, Iso=5
            res = strategy.run_long_term_backtest(period="2y", vol_t=2.0, retrace_l=0.618, iso_y=5)
            results.append(res)
            print(f"Done. Trades: {res['trades']} | Win Rate: {res['win_rate']:.1f}% | ROI: {res['roi']:.1f}%")
            time.sleep(1) # Polite delay for yfinance
        except Exception as e:
            print(f"Failed: {e}")
            results.append({'symbol': ticker, 'trades': 0, 'win_rate': 0.0, 'pnl': 0.0, 'roi': 0.0, 'error': str(e)})

    # Consolidate
    df = pd.DataFrame(results)
    df = df.sort_values('roi', ascending=False)
    
    # Save
    csv_path = "sfp_bulk_results_2y.csv"
    df.to_csv(csv_path, index=False)
    
    print("-" * 60)
    print(f"Bulk Backtest Complete. Results saved to {csv_path}")
    print("\n--- Top 5 Performers ---")
    print(df[['symbol', 'trades', 'win_rate', 'roi']].head())

if __name__ == "__main__":
    run_bulk_backtest()
