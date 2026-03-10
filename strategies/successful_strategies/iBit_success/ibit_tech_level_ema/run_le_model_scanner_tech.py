
import os
import sys
import pandas as pd
from datetime import datetime

# Add strategy folder to path for direct import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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
from le_model_visualization import plot_le_model_chart

def run_le_model_scanner():
    """
    Implements Le Model Tech Scanner (Successful Strategy):
    - Targeted Watchlist: AAPL, TSLA, META, MSFT (Proven Performers)
    - Runs full pipeline.
    - Generates Performance Report (Sharpe, WR, PnL).
    """
    # Expanded Watchlist for Multi-Ticker Performance Analysis
    watchlist = ['IBIT', 'CLNK', 'ETHE', 'IREN', 'AAPL', 'TSLA', 'META', 'MSFT', 'GOOGL']
    
    print(f"--- Le Model Scanner: {datetime.now()} ---")
    
    results = []
    
    for ticker in watchlist:
        try:
            # 1. Data Prep
            data_dict = fetch_multi_timeframe_data(ticker, period="60d")
            if not data_dict: continue
            
            # 2. Indicators
            df = calculate_indicators(data_dict)
            df = calculate_atr_vol(df)
            
            # 3. Logic Application
            df = apply_anchor_filter(df)
            df = detect_ema_touch(df)
            df = detect_pivot_levels(df)
            df = check_volume_confirmation(df)
            df = apply_time_filter(df) # Time filter modifies signals logic prep
            df = generate_signals(df) # Generate actual entry flags
            
            # 4. Backtest (10m bars over last 60d)
            # Need to drop NaNs from indicators before backtest loop?
            df_clean = df.dropna()
            
            trades = run_backtest_with_tsl(df_clean)
            
            # 5. Performance Metrics
            total_trades = len(trades)
            win_rate = 0
            pnl = 0
            sharpe = 0
            
            if total_trades > 0:
                wins = trades[trades['pnl'] > 0]
                win_rate = len(wins) / total_trades * 100
                pnl = trades['pnl'].sum()
                
                # Sharpe (Daily returns approx?)
                # Just simplified Risk/Reward capture for scanner sorting
                avg_pnl = trades['pnl'].mean()
                std_pnl = trades['pnl'].std()
                sharpe = avg_pnl / std_pnl if std_pnl != 0 else 0
                
            # 6. Live Signal Check (Last Bar)
            last_bar = df.iloc[-1]
            signal_active = last_bar['Long_Entry_Signal'] or last_bar['Short_Entry_Signal']
            
            results.append({
                'Ticker': ticker,
                'Trades': total_trades,
                'Win Rate': win_rate,
                'Total PnL': pnl,
                'Sharpe': sharpe,
                'Signal Active': signal_active
            })
            
            # Plot for top assets?
            if total_trades > 5:
                plot_le_model_chart(df, ticker)
            
        except Exception as e:
            print(f"Error Scanner {ticker}: {e}")

    # Results Table
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df = res_df.sort_values('Sharpe', ascending=False)
        print("\n--- Scanner Results ---")
        print(res_df.to_markdown(index=False))
        
        # Save Report
        output_dir = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\ibit_tech_level_ema"
        if not os.path.exists(output_dir): os.makedirs(output_dir)
        
        # Mandatory Backtest Filing
        with open(os.path.join(output_dir, "backtest.md"), 'w') as f:
             f.write(f"# Le Model Scanner Report (Multi-Ticker Bulk Backtest)\n")
             f.write(f"**Date**: {datetime.now()}\n\n")
             f.write(res_df.to_markdown(index=False))
             
        print(f"Report saved to {output_dir}/backtest.md")
    else:
        print("No results generated.")

if __name__ == "__main__":
    run_le_model_scanner()
