import yfinance as yf
import pandas as pd
import numpy as np
import datetime

# --- MACD Oscillator Functions ---

def macd_oscillator_calculation(df, ma1=12, ma2=26):
    """
    Generates signals based on MACD Oscillator.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    signals = df.copy()
    signals['ma1'] = signals['Close'].rolling(window=ma1, min_periods=1, center=False).mean()
    signals['ma2'] = signals['Close'].rolling(window=ma2, min_periods=1, center=False).mean()
    
    signals['positions'] = 0
    # Use integer-based location for indexing safely
    signals.at[signals.index[ma1:], 'positions'] = np.where(signals['ma1'].iloc[ma1:] >= signals['ma2'].iloc[ma1:], 1, 0)
    
    signals['signals'] = signals['positions'].diff()
    signals['oscillator'] = signals['ma1'] - signals['ma2']
    
    return signals

# --- Main Entry for Dexter Integration ---

def run_strategy():
    # Assets: Magnificent 7 + Top 8 Backtest (Merged)
    # Mag 7: AAPL, MSFT, GOOGL, AMZN, META, TSLA, NVDA
    # Top 8 Backtest: TSLA, CAT, GOOGL, GS, AMZN, META, MSFT, SPY
    assets = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "CAT", "GS", "SPY"]
    
    print(f"--- Dexter Quant: MACD Oscillator Testing ---")
    print(f"Assets: {assets}")
    
    for ticker in assets:
        print(f"\nProcessing {ticker}...")
        try:
            # Need at least ma2 (26) periods for full signal accuracy
            data = yf.download(ticker, period="60d", interval="1d", progress=False)
            if data.empty:
                print(f"No data for {ticker}")
                continue
                
            results = macd_oscillator_calculation(data)
            last_signal = results['signals'].iloc[-1]
            last_osc = results['oscillator'].iloc[-1]
            last_ma1 = results['ma1'].iloc[-1]
            last_ma2 = results['ma2'].iloc[-1]
            
            print(f"MA1 (12): {last_ma1:.2f} | MA2 (26): {last_ma2:.2f}")
            print(f"Oscillator: {last_osc:.4f}")
            
            if last_signal == 1:
                print(f"*** SIGNAL DETECTED: [BUY] on {ticker} (MACD Bullish Cross) ***")
            elif last_signal == -1:
                print(f"*** SIGNAL DETECTED: [SELL] on {ticker} (MACD Bearish Cross) ***")
            else:
                # Current holding check
                if results['positions'].iloc[-1] == 1:
                    print(f"Status: Bullish Holding")
                else:
                    print(f"Status: Neutral/Bearish")
                
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

if __name__ == "__main__":
    run_strategy()
