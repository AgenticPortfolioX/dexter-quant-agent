
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

# Add strategy paths
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'active-strategies'))

from ny_orb_strategy import NYOrbStrategy

class MultiAssetBacktest:
    def __init__(self, initial_capital=100000, shares_per_trade=100):
        self.initial_capital = initial_capital
        self.shares_per_trade = shares_per_trade
        self.capital = initial_capital
        self.portfolio_results = []
        self.all_trades = []

    def run_asset(self, ticker, data_file):
        strategy = NYOrbStrategy(volatility_threshold_pct=1.5) # Looser threshold for stocks
        
        real_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'incubator', data_file)
        
        if not os.path.exists(real_data_path):
            print(f"Data not found for {ticker}")
            return None

        results_df = strategy.run_analysis(real_data_path)
        
        if results_df.empty:
            return None

        # Debug: Count reasons
        if not results_df[results_df['trade_allowed']].empty:
            print(f"  {ticker}: {len(results_df[results_df['trade_allowed']])} days allowed.")
        else:
            print(f"  {ticker}: All days filtered. Top reasons: {results_df['reasons'].value_counts().head(2).to_dict()}")

        asset_trades = []
        commission = 1.00 # $1.00 per trade for stocks
        
        for index, row in results_df.iterrows():
            if not row['trade_allowed']:
                continue
            
            if row['outcome'] not in ['Filtered', 'No Trade', 'No Breakout', 'No Trigger']:
                pnl = row['pnl'] * self.shares_per_trade - commission
                trade = {
                    'Ticker': ticker,
                    'Date': row['date'],
                    'Outcome': row['outcome'],
                    'PnL': pnl,
                    'Points': row['pnl']
                }
                asset_trades.append(trade)
                self.all_trades.append(trade)
        
        if asset_trades:
            tdf = pd.DataFrame(asset_trades)
            total_pnl = tdf['PnL'].sum()
            win_rate = (len(tdf[tdf['PnL'] > 0]) / len(tdf) * 100)
            gross_profit = tdf[tdf['PnL'] > 0]['PnL'].sum()
            gross_loss = abs(tdf[tdf['PnL'] <= 0]['PnL'].sum())
            pf = gross_profit / gross_loss if gross_loss > 0 else 5.0
            
            res = {
                'Ticker': ticker,
                'Trades': len(tdf),
                'Win Rate': f"{win_rate:.2f}%",
                'Total PnL': round(total_pnl, 2),
                'Profit Factor': round(pf, 2)
            }
            print(f"  {ticker}: {len(tdf)} trades, PnL: {total_pnl:.2f}, PF: {pf:.2f}")
            self.portfolio_results.append(res)
            return res
        else:
            print(f"  {ticker}: No trades generated.")
            # Still add to results with 0s to avoid KeyError
            self.portfolio_results.append({
                'Ticker': ticker, 'Trades': 0, 'Win Rate': '0.00%', 'Total PnL': 0.0, 'Profit Factor': 0.0
            })
        return None

    def generate_final_report(self):
        if not self.portfolio_results:
            print("No results to report.")
            return

        res_df = pd.DataFrame(self.portfolio_results).sort_values(by='Profit Factor', ascending=False)
        
        total_pnl = sum([r['Total PnL'] for r in self.portfolio_results])
        total_trades = sum([r['Trades'] for r in self.portfolio_results])
        
        summary = f"# NY ORB Multi-Asset Portfolio Report (60 Days)\n"
        summary += f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += f"**Capital**: ${self.initial_capital:,.2f}\n"
        summary += f"**Size**: {self.shares_per_trade} shares per trade\n\n"
        
        summary += "## 1. Asset Performance Ranking\n"
        summary += res_df.to_markdown(index=False) + "\n\n"
        
        summary += "## 2. Portfolio Totals\n"
        summary += f"- **Total PnL**: ${total_pnl:,.2f}\n"
        summary += f"- **Total Trades**: {total_trades}\n"
        summary += f"- **Portfolio Return**: {(total_pnl/self.initial_capital*100):.2f}%\n"
        
        output_dir = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\ny_orb"
        if not os.path.exists(output_dir): os.makedirs(output_dir)
        filepath = os.path.join(output_dir, "backtest.md")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(summary)
            
        print(summary)
        print(f"Full report saved to {filepath}")

if __name__ == "__main__":
    tickers = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD"]
    engine = MultiAssetBacktest()
    
    for t in tickers:
        print(f"Running ORB Backtest for {t}...")
        engine.run_asset(t, f"{t}_5m_orb.pkl")
        
    engine.generate_final_report()
