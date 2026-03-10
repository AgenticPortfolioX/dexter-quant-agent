"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Strategy: GEMINI — Vortex Squeeze (Volatility Expansion)                    ║
║  Label   : G1 (Ai-strats / G-Series)                                         ║
║  Author  : Antigravity Orchestrator | Google Gemini 3.1                      ║
║  Worker  : Dexter [AI Quant Agent]                                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  EDGE:                                                                        ║
║    Markets alternate between phases of volatility contraction (consolidation)  ║
║    and volatility expansion (trends). The "Vortex Squeeze" detects maximum   ║
║    compression when Bollinger Bands (Standard Deviation) completely narrow   ║
║    inside Keltner Channels (Average True Range).                             ║
║                                                                               ║
║    When the squeeze "fires" (volatility expands out of the channel), we stack║
║    two confirmations:                                                         ║
║      1. ADX (Average Directional Index) > 20: Ensures a valid trend is       ║
║         forming, filtering out chop/whipsaw.                                 ║
║      2. MACD Histogram: Dictates the true underlying momentum direction.     ║
║                                                                               ║
║  WHY THIS IS DIFFERENT:                                                       ║
║    - Apex (Pivot): Structural level mean-reversion/bounce                    ║
║    - Sonnet (ORB): Time-based breakout (Opening Range)                       ║
║    - Opus (Keltner): Counter-trend extreme mean-reversion                    ║
║    - GEMINI: Pure Volatility Expansion. It waits for the market to go "quiet"║
║      and store kinetic energy, then catches the explosive release.           ║
║                                                                               ║
║  v2.0 IMPROVEMENTS:                                                           ║
║    - TP reduced 3.0→2.5× ATR to secure higher WR on intraday breakouts       ║
║    - 50-EMA Trend Filter added to align breakouts with dominant trend        ║
║    - ADX Threshold bumped 20.0→22.0 to ensure higher explosive conviction    ║
║                                                                               ║
║  ASSETS  : High-liquidity, high-growth names that trend cleanly.             ║
║            (AAPL, MSFT, GOOGL, AMZN, NFLX, META, CRWD, PANW)                 ║
║  TIMEFRAME: 5-minute intraday bars                                            ║
║  SESSION : 09:30 – 16:00 EST                                                 ║
║  RISK    : 1.5× ATR Stop | Target = 2.5× ATR | R:R = 1.66                    ║
║  SIGNALS : Max 1 per ticker per day (captures the daily dominant trend)      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
import json
import os
from datetime import datetime, time, date
from typing import Dict, List, Optional, Tuple

# ─── Constants ────────────────────────────────────────────────────────────────

STRATEGY_ID   = "G1"
STRATEGY_NAME = "Gemini (Vortex Squeeze)"
VERSION       = "2.0.0"

SESSION_START = time(9, 30)
SESSION_END   = time(16, 0)

# Squeeze Parameters
BB_PERIOD     = 20
BB_STD        = 2.0
KC_PERIOD     = 20
KC_ATR_MULT   = 1.5

# Confirmations
ADX_PERIOD    = 14
ADX_THRESHOLD = 22.0

MACD_FAST     = 12
MACD_SLOW     = 26
MACD_SIGNAL   = 9

# Risk Management
ATR_PERIOD    = 14
SL_ATR_MULT   = 1.5
TP_ATR_MULT   = 2.5
MIN_RR        = 1.5
MIN_ATR_DOLLARS = 0.20


# ─── Strategy Class ──────────────────────────────────────────────────────────


class GeminiVortexSqueeze:
    """
    GEMINI — Vortex Squeeze.

    Volatility expansion strategy. Detects periods where Bollinger Bands contract
    inside Keltner Channels (the squeeze). Once BB expands back outside KC, it
    checks ADX and MACD to confirm trend strength and direction, entering on
    the breakout.
    """

    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = tickers or [
            "AAPL", "MSFT", "GOOGL", "AMZN",
            "NFLX", "META", "CRWD", "PANW"
        ]
        self.tz = pytz.timezone("US/Eastern")

    # ── Data Layer ────────────────────────────────────────────────────────────

    def _fetch(self, ticker: str, period: str = "5d") -> pd.DataFrame:
        """Download 5-minute intraday bars, normalize to EST."""
        df = yf.download(ticker, period=period, interval="5m", progress=False)
        if df.empty:
            return df

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(self.tz)
        else:
            df.index = df.index.tz_convert(self.tz)

        return df

    # ── Indicators ────────────────────────────────────────────────────────────

    def _atr(self, df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
        hl  = df["High"] - df["Low"]
        hcp = (df["High"] - df["Close"].shift()).abs()
        lcp = (df["Low"]  - df["Close"].shift()).abs()
        tr  = pd.concat([hl, hcp, lcp], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _squeeze_bands(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Bollinger Bands and Keltner Channels to detect Squeeze."""
        df = df.copy()
        
        # Bollinger Bands
        sma = df["Close"].rolling(BB_PERIOD).mean()
        std = df["Close"].rolling(BB_PERIOD).std()
        df["BB_Upper"] = sma + (BB_STD * std)
        df["BB_Lower"] = sma - (BB_STD * std)
        
        # Keltner Channels
        ema = df["Close"].ewm(span=KC_PERIOD, adjust=False).mean()
        atr = self._atr(df, KC_PERIOD)
        df["KC_Upper"] = ema + (KC_ATR_MULT * atr)
        df["KC_Lower"] = ema - (KC_ATR_MULT * atr)
        
        # Squeeze Condition: BB entirely inside KC
        # True = Squeeze is ON, False = Squeeze is OFF (Expanded)
        df["Squeeze_On"] = (df["BB_Upper"] < df["KC_Upper"]) & (df["BB_Lower"] > df["KC_Lower"])
        
        return df

    def _macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate MACD Line, Signal, and Histogram."""
        df = df.copy()
        ema_fast = df["Close"].ewm(span=MACD_FAST, adjust=False).mean()
        ema_slow = df["Close"].ewm(span=MACD_SLOW, adjust=False).mean()
        df["MACD_Line"] = ema_fast - ema_slow
        df["MACD_Signal"] = df["MACD_Line"].ewm(span=MACD_SIGNAL, adjust=False).mean()
        df["MACD_Hist"] = df["MACD_Line"] - df["MACD_Signal"]
        return df

    def _adx(self, df: pd.DataFrame) -> pd.Series:
        """Calculate ADX (Average Directional Index)."""
        up_move = df["High"] - df["High"].shift(1)
        down_move = df["Low"].shift(1) - df["Low"]
        
        pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        pos_dm = pd.Series(pos_dm, index=df.index)
        neg_dm = pd.Series(neg_dm, index=df.index)
        
        tr_smooth = self._atr(df, 1).ewm(alpha=1/ADX_PERIOD, adjust=False).mean()
        pos_di = 100 * (pos_dm.ewm(alpha=1/ADX_PERIOD, adjust=False).mean() / tr_smooth)
        neg_di = 100 * (neg_dm.ewm(alpha=1/ADX_PERIOD, adjust=False).mean() / tr_smooth)
        
        dx = 100 * np.abs(pos_di - neg_di) / (pos_di + neg_di).replace(0, 1)
        adx = dx.ewm(alpha=1/ADX_PERIOD, adjust=False).mean()
        return adx

    def _calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self._squeeze_bands(df)
        df = self._macd(df)
        df["ADX"] = self._adx(df)
        df["ATR"] = self._atr(df, ATR_PERIOD)
        df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()
        return df

    # ── Main Signal Generator ─────────────────────────────────────────────────

    def generate_signals(self, ticker: str, period: str = "5d") -> List[Dict]:
        """
        Scan a single ticker for Vortex Squeeze Breakouts.
        Returns Dexter-compatible signal dicts.
        """
        df = self._fetch(ticker, period=period)
        if df.empty or len(df) < max(MACD_SLOW, ADX_PERIOD, BB_PERIOD) + 10:
            print(f"  [{ticker}] No data / insufficient history.")
            return []

        df = self._calculate_all(df)

        # Filter to session hours
        session_df = df.between_time(
            SESSION_START.strftime("%H:%M"),
            SESSION_END.strftime("%H:%M")
        )

        if len(session_df) < 3:
            return []

        signals = []
        fired_dates = set()

        for i in range(1, len(session_df)):
            row  = session_df.iloc[i]
            prev = session_df.iloc[i - 1]
            ts   = session_df.index[i]
            trade_date = ts.date()

            # Enforce max 1 signal per day
            if trade_date in fired_dates:
                continue

            if any(pd.isna(row.get(col, np.nan)) for col in ["ATR", "Squeeze_On", "MACD_Hist", "ADX"]):
                continue

            close = float(row["Close"])
            atr   = float(row["ATR"])
            if atr < MIN_ATR_DOLLARS:
                continue

            # The trigger: Squeeze was ON in the previous bar, but is OFF in the current bar
            # meaning volatility is actively expanding.
            squeeze_fired = bool(prev["Squeeze_On"] == True) and bool(row["Squeeze_On"] == False)
            
            adx_strong = float(row["ADX"]) > ADX_THRESHOLD
            macd_hist  = float(row["MACD_Hist"])
            ema_50     = float(row["EMA_50"])

            if squeeze_fired and adx_strong:
                # ── LONG: MACD Histogram is positive and growing AND price > 50-EMA ─────────
                if macd_hist > 0 and macd_hist > float(prev["MACD_Hist"]) and close > ema_50:
                    stop_loss   = round(close - (SL_ATR_MULT * atr), 2)
                    take_profit = round(close + (TP_ATR_MULT * atr), 2)
                    risk = close - stop_loss
                    reward = take_profit - close
                    
                    if risk <= 0: continue
                    rr = round(reward / risk, 2)
                    if rr < MIN_RR: continue

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
                        "adx"          : round(float(row["ADX"]), 2),
                        "macd_hist"    : round(macd_hist, 4),
                        "atr"          : round(atr, 4),
                        "model"        : f"Gemini G1 v{VERSION}",
                    })
                    fired_dates.add(trade_date)
                    print(f"  [{ticker}] 🟢 LONG  (Vortex Squeeze) @ ${close:.2f}"
                          f" | TP ${take_profit:.2f} | SL ${stop_loss:.2f}"
                          f" | R:R {rr} | {ts}")
                
                # ── SHORT: MACD Histogram is negative and falling AND price < 50-EMA ─────────
                elif macd_hist < 0 and macd_hist < float(prev["MACD_Hist"]) and close < ema_50:
                    stop_loss   = round(close + (SL_ATR_MULT * atr), 2)
                    take_profit = round(close - (TP_ATR_MULT * atr), 2)
                    risk = stop_loss - close
                    reward = close - take_profit
                    
                    if risk <= 0: continue
                    rr = round(reward / risk, 2)
                    if rr < MIN_RR: continue

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
                        "adx"          : round(float(row["ADX"]), 2),
                        "macd_hist"    : round(macd_hist, 4),
                        "atr"          : round(atr, 4),
                        "model"        : f"Gemini G1 v{VERSION}",
                    })
                    fired_dates.add(trade_date)
                    print(f"  [{ticker}] 🔴 SHORT (Vortex Squeeze) @ ${close:.2f}"
                          f" | TP ${take_profit:.2f} | SL ${stop_loss:.2f}"
                          f" | R:R {rr} | {ts}")

        return signals

    # ── Multi-Ticker Scanner ──────────────────────────────────────────────────

    def scan_all(self, period: str = "5d") -> List[Dict]:
        """Scan entire ticker universe and aggregate signals."""
        all_signals = []

        print("=" * 72)
        print(f"  GEMINI G1 — Vortex Squeeze Scanner")
        print(f"  Orchestrator: Antigravity | Agent: Dexter | v{VERSION}")
        print(f"  Edge: Volatility Expansion (BB breaks KC) + ADX + MACD")
        print("=" * 72)

        for ticker in self.tickers:
            try:
                sigs = self.generate_signals(ticker, period=period)
                all_signals.extend(sigs)
                if not sigs:
                    print(f"  [{ticker}] — No vortex squeeze setups found.")
            except Exception as e:
                print(f"  [{ticker}] ERROR: {e}")

        return all_signals

    # ── Signal Emitter ────────────────────────────────────────────────────────

    def emit_signals(self, signals: List[Dict]) -> None:
        """Write signals to standard Dexter log format."""
        output_dir  = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
        output_file = os.path.join(output_dir, "gemini_g1_signals.json")

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
    strat   = GeminiVortexSqueeze()
    signals = strat.scan_all(period="5d")

    total_long  = sum(1 for s in signals if s["type"] == "LONG_ENTRY")
    total_short = sum(1 for s in signals if s["type"] == "SHORT_ENTRY")

    print(f"\n{'=' * 72}")
    print(f"  Scan Complete — {len(signals)} total signal(s)")
    print(f"  Long Breakouts:  {total_long}")
    print(f"  Short Breakdowns: {total_short}")
    print(f"{'=' * 72}\n")

    if signals:
        strat.emit_signals(signals)

        print(f"\n  {'TICKER':<8} {'TYPE':<14} {'ENTRY':>8} {'SL':>8} {'TP':>8} {'R:R':>5}  TIMESTAMP")
        print(f"  {'-' * 72}")
        for sig in signals:
            icon = "🟢 LONG " if sig["type"] == "LONG_ENTRY" else "🔴 SHORT"
            print(
                f"  {sig['ticker']:<8} {icon:<14} "
                f"${sig['entry']:>7.2f}  ${sig['stop_loss']:>7.2f}  "
                f"${sig['take_profit']:>7.2f}  {sig['rr']:>4.1f}  "
                f"{sig['timestamp']}"
            )
    else:
        print("  No volatility squeezes fired in the lookback period.")
