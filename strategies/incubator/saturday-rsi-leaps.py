# saturday-rsi-leaps.py
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import os

# --- Configuration ---
CSP_PULLBACK_RANGE = (0.05, 0.15) # 5-15% pullback for CSP
LEAP_PULLBACK_MIN = 0.10          # 10% off highs for LEAPS
LEAP_RSI_THRESHOLD = 30           # Weekly RSI oversold
CSP_EXIT_PROFIT_PCT = 0.50        # Close CSP at 50% max profit
LEAP_EXIT_HALVE_PCT = 1.00        # Sell half of LEAP at 100% gain

def calculate_sma(series, length):
    return series.rolling(window=length).mean()

def calculate_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def calculate_rsi(series, length=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=length).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=length).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

class SaturdayRSILoops:
    """
    Implements the Saturday RSI LEAPS Loop Strategy:
    1. Engine (CSP): Generate Income from pullbacks in green trend clouds.
    2. Fuel: Funnel CSP profits into a Growth Bucket.
    3. Rocket (LEAPS): Use House Money for massive recovery plays.
    """
    def __init__(self):
        self.universe = ["SPY", "QQQ", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "JPM"]

    def get_weekly_ema_cloud(self, ticker):
        """Checks if Weekly EMA Trend Cloud is Green."""
        df = yf.download(ticker, period="2y", interval="1wk", progress=False, auto_adjust=True)
        if df.empty: return False
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # Trend Cloud: Short EMA (10) > Long EMA (30)
        df['ema10'] = calculate_ema(df['Close'], 10)
        df['ema30'] = calculate_ema(df['Close'], 30)
        
        last = df.iloc[-1]
        return last['ema10'] > last['ema30']

    def get_daily_ema_cloud(self, ticker):
        """Checks if Daily EMA Trend Cloud is Green."""
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df.empty: return False
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df['ema10'] = calculate_ema(df['Close'], 10)
        df['ema30'] = calculate_ema(df['Close'], 30)
        
        last = df.iloc[-1]
        return last['ema10'] > last['ema30']

    def run_engine_scan(self):
        """Step 1: Building the Engine (The CSP)"""
        print("\n--- 🟢 STEP 1: CSP ENGINE SCAN (Income Generation) ---")
        candidates = []
        for ticker in self.universe:
            try:
                # 1. Pullback Check (5-15%)
                df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True)
                if df.empty: continue
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                
                recent_high = df['High'].tail(30).max()
                current_price = df['Close'].iloc[-1]
                pullback_pct = (recent_high - current_price) / recent_high
                
                if CSP_PULLBACK_RANGE[0] <= pullback_pct <= CSP_PULLBACK_RANGE[1]:
                    # 2. Technical Confirmation (Daily + Weekly Trend Clouds)
                    if self.get_daily_ema_cloud(ticker) and self.get_weekly_ema_cloud(ticker):
                        candidates.append({
                            "ticker": ticker,
                            "price": current_price,
                            "pullback": f"{pullback_pct*100:.1f}%",
                            "strategy": "30D CSP (Target 5% Return)"
                        })
            except Exception as e:
                print(f"Error scanning {ticker} for CSP: {e}")
        
        return candidates

    def run_growth_scan(self):
        """Step 2: Buying the LEAP (The Growth)"""
        print("\n--- 🚀 STEP 2: LEAPS GROWTH SCAN (House Money Entry) ---")
        candidates = []
        for ticker in self.universe:
            try:
                # 1. Macro Pullback Check (10-15%)
                df_w = yf.download(ticker, period="2y", interval="1wk", progress=False, auto_adjust=True)
                if df_w.empty: continue
                if isinstance(df_w.columns, pd.MultiIndex): df_w.columns = df_w.columns.get_level_values(0)
                
                all_time_high = df_w['High'].max()
                current_price = df_w['Close'].iloc[-1]
                off_highs_pct = (all_time_high - current_price) / all_time_high
                
                # 2. Weekly RSI < 30
                df_w['rsi'] = calculate_rsi(df_w['Close'], 14)
                last_rsi = df_w['rsi'].iloc[-1]
                
                if off_highs_pct >= LEAP_PULLBACK_MIN and last_rsi <= LEAP_RSI_THRESHOLD:
                    candidates.append({
                        "ticker": ticker,
                        "price": current_price,
                        "off_highs": f"{off_highs_pct*100:.1f}%",
                        "rsi": f"{last_rsi:.1f}",
                        "strategy": "JAN LEAPS (300-365 DTE)"
                    })
            except Exception as e:
                print(f"Error scanning {ticker} for LEAPS: {e}")
        
        return candidates

if __name__ == "__main__":
    strategy = SaturdayRSILoops()
    import json
    
    results = {
        "csp": strategy.run_engine_scan(),
        "leaps": strategy.run_growth_scan()
    }
    
    with open("leaps_loop_candidates.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\nScan results saved to leaps_loop_candidates.json")
