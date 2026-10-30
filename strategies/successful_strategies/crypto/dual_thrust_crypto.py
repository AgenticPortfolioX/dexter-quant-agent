import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

def dual_thrust_calculation(df, rg=4, k1=0.2, k2=0.2):
    """
    Dual Thrust calculation for daily data breakout.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    signals = df.copy()
    signals['signals'] = 0
    
    # Range calculation from previous rg days
    signals['hh'] = signals['High'].rolling(window=rg).max().shift(1)
    signals['lc'] = signals['Close'].rolling(window=rg).min().shift(1)
    signals['hc'] = signals['Close'].rolling(window=rg).max().shift(1)
    signals['ll'] = signals['Low'].rolling(window=rg).min().shift(1)
    
    signals['r1'] = signals['hh'] - signals['lc']
    signals['r2'] = signals['hc'] - signals['ll']
    signals['range'] = np.maximum(signals['r1'], signals['r2'])
    
    in_pos = False
    for i in range(rg, len(signals)):
        price = signals['Close'].iloc[i]
        opening = signals['Open'].iloc[i]
        r = signals['range'].iloc[i]
        
        buy_line = opening + k1 * r
        sell_line = opening - k2 * r
        
        if not in_pos:
            if price >= buy_line:
                signals.at[signals.index[i], 'signals'] = 1
                in_pos = True
        else:
            if price <= sell_line:
                signals.at[signals.index[i], 'signals'] = -1
                in_pos = False
                
    return signals

def run_strategy():
    # Only Cryptos Extracted from Main Dual Thrust
    assets = [
        "SOL-USD", "ADA-USD", "XRP-USD", "NEAR-USD", "DOGE-USD", 
        "AVAX-USD", "DOT-USD", "BNB-USD", "ALGO-USD"
    ]
    
    print(f"--- Dexter Quant: Dual Thrust (DT) Crypto Edition Testing ---")
    print(f"Assets: {len(assets)} crypto tickers identified")
    
    for ticker in assets:
        print(f"\nProcessing {ticker}...")
        try:
            data = yf.download(ticker, period="60d", interval="1d", progress=False)
            if data.empty:
                print(f"No data for {ticker}")
                continue
                
            results = dual_thrust_calculation(data)
            last_signal = results['signals'].iloc[-1]
            last_price = results['Close'].iloc[-1]
            last_opening = data['Open'].iloc[-1]
            last_range = results['range'].iloc[-1]
            
            k1, k2 = 0.2, 0.2
            buy_line = last_opening + k1 * last_range
            sell_line = last_opening - k2 * last_range
            
            print(f"Price: {last_price:.2f} | Open: {last_opening:.2f} | Range: {last_range:.2f}")
            print(f"Buy Level: {buy_line:.2f} | Sell Level: {sell_line:.2f}")
            
            if last_signal == 1:
                print(f"*** SIGNAL DETECTED: [BUY] on {ticker} (DT Crypto Breakout) ***")
            elif last_signal == -1:
                print(f"*** SIGNAL DETECTED: [SELL] on {ticker} (DT Crypto Breakout) ***")
            else:
                print(f"Status: Neutral")
                
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

if __name__ == "__main__":
    run_strategy()
