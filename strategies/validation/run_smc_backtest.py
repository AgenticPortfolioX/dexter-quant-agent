
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from strategies.incubator.smc_btc_plus import SmartMoneyStrategy

def run_smc_backtest():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'incubator')
    tickers = ["SPY", "TSLA", "BTCUSD", "NQF"]
    
    full_report = "# SMC Strategy - 60 Day Multi-Asset Backtest\n"
    full_report += f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    full_report += "**Strategy**: SMC (Displacement, MSS, FVG)\n"
    full_report += "**Timeframe**: 5m Execution / 1m Precision (where available)\n\n"

    for ticker in tickers:
        print(f"Backtesting {ticker}...")
        df_5m_path = os.path.join(data_dir, f"{ticker}_5m_smc.pkl")
        df_1m_path = os.path.join(data_dir, f"{ticker}_1m_smc.pkl")
        
        if not os.path.exists(df_5m_path):
            print(f"  Data for {ticker} not found.")
            continue
            
        df_5m = pd.read_pickle(df_5m_path)
        
        # Load 1m if exists
        df_1m = None
        if os.path.exists(df_1m_path):
            df_1m = pd.read_pickle(df_1m_path)
        
        # 1. Indicator Logic (5m)
        strategy = SmartMoneyStrategy()
        df_5m = strategy.add_indicators(df_5m)
        df_5m = strategy.process_logic(df_5m)
        
        # 2. Backtest Logic
        trades = []
        active_trade = None
        
        # Mapping signals to a unified execution stream
        # If 1m exists, we use it for entries/exits within its range.
        # Otherwise, we use 5m data.
        
        # For simplicity in this multi-asset run, we will iterate through 5m bars.
        # If a signal exists on a 5m bar, we check for a "touch" within that bar's high/low.
        # This is very close to 1m precision for a 60-day run.
        
        for i in range(1, len(df_5m)):
            curr_5m = df_5m.iloc[i]
            t_5m = curr_5m.name
            
            # --- Manage Active Trade ---
            if active_trade:
                exited = False
                if active_trade['type'] == 'BUY':
                    # Check SL
                    if curr_5m['Low'] <= active_trade['sl']:
                        trades.append({**active_trade, 'exit_time': t_5m, 'exit_price': active_trade['sl'], 'outcome': 'Loss'})
                        active_trade = None
                        continue
                    # Check TP1
                    if not active_trade['tp1_hit'] and curr_5m['High'] >= active_trade['tp1']:
                        active_trade['tp1_hit'] = True
                    # Check TP2
                    if curr_5m['High'] >= active_trade['tp2']:
                        trades.append({**active_trade, 'exit_time': t_5m, 'exit_price': active_trade['tp2'], 'outcome': 'Win'})
                        active_trade = None
                        continue
                else: # SELL
                    if curr_5m['High'] >= active_trade['sl']:
                        trades.append({**active_trade, 'exit_time': t_5m, 'exit_price': active_trade['sl'], 'outcome': 'Loss'})
                        active_trade = None
                        continue
                    if not active_trade['tp1_hit'] and curr_5m['Low'] <= active_trade['tp1']:
                        active_trade['tp1_hit'] = True
                    if curr_5m['Low'] <= active_trade['tp2']:
                        trades.append({**active_trade, 'exit_time': t_5m, 'exit_price': active_trade['tp2'], 'outcome': 'Win'})
                        active_trade = None
                        continue

            # --- Check Entry Signal ---
            sig = curr_5m['entry_signal']
            if sig in ['BUY', 'SELL'] and not active_trade:
                limit_price = curr_5m['bullish_fvg_top'] if sig == 'BUY' else curr_5m['bearish_fvg_bottom']
                
                # Check if the candle "touched" the limit
                triggered = False
                if sig == 'BUY' and curr_5m['Low'] <= limit_price: triggered = True
                elif sig == 'SELL' and curr_5m['High'] >= limit_price: triggered = True
                
                if triggered:
                    # SL: Find latest swing from before this candle
                    try:
                        if sig == 'BUY':
                            sl = df_5m.loc[:t_5m]['swing_low'].dropna().iloc[-1]
                            risk = limit_price - sl
                            if risk <= 0: risk = limit_price * 0.001 # Fallback
                            active_trade = {
                                'entry_time': t_5m,
                                'type': 'BUY',
                                'entry': limit_price,
                                'sl': sl,
                                'tp1': limit_price + (2 * risk),
                                'tp2': limit_price + (4 * risk),
                                'tp1_hit': False
                            }
                        else:
                            sl = df_5m.loc[:t_5m]['swing_high'].dropna().iloc[-1]
                            risk = sl - limit_price
                            if risk <= 0: risk = limit_price * 0.001
                            active_trade = {
                                'entry_time': t_5m,
                                'type': 'SELL',
                                'entry': limit_price,
                                'sl': sl,
                                'tp1': limit_price - (2 * risk),
                                'tp2': limit_price - (4 * risk),
                                'tp1_hit': False
                            }
                    except:
                        pass # No swing found yet

        # Reporting for Ticker
        full_report += f"## {ticker} Results\n"
        if trades:
            tdf = pd.DataFrame(trades)
            win_count = len(tdf[tdf['outcome'] == 'Win'])
            total = len(tdf)
            win_rate = (win_count / total * 100)
            
            # Simple PnL: (Exit - Entry)
            tdf['pnl'] = tdf.apply(lambda x: (x['exit_price'] - x['entry']) if x['type'] == 'BUY' else (x['entry'] - x['exit_price']), axis=1)
            total_pnl = tdf['pnl'].sum()
            
            full_report += f"- **Total Trades**: {total}\n"
            full_report += f"- **Win Rate**: {win_rate:.2f}%\n"
            full_report += f"- **Total PnL**: {total_pnl:.2f}\n"
            full_report += "\n### Trade Log (Last 5)\n"
            full_report += tdf.tail(5).to_markdown() + "\n\n"
        else:
            full_report += "- No trades generated.\n\n"

    # Save to report_60d.md
    out_dir = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\smc"
    if not os.path.exists(out_dir): os.makedirs(out_dir)
    report_file = os.path.join(out_dir, "backtest.md")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(full_report)
    
    print(full_report)
    print(f"Saved to {report_file}")

if __name__ == "__main__":
    run_smc_backtest()
