import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime
import traceback

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from smc_strategy import SmartMoneyStrategy

def run_smc_bulk_backtest():
    tickers = ["IBIT", "CLNK", "ETHE", "IREN"]
    strategy = SmartMoneyStrategy()
    
    results = []
    
    print(f"--- SMC Bulk Backtest [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ---")
    
    for ticker in tickers:
        print(f"Testing {ticker}...")
        try:
            df = yf.download(ticker, period="1y", interval="1h", progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            if df.empty:
                print(f"No data for {ticker}")
                continue
                
            df = strategy.add_indicators(df)
            df = strategy.process_logic(df)
            
            # Simple Backtest Simulation
            trades = []
            active_trade = None
            
            for idx, row in df.iterrows():
                if active_trade:
                    # Check Exit (ATR Based)
                    if active_trade['type'] == 'BUY':
                        if row['Low'] <= active_trade['sl']:
                            trades.append({'ticker': ticker, 'pnl': -1, 'win': 0})
                            active_trade = None
                        elif row['High'] >= active_trade['tp']:
                            trades.append({'ticker': ticker, 'pnl': 2, 'win': 1})
                            active_trade = None
                    else: # SELL
                        if row['High'] >= active_trade['sl']:
                            trades.append({'ticker': ticker, 'pnl': -1, 'win': 0})
                            active_trade = None
                        elif row['Low'] <= active_trade['tp']:
                            trades.append({'ticker': ticker, 'pnl': 2, 'win': 1})
                            active_trade = None
                
                if not active_trade and row['entry_signal'] in ['BUY', 'SELL']:
                    atr = row['ATR']
                    if row['entry_signal'] == 'BUY':
                        sl = row['Low'] - (1.5 * atr)
                        tp = row['High'] + (3.0 * atr)
                    else:
                        sl = row['High'] + (1.5 * atr)
                        tp = row['Low'] - (3.0 * atr)
                    
                    active_trade = {
                        'type': row['entry_signal'],
                        'entry': row['Close'],
                        'sl': sl,
                        'tp': tp
                    }
            
            if trades:
                wr = (len([t for t in trades if t['win'] == 1]) / len(trades)) * 100
                pnl = sum([t['pnl'] for t in trades])
                results.append({'ticker': ticker, 'wr': wr, 'pnl': pnl, 'count': len(trades)})
                print(f"Done {ticker}: {len(trades)} trades, {wr:.2f}% WR")
            else:
                results.append({'ticker': ticker, 'wr': 0, 'pnl': 0, 'count': 0})
                
        except Exception as e:
            print(f"Error testing {ticker}: {e}")
            traceback.print_exc()

    # Save results
    output_dir = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\smc_bulk"
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    
    res_df = pd.DataFrame(results)
    res_df.to_markdown(os.path.join(output_dir, "backtest.md"), index=False)
    print("\nBulk Results Saved.")

if __name__ == "__main__":
    run_smc_bulk_backtest()
