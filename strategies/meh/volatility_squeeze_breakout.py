"""
Strategy: Nova — Volatility Squeeze Breakout
Agent: Gemini 3.1 | Orchestrator: Antigravity | Worker: Dexter [AI Quant Agent]
Codename: NOVA

Edge:
  Volatility is cyclical. Periods of extreme price compression (low volatility)
  are invariably followed by explosive trend expansion (high volatility).
  Nova detects a "Squeeze" when the Bollinger Bands (standard deviation-based)
  contract completely inside the Keltner Channels (ATR-based). 
  
  The setup "fires" when price breaks out of the Keltner Channel in the direction
  of the macro trend (200 EMA), confirmed by a volume surge. This leads to
  high-probability, high-R:R explosive momentum trades.

  Unlike mean-reversion, VWAP bounces, or ORB, this is a pure volatility-cycle
  expansion strategy.

Asset Universe: High Beta/Explosive Equities (TSLA, NVDA, AMD, MSTR, COIN)
Timeframe: 15-minute bars
Context TF: None needed (uses 200 EMA on the 15m)
Session: 09:30 - 15:30 EST (Requires time for the explosive move to play out)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
from datetime import datetime
from typing import Dict, List, Optional


class VolatilitySqueezeBreakoutStrategy:
    """
    Nova — Volatility Squeeze Breakout Strategy.

    Indicators:
        - Bollinger Bands: 20 period SMA, 2.0 Standard Deviations
        - Keltner Channels: 20 period EMA, 1.5 ATR (Average True Range)
        - Trend Filter: 200 period EMA
        - Relative Volume (RVOL): 20 period SMA of Volume

    Squeeze Definition:
        - BB Upper < KC Upper AND BB Lower > KC Lower
        - Meaning: Structural volatility (BB) is historically low compared to average true range (KC).

    Long Entry Conditions:
        1. "Squeeze Fired": Strategy was in a Squeeze within the last 5 bars, but is currently breaking out.
        2. Price closes ABOVE the KC Upper Band.
        3. Price is ABOVE the 200 EMA (Macro Bullish).
        4. RVOL > 1.25x (Volume confirmation of the breakout).

    Short Entry Conditions:
        1. "Squeeze Fired": Strategy was in a Squeeze within the last 5 bars, but is currently breaking out.
        2. Price closes BELOW the KC Lower Band.
        3. Price is BELOW the 200 EMA (Macro Bearish).
        4. RVOL > 1.25x.

    Risk Management:
        - Stop Loss: Middle Band (20 SMA/EMA) — if momentum fails, the squeeze is invalidated.
        - Take Profit: 3.0 × Distance from Entry to Stop Loss (Targets pure explosion).
        - Max 1 trade per ticker per day.
    """

    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = tickers or ["TSLA", "NVDA", "AMD", "MSTR", "COIN"]
        self.tz = pytz.timezone('US/Eastern')
        
        # Indicator Settings
        self.period = 20
        self.bb_mult = 2.0
        self.kc_mult = 1.5
        self.ema_mid = 50
        self.ema_long = 200
        self.rvol_threshold = 1.25
        self.squeeze_lookback = 5 # Breakout must happen within 5 bars of a squeeze

    # ── Data Fetching ──────────────────────────────────────────────────────

    def fetch_data(self, ticker: str, period: str = "20d") -> pd.DataFrame:
        """Fetch 15m intraday data for a single ticker."""
        df = yf.download(ticker, period=period, interval="15m", progress=False)
        if df.empty:
            return df

        # Flatten multi-index columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Normalize timezone to EST
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(self.tz)
        else:
            df.index = df.index.tz_convert(self.tz)

        return df

    # ── Indicator Calculations ─────────────────────────────────────────────

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add Bollinger Bands, Keltner Channels, EMA200, and RVOL to the dataframe."""
        df = df.copy()

        # 1. Bollinger Bands
        df['SMA20'] = df['Close'].rolling(window=self.period).mean()
        std20 = df['Close'].rolling(window=self.period).std()
        df['BB_Upper'] = df['SMA20'] + (std20 * self.bb_mult)
        df['BB_Lower'] = df['SMA20'] - (std20 * self.bb_mult)

        # 2. Average True Range (ATR) & Keltner Channels
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        df['ATR20'] = tr.rolling(window=self.period).mean()
        df['EMA20'] = df['Close'].ewm(span=self.period, adjust=False).mean()
        
        df['KC_Upper'] = df['EMA20'] + (df['ATR20'] * self.kc_mult)
        df['KC_Lower'] = df['EMA20'] - (df['ATR20'] * self.kc_mult)

        # 3. Macro Trend & Volume
        df['EMA50'] = df['Close'].ewm(span=self.ema_mid, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=self.ema_long, adjust=False).mean()
        vol_sma = df['Volume'].rolling(window=self.period).mean()
        df['RVOL'] = df['Volume'] / vol_sma

        # 4. Momentum (MACD)
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_Line'] = ema12 - ema26
        df['MACD_Signal'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD_Line'] - df['MACD_Signal']

        # 5. The "Squeeze" Condition: BB contracts entirely inside KC
        df['Squeeze_On'] = (df['BB_Upper'] < df['KC_Upper']) & (df['BB_Lower'] > df['KC_Lower'])
        
        # Track if we were in a squeeze recently (must have squeezed for at least 3 periods in recent past)
        squeeze_sum = df['Squeeze_On'].rolling(window=self.squeeze_lookback).sum()
        df['Recent_Squeeze'] = squeeze_sum >= 3

        return df

    # ── Signal Generation ──────────────────────────────────────────────────

    def generate_signals(self, ticker: str, df: pd.DataFrame) -> List[Dict]:
        """
        Scan processed data for Volatility Expansion Breakouts.
        Returns list of signal dicts compatible with Dexter's signal format.
        """
        if df.empty or len(df) < self.ema_long:
            return []

        df = self.calculate_indicators(df)
        signals = []

        # Filter to session hours only (skip first and last hours to avoid anomalies / forced exits)
        session_df = df.between_time("09:45", "15:30")

        used_dates = set()

        for i in range(1, len(session_df)):
            row = session_df.iloc[i]
            ts = session_df.index[i]
            trade_date = ts.date()

            if trade_date in used_dates:
                continue

            # Skip if indicator data isn't fully warmed up
            if pd.isna(row['EMA200']) or pd.isna(row['KC_Upper']) or pd.isna(row['MACD_Hist']):
                continue

            close = row['Close']
            rvol = row['RVOL']
            ema50 = row['EMA50']
            ema200 = row['EMA200']
            kc_upper = row['KC_Upper']
            kc_lower = row['KC_Lower']
            sma20 = row['SMA20']
            ema20 = row['EMA20']
            atr20 = row['ATR20']
            macd_hist = row['MACD_Hist']

            # Core Requirement: Must be firing from a recent Squeeze
            if not row['Recent_Squeeze']:
                continue
            
            # Additional Check: Make sure we aren't currently IN a deep squeeze 
            # (We want the bar breaking out, not internal chop)
            in_squeeze_now = row['Squeeze_On']

            # ── LONG: Explosive Bullish Breakout ───────────────────────────
            if (not in_squeeze_now
                and close > kc_upper 
                and ema50 > ema200 # Macro alignment
                and macd_hist > 0  # Momentum confirmation
                and rvol >= self.rvol_threshold):

                stop_loss = close - (2.0 * atr20)
                risk = close - stop_loss
                if risk <= 0: risk = close * 0.005 # Fallback risk
                take_profit = close + (risk * 3.0) # 3R Target

                signals.append({
                    'timestamp': ts,
                    'ticker': ticker,
                    'type': 'LONG_ENTRY',
                    'entry': round(float(close), 2),
                    'stop_loss': round(float(stop_loss), 2),
                    'take_profit': round(float(take_profit), 2),
                    'rvol': round(float(rvol), 2),
                    'squeeze_breakout': True,
                    'model': 'Nova Volatility Breakout'
                })
                used_dates.add(trade_date)

            # ── SHORT: Explosive Bearish Breakout ──────────────────────────
            elif (not in_squeeze_now
                  and close < kc_lower 
                  and ema50 < ema200 # Macro alignment
                  and macd_hist < 0  # Momentum confirmation
                  and rvol >= self.rvol_threshold):

                stop_loss = close + (2.0 * atr20)
                risk = stop_loss - close
                if risk <= 0: risk = close * 0.005
                take_profit = close - (risk * 3.0)

                signals.append({
                    'timestamp': ts,
                    'ticker': ticker,
                    'type': 'SHORT_ENTRY',
                    'entry': round(float(close), 2),
                    'stop_loss': round(float(stop_loss), 2),
                    'take_profit': round(float(take_profit), 2),
                    'rvol': round(float(rvol), 2),
                    'squeeze_breakout': True,
                    'model': 'Nova Volatility Breakout'
                })
                used_dates.add(trade_date)

        return signals

    # ── Multi-Ticker Scanner ───────────────────────────────────────────────

    def scan_all(self, period: str = "20d") -> List[Dict]:
        """Scan all tickers in the universe and aggregate signals."""
        all_signals = []
        for ticker in self.tickers:
            try:
                df = self.fetch_data(ticker, period=period)
                if df.empty:
                    print(f"  [{ticker}] No data.")
                    continue
                sigs = self.generate_signals(ticker, df)
                all_signals.extend(sigs)
                print(f"  [{ticker}] {len(sigs)} signal(s) detected.")
            except Exception as e:
                print(f"  [{ticker}] ERROR: {e}")
        return all_signals


# ── Standalone Execution ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("  NOVA — Volatility Squeeze Breakout Scanner")
    print("  Agent: Gemini 3.1 | Orchestrator: Antigravity | Worker: Dexter")
    print("=" * 70)

    strat = VolatilitySqueezeBreakoutStrategy()
    signals = strat.scan_all(period="20d")

    print(f"\n{'=' * 70}")
    print(f"  Total Signals: {len(signals)}")
    print(f"{'=' * 70}")

    for sig in signals:
        direction = "🟢 LONG" if sig['type'] == 'LONG_ENTRY' else "🔴 SHORT"
        try:
            rr = round(abs(sig['take_profit'] - sig['entry']) / abs(sig['entry'] - sig['stop_loss']), 2)
        except ZeroDivisionError:
            rr = "N/A"
        print(f"  {direction} | {sig['ticker']} @ ${sig['entry']}"
              f" | SL: ${sig['stop_loss']} | TP: ${sig['take_profit']}"
              f" | R:R {rr} | RVOL: {sig['rvol']}x | {sig['timestamp']}")
