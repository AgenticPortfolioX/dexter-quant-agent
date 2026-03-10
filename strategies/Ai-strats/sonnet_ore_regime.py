"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Strategy: SONNET — Opening Range Expansion + Regime Filter                  ║
║  Label   : S1 (Ai-strats / S-Series)                                         ║
║  Author  : Antigravity Orchestrator | Claude Sonnet 4.6                      ║
║  Worker  : Dexter [AI Quant Agent]                                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  EDGE:                                                                        ║
║    The first 15 minutes of the US equity session create an "Opening Range"   ║
║    (ORH / ORL). When price breaks this range with BOTH of the following:     ║
║      1. SPY Regime Alignment  — SPY must be trending in the same direction   ║
║         as the breakout (20-EMA slope filter, updated hourly).               ║
║      2. Volume Delta Surge    — The breakout bar's buy/sell volume imbalance ║
║         must exceed 60% dominant side (proxy: close position in bar).        ║
║    This confluence confirms institutional participation and not merely a      ║
║    retail stop-hunt, dramatically improving the signal-to-noise ratio.       ║
║                                                                               ║
║  WHEN IT FIRES:                                                               ║
║    • Long  → breakout candle CLOSES above ORH + regime bullish + vol surge   ║
║    • Short → breakout candle CLOSES below ORL + regime bearish + vol surge   ║
║                                                                               ║
║  ASSETS  : High-beta US equities with strong intraday range and volume       ║
║            (NVDA, TSLA, META, AAPL, AMZN, MSFT, AMD, PLTR, COIN, MSTR)     ║
║  TIMEFRAME: 5-minute intraday bars                                            ║
║  SESSION : 09:30 – 16:00 EST (ORH/ORL locked at 09:45 EST)                  ║
║  RISK    : 1.5× ATR Stop | 3.0× ATR Target | R:R ≥ 2.0                     ║
║  SIGNALS : Max 1 per ticker per day (first valid breakout only)              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
import json
import os
import sys
from datetime import datetime, time, date, timedelta
from typing import Dict, List, Optional, Tuple


# ─── Constants ────────────────────────────────────────────────────────────────

STRATEGY_ID   = "S1"
STRATEGY_NAME = "Sonnet (ORE + Regime)"
VERSION       = "1.0.0"

# Opening Range window: market open to 09:45 EST (3 × 5-min bars)
OR_CLOSE_TIME  = time(9, 45)
SESSION_START  = time(9, 30)
SESSION_END    = time(16, 0)

# Regime filter — SPY 20-bar EMA slope on 5-min
REGIME_EMA_PERIOD   = 20

# Volume-delta proxy threshold: close must be in top/bottom X% of bar range
# 0.60 = price closed in upper 60% of bar (bullish delta confirmation)
VOL_DELTA_THRESHOLD = 0.60

# Risk parameters
SL_ATR_MULT = 1.5
TP_ATR_MULT = 3.0
ATR_PERIOD  = 14

# Minimum ATR in $ for a valid signal (avoid low-vol noise)
MIN_ATR_DOLLARS = 0.25

# ─── Strategy Class ───────────────────────────────────────────────────────────


class SonnetORERegime:
    """
    SONNET — Opening Range Expansion + Regime Filter + Volume Delta.

    Dexter executes this during normal market hours (09:30–16:00 EST).
    One signal per ticker per session. First clean breakout wins.
    """

    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = tickers or [
            "NVDA", "TSLA", "META", "AAPL", "AMZN",
            "MSFT", "AMD",  "PLTR", "COIN", "MSTR"
        ]
        self.tz = pytz.timezone("US/Eastern")
        self.spy_cache: Optional[pd.DataFrame] = None

    # ── Data Layer ────────────────────────────────────────────────────────────

    def _fetch(self, ticker: str, period: str = "5d") -> pd.DataFrame:
        """Download 5-minute bars and normalize to EST timezone."""
        df = yf.download(ticker, period=period, interval="5m", progress=False)
        if df.empty:
            return df

        # Flatten multi-index if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Normalize to EST
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(self.tz)
        else:
            df.index = df.index.tz_convert(self.tz)

        return df

    def _get_spy(self, period: str = "5d") -> pd.DataFrame:
        """Cached SPY fetch — shared across all ticker scans."""
        if self.spy_cache is None:
            self.spy_cache = self._fetch("SPY", period=period)
        return self.spy_cache

    # ── Indicators ────────────────────────────────────────────────────────────

    def _atr(self, df: pd.DataFrame) -> pd.Series:
        """True Range → ATR(14)."""
        hl   = df["High"] - df["Low"]
        hcp  = (df["High"] - df["Close"].shift()).abs()
        lcp  = (df["Low"]  - df["Close"].shift()).abs()
        tr   = pd.concat([hl, hcp, lcp], axis=1).max(axis=1)
        return tr.rolling(ATR_PERIOD).mean()

    def _ema(self, series: pd.Series, n: int) -> pd.Series:
        return series.ewm(span=n, adjust=False).mean()

    def _opening_range(self, df: pd.DataFrame, trade_date: date) -> Optional[Tuple[float, float]]:
        """
        Calculate Opening Range High/Low for a specific date.
        Uses bars from 09:30 to 09:45 (inclusive of the 09:45 close bar).
        Returns (or_high, or_low) or None if insufficient data.
        """
        day_df = df[df.index.date == trade_date]
        or_bars = day_df.between_time("09:30", "09:44")   # up to & including 09:40 open bar

        # We need at least 2 bars (09:30 and 09:35 bars) to define a range
        if len(or_bars) < 2:
            return None

        or_high = float(or_bars["High"].max())
        or_low  = float(or_bars["Low"].min())

        # Reject degenerate ranges (less than $0.05)
        if (or_high - or_low) < 0.05:
            return None

        return or_high, or_low

    def _spy_regime(self, spy_df: pd.DataFrame, bar_ts: pd.Timestamp) -> int:
        """
        SPY Regime Filter.
        Returns:
            +1 = bullish  (SPY 5-min EMA20 slope is positive)
            -1 = bearish  (slope is negative)
             0 = neutral  (flat / insufficient data)
        """
        if spy_df.empty:
            return 0

        # Use bars up to and including the current bar timestamp
        hist = spy_df[spy_df.index <= bar_ts].tail(REGIME_EMA_PERIOD + 5)
        if len(hist) < REGIME_EMA_PERIOD:
            return 0

        ema = self._ema(hist["Close"], REGIME_EMA_PERIOD)
        if len(ema) < 2 or pd.isna(ema.iloc[-1]) or pd.isna(ema.iloc[-2]):
            return 0

        slope = ema.iloc[-1] - ema.iloc[-2]

        if slope > 0.005:    # at least half a cent per 5-min bar
            return 1
        elif slope < -0.005:
            return -1
        return 0

    def _volume_delta_long(self, row: pd.Series) -> bool:
        """
        Bullish volume-delta proxy.
        Close must be in the TOP VOL_DELTA_THRESHOLD of [Low, High].
        Indicates buyers dominated the bar.
        """
        bar_range = row["High"] - row["Low"]
        if bar_range < 0.01:
            return False
        close_position = (row["Close"] - row["Low"]) / bar_range
        return close_position >= VOL_DELTA_THRESHOLD

    def _volume_delta_short(self, row: pd.Series) -> bool:
        """
        Bearish volume-delta proxy.
        Close must be in the BOTTOM (1 - VOL_DELTA_THRESHOLD) of [Low, High].
        Indicates sellers dominated the bar.
        """
        bar_range = row["High"] - row["Low"]
        if bar_range < 0.01:
            return False
        close_position = (row["Close"] - row["Low"]) / bar_range
        return close_position <= (1.0 - VOL_DELTA_THRESHOLD)

    # ── Signal Generation ─────────────────────────────────────────────────────

    def generate_signals(self, ticker: str, period: str = "5d") -> List[Dict]:
        """
        Main signal scanner for a single ticker.
        Returns a list of signal dicts compatible with Dexter's alpha_autotrader.
        """
        df = self._fetch(ticker, period=period)
        if df.empty or len(df) < ATR_PERIOD + 5:
            print(f"  [{ticker}] No data / insufficient history.")
            return []

        spy_df = self._get_spy(period=period)
        df["ATR"] = self._atr(df)

        signals    = []
        fired_dates = set()

        # Get unique trading dates in data
        unique_dates = sorted(set(df.index.date))

        for trade_date in unique_dates:
            # Skip already-fired dates (one signal per day max)
            if trade_date in fired_dates:
                continue

            # ── Build Opening Range ─────────────────────────────────────
            or_result = self._opening_range(df, trade_date)
            if or_result is None:
                continue
            or_high, or_low = or_result

            # ── Scan breakout bars (from 09:45 onwards) ────────────────
            day_df = df[df.index.date == trade_date]
            # Breakout zone: after OR locks in, within session
            breakout_bars = day_df.between_time("09:45", "15:55")

            for i, (ts, row) in enumerate(breakout_bars.iterrows()):
                if trade_date in fired_dates:
                    break

                atr = row.get("ATR", np.nan)
                if pd.isna(atr) or atr < MIN_ATR_DOLLARS:
                    continue

                close = float(row["Close"])
                open_ = float(row["Open"])

                # ── Regime check ────────────────────────────────────────
                regime = self._spy_regime(spy_df, ts)

                # ── LONG: Breakout above ORH ─────────────────────────
                if (close > or_high                       # closes ABOVE ORH
                        and open_ < or_high               # opened below (true breakout)
                        and regime == 1                   # SPY trending bullish
                        and self._volume_delta_long(row)  # buyers dominated bar
                        and close > open_):               # green candle

                    stop_loss   = round(close - SL_ATR_MULT * atr, 2)
                    take_profit = round(close + TP_ATR_MULT * atr, 2)
                    rr          = round((take_profit - close) / (close - stop_loss), 2) if (close - stop_loss) > 0 else 0

                    # Enforce R:R minimum
                    if rr < 2.0:
                        continue

                    signals.append({
                        "timestamp"    : ts.isoformat(),
                        "ticker"       : ticker,
                        "strategy_id"  : STRATEGY_ID,
                        "strategy_name": STRATEGY_NAME,
                        "type"         : "LONG_ENTRY",
                        "entry"        : round(close, 2),
                        "stop_loss"    : stop_loss,
                        "take_profit"  : take_profit,
                        "rr"           : rr,
                        "or_high"      : round(or_high, 2),
                        "or_low"       : round(or_low, 2),
                        "atr"          : round(atr, 4),
                        "regime"       : "BULLISH",
                        "model"        : f"Sonnet S1 v{VERSION}",
                    })
                    fired_dates.add(trade_date)
                    print(f"  [{ticker}] 🟢 LONG  @ ${close:.2f} | TP ${take_profit:.2f} | SL ${stop_loss:.2f} | R:R {rr} | {ts}")

                # ── SHORT: Breakdown below ORL ────────────────────────
                elif (close < or_low                        # closes BELOW ORL
                        and open_ > or_low                  # opened above (true breakdown)
                        and regime == -1                    # SPY trending bearish
                        and self._volume_delta_short(row)   # sellers dominated bar
                        and close < open_):                 # red candle

                    stop_loss   = round(close + SL_ATR_MULT * atr, 2)
                    take_profit = round(close - TP_ATR_MULT * atr, 2)
                    rr          = round((close - take_profit) / (stop_loss - close), 2) if (stop_loss - close) > 0 else 0

                    if rr < 2.0:
                        continue

                    signals.append({
                        "timestamp"    : ts.isoformat(),
                        "ticker"       : ticker,
                        "strategy_id"  : STRATEGY_ID,
                        "strategy_name": STRATEGY_NAME,
                        "type"         : "SHORT_ENTRY",
                        "entry"        : round(close, 2),
                        "stop_loss"    : stop_loss,
                        "take_profit"  : take_profit,
                        "rr"           : rr,
                        "or_high"      : round(or_high, 2),
                        "or_low"       : round(or_low, 2),
                        "atr"          : round(atr, 4),
                        "regime"       : "BEARISH",
                        "model"        : f"Sonnet S1 v{VERSION}",
                    })
                    fired_dates.add(trade_date)
                    print(f"  [{ticker}] 🔴 SHORT @ ${close:.2f} | TP ${take_profit:.2f} | SL ${stop_loss:.2f} | R:R {rr} | {ts}")

        return signals

    # ── Multi-Ticker Scanner ──────────────────────────────────────────────────

    def scan_all(self, period: str = "5d") -> List[Dict]:
        """Scan full ticker universe. Pre-fetches SPY once for efficiency."""
        self.spy_cache = None   # Reset cache for fresh run
        all_signals = []

        print("=" * 72)
        print(f"  SONNET S1 — Opening Range Expansion + Regime Scanner")
        print(f"  Orchestrator: Antigravity | Agent: Dexter | v{VERSION}")
        print("=" * 72)

        for ticker in self.tickers:
            try:
                sigs = self.generate_signals(ticker, period=period)
                all_signals.extend(sigs)
                if not sigs:
                    print(f"  [{ticker}] — No setups found.")
            except Exception as e:
                print(f"  [{ticker}] ERROR: {e}")

        return all_signals

    # ── Dexter Signal Emitter ─────────────────────────────────────────────────

    def emit_signals(self, signals: List[Dict]) -> None:
        """
        Write signals to the standard Dexter signal log format.
        alpha_autotrader.py reads from this location.
        """
        output_dir  = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
        output_file = os.path.join(output_dir, "sonnet_s1_signals.json")

        os.makedirs(output_dir, exist_ok=True)

        payload = {
            "strategy_id"  : STRATEGY_ID,
            "strategy_name": STRATEGY_NAME,
            "version"      : VERSION,
            "generated_at" : datetime.now(pytz.timezone("US/Eastern")).isoformat(),
            "signal_count" : len(signals),
            "signals"      : signals,
        }

        with open(output_file, "w") as f:
            json.dump(payload, f, indent=2, default=str)

        print(f"\n  ✅ Signals written → {output_file}")


# ── Standalone Execution ───────────────────────────────────────────────────────

if __name__ == "__main__":
    strat   = SonnetORERegime()
    signals = strat.scan_all(period="5d")

    total_long  = sum(1 for s in signals if s["type"] == "LONG_ENTRY")
    total_short = sum(1 for s in signals if s["type"] == "SHORT_ENTRY")

    print(f"\n{'=' * 72}")
    print(f"  Scan Complete — {len(signals)} total signal(s)")
    print(f"  Long: {total_long}  |  Short: {total_short}")
    print(f"{'=' * 72}\n")

    if signals:
        strat.emit_signals(signals)

        print(f"\n  {'TICKER':<8} {'TYPE':<12} {'ENTRY':>8} {'SL':>8} {'TP':>8} {'R:R':>5}  TIMESTAMP")
        print(f"  {'-'*72}")
        for sig in signals:
            direction = "🟢 LONG " if sig["type"] == "LONG_ENTRY" else "🔴 SHORT"
            print(
                f"  {sig['ticker']:<8} {direction:<12} "
                f"${sig['entry']:>7.2f}  ${sig['stop_loss']:>7.2f}  "
                f"${sig['take_profit']:>7.2f}  {sig['rr']:>4.1f}  {sig['timestamp']}"
            )
    else:
        print("  No signals generated for the lookback period.")
