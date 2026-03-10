
import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np

# Add project root to path
# Add strategy folder to path for direct import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from inside_candle_strategy import InsideCandleStrategy

def run_inside_candle_backtest():
    # 1. Configuration (IBIT Specific)
    assets = ['IBIT', 'CLNK', 'ETHE', 'IREN']
    interval = '1h'
    period = '1y' 
    
    print(f"--- Inside Candle Strategy Backtest: IBIT ({period} / {interval}) ---")
    
    strategy = InsideCandleStrategy(rr=3.0, atr_period=10, atr_multiplier=1.0, use_tsl=True)
    
    all_trades = []
    report_lines = []
    
    # 2. Iterate Assets
    for ticker in assets:
        print(f"Fetching data for {ticker}...")
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
            if df.empty:
                print(f"  No data for {ticker}")
                continue
            
            # Helper for multi-index columns if they exist
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Apply Indicators
            # Calculate ATR manually or via library inside strategy class
            # We need to ensure minimal data for ATR
            if len(df) < 50:
                print(f"  Not enough data for {ticker}")
                continue
            
            # Add Indicators FIRST
            df = strategy.add_indicators(df)
                
            # Backtest
            trades = strategy.backtest(df)
            
            if not trades.empty:
                trades['ticker'] = ticker
                all_trades.append(trades)
                
                # Asset Stats
                win_rate = len(trades[trades['pnl'] > 0]) / len(trades) * 100
                total_pnl = trades['pnl'].sum()
                print(f"  {ticker}: {len(trades)} trades, WR: {win_rate:.1f}%, PnL: ${total_pnl:.2f}")
                report_lines.append(f"| {ticker} | {len(trades)} | {win_rate:.2f}% | ${total_pnl:.2f} |")
            else:
                print(f"  {ticker}: No trades.")
                report_lines.append(f"| {ticker} | 0 | 0.00% | $0.00 |")
                
        except Exception as e:
            print(f"  Error {ticker}: {e}")

    # 3. Aggregate Results
    if all_trades:
        results_df = pd.concat(all_trades, ignore_index=True)
        total_pnl = results_df['pnl'].sum()
        total_trades = len(results_df)
        win_rate = len(results_df[results_df['pnl'] > 0]) / total_trades * 100
        
        print("\n--- Portfolio Result ---")
        print(f"Total PnL: ${total_pnl:.2f}")
        print(f"Win Rate: {win_rate:.2f}%")
        
        # 4. Generate Report (Mandatory: backtest.md)
        output_dir = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\inside_candle_ibit"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        report_file = os.path.join(output_dir, "backtest.md")
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"# Inside Candle Strategy Backtest\n")
            f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Period**: {period} (1 Hour Interval)\n")
            f.write(f"**Strategy**: RR=3.0, TSL=ATR(10)*1.0\n\n")
            
            f.write("## Portfolio Summary\n")
            f.write(f"- **Total PnL**: ${total_pnl:.2f}\n")
            f.write(f"- **Total Trades**: {total_trades}\n")
            f.write(f"- **Win Rate**: {win_rate:.2f}%\n\n")
            
            f.write("## Asset Breakdown\n")
            f.write("| Ticker | Trades | Win Rate | PnL |\n")
            f.write("|---|---|---|---|\n")
            for line in report_lines:
                f.write(line + "\n")
            
            f.write("\n## Recent Trade Log\n")
            f.write(results_df[['ticker', 'entry_time', 'type', 'entry', 'exit', 'pnl']].tail(20).to_markdown(index=False))
            
        print(f"Report saved to {report_file}")
            
    else:
        print("No trades generated across portfolio.")

if __name__ == "__main__":
    run_inside_candle_backtest()
