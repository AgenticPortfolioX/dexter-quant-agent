
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

# Add strategy path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'incubator'))
from ny_orb_strategy import NYOrbStrategy

class BacktestEngine:
    def __init__(self, initial_capital=50000, contract_multiplier=50):
        self.initial_capital = initial_capital
        self.contract_multiplier = contract_multiplier
        self.capital = initial_capital
        self.equity_curve = [initial_capital]
        self.trades = []
        self.filtered_days = []

    def run(self, data_path):
        strategy = NYOrbStrategy()
        
        # Determine strict path to data
        # Assuming data is in strategies/incubator/ES_1m_aligned.pkl based on previous steps
        # But script is running from strategies/validation/
        # so data path relative to this script: ../incubator/ES_1m_aligned.pkl
        real_data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'incubator', data_path)
        
        if not os.path.exists(real_data_path):
            print(f"Data not found at {real_data_path}")
            return

        results_df = strategy.run_analysis(real_data_path)
        
        if results_df.empty:
            print("No analysis results generated.")
            return

        # Process Results for Portfolio simulation
        for index, row in results_df.iterrows():
            date = row['date']
            
            if not row['trade_allowed']:
                self.filtered_days.append({
                    'Date': date,
                    'Reason': row['reasons']
                })
                # Capital unchanged
                self.equity_curve.append(self.capital)
                continue
                
            # Trade occurred (or attempted)
            # Row has 'pnl' in points, 'outcome'
            points = row['pnl']
            dollar_pnl = points * self.contract_multiplier
            
            # Slippage/Commission could be added here
            commission = 5.00 # $5 round trip example
            net_pnl = dollar_pnl - commission if row['outcome'] != 'Filtered' and row['outcome'] != 'No Trade' and row['outcome'] != 'No Breakout' else 0
            
            if row['outcome'] not in ['Filtered', 'No Trade', 'No Breakout', 'No Trigger']:
                 self.trades.append({
                     'Date': date,
                     'Type': 'Trade', # Long/Short not in summary df yet, can infer or just log PnL
                     'Points': points,
                     'PnL': net_pnl,
                     'Outcome': row['outcome']
                 })
                 self.capital += net_pnl
            
            self.equity_curve.append(self.capital)

    def generate_report(self, output_dir):
        # Calculate Metrics
        total_trades = len(self.trades)
        wins = [t for t in self.trades if t['PnL'] > 0]
        losses = [t for t in self.trades if t['PnL'] <= 0]
        
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0
        
        gross_profit = sum(t['PnL'] for t in wins)
        gross_loss = abs(sum(t['PnL'] for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)
        
        equity_series = pd.Series(self.equity_curve)
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max * 100
        max_drawdown = drawdown.min()
        
        total_return = (self.capital - self.initial_capital) / self.initial_capital * 100
        
        report = f"""# NY 15min ORB Strategy - Backtest Report

**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Strategy**: ES_ORB_Hybrid
**Data Source**: ES Futures (60-Day Sample / 5-minute Granularity)
**Initial Capital**: ${self.initial_capital:,.2f}
**Contract Size**: 1 (Multiplier {self.contract_multiplier})

## 1. Performance Summary
- **Total Trades**: {total_trades}
- **Win Rate**: {win_rate:.2f}%
- **Profit Factor**: {profit_factor:.2f}
- **max_drawdown**: {max_drawdown:.2f}%
- **Total Return**: {total_return:.2f}% (${self.capital - self.initial_capital:,.2f})
- **Ending Equity**: ${self.capital:,.2f}

## 2. Trade Log
| Date | Type | Points | PnL | Outcome |
|------|------|--------|-----|---------|
"""
        if not self.trades:
            report += "| - | - | - | - | No Trades |\n"
        else:
            for t in self.trades:
                report += f"| {t['Date']} | {t['Type']} | {t['Points']:.2f} | ${t['PnL']:.2f} | {t['Outcome']} |\n"

        report += "\n## 3. Filtered Days (No Trade)\n"
        report += "| Date | Reason |\n|------|--------|\n"
        
        if not self.filtered_days:
             report += "| - | No Days Filtered |\n"
        else:
             for f in self.filtered_days:
                 report += f"| {f['Date']} | {f['Reason']} |\n"

        # Save
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        filename = f"backtest_report_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)
            
        print(report)
        print(f"\nReport saved to: {filepath}")

if __name__ == "__main__":
    # Path to where we saved data in Step 1
    # Using relative name as run() handles path construction
    data_file = "ES_5m_aligned.pkl" 
    
    # Validation results folder
    output_folder = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\ny_orb"
    
    engine = BacktestEngine(initial_capital=50000)
    engine.run(data_file)
    engine.generate_report(output_folder)
