
import sys
import os
import pandas as pd
import yfinance as yf

# Ingest Weekly Data for a Universe of Stocks (e.g., S&P 100/500 proxy)
def process_rsi_leaps_data(tickers=["SPY", "QQQ", "IWM", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA"]):
    # Fetch 2 years of weekly data
    print(f"Fetching 2 years of weekly data for {len(tickers)} tickers...")
    
    # yfinance handles list of tickers
    # period='2y', interval='1wk'
    df = yf.download(tickers, period="2y", interval="1wk", progress=False, group_by='ticker', auto_adjust=True)
    
    if df.empty:
        print("No data fetched.")
        return

    # Check structure. If multiple tickers, columns are MultiIndex (Ticker, OHLC)
    # We want to keep it as is or save in a way that scan logic can iterate.
    # Saving as pickle preserves MultiIndex.
    
    output_path = "weekly_data_universe.pkl"
    df.to_pickle(output_path)
    print(f"Weekly Data saved to {output_path}")
    print("Columns:", df.columns)

if __name__ == "__main__":
    # Expanded list could be passed here
    universe = ["SPY", "QQQ", "IWM", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "JPM", "V"]
    process_rsi_leaps_data(universe)
