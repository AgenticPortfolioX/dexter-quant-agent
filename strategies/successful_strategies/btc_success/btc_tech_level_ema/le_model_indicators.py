
import pandas as pd
import yfinance as yf
# Assuming pandas_ta is unavailable based on earlier context, we will implement manually.

def calculate_indicators(data_dict):
    """
    Calculates technical indicators for Le Model.
    - 10m: 8 EMA, 200 EMA
    - 1h: 200 EMA
    - Merges 1h indicators into 10m with proper alignment.
    """
    try:
        df_10m = data_dict['data_10m'].copy()
        df_1h = data_dict['data_1h'].copy()
        
        # 1. Calculate 10m Indicators
        df_10m['EMA_8'] = df_10m['Close'].ewm(span=8, adjust=False).mean()
        df_10m['EMA_200'] = df_10m['Close'].ewm(span=200, adjust=False).mean()
        
        # 2. Calculate 1h Indicators (Use the PRE-SHIFTED data)
        # Note: The data_dict['data_1h'] is already shifted by 1 hour (lagged).
        # So at index 10:00, it contains the 09:00-10:00 candle.
        # Calculating EMA on this shifted data means we are using CLOSED candles.
        df_1h['EMA_200_1h'] = df_1h['Close'].ewm(span=200, adjust=False).mean()
        
        # 3. Merge 1h EMA into 10m Data
        # We merge on index. Since 1h index is sparse, we forward fill for the 10m intervals.
        # This correctly propagates the "last known hourly EMA" through the subsequent 10m bars.
        
        # Resample 1h to 10m with forward fill
        df_1h_resampled = df_1h[['EMA_200_1h']].reindex(df_10m.index, method='ffill')
        
        # Combine
        df_combined = pd.concat([df_10m, df_1h_resampled], axis=1)
        
        return df_combined

    except Exception as e:
        print(f"Error calculating indicators: {e}")
        return None
