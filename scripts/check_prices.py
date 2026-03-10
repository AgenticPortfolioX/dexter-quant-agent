import yfinance as yf
tickers = ["SPY", "QQQ", "NVDA", "AAPL", "TSLA", "META", "DIA", "AMZN", "PLTR"]
for t in tickers:
    try:
        data = yf.download(t, period="1d", interval="5m", progress=False)
        if not data.empty:
            last_price = data['Close'].iloc[-1]
            print(f"{t}: {last_price}")
        else:
            print(f"{t}: Error no data")
    except Exception as e:
        print(f"{t}: Error {e}")
