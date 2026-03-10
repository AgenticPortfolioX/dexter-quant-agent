import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime

# Path logic
sys.path.append(os.getcwd())
from strategies.incubator.smc_btc_plus import SmartMoneyStrategy

ASSETS = [
    "SPY", "QQQ", "DIA", "IWM", 
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
    "GC=F", "SI=F", "CL=F",
    "BTC-USD", "ETH-USD",
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL"
]

def run_bulk_smc_backtest():
    results_list = []
    print("\n" + "="*60)
    print("      SMC STRATEGY BULK BACKTEST (2 YEARS)")
    print("="*60)

    strategy = SmartMoneyStrategy()

    for ticker in ASSETS:
        print(f"Processing {ticker}...", end=" ", flush=True)
        try:
            # 1. Data Prep (1h interval for 2y)
            df_1h = yf.download(ticker, period="2y", interval="1h", progress=False)
            if df_1h.empty:
                print("FAILED (No data)")
                continue
            
            if isinstance(df_1h.columns, pd.MultiIndex):
                df_1h.columns = df_1h.columns.get_level_values(0)

            # 2. Strategy Logic
            df = strategy.add_indicators(df_1h)
            df = strategy.process_logic(df)

            # 3. Execution (Iterative backtester based on logic)
            trades = []
            active_trade = None

            for i in range(1, len(df)):
                curr = df.iloc[i]
                t = curr.name
                
                if active_trade:
                    if active_trade['type'] == 'BUY':
                        if curr['Low'] <= active_trade['sl']:
                            trades.append({'outcome': 'Loss', 'pnl': active_trade['sl'] - active_trade['entry']})
                            active_trade = None
                        elif curr['High'] >= active_trade['tp']: # TP2 Target
                            trades.append({'outcome': 'Win', 'pnl': active_trade['tp'] - active_trade['entry']})
                            active_trade = None
                    else: # SELL
                        if curr['High'] >= active_trade['sl']:
                            trades.append({'outcome': 'Loss', 'pnl': active_trade['entry'] - active_trade['sl']})
                            active_trade = None
                        elif curr['Low'] <= active_trade['tp']:
                            trades.append({'outcome': 'Win', 'pnl': active_trade['entry'] - active_trade['tp']})
                            active_trade = None

                sig = curr['entry_signal']
                if sig in ['BUY', 'SELL'] and not active_trade:
                    limit = curr['bullish_fvg_top'] if sig == 'BUY' else curr['bearish_fvg_bottom']
                    triggered = (sig == 'BUY' and curr['Low'] <= limit) or (sig == 'SELL' and curr['High'] >= limit)
                    
                    if triggered:
                        try:
                            if sig == 'BUY':
                                sl = df.loc[:t]['swing_low'].dropna().iloc[-1]
                                risk = limit - sl
                                if risk <= 0: continue
                                active_trade = {'type': 'BUY', 'entry': limit, 'sl': sl, 'tp': limit + (3*risk)}
                            else:
                                sl = df.loc[:t]['swing_high'].dropna().iloc[-1]
                                risk = sl - limit
                                if risk <= 0: continue
                                active_trade = {'type': 'SELL', 'entry': limit, 'sl': sl, 'tp': limit - (3*risk)}
                        except: pass

            # 4. Metrics
            tdf = pd.DataFrame(trades)
            total = len(tdf)
            wr = 0
            pnl = 0
            if total > 0:
                wr = len(tdf[tdf['outcome']=='Win']) / total * 100
                pnl = tdf['pnl'].sum()
                print(f"DONE. Trades: {total} | WR: {wr:.1f}% | P/L: ${pnl:,.2f}")
            else:
                print("DONE. No trades.")

            results_list.append({
                'Ticker': ticker,
                'total_trades': total,
                'win_rate': wr,
                'total_pnl': pnl
            })

        except Exception as e:
            print(f"ERROR: {e}")

    if not results_list: return
    res_df = pd.DataFrame(results_list)
    
    import os
    REPORTING_PATH = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\backtests"
    if not os.path.exists(REPORTING_PATH):
        os.makedirs(REPORTING_PATH, exist_ok=True)
        
    output_path = os.path.join(REPORTING_PATH, 'SMC_Expanded_Results.csv')
    res_df.to_csv(output_path, index=False)
    
    print("\n" + "="*60)
    print("      FINAL AGGREGATE PERFORMANCE (SMC)")
    print("="*60)
    print(f"Total Net P/L: ${res_df['total_pnl'].sum():,.2f}")
    print(f"Avg Win Rate:  {res_df[res_df['total_trades']>0]['win_rate'].mean():.1f}%")
    print("="*60)

if __name__ == "__main__":
    run_bulk_smc_backtest()
