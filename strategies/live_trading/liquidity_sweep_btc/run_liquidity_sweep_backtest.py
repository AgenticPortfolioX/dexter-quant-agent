
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
import traceback

# Add current directory to path to allow local import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from liquidity_sweep_strategy import LiquiditySweepStrategy

def run_liquidity_sweep_backtest():
    # Load Data (Local Directory)
    data_dir = os.path.dirname(os.path.abspath(__file__))
    
    tickers = ["BTCUSD"]
    
    # Report Generation
    full_report = "# BTC Liquidity Sweep Strategy - Finalized Report\n"
    full_report += f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    full_report += "**Strategy**: SMC Liquidity Sweep + MSS + FVG (Optimized for BTC)\n"
    full_report += "**Asset**: BTC/USD (1h Execution / 1d Context)\n\n"
    
    # NOTE: With 1d context, lookback_15m=48 means 48 days lookback for Swing Points.
    # This is reasonable for high timeframe swing trading.
    strategy = LiquiditySweepStrategy(lookback_15m=20) 
    
    for ticker in tickers:
        print(f"Backtesting {ticker}...")
        
        # 1h Data
        df_exec_path = os.path.join(data_dir, f"{ticker}_1h_sweep.pkl")
        df_ctxt_path = os.path.join(data_dir, f"{ticker}_1d_sweep.pkl")
        
        if not os.path.exists(df_exec_path) or not os.path.exists(df_ctxt_path):
            print(f"  Data files not found for {ticker}")
            full_report += f"## {ticker}\n- Data not found.\n\n"
            continue
            
        try:
            df_exec = pd.read_pickle(df_exec_path)
            df_ctxt = pd.read_pickle(df_ctxt_path)
            
            # Run Backtest
            trades_df = strategy.backtest(df_exec, df_ctxt)
            
            total_trades = len(trades_df)
            full_report += f"## {ticker}\n"
            full_report += f"- **Total Trades**: {total_trades}\n"
            
            if total_trades > 0:
                wins = trades_df[trades_df['pnl'] > 0]
                losses = trades_df[trades_df['pnl'] <= 0]
                
                win_rate = (len(wins) / total_trades) * 100
                total_pnl = trades_df['pnl'].sum()
                
                gross_profit = wins['pnl'].sum()
                gross_loss = abs(losses['pnl'].sum())
                profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
                
                full_report += f"- **Win Rate**: {win_rate:.2f}%\n"
                full_report += f"- **Profit Factor**: {profit_factor:.2f}\n"
                full_report += f"- **Total PnL**: {total_pnl:.5f}\n"
                
                full_report += "\n### Trade Log\n"
                
                # Manual Table
                cols = ['entry_time', 'exit_time', 'type', 'entry', 'exit', 'pnl', 'outcome']
                rows = "| " + " | ".join(cols) + " |\n| " + " | ".join(["---"] * len(cols)) + " |\n"
                for idx, row in trades_df.tail(10).iterrows():
                     rows += "| " + " | ".join([str(row[c]) for c in cols]) + " |\n"
                full_report += rows
                full_report += "\n"
            else:
                full_report += "- No trades generated.\n\n"
                
        except Exception as e:
            print(f"  Error processing {ticker}: {e}")
            traceback.print_exc()
            full_report += f"- Error: {e}\n\n"

    # Save
    output_dir = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\liquidity_sweep_btc"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    report_file = os.path.join(output_dir, "backtest.md")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(full_report)
        
    print(full_report)
    print(f"Saved to {report_file}")

if __name__ == "__main__":
    run_liquidity_sweep_backtest()
