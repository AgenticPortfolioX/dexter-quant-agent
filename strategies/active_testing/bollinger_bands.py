import yfinance as yf
import pandas as pd
import numpy as np
import datetime

# --- Bollinger Bands Functions ---

def bollinger_bands_calculation(df, window=20):
    """Calculates Bollinger Bands indicators."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    data = df.copy()
    data['std'] = data['Close'].rolling(window=window, min_periods=window).std()
    data['mid band'] = data['Close'].rolling(window=window, min_periods=window).mean()
    data['upper band'] = data['mid band'] + 2 * data['std']
    data['lower band'] = data['mid band'] - 2 * data['std']
    return data

def generate_bb_signals(df, alpha_pct=0.01, beta_pct=0.005):
    """
    Generates signals based on Bollinger Bands.
    """
    df = bollinger_bands_calculation(df)
    df['signals'] = 0
    
    # Simpler daily BB strategy: BUY when price <= lower band * (1 + alpha_pct)
    # SELL when price >= upper band * (1 - beta_pct)
    in_position = False
    for i in range(1, len(df)):
        price = df['Close'].iloc[i]
        low = df['lower band'].iloc[i]
        high = df['upper band'].iloc[i]
        
        if np.isnan(low) or np.isnan(high): continue

        if not in_position:
            if price <= low * (1 + alpha_pct):
                df.at[df.index[i], 'signals'] = 1
                in_position = True
        else:
            if price >= high * (1 - beta_pct):
                df.at[df.index[i], 'signals'] = -1
                in_position = False
                
    return df

# --- Main Entry for Dexter Integration ---

def run_strategy():
    mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA"]
    print(f"--- Dexter Quant: Bollinger Bands (BB) Testing ---")
    print(f"Assets: {mag_7}")
    
    for ticker in mag_7:
        print(f"\nProcessing {ticker}...")
        try:
            # Need at least 20 periods for Bollinger Bands
            data = yf.download(ticker, period="60d", interval="1d", progress=False)
            if data.empty:
                print(f"No data for {ticker}")
                continue
                
            results = generate_bb_signals(data)
            last_signal = results['signals'].iloc[-1]
            last_price = results['Close'].iloc[-1]
            last_low = results['lower band'].iloc[-1]
            last_high = results['upper band'].iloc[-1]
            
            print(f"Price: {last_price:.2f} | Lower: {last_low:.2f} | Upper: {last_high:.2f}")
            
            if last_signal == 1:
                print(f"*** SIGNAL DETECTED: [BUY] on {ticker} (BB Rebound) ***")
            elif last_signal == -1:
                print(f"*** SIGNAL DETECTED: [SELL] on {ticker} (BB Overbought) ***")
            else:
                # Check current position from the backtest logic flow
                # (Simple check: if price is between bands but was previously a cross)
                # For signal monitor, we just care about the instantaneous cross.
                print(f"Status: Neutral")
                
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

if __name__ == "__main__":
    run_strategy()
