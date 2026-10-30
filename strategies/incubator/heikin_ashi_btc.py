import yfinance as yf
import pandas as pd
import numpy as np

def heikin_ashi_calculation(ha_df):
    """
    Heikin-Ashi candlestick calculation.
    """
    if isinstance(ha_df.columns, pd.MultiIndex):
        ha_df.columns = ha_df.columns.get_level_values(0)
        
    ha_df = ha_df.copy()
    ha_df['HA open'] = 0.0
    ha_df['HA close'] = 0.0
    ha_df['HA high'] = 0.0
    ha_df['HA low'] = 0.0
    
    # Initialize first HA candle
    ha_df.at[ha_df.index[0], 'HA close'] = (ha_df['Open'].iloc[0] + ha_df['Close'].iloc[0] + ha_df['High'].iloc[0] + ha_df['Low'].iloc[0]) / 4
    ha_df.at[ha_df.index[0], 'HA open'] = (ha_df['Open'].iloc[0] + ha_df['Close'].iloc[0]) / 2
    ha_df.at[ha_df.index[0], 'HA high'] = ha_df['High'].iloc[0]
    ha_df.at[ha_df.index[0], 'HA low'] = ha_df['Low'].iloc[0]
    
    # HA candle calculations
    for n in range(1, len(ha_df)):
        ha_df.at[ha_df.index[n], 'HA open'] = (ha_df['HA open'].iloc[n-1] + ha_df['HA close'].iloc[n-1]) / 2
        ha_df.at[ha_df.index[n], 'HA close'] = (ha_df['Open'].iloc[n] + ha_df['Close'].iloc[n] + ha_df['High'].iloc[n] + ha_df['Low'].iloc[n]) / 4
        ha_df.at[ha_df.index[n], 'HA high'] = max(ha_df['High'].iloc[n], ha_df['HA open'].iloc[n], ha_df['HA close'].iloc[n])
        ha_df.at[ha_df.index[n], 'HA low'] = min(ha_df['Low'].iloc[n], ha_df['HA open'].iloc[n], ha_df['HA close'].iloc[n])
        
    return ha_df

def generate_btc_ha_signals(df, stls=3):
    """
    Generates signals for BTC-USD specifically using Heikin-Ashi.
    """
    data = heikin_ashi_calculation(df.copy())
    data['signals'] = 0
    data['cumsum'] = 0
    
    for n in range(1, len(data)):
        if (data['HA open'].iloc[n] > data['HA close'].iloc[n] and 
            data['HA open'].iloc[n] == data['HA high'].iloc[n] and
            np.abs(data['HA open'].iloc[n] - data['HA close'].iloc[n]) > np.abs(data['HA open'].iloc[n-1] - data['HA close'].iloc[n-1]) and
            data['HA open'].iloc[n-1] > data['HA close'].iloc[n-1]):
            
            data.at[data.index[n], 'signals'] = 1
            data['cumsum'] = data['signals'].cumsum()
            if data['cumsum'].iloc[n] > stls:
                data.at[data.index[n], 'signals'] = 0
        
        elif (data['HA open'].iloc[n] < data['HA close'].iloc[n] and 
              data['HA open'].iloc[n] == data['HA low'].iloc[n] and 
              data['HA open'].iloc[n-1] < data['HA close'].iloc[n-1]):
            
            data['cumsum'] = data['signals'].cumsum()
            if data['cumsum'].iloc[n] > 0:
                data.at[data.index[n], 'signals'] = -1 * data['cumsum'].iloc[n-1]
            else:
                data.at[data.index[n], 'signals'] = 0
    
    return data

def main():
    ticker = "BTC-USD"
    print(f"--- Dexter Quant: Standalone BTC-USD Heikin-Ashi Strategy ---")
    data = yf.download(ticker, period="60d", interval="1d", progress=False)
    if data.empty:
        print(f"No data for {ticker}")
        return
        
    results = generate_btc_ha_signals(data)
    last_signal = results['signals'].iloc[-1]
    
    print(f"Latest Signal for BTC-USD: {last_signal}")
    if last_signal >= 1:
        print("SIGNIFICANT BULLISH SIGNAL DETECTED.")
    elif last_signal <= -1:
        print("SIGNIFICANT BEARISH SIGNAL DETECTED.")
    else:
        print("BTC-USD Status: Neutral")

if __name__ == "__main__":
    main()
