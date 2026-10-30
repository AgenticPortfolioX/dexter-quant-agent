"""
Strategy: Volcanix — VWAP Reclaim + Relative Volume Surge
Orchestrator: Antigravity | Worker Agent: Dexter [AI Quant Agent]
Role: High-probability intraday momentum strategy

Edge:
  When price loses VWAP and aggressively reclaims it on abnormally high
  relative volume (RVOL >= 2.0x), institutions are repositioning. The reclaim
  traps counter-trend traders and creates a momentum impulse.
  Inverse logic (VWAP rejection on high RVOL) provides short setups.

Assets: SPY, QQQ, NVDA, AAPL, TSLA, META
TF: 5-minute intraday
Session: 09:35 - 15:45 EST
"""

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
from datetime import datetime, time
from typing import Dict, List, Optional


class VWAPReclaimRVOLStrategy:
    """
    Volcanix — VWAP Reclaim + Relative Volume Surge.

    Entry Logic:
      LONG (Reclaim):
        1. Price below VWAP for >= 3 consecutive bars
        2. Current bar closes above VWAP (the reclaim)
        3. Reclaim bar RVOL >= 2.0
        4. Reclaim bar closes above EMA(9)
        5. Bullish candle body (Close > Open)

      SHORT (Rejection):
        1. Price above VWAP for >= 3 consecutive bars
        2. Current bar closes below VWAP (the rejection)
        3. Rejection bar RVOL >= 2.0
        4. Rejection bar closes below EMA(9)
        5. Bearish candle body (Close < Open)

    Risk Management:
        - Stop Loss: 1.5 × ATR(14) from entry
        - Take Profit: 2.5 × ATR(14) from entry (R:R ≈ 1.67)
        - Max 1 trade per ticker per day
        - Exit by 15:45 EST
    """

    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = tickers or ["SPY", "QQQ", "NVDA", "AAPL", "TSLA", "META"]
        self.tz = pytz.timezone('US/Eastern')
        self.rvol_threshold = 2.0
        self.rvol_lookback = 20      # bars for volume SMA baseline
        self.consec_bars = 3         # bars price must be on wrong side of VWAP
        self.atr_period = 14
        self.ema_period = 9
        self.sl_atr_mult = 1.5
        self.tp_atr_mult = 2.5
        self.session_start = time(9, 35)
        self.session_end = time(15, 45)

    # ── Data Fetching ──────────────────────────────────────────────────────

    def fetch_data(self, ticker: str, period: str = "5d") -> pd.DataFrame:
        """Fetch 5m intraday data for a single ticker."""
        df = yf.download(ticker, period=period, interval="5m", progress=False)
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

    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Session VWAP — resets daily."""
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        pv = tp * df['Volume']
        cum_pv = pv.groupby(df.index.date).cumsum()
        cum_v = df['Volume'].groupby(df.index.date).cumsum()
        vwap = cum_pv / cum_v
        return vwap

    def calculate_rvol(self, df: pd.DataFrame) -> pd.Series:
        """Relative Volume — current bar volume / 20-bar SMA of volume."""
        vol_sma = df['Volume'].rolling(window=self.rvol_lookback).mean()
        rvol = df['Volume'] / vol_sma
        return rvol

    def calculate_atr(self, df: pd.DataFrame) -> pd.Series:
        """Average True Range (14)."""
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all indicators to the dataframe."""
        df = df.copy()
        df['VWAP'] = self.calculate_vwap(df)
        df['RVOL'] = self.calculate_rvol(df)
        df['ATR'] = self.calculate_atr(df)
        df['EMA_9'] = df['Close'].ewm(span=self.ema_period, adjust=False).mean()

        # Price position relative to VWAP (1 = above, -1 = below)
        df['Above_VWAP'] = np.where(df['Close'] > df['VWAP'], 1, -1)

        # Consecutive bars below/above VWAP
        # Count consecutive bars of the same VWAP position
        shifted = df['Above_VWAP'] != df['Above_VWAP'].shift()
        df['VWAP_Streak'] = df.groupby(shifted.cumsum()).cumcount() + 1

        # Candle body direction (1 = bullish, -1 = bearish)
        df['Body_Dir'] = np.where(df['Close'] > df['Open'], 1, -1)

        return df

    # ── Signal Generation ──────────────────────────────────────────────────

    def generate_signals(self, ticker: str, df: pd.DataFrame) -> List[Dict]:
        """
        Scan processed data for VWAP Reclaim (long) and Rejection (short) setups.
        Returns list of signal dicts compatible with Dexter's signal format.
        """
        if df.empty or len(df) < self.rvol_lookback + self.atr_period:
            return []

        df = self.calculate_indicators(df)
        signals = []

        # Filter to session hours only
        session_df = df.between_time(
            self.session_start.strftime("%H:%M"),
            self.session_end.strftime("%H:%M")
        )

        # Track used dates — max 1 signal per day per ticker
        used_dates = set()

        for i in range(1, len(session_df)):
            row = session_df.iloc[i]
            prev = session_df.iloc[i - 1]
            ts = session_df.index[i]
            trade_date = ts.date()

            # Skip if already fired today
            if trade_date in used_dates:
                continue

            # Skip if indicators not warm
            if pd.isna(row['ATR']) or pd.isna(row['VWAP']) or pd.isna(row['RVOL']):
                continue

            close = row['Close']
            vwap = row['VWAP']
            rvol = row['RVOL']
            atr = row['ATR']
            ema9 = row['EMA_9']

            # ── LONG: VWAP Reclaim ──────────────────────────────────────
            #   Previous bar was BELOW VWAP with streak >= consec_bars
            #   Current bar closes ABOVE VWAP
            #   RVOL >= threshold, EMA(9) confirmation, bullish body
            if (prev['Above_VWAP'] == -1
                    and prev['VWAP_Streak'] >= self.consec_bars
                    and close > vwap
                    and rvol >= self.rvol_threshold
                    and close > ema9
                    and row['Body_Dir'] == 1):

                stop_loss = close - (self.sl_atr_mult * atr)
                take_profit = close + (self.tp_atr_mult * atr)

                signals.append({
                    'timestamp': ts,
                    'ticker': ticker,
                    'type': 'LONG_ENTRY',
                    'entry': round(float(close), 2),
                    'stop_loss': round(float(stop_loss), 2),
                    'take_profit': round(float(take_profit), 2),
                    'rvol': round(float(rvol), 2),
                    'atr': round(float(atr), 4),
                    'vwap': round(float(vwap), 2),
                    'model': 'Volcanix VWAP Reclaim'
                })
                used_dates.add(trade_date)

            # ── SHORT: VWAP Rejection ───────────────────────────────────
            #   Previous bar was ABOVE VWAP with streak >= consec_bars
            #   Current bar closes BELOW VWAP
            #   RVOL >= threshold, EMA(9) confirmation, bearish body
            elif (prev['Above_VWAP'] == 1
                    and prev['VWAP_Streak'] >= self.consec_bars
                    and close < vwap
                    and rvol >= self.rvol_threshold
                    and close < ema9
                    and row['Body_Dir'] == -1):

                stop_loss = close + (self.sl_atr_mult * atr)
                take_profit = close - (self.tp_atr_mult * atr)

                signals.append({
                    'timestamp': ts,
                    'ticker': ticker,
                    'type': 'SHORT_ENTRY',
                    'entry': round(float(close), 2),
                    'stop_loss': round(float(stop_loss), 2),
                    'take_profit': round(float(take_profit), 2),
                    'rvol': round(float(rvol), 2),
                    'atr': round(float(atr), 4),
                    'vwap': round(float(vwap), 2),
                    'model': 'Volcanix VWAP Rejection'
                })
                used_dates.add(trade_date)

        return signals

    # ── Multi-Ticker Scanner ───────────────────────────────────────────────

    def scan_all(self, period: str = "5d") -> List[Dict]:
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
    print("  VOLCANIX — VWAP Reclaim + Relative Volume Surge Scanner")
    print("  Orchestrator: Antigravity | Agent: Dexter")
    print("=" * 70)

    strat = VWAPReclaimRVOLStrategy()
    signals = strat.scan_all(period="5d")

    print(f"\n{'=' * 70}")
    print(f"  Total Signals: {len(signals)}")
    print(f"{'=' * 70}")

    for sig in signals:
        direction = "🟢 LONG" if sig['type'] == 'LONG_ENTRY' else "🔴 SHORT"
        print(f"  {direction} | {sig['ticker']} @ ${sig['entry']}"
              f" | SL: ${sig['stop_loss']} | TP: ${sig['take_profit']}"
              f" | RVOL: {sig['rvol']}x | {sig['timestamp']}")
