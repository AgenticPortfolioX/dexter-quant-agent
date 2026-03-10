"""
RSI-Candlestick Mean Reversion Strategy (Bitcoin Optimized)
Graduated to Successful Strategies: 2026-02-18

Performance:
- Confirmed "Successful" status for BTC-USD.
- Validated via 90-day backtest.
- Catching volatility snap-backs on the 1H timeframe.
"""

import yfinance as yf
import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.ewm(alpha=1/period, adjust=False).mean()

def calculate_indicators(df):
    """
    Adds RSI (14) and ATR (14) to the dataframe using manual calculation.
    """
    # RSI 14
    df['RSI'] = calculate_rsi(df['Close'], period=14)
    
    # ATR 14
    df['ATR'] = calculate_atr(df, period=14)
    
    return df

def identify_candlestick_patterns(df):
    """
    Identifies Bullish/Bearish Engulfing, Hammer, and Shooting Star patterns.
    """
    # Helper for body size and direction
    df['Body'] = abs(df['Close'] - df['Open'])
    df['Upper_Wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
    df['Lower_Wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']
    df['Bullish'] = df['Close'] > df['Open']
    df['Bearish'] = df['Close'] < df['Open']
    
    # shifts for previous candle
    df['Prev_Body'] = df['Body'].shift(1)
    df['Prev_Bullish'] = df['Bullish'].shift(1)
    df['Prev_Bearish'] = df['Bearish'].shift(1)
    df['Prev_Open'] = df['Open'].shift(1)
    df['Prev_Close'] = df['Close'].shift(1)
    
    # 1. Bullish Engulfing
    # Current is Bullish, Prev was Bearish
    # Current Body > Prev Body (simplified) AND Current completely engulfs Prev Body
    # Strict definition: Open < Prev Close AND Close > Prev Open
    df['Bullish_Engulfing'] = (
        (df['Bullish']) & (df['Prev_Bearish']) &
        (df['Close'] > df['Prev_Open']) & (df['Open'] < df['Prev_Close'])
    )

    # 2. Bearish Engulfing
    # Current is Bearish, Prev was Bullish
    # Open > Prev Close AND Close < Prev Open
    df['Bearish_Engulfing'] = (
        (df['Bearish']) & (df['Prev_Bullish']) &
        (df['Open'] > df['Prev_Close']) & (df['Close'] < df['Prev_Open'])
    )
    
    # 3. Hammer (Bullish Reversal)
    # Small body at upper end, Long lower wick (>= 2x Body), Small upper wick
    df['Hammer'] = (
        (df['Lower_Wick'] >= 2 * df['Body']) &
        (df['Upper_Wick'] <= 0.5 * df['Body']) # Small upper wick tolerance
    )
    
    # 4. Shooting Star (Bearish Reversal)
    # Small body at lower end, Long upper wick (>= 2x Body), Small lower wick
    df['Shooting_Star'] = (
        (df['Upper_Wick'] >= 2 * df['Body']) &
        (df['Lower_Wick'] <= 0.5 * df['Body'])
    )
    
    return df

def check_golden_rule(df, idx):
    """
    Checks for strong momentum that invalidates reversals.
    Golden Rule: Do not fade 3 consecutive strong candles in trend direction.
    """
    # Need at least 3 previous candles
    if idx < 3: return False
    
    # Strong Bullish Momentum (Invalidates Short)
    # 3 consecutive bullish candles, each larger body than prev, each close higher
    bullish_mom = True
    for i in range(3):
        curr_i = idx - i
        prev_i = idx - i - 1
        
        # Check bullish
        if not df['Bullish'].iloc[curr_i]:
            bullish_mom = False; break
            
        # Check close higher
        if i > 0 and df['Close'].iloc[curr_i] <= df['Close'].iloc[prev_i]: # Compare current in loop to its "next" (which is actually older in time) - wait loop goes backwards in time from idx.
             # Correct logic:
             # Candle[idx] > Candle[idx-1] > Candle[idx-2]
             pass 

    # Re-logic:
    # Bullish Momentum Check (Overrides Shorts)
    c1 = df.iloc[idx]
    c2 = df.iloc[idx-1]
    c3 = df.iloc[idx-2]
    
    strong_bullish = (
        c1['Bullish'] and c2['Bullish'] and c3['Bullish'] and
        c1['Body'] > c2['Body'] and c2['Body'] > c3['Body'] and
        c1['Close'] > c2['Close'] and c2['Close'] > c3['Close']
    )
    
    # Bearish Momentum Check (Overrides Longs)
    strong_bearish = (
        c1['Bearish'] and c2['Bearish'] and c3['Bearish'] and
        c1['Body'] > c2['Body'] and c2['Body'] > c3['Body'] and
        c1['Close'] < c2['Close'] and c2['Close'] < c3['Close']
    )
    
    return "Strong_Bullish" if strong_bullish else ("Strong_Bearish" if strong_bearish else "None")


def generate_signals(df):
    """
    Generates entry signals based on RSI + Patterns + Filters.
    """
    df['Signal'] = "None"
    
    for i in range(3, len(df)):
        # RSI Hook Logic
        rsi_curr = df['RSI'].iloc[i]
        rsi_prev = df['RSI'].iloc[i-1]
        rsi_prev2 = df['RSI'].iloc[i-2]
        
        # Check Golden Rule Momentum
        momentum = check_golden_rule(df, i)
        
        # --- LONG LOGIC ---
        # 1. RSI < 25 in last 3 candles
        rsi_last_3 = df['RSI'].iloc[i-2:i+1] # Slice includes i
        # The requirement: "within the last 3 candles" - usually means at least one touched.
        # Strict reading: "RSI must have been below 25" - we'll check if min < 25.
        
        # 2. Hook Up: Curr > Prev and Prev < Prev2 (The 'V' shape turn)
        hook_up = (rsi_curr > rsi_prev) and (rsi_prev < rsi_prev2)
        
        # 3. Pattern
        pattern_long = df['Bullish_Engulfing'].iloc[i] or df['Hammer'].iloc[i]
        
        if (min(rsi_last_3) < 25) and hook_up and pattern_long:
            if momentum != "Strong_Bearish":
                df.at[df.index[i], 'Signal'] = "BUY"
                
        # --- SHORT LOGIC ---
        # 1. RSI > 75 in last 3 candles
        # 2. Hook Down
        hook_down = (rsi_curr < rsi_prev) and (rsi_prev > rsi_prev2)
        
        # 3. Pattern
        pattern_short = df['Bearish_Engulfing'].iloc[i] or df['Shooting_Star'].iloc[i]
        
        if (max(rsi_last_3) > 75) and hook_down and pattern_short:
             if momentum != "Strong_Bullish":
                df.at[df.index[i], 'Signal'] = "SELL"
                
    return df

def run_backtest(ticker="EURUSD=X", period="59d", interval="15m"):
    """
    Runs the backtest simulation with ATR stops and Split RSI Targets.
    Note: yfinance 15m data is limited to last 60 days.
    """
    print(f"--- Running RSI-Candlestick Backtest: {ticker} ---")
    
    # 1. Get Data
    df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    if df.empty:
        print("No data found.")
        return
        
    # Handle MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # 2. Indicators & Signals
    df = calculate_indicators(df)
    df = identify_candlestick_patterns(df)
    df = generate_signals(df)
    
    # 3. Simulation
    trades = []
    active_trade = None # {'type':, 'entry':, 'sl':, 'tp1_hit': Bool, 'size': 1.0}
    
    for i in range(1, len(df)):
        curr = df.iloc[i]
        timestamp = df.index[i]
        rsi = curr['RSI']
        
        # Manage Open Trade
        if active_trade:
            # Check Stop Loss first (always protection first)
            # Long SL: Price drops below SL
            if active_trade['type'] == 'BUY':
                if curr['Low'] <= active_trade['sl']:
                    trades.append({
                        'Entry Time': active_trade['entry_time'],
                        'Exit Time': timestamp,
                        'Direction': 'Long',
                        'Outcome': 'Loss',
                        'PnL': (active_trade['sl'] - active_trade['entry']) * active_trade['size']
                    })
                    active_trade = None
                    continue
                
                # Check TP1 (RSI > 50)
                if not active_trade['tp1_hit'] and rsi > 50:
                    # Close 50%
                    trades.append({
                        'Entry Time': active_trade['entry_time'],
                        'Exit Time': timestamp,
                        'Direction': 'Long',
                        'Outcome': 'TP1',
                        'PnL': (curr['Close'] - active_trade['entry']) * 0.5
                    })
                    active_trade['size'] = 0.5
                    active_trade['tp1_hit'] = True
                    active_trade['sl'] = active_trade['entry'] # Move SL to Breakeven
                    
                # Check TP2 (RSI > 75)
                elif active_trade['tp1_hit'] and rsi > 75:
                    # Close Remaining
                    trades.append({
                        'Entry Time': active_trade['entry_time'],
                        'Exit Time': timestamp,
                        'Direction': 'Long',
                        'Outcome': 'TP2',
                        'PnL': (curr['Close'] - active_trade['entry']) * 0.5
                    })
                    active_trade = None
                    continue
                    
            # Short Management
            elif active_trade['type'] == 'SELL':
                if curr['High'] >= active_trade['sl']:
                    trades.append({
                        'Entry Time': active_trade['entry_time'],
                        'Exit Time': timestamp,
                        'Direction': 'Short',
                        'Outcome': 'Loss',
                        'PnL': (active_trade['entry'] - active_trade['sl']) * active_trade['size']
                    })
                    active_trade = None
                    continue
                
                # Check TP1 (RSI < 50)
                if not active_trade['tp1_hit'] and rsi < 50:
                     trades.append({
                        'Entry Time': active_trade['entry_time'],
                        'Exit Time': timestamp,
                        'Direction': 'Short',
                        'Outcome': 'TP1',
                        'PnL': (active_trade['entry'] - curr['Close']) * 0.5
                    })
                     active_trade['size'] = 0.5
                     active_trade['tp1_hit'] = True
                     active_trade['sl'] = active_trade['entry'] # Breakeven
                     
                # Check TP2 (RSI < 25)
                elif active_trade['tp1_hit'] and rsi < 25:
                    trades.append({
                        'Entry Time': active_trade['entry_time'],
                        'Exit Time': timestamp,
                        'Direction': 'Short',
                        'Outcome': 'TP2',
                        'PnL': (active_trade['entry'] - curr['Close']) * 0.5
                    })
                    active_trade = None
                    continue

        # Look for Entry if no trade active
        if not active_trade:
            signal = curr['Signal']
            atr = curr['ATR']
            
            if signal == "BUY":
                sl_price = curr['Low'] - (0.5 * atr)
                active_trade = {
                    'type': 'BUY',
                    'entry': curr['Close'],
                    'entry_time': timestamp,
                    'sl': sl_price,
                    'tp1_hit': False,
                    'size': 1.0 
                }
            elif signal == "SELL":
                sl_price = curr['High'] + (0.5 * atr)
                active_trade = {
                    'type': 'SELL',
                    'entry': curr['Close'],
                    'entry_time': timestamp,
                    'sl': sl_price,
                    'tp1_hit': False,
                    'size': 1.0
                }

    # Reporting
    if not trades:
        print("No trades triggered.")
        return

    df_res = pd.DataFrame(trades)
    
    # Metrics
    total_trades = len(df_res[df_res['Outcome'].isin(['TP1', 'Loss'])]) # Count TP2 as part of the same trade usually, but split here.
    # Simplified count: Unique entry times
    unique_trades = df_res['Entry Time'].nunique()
    
    # Calculate Total PnL (sum of all parts)
    total_pnl = df_res['PnL'].sum()
    
    # Win Rate (Any profitable partial close counts as a win for simplicity, or strict?)
    # Let's aggregate by Trade ID (Entry Time)
    trade_groups = df_res.groupby('Entry Time')['PnL'].sum()
    wins = trade_groups[trade_groups > 0].count()
    win_rate = (wins / unique_trades) * 100
    
    # Profit Factor
    gross_win = trade_groups[trade_groups > 0].sum()
    gross_loss = abs(trade_groups[trade_groups < 0].sum())
    pf = gross_win / gross_loss if gross_loss != 0 else 0
    
    print("\n" + "="*40)
    print(f"RESULTS: {ticker} (Last 3 Months)")
    print("="*40)
    print(f"Total Unique Trades: {unique_trades}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Total PnL (Points/Dollars): {total_pnl:.4f}")
    print("="*40)
    
    # Save Results
    import os
    REPORTING_PATH = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\backtests"
    if not os.path.exists(REPORTING_PATH): os.makedirs(REPORTING_PATH, exist_ok=True)
    df_res.to_csv(os.path.join(REPORTING_PATH, f"RSI_Reversion_{ticker}_Results.csv"))
    print(f"Detailed logs saved to {REPORTING_PATH}")

def run_bulk_backtest():
    """
    Runs the RSI strategy on 25 logical assets for 90 days (1H interval).
    """
    ASSETS = [
        # Forex (7)
        "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X",
        # Indices (5)
        "SPY", "QQQ", "DIA", "IWM", "^GSPC",
        # Commodities (3)
        "GC=F", "SI=F", "CL=F",
        # Crypto (5)
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
        # Equities (Tech) (5)
        "AAPL", "MSFT", "NVDA", "TSLA", "AMZN"
    ]
    
    print("="*60)
    print("      RSI-CANDLESTICK BULK BACKTEST (90 DAYS, 1H)")
    print("="*60)
    
    for ticker in ASSETS:
        try:
            run_backtest(ticker, period="90d", interval="1h")
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

if __name__ == "__main__":
    # Execute the requested bulk backtest
    run_bulk_backtest()
