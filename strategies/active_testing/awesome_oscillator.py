import yfinance as yf
import pandas as pd
import numpy as np
import datetime

# --- Awesome Oscillator Functions ---

def awesome_ma(signals):
    """Moving average based on the mean of high and low."""
    # Ensure MultiIndex handle
    if isinstance(signals.columns, pd.MultiIndex):
        signals.columns = signals.columns.get_level_values(0)
    
    signals['awesome ma1'] = ((signals['High'] + signals['Low']) / 2).rolling(window=5).mean()
    signals['awesome ma2'] = ((signals['High'] + signals['Low']) / 2).rolling(window=34).mean()
    return signals

def calculate_ao_signals(df):
    """
    Generates signals based on Awesome Oscillator (AO).
    Includes Saucer setups and Zero Line crosses.
    """
    signals = awesome_ma(df.copy())
    # Note: Using .iloc indices so reset_index isn't strictly necessary but helpful if we want 0-N
    # signals.reset_index(inplace=True, drop=True) 
    
    signals['awesome signals'] = 0
    signals['ao'] = signals['awesome ma1'] - signals['awesome ma2']
    signals['cumsum'] = 0

    for i in range(2, len(signals)):
        # Bearish Saucer (Bearish reversal in AO)
        if (signals['Open'].iloc[i] > signals['Close'].iloc[i] and 
            signals['Open'].iloc[i-1] < signals['Close'].iloc[i-1] and 
            signals['Open'].iloc[i-2] < signals['Close'].iloc[i-2] and
            signals['ao'].iloc[i-1] > signals['ao'].iloc[i-2] and
            signals['ao'].iloc[i-1] < 0 and 
            signals['ao'].iloc[i] < 0):
            signals.at[signals.index[i], 'awesome signals'] = 1

        # Bullish Saucer (Bullish reversal in AO)
        if (signals['Open'].iloc[i] < signals['Close'].iloc[i] and 
            signals['Open'].iloc[i-1] > signals['Close'].iloc[i-1] and 
            signals['Open'].iloc[i-2] > signals['Close'].iloc[i-2] and
            signals['ao'].iloc[i-1] < signals['ao'].iloc[i-2] and
            signals['ao'].iloc[i-1] > 0 and
            signals['ao'].iloc[i] > 0):
            signals.at[signals.index[i], 'awesome signals'] = -1

        # Zero Line Cross / Momentum Change
        if signals['awesome ma1'].iloc[i] > signals['awesome ma2'].iloc[i]:
            signals.at[signals.index[i], 'awesome signals'] = 1
            signals['cumsum'] = signals['awesome signals'].cumsum()
            if signals['cumsum'].iloc[i] > 1:
                signals.at[signals.index[i], 'awesome signals'] = 0
            
        if signals['awesome ma1'].iloc[i] < signals['awesome ma2'].iloc[i]:
            signals.at[signals.index[i], 'awesome signals'] = -1
            signals['cumsum'] = signals['awesome signals'].cumsum()
            if signals['cumsum'].iloc[i] < 0:
                signals.at[signals.index[i], 'awesome signals'] = 0
    
    return signals

# --- Main Entry for Dexter Integration ---

def run_strategy():
    mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA"]
    print(f"--- Dexter Quant: Awesome Oscillator (AO) Testing ---")
    print(f"Assets: {mag_7}")
    
    for ticker in mag_7:
        print(f"\nProcessing {ticker}...")
        try:
            # Lookback needed for 34-period MA
            data = yf.download(ticker, period="60d", interval="1d", progress=False)
            if data.empty:
                print(f"No data for {ticker}")
                continue
                
            results = calculate_ao_signals(data)
            last_signal = results['awesome signals'].iloc[-1]
            last_ao = results['ao'].iloc[-1]
            
            print(f"Current AO Value: {last_ao:.4f}")
            if last_signal == 1:
                print(f"*** SIGNAL DETECTED: [BUY] on {ticker} ***")
            elif last_signal == -1:
                print(f"*** SIGNAL DETECTED: [SELL] on {ticker} ***")
            else:
                print(f"Status: Neutral")
                
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

if __name__ == "__main__":
    run_strategy()
