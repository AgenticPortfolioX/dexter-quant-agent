import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

# Assets to check for each strategy
STRATEGIES_ASSETS = {
    "Strategy 1: Price Retreat": ["GOOGL", "AMZN", "META", "NVDA", "WMT", "MSFT", "JPM", "LLY", "JNJ", "QQQ"],
    "Strategy 2: Turnaround Tuesday": ["NVDA", "MSFT", "AMZN", "LLY", "GOOGL", "META", "BRK-B", "SPY", "WMT", "AAPL"],
    "Strategy 3: Low Close and IBS": ["NVDA", "LLY", "META", "V", "GOOGL", "QQQ", "AAPL", "MSFT", "MA", "JPM"],
    "Strategy 4: DeMarker Indicator": ["NVDA", "SPY", "AMZN", "META", "GOOGL", "AAPL", "MSFT", "V", "QQQ", "LLY"],
    "Strategy 5: High of Past Ten Days IBS": ["META", "GOOGL", "AMZN", "JPM", "NVDA", "MSFT", "WMT", "SPY", "AAPL", "BRK-B"],
    "Awesome Oscillator (AO)": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA"],
    "MACD Oscillator (MACD)": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "CAT", "GS", "SPY"],
    "Bollinger Bands (BB)": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA"],
    "Shooting Star (SS)": ["NVDA", "AVGO", "TSLA", "CAT", "GS", "META", "WMT", "JPM", "GOOGL"],
    "Dual Thrust (DT)": [
        "SOL-USD", "ADA-USD", "SMCI", "XRP-USD", "NEAR-USD", "PLTR", "MU", "DOGE-USD", 
        "COIN", "NET", "NVDA", "AVAX-USD", "DOT-USD", "BNB-USD", "ALGO-USD", "PATH", 
        "ARM", "CAT", "AVGO", "MSTR", "SLV", "KLAC", "TSM", "SHOP", "ARKW"
    ],
    "Heikin Ashi (HA)": [
        "SMCI", "LRCX", "DOGE-USD", "MSTR", "PLTR", "NVDA", "TSM", "ARM", "COIN", "LINK-USD",
        "KLAC", "DDOG", "LTC-USD", "TQQQ", "MU", "SHOP", "AVGO", "SNOW", "NET", "SHIB-USD",
        "CRWD", "MDB", "SMH", "ASML", "META"
    ],
    "Strategy OS": [
        "SMCI", "MU", "COIN", "ARM", "PLTR", "TSLA", "AVGO", "NVDA", "NET", "INTC", 
        "CAT", "SHOP", "MSTR", "TQQQ", "ARKW", "IBM", "CRWD", "SMH", "LRCX", "GOOGL", 
        "AMAT", "JPM", "IGV", "ROKU", "KLAC"
    ]
}

# Fetch enough data
LOOKBACK_DAYS = 50 
END_DATE = datetime.now()
START_DATE = END_DATE - timedelta(days=LOOKBACK_DAYS)

def fetch_data(ticker):
    data = yf.download(ticker, start=START_DATE.strftime('%Y-%m-%d'), end=END_DATE.strftime('%Y-%m-%d'), progress=False)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    df = data.copy()
    if df.empty:
        return df
    df['IBS'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'])
    return df.dropna()

def check_strategy_1(df):
    if len(df) < 26: return False
    df['HighLowRange'] = df['High'] - df['Low']
    df['AvgHighLowRange_25'] = df['HighLowRange'].rolling(window=25).mean()
    df['Rolling_High_10'] = df['High'].rolling(window=10).max()
    df['Entry_Condition'] = (df['Close'] < (df['Rolling_High_10'] - df['AvgHighLowRange_25'])) & (df['IBS'] < 0.3)
    return df['Entry_Condition'].iloc[-1]

def check_strategy_2(df):
    if len(df) < 3: return False
    df['Day_Of_Week'] = df.index.dayofweek
    df['Daily_Return'] = df['Close'].pct_change()
    df['Is_Down_Day'] = df['Daily_Return'] < 0
    df['Prev_Is_Down_Day'] = df['Is_Down_Day'].shift(1)
    df['Entry_Condition'] = (df['Day_Of_Week'] == 0) & df['Is_Down_Day'] & df['Prev_Is_Down_Day']
    return df['Entry_Condition'].iloc[-1]

def check_strategy_3(df):
    if len(df) < 6: return False
    df['Prev_Lowest_Low_5'] = df['Low'].shift(1).rolling(window=5).min()
    df['Entry_Condition'] = (df['Close'] < df['Prev_Lowest_Low_5']) & (df['IBS'] < 0.25)
    return df['Entry_Condition'].iloc[-1]

def check_strategy_4(df):
    if len(df) < 6: return False
    df['Prev_High'] = df['High'].shift(1)
    df['Prev_Low'] = df['Low'].shift(1)
    df['DeMax'] = np.where(df['High'] > df['Prev_High'], df['High'] - df['Prev_High'], 0)
    df['DeMin'] = np.where(df['Prev_Low'] > df['Low'], df['Prev_Low'] - df['Low'], 0)
    sma_demax = df['DeMax'].rolling(window=5).mean()
    sma_demin = df['DeMin'].rolling(window=5).mean()
    denominator = sma_demax + sma_demin
    denominator = denominator.replace(0, np.nan)
    df['DeMarker'] = 100 * (sma_demax / denominator)
    df['Entry_Condition'] = df['DeMarker'] < 10
    return df['Entry_Condition'].iloc[-1]

def check_strategy_5(df):
    if len(df) < 11: return False
    df['Prev_Highest_High_10'] = df['High'].shift(1).rolling(window=10).max()
    df['Entry_Condition'] = (df['High'] > df['Prev_Highest_High_10']) & (df['IBS'] < 0.15)
    return df['Entry_Condition'].iloc[-1]

def check_awesome_oscillator(df):
    if len(df) < 35: return False
    mid = (df['High'] + df['Low']) / 2
    ao = mid.rolling(window=5).mean() - mid.rolling(window=34).mean()
    return (ao > 0).iloc[-1] and (ao.shift(1) < 0).iloc[-1]

def check_macd_oscillator(df):
    if len(df) < 27: return False
    ma1 = df['Close'].rolling(window=12, min_periods=1, center=False).mean()
    ma2 = df['Close'].rolling(window=26, min_periods=1, center=False).mean()
    return (ma1 > ma2).iloc[-1] and (ma1.shift(1) < ma2).iloc[-1]

def check_bollinger_bands(df):
    if len(df) < 21: return False
    std = df['Close'].rolling(window=20).std()
    ma = df['Close'].rolling(window=20).mean()
    lower = ma - 2 * std
    return (df['Close'] <= lower * 1.01).iloc[-1]

def check_shooting_star(df, multiplier=1.5):
    if len(df) < 15: return False
    p = df['Close'].iloc[-1]
    o = df['Open'].iloc[-1]
    h = df['High'].iloc[-1]
    l = df['Low'].iloc[-1]
    range_val = df['High'] - df['Low']
    atr = range_val.rolling(window=14).mean().iloc[-1]
    body = abs(o - p)
    upper_wick = h - max(o, p)
    lower_wick = min(o, p) - l
    return upper_wick > multiplier * body and upper_wick > 0.5 * atr and lower_wick < 0.2 * atr

def check_dual_thrust(df, k1=0.2):
    if len(df) < 6: return False
    hh = df['High'].iloc[-5:-1].max()
    lc = df['Close'].iloc[-5:-1].min()
    hc = df['Close'].iloc[-5:-1].max()
    ll = df['Low'].iloc[-5:-1].min()
    r = max(hh - lc, hc - ll)
    opening = df['Open'].iloc[-1]
    price = df['Close'].iloc[-1]
    buy_line = opening + k1 * r
    return price >= buy_line

def check_heikin_ashi(df):
    if len(df) < 5: return False
    ha_close = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    ha_open = ha_close.copy()
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2
    ha_high = pd.concat([df['High'], ha_open, ha_close], axis=1).max(axis=1)
    curr_open = ha_open.iloc[-1]
    curr_close = ha_close.iloc[-1]
    curr_high = ha_high.iloc[-1]
    prev_open = ha_open.iloc[-2]
    prev_close = ha_close.iloc[-2]
    return (curr_open > curr_close and curr_open == curr_high and 
            abs(curr_open - curr_close) > abs(prev_open - prev_close) and
            prev_open > prev_close)

def check_strategy_os(df):
    """ London Breakout / OS Daily Strategy """
    if len(df) < 2: return False
    price = df['Close'].iloc[-1]
    ph = df['High'].iloc[-2]
    pl = df['Low'].iloc[-2]
    return (price > ph) or (price < pl)

def main():
    print(f"=== Dexter Quant: Daily Signal Monitor ===")
    print(f"Date: {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Mode: Paper Trading / Monitoring Only\n")

    strategy_funcs = {
        "Strategy 1: Price Retreat": check_strategy_1,
        "Strategy 2: Turnaround Tuesday": check_strategy_2,
        "Strategy 3: Low Close and IBS": check_strategy_3,
        "Strategy 4: DeMarker Indicator": check_strategy_4,
        "Strategy 5: High of Past Ten Days IBS": check_strategy_5,
        "Awesome Oscillator (AO)": check_awesome_oscillator,
        "MACD Oscillator (MACD)": check_macd_oscillator,
        "Bollinger Bands (BB)": check_bollinger_bands,
        "Shooting Star (SS)": check_shooting_star,
        "Dual Thrust (DT)": check_dual_thrust,
        "Heikin Ashi (HA)": check_heikin_ashi,
        "Strategy OS": check_strategy_os
    }

    signals_found = 0

    for strat_name, func in strategy_funcs.items():
        assets_to_check = STRATEGIES_ASSETS[strat_name]
        strat_signals = []
        
        for asset in assets_to_check:
            df = fetch_data(asset)
            if df.empty:
                continue
                
            try:
                is_signal = func(df.copy())
                if is_signal:
                    strat_signals.append(asset)
                    signals_found += 1
            except Exception as e:
                print(f"Error evaluating {asset} for {strat_name}: {e}")
                
        if strat_signals:
            print(f"[SIGNALS DETECTED] {strat_name}")
            for s in strat_signals:
                print(f"  -> SIGNAL on {s}")
            print()
            
    if signals_found == 0:
        print("No signals triggered today.")
    else:
        print(f"Total Signals Detected Today: {signals_found}")

if __name__ == "__main__":
    main()
