import sys
import os

# Add paths
sys.path.append(os.path.join(os.getcwd(), 'rsi_hybrid_reversion'))
sys.path.append(os.path.join(os.getcwd(), 'volatility_contraction'))

from rsi_hybrid_reversion.backtest import Backtester as RsiBacktester
from volatility_contraction.backtest import Backtester as VolBacktester

def run_secondary():
    print("Running Secondary Backtests (Variations)...")
    
    # 1. RSI Hybrid: Forex and Indices
    print("\n--- RSI Hybrid Reversion: EUR/USD & SPY ---")
    rsi_bt = RsiBacktester(config_path='rsi_hybrid_reversion/config.yaml')
    try:
        rsi_bt.run_backtest('EUR/USD', days=30)
        rsi_bt.run_backtest('SPY', days=30)
    except Exception as e:
        print(f"RSI Secondary Failed: {e}")

    # 2. Volatility Contraction: Low Timeframe (5m)
    print("\n--- Volatility Contraction: ETH/USDT (5m) ---")
    # Need to override timeframe in config or runtime
    # We can hack the config object
    vol_bt = VolBacktester(config_path='volatility_contraction/config.yaml')
    vol_bt.market_data.timeframe = '5m' # Override
    try:
        vol_bt.run_backtest('ETH/USDT', days=10)
    except Exception as e:
        print(f"Vol Secondary Failed: {e}")

if __name__ == "__main__":
    run_secondary()
