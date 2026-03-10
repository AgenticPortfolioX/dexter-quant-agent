import yfinance as yf
import pandas as pd
import numpy as np

def backtest_strategy_3():
    print("--- Backtesting Strategy 3: Low Close and IBS ---")
    
    # 1. Fetch SPY Data
    data = yf.download("SPY", start="1993-01-01", end="2025-01-01", progress=False)
    
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
        
    df = data.copy()
    
    # 2. Indicators Calculation
    df['IBS'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'])
    
    # Lowest low of the previous five trading days
    df['Prev_Lowest_Low_5'] = df['Low'].shift(1).rolling(window=5).min()
    
    df.dropna(inplace=True)
    
    # 3. Entry & Exit Conditions
    # Entry: Close < Previous 5 days lowest low AND IBS < 0.25
    df['Entry_Condition'] = (df['Close'] < df['Prev_Lowest_Low_5']) & (df['IBS'] < 0.25)
    
    # Exit: Close > Previous day's high
    df['Prev_High'] = df['High'].shift(1)
    df['Exit_Condition'] = df['Close'] > df['Prev_High']
    
    # 4. Backtest Loop
    in_position = False
    entry_price = 0
    trades = []
    
    for i in range(1, len(df)):
        if not in_position:
            if df['Entry_Condition'].iloc[i]:
                in_position = True
                entry_price = df['Close'].iloc[i]
                entry_date = df.index[i]
        else:
            if df['Exit_Condition'].iloc[i]:
                in_position = False
                exit_price = df['Close'].iloc[i]
                exit_date = df.index[i]
                
                pct_return = (exit_price - entry_price) / entry_price
                trades.append({
                    'Entry Date': entry_date,
                    'Exit Date': exit_date,
                    'Return': pct_return
                })
                
    # 5. Performance Metrics
    if not trades:
        print("No trades executed.")
        return
        
    trades_df = pd.DataFrame(trades)
    
    equity = 100000
    equity_curve = [equity]
    
    for pct_return in trades_df['Return']:
        equity = equity * (1 + pct_return)
        equity_curve.append(equity)
        
    avg_return = np.mean(trades_df['Return'])
    win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df)
    
    print(f"Total Trades: {len(trades_df)}")
    print(f"Win Rate: {win_rate:.2%}")
    print(f"Average Profit per Trade: {avg_return:.2%}")
    print(f"Final Equity (Starting $100k): ${equity:,.2f}")
    
if __name__ == "__main__":
    backtest_strategy_3()
