import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

def london_breakout_calculation(df, lookback=1):
    """
    London Breakout implementation for daily data.
    Uses previous day's high/low as breakout triggers.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    df = df.copy()
    df['signals'] = 0
    
    # Simple daily breakout: trigger if current price exceeds previous day's high/low
    df['prev_high'] = df['High'].shift(lookback)
    df['prev_low'] = df['Low'].shift(lookback)
    
    in_pos = False
    for i in range(lookback, len(df)):
        price = df['Close'].iloc[i]
        ph = df['prev_high'].iloc[i]
        pl = df['prev_low'].iloc[i]
        
        if np.isnan(ph) or np.isnan(pl): continue
        
        if not in_pos:
            if price > ph:
                df.at[df.index[i], 'signals'] = 1
                in_pos = True
            elif price < pl:
                df.at[df.index[i], 'signals'] = -1
                in_pos = True
        else:
            # Simple exit on reversal or specific logic
            # For LB, we often exit at end of session or on a stop.
            # Here we just look for a counter-breakout as a simple reversal.
            lsig = df['signals'].cumsum().iloc[i-1]
            if lsig == 1 and price < ph: # Re-entered the range
                df.at[df.index[i], 'signals'] = -1
                in_pos = False
            elif lsig == -1 and price > pl:
                df.at[df.index[i], 'signals'] = 1
                in_pos = False
                
    return df

def run_strategy():
    # Top 20 Assets from Phase 2 Backtest for Strategy: LB
    assets = [
        "XRP-USD", "SMCI", "SOL-USD", "MU", "ALGO-USD", "AVAX-USD", "DOGE-USD", 
        "COIN", "ARM", "SHIB-USD", "PLTR", "NEAR-USD", "TSLA", "AVGO", "NVDA", 
        "NET", "INTC", "BNB-USD", "CAT", "SHOP"
    ]
    
    print(f"--- Dexter Quant: London Breakout (LB) Testing ---")
    print(f"Assets: {len(assets)} tickers identified")
    
    for ticker in assets:
        print(f"\nProcessing {ticker}...")
        try:
            data = yf.download(ticker, period="60d", interval="1d", progress=False)
            if data.empty:
                print(f"No data for {ticker}")
                continue
                
            results = london_breakout_calculation(data)
            last_signal = results['signals'].iloc[-1]
            last_price = results['Close'].iloc[-1]
            prev_high = results['prev_high'].iloc[-1]
            prev_low = results['prev_low'].iloc[-1]
            
            print(f"Price: {last_price:.2f} | Prev High: {prev_high:.2f} | Prev Low: {prev_low:.2f}")
            
            if last_signal >= 1:
                print(f"*** SIGNAL DETECTED: [BUY/LONG] on {ticker} (LB Breakout High) ***")
            elif last_signal <= -1:
                print(f"*** SIGNAL DETECTED: [SELL/SHORT] on {ticker} (LB Breakout Low) ***")
            else:
                # Check current position
                pos = results['signals'].cumsum().iloc[-1]
                if pos > 0:
                    print(f"Status: Long")
                elif pos < 0:
                    print(f"Status: Short")
                else:
                    print(f"Status: Neutral (Inside Range)")
                
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

if __name__ == "__main__":
    run_strategy()
