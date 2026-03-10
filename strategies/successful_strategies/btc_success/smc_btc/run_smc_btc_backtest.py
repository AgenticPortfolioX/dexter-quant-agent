import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from smc_strategy import SmartMoneyStrategy

def run_smc_btc_backtest():
    ticker = "BTC-USD"
    strategy = SmartMoneyStrategy()
    
    print(f"--- SMC BTC Backtest [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ---")
    
    try:
        df = yf.download(ticker, period="1y", interval="1h", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        if df.empty:
            print(f"No data for {ticker}")
            return
            
        df = strategy.add_indicators(df)
        df = strategy.process_logic(df)
        
        # Simple Backtest Simulation
        trades = []
        active_trade = None
        
        for idx, row in df.iterrows():
            if active_trade:
                if active_trade['type'] == 'BUY':
                    if row['Low'] <= active_trade['sl']:
                        trades.append({'pnl': -1})
                        active_trade = None
                    elif row['High'] >= active_trade['tp']:
                        trades.append({'pnl': 2})
                        active_trade = None
                else: # SELL
                    if row['High'] >= active_trade['sl']:
                        trades.append({'pnl': -1})
                        active_trade = None
                    elif row['Low'] <= active_trade['tp']:
                        trades.append({'pnl': 2})
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
            wr = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100
            pnl = sum([t['pnl'] for t in trades])
            print(f"RESULTS: {len(trades)} trades, {wr:.2f}% WR, Total PnL: {pnl}")
        else:
            print("No trades triggered.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_smc_btc_backtest()
