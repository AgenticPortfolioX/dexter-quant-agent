import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime

# Path logic for strategy imports
strategy_dir = os.path.join(os.getcwd(), 'strategies', 'successful_strategies', 'btc_tech_level_ema')
sys.path.append(strategy_dir)

from le_model_data_prep import fetch_multi_timeframe_data
from le_model_indicators import calculate_indicators
from le_model_atr_vol import calculate_atr_vol
from le_model_anchor import apply_anchor_filter
from le_model_e_touch import detect_ema_touch
from le_model_pivots import detect_pivot_levels
from le_model_volume import check_volume_confirmation
from le_model_signals import generate_signals
from le_model_time_filter import apply_time_filter
from le_model_backtest import run_backtest_with_tsl

ASSETS = [
    "SPY", "QQQ", "DIA", "IWM", 
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
    "GC=F", "SI=F", "CL=F",
    "BTC-USD", "ETH-USD",
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL"
]

def run_bulk_le_backtest():
    results = []
    print("\n" + "="*60)
    print("      LE MODEL TECH BULK BACKTEST (2 YEARS)")
    print("="*60)

    for ticker in ASSETS:
        print(f"Processing {ticker}...", end=" ", flush=True)
        try:
            # 1. Data Prep (2y history) - Use 1h data as primary for 2-year history
            # yfinance only gives 5m/10m for 60d.
            df_primary = yf.download(ticker, period="2y", interval="1h", progress=False, auto_adjust=True)
            if df_primary.empty:
                print("FAILED (No data)")
                continue
            
            if isinstance(df_primary.columns, pd.MultiIndex):
                df_primary.columns = df_primary.columns.get_level_values(0)

            # Localize and convert to Eastern for strategy logic
            if df_primary.index.tz is None:
                df_primary = df_primary.tz_localize('UTC')
            df_primary = df_primary.tz_convert('US/Eastern')

            # Simulate "Multi-Timeframe" with 1h primary and a shifted anchor
            # Since we are on 1h, we will use it for all logic.
            data_dict = {
                'data_10m': df_primary, # Using 1h as primary
                'data_1h': df_primary.shift(1) # Using previous 1h as anchor
            }

            # 2. Indicators & Pipeline (Adapted for 1h)
            df = calculate_indicators(data_dict)
            df = calculate_atr_vol(df)
            df = apply_anchor_filter(df)
            df = detect_ema_touch(df)
            df = detect_pivot_levels(df)
            df = check_volume_confirmation(df)
            df = apply_time_filter(df) 
            df = generate_signals(df) 

            # 3. Execution (1h bars over last 2y)
            df_clean = df.dropna()
            trades = run_backtest_with_tsl(df_clean)

            # 4. Metrics
            total_trades = len(trades)
            win_rate = 0
            total_pnl = 0
            sharpe = 0

            if total_trades > 0:
                wins = trades[trades['pnl'] > 0]
                win_rate = len(wins) / total_trades * 100
                total_pnl = trades['pnl'].sum()
                avg_pnl = trades['pnl'].mean()
                std_pnl = trades['pnl'].std()
                sharpe = avg_pnl / std_pnl if std_pnl != 0 else 0

                print(f"DONE. Trades: {total_trades} | WR: {win_rate:.1f}% | P/L: ${total_pnl:,.2f}")
            else:
                print("DONE. No trades.")

            results.append({
                'Ticker': ticker,
                'total_trades': total_trades,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'sharpe': sharpe
            })

        except Exception as e:
            print(f"ERROR: {e}")

    # Summary report
    if not results: return
    res_df = pd.DataFrame(results)
    
    import os
    REPORTING_PATH = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\backtests"
    if not os.path.exists(REPORTING_PATH):
        os.makedirs(REPORTING_PATH, exist_ok=True)
        
    output_path = os.path.join(REPORTING_PATH, 'LE_Model_Expanded_Results.csv')
    res_df.to_csv(output_path, index=False)
    
    print("\n" + "="*60)
    print("      FINAL AGGREGATE PERFORMANCE (LE MODEL)")
    print("="*60)
    print(f"Total Net P/L: ${res_df['total_pnl'].sum():,.2f}")
    print(f"Total Trades:  {res_df['total_trades'].sum()}")
    print(f"Avg Win Rate:  {res_df[res_df['total_trades']>0]['win_rate'].mean():.1f}%")
    print("="*60)

if __name__ == "__main__":
    run_bulk_le_backtest()
