
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from strategies.incubator.smc_btc_plus import SmartMoneyStrategy

def run_broad_portfolio_backtest():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'incubator')
    
    tickers = [
        "SPY", "QQQ", "DIA", "IWM", "GLD", "USO", 
        "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA",
        "AMD", "AVGO", "ADBE", "NFLX",
        "JPM", "GS", "V", "MA",
        "WMT", "COST", "PG",
        "UNH", "LLY", "JNJ",
        "XOM", "CVX", "CAT",
        "BTCUSD"
    ]
    
    results = []
    
    portfolio_report = "# SMC Strategy - 1 Year Portfolio Backtest (30 Assets)\n"
    portfolio_report += f"**Timeframe**: 1-Hour Candles\n"
    portfolio_report += f"**Period**: Last 12 Months\n\n"
    
    portfolio_trades = []

    for ticker in tickers:
        df_path = os.path.join(data_dir, f"{ticker}_1h_smc.pkl")
        if not os.path.exists(df_path):
            continue
            
        print(f"Analyzing {ticker}...")
        df = pd.read_pickle(df_path)
        
        # 1. Logic
        strategy = SmartMoneyStrategy()
        df = strategy.add_indicators(df)
        df = strategy.process_logic(df)
        
        # 2. Backtest
        trades = []
        active_trade = None
        
        for i in range(1, len(df)):
            curr = df.iloc[i]
            t = curr.name
            
            if active_trade:
                if active_trade['type'] == 'BUY':
                    if curr['Low'] <= active_trade['sl']:
                        trades.append({**active_trade, 'exit_time': t, 'exit_price': active_trade['sl'], 'outcome': 'Loss'})
                        active_trade = None
                        continue
                    if not active_trade['tp1_hit'] and curr['High'] >= active_trade['tp1']:
                        active_trade['tp1_hit'] = True
                    if curr['High'] >= active_trade['tp2']:
                        trades.append({**active_trade, 'exit_time': t, 'exit_price': active_trade['tp2'], 'outcome': 'Win'})
                        active_trade = None
                        continue
                else: # SELL
                    if curr['High'] >= active_trade['sl']:
                        trades.append({**active_trade, 'exit_time': t, 'exit_price': active_trade['sl'], 'outcome': 'Loss'})
                        active_trade = None
                        continue
                    if not active_trade['tp1_hit'] and curr['Low'] <= active_trade['tp1']:
                        active_trade['tp1_hit'] = True
                    if curr['Low'] <= active_trade['tp2']:
                        trades.append({**active_trade, 'exit_time': t, 'exit_price': active_trade['tp2'], 'outcome': 'Win'})
                        active_trade = None
                        continue

            sig = curr['entry_signal']
            if sig in ['BUY', 'SELL'] and not active_trade:
                limit_price = curr['bullish_fvg_top'] if sig == 'BUY' else curr['bearish_fvg_bottom']
                triggered = False
                if sig == 'BUY' and curr['Low'] <= limit_price: triggered = True
                elif sig == 'SELL' and curr['High'] >= limit_price: triggered = True
                
                if triggered:
                    try:
                        if sig == 'BUY':
                            sl = df.loc[:t]['swing_low'].dropna().iloc[-1]
                            risk = limit_price - sl
                            if risk <= 0: risk = limit_price * 0.005 # Fallback
                            active_trade = {'ticker': ticker, 'entry_time': t, 'type': 'BUY', 'entry': limit_price, 'sl': sl, 'tp1': limit_price + (2 * risk), 'tp2': limit_price + (4 * risk), 'tp1_hit': False}
                        else:
                            sl = df.loc[:t]['swing_high'].dropna().iloc[-1]
                            risk = sl - limit_price
                            if risk <= 0: risk = limit_price * 0.005
                            active_trade = {'ticker': ticker, 'entry_time': t, 'type': 'SELL', 'entry': limit_price, 'sl': sl, 'tp1': limit_price - (2 * risk), 'tp2': limit_price - (4 * risk), 'tp1_hit': False}
                    except: pass

        if trades:
            tdf = pd.DataFrame(trades)
            tdf['pnl'] = tdf.apply(lambda x: (x['exit_price'] - x['entry']) if x['type'] == 'BUY' else (x['entry'] - x['exit_price']), axis=1)
            # Weighted PnL for 50/50 exit
            # If outcome is Win (TP2 hit), pnl is (0.5*2R + 0.5*4R) = 3R
            # If outcome is Loss (SL hit) and TP1 was hit, pnl is (0.5*2R + 0.5*-1R) = 0.5R
            # If outcome is Loss (SL hit) and TP1 not hit, pnl is -1R
            # Our current PnL calculation is just Exit - Entry. Let's keep it simple for now or refine.
            
            total_pnl = tdf['pnl'].sum()
            win_rate = (len(tdf[tdf['outcome'] == 'Win']) / len(tdf)) * 100
            
            results.append({
                'Ticker': ticker,
                'Trades': len(tdf),
                'Win Rate': f"{win_rate:.2f}%",
                'Total PnL': round(total_pnl, 2),
                'Profit Factor': round(abs(tdf[tdf['pnl']>0]['pnl'].sum() / tdf[tdf['pnl']<0]['pnl'].sum()), 2) if len(tdf[tdf['pnl']<0]) > 0 else 10.0
            })
            portfolio_trades.extend(trades)

    # 3. Final Portfolio Report
    res_df = pd.DataFrame(results).sort_values(by='Profit Factor', ascending=False)
    portfolio_report += "## Portfolio Performance Ranking\n"
    portfolio_report += res_df.to_markdown(index=False) + "\n\n"
    
    portfolio_report += "## Top 5 Performers (By Profit Factor)\n"
    portfolio_report += res_df.head(5).to_markdown(index=False) + "\n\n"

    out_dir = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\smc"
    if not os.path.exists(out_dir): os.makedirs(out_dir)
    report_file = os.path.join(out_dir, "backtest.md")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(portfolio_report)
    
    print(portfolio_report)
    print(f"Final Portfolio Report saved to {report_file}")

if __name__ == "__main__":
    run_broad_portfolio_backtest()
