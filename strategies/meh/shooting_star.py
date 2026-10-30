import yfinance as yf
import pandas as pd
import numpy as np
import datetime

# --- Shooting Star Functions ---

def generate_ss_signals(df, atr_period=14, multiplier=1.5):
    """
    Refined Shooting Star logic for daily data.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    df = df.copy()
    df['signals'] = 0
    df['range'] = df['High'] - df['Low']
    df['atr'] = df['range'].rolling(window=atr_period).mean()
    
    in_pos = False
    for i in range(atr_period, len(df)):
        # Data points
        p = df['Close'].iloc[i]
        o = df['Open'].iloc[i]
        h = df['High'].iloc[i]
        l = df['Low'].iloc[i]
        atr = df['atr'].iloc[i]
        
        if np.isnan(atr): continue
        
        body = abs(o - p)
        upper_wick = h - max(o, p)
        lower_wick = min(o, p) - l
        
        # Criteria: Small body, significant upper wick, minimal lower wick
        if not in_pos:
            # Bullish Body Check (if any)
            # Long Upper Wick (Hammer inversion)
            if upper_wick > multiplier * body and upper_wick > 0.5 * atr and lower_wick < 0.2 * atr:
                df.at[df.index[i], 'signals'] = -1
                in_pos = True
        else:
            # Temporary Exit Logic (Exit 1 day later for backtest visibility/monitor)
            df.at[df.index[i], 'signals'] = 1
            in_pos = False
                
    return df

# --- Main Entry for Dexter Integration ---

def run_strategy():
    # Top 9 Assets from Backtest
    top_9 = ["NVDA", "AVGO", "TSLA", "CAT", "GS", "META", "WMT", "JPM", "GOOGL"]
    print(f"--- Dexter Quant: Shooting Star (SS) Testing ---")
    print(f"Assets: {top_9}")
    
    for ticker in top_9:
        print(f"\nProcessing {ticker}...")
        try:
            # Need ATR period
            data = yf.download(ticker, period="60d", interval="1d", progress=False)
            if data.empty:
                print(f"No data for {ticker}")
                continue
                
            results = generate_ss_signals(data)
            last_signal = results['signals'].iloc[-1]
            last_price = results['Close'].iloc[-1]
            last_atr = results['atr'].iloc[-1]
            
            print(f"Price: {last_price:.2f} | ATR (14): {last_atr:.2f}")
            
            if last_signal == -1:
                print(f"*** SIGNAL DETECTED: [SELL/SHORT] on {ticker} (Shooting Star Pattern) ***")
            elif last_signal == 1:
                print(f"*** SIGNAL DETECTED: [BUY/COVER] on {ticker} (Pattern Exit) ***")
            else:
                print(f"Status: Neutral")
                
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

if __name__ == "__main__":
    run_strategy()
