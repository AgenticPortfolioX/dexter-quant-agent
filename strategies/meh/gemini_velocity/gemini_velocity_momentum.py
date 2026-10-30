"""
Strategy: Gemini Velocity — Momentum Flow
Agent: Gemini 3.1 | Orchestrator: Antigravity | Worker: Dexter [AI Quant Agent]
Codename: GEMINI-VELOCITY

Edge:
  This strategy is a pure trend-following model designed to catch the "meat" of a strong move.
  It uses the Average Directional Index (ADX) to determine if a strong trend exists (>25).
  Once a trend is confirmed, it waits for price to dip back to the mean (EMA20), and uses 
  the Stochastic RSI (crossing up from <20 for longs, or crossing down from >80 for shorts)
  to precisely time the re-entry in the direction of the macro trend (EMA200).

Asset Universe: High Beta/Crypto proxies (NVDA, MSTR, TSLA, COIN, AMD, PLTR)
Timeframe: 15-minute bars
Session: 09:30 - 15:45 EST
"""

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
from typing import Dict, List, Optional

class GeminiVelocityStrategy:
    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = tickers or ["NVDA", "MSTR", "TSLA", "COIN", "AMD", "PLTR"]
        self.tz = pytz.timezone('US/Eastern')
        
        # Parameters
        self.adx_period = 14
        self.adx_threshold = 20 # Lowered from 25 to capture earlier trends
        self.ema_short = 20
        self.ema_long = 200
        self.stoch_len = 14
        self.stoch_k = 3
        self.stoch_d = 3

    def fetch_data(self, ticker: str, period: str = "20d") -> pd.DataFrame:
        df = yf.download(ticker, period=period, interval="15m", progress=False)
        if df.empty:
            return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(self.tz)
        else:
            df.index = df.index.tz_convert(self.tz)
        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # 1. EMAs
        df['EMA20'] = df['Close'].ewm(span=self.ema_short, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=self.ema_long, adjust=False).mean()
        
        # 2. ADX (Average Directional Index) using wilders smoothing
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        up_move = df['High'] - df['High'].shift()
        down_move = df['Low'].shift() - df['Low']
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        plus_dm = pd.Series(plus_dm, index=df.index)
        minus_dm = pd.Series(minus_dm, index=df.index)
        
        tr_smooth = tr.ewm(alpha=1/self.adx_period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/self.adx_period, adjust=False).mean() / tr_smooth)
        minus_di = 100 * (minus_dm.ewm(alpha=1/self.adx_period, adjust=False).mean() / tr_smooth)
        
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        df['ADX'] = dx.ewm(alpha=1/self.adx_period, adjust=False).mean()
        
        # ATR for risk
        df['ATR'] = tr.rolling(window=self.adx_period).mean()

        # 3. Stochastic RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.stoch_len).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.stoch_len).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        rsi_min = rsi.rolling(window=self.stoch_len).min()
        rsi_max = rsi.rolling(window=self.stoch_len).max()
        stoch_rsi = 100 * ((rsi - rsi_min) / (rsi_max - rsi_min))
        
        df['StochRSI_K'] = stoch_rsi.rolling(window=self.stoch_k).mean()
        df['StochRSI_D'] = df['StochRSI_K'].rolling(window=self.stoch_d).mean()

        return df

    def generate_signals(self, ticker: str, df: pd.DataFrame) -> List[Dict]:
        if df.empty or len(df) < self.ema_long:
            return []

        df = self.calculate_indicators(df)
        signals = []
        session_df = df.between_time("09:45", "15:45")
        used_dates = set()

        for i in range(1, len(session_df)):
            row = session_df.iloc[i]
            prev_row = session_df.iloc[i-1]
            ts = session_df.index[i]
            trade_date = ts.date()

            if trade_date in used_dates:
                continue

            if pd.isna(row['EMA200']) or pd.isna(row['ADX']):
                continue

            # Core Logic requirements
            close = row['Close']
            ema20 = row['EMA20']
            ema200 = row['EMA200']
            adx = row['ADX']
            atr = row['ATR']
            
            k = row['StochRSI_K']
            d = row['StochRSI_D']
            prev_k = prev_row['StochRSI_K']
            prev_d = prev_row['StochRSI_D']

            # LONG: Trend > 20, Price > EMA 200, pull back near EMA20 (within 1.5%), StochRSI < 40 and crossing up
            if (adx > self.adx_threshold 
                and close > ema200
                and abs(close - ema20) / close < 0.015 # Widened pullback zone to 1.5%
                and prev_k < prev_d and k > d # Cross up
                and k < 40): # Widened from 20 to 40 

                stop_loss = close - (2.5 * atr)
                risk = close - stop_loss
                if risk <= 0: risk = close * 0.005
                take_profit = close + (risk * 2.5) # 2.5R target

                signals.append({
                    'timestamp': ts,
                    'ticker': ticker,
                    'type': 'LONG_ENTRY',
                    'entry': round(float(close), 2),
                    'stop_loss': round(float(stop_loss), 2),
                    'take_profit': round(float(take_profit), 2),
                    'model': 'Gemini Velocity Momentum',
                    'adx': round(float(adx), 1)
                })
                used_dates.add(trade_date)

            # SHORT: Trend > 20, Price < EMA 200, pull back near EMA20 (within 1.5%), StochRSI > 60 and crossing down
            elif (adx > self.adx_threshold 
                  and close < ema200
                  and abs(close - ema20) / close < 0.015 # Widened pullback zone to 1.5%
                  and prev_k > prev_d and k < d # Cross down
                  and k > 60): # Widened from 80 to 60

                stop_loss = close + (2.5 * atr)
                risk = stop_loss - close
                if risk <= 0: risk = close * 0.005
                take_profit = close - (risk * 2.5)

                signals.append({
                    'timestamp': ts,
                    'ticker': ticker,
                    'type': 'SHORT_ENTRY',
                    'entry': round(float(close), 2),
                    'stop_loss': round(float(stop_loss), 2),
                    'take_profit': round(float(take_profit), 2),
                    'model': 'Gemini Velocity Momentum',
                    'adx': round(float(adx), 1)
                })
                used_dates.add(trade_date)

        return signals

    def scan_all(self, period: str = "20d") -> List[Dict]:
        all_signals = []
        for ticker in self.tickers:
            try:
                df = self.fetch_data(ticker, period=period)
                if df.empty:
                    continue
                sigs = self.generate_signals(ticker, df)
                all_signals.extend(sigs)
            except Exception as e:
                pass
        return all_signals

if __name__ == "__main__":
    print("=" * 70)
    print("  GEMINI VELOCITY — Momentum Flow Scanner")
    print("=" * 70)

    strat = GeminiVelocityStrategy()
    signals = strat.scan_all(period="20d")

    print(f"\nTotal Signals: {len(signals)}")
    for sig in signals:
        direction = "🟢 LONG" if sig['type'] == 'LONG_ENTRY' else "🔴 SHORT"
        print(f"  {direction} | {sig['ticker']} @ ${sig['entry']} | SL: ${sig['stop_loss']} | TP: ${sig['take_profit']}")

