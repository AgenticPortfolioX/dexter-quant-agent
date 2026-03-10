"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Strategy: OPUS — Keltner Exhaustion Reversal  (v2.0)                        ║
║  Label   : O1 (Ai-strats / O-Series)                                         ║
║  Author  : Antigravity Orchestrator | Claude Opus 4.6                        ║
║  Worker  : Dexter [AI Quant Agent]                                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  EDGE:                                                                        ║
║    Intraday price moves that penetrate the outer Keltner Channel (2.0× ATR   ║
║    bands) are statistically unsustainable. When this extension coincides      ║
║    with THREE independent exhaustion signals:                                 ║
║                                                                               ║
║      1. Keltner Breach     — Close beyond the outer band (overextension)     ║
║      2. StochRSI Zone+Dir  — StochRSI was in extreme zone within last 3 bars ║
║         AND is now reversing direction (momentum DECELERATING).              ║
║      3. Volume Climax      — Current bar volume ≥ 1.5× the 20-bar SMA,      ║
║         signaling capitulation (on shorts) or euphoria blow-off (on longs). ║
║                                                                               ║
║    The combination catches the "rubber band snap" — the moment smart money   ║
║    absorbs the exhausted move and price reverts toward the 20-EMA mean.      ║
║                                                                               ║
║  v2.0 IMPROVEMENTS:                                                           ║
║    - KC outer band reduced 2.5→2.0× to capture more valid reversals          ║
║    - Volume climax lowered 2.0→1.5× for realistic institutional detection    ║
║    - StochRSI hook replaced with 3-bar zone + direction logic                ║
║    - Candle body filter removed (wicks ARE the exhaustion signal)             ║
║    - Session extended to 09:35–15:55 (captures EOD mean-reversion)           ║
║                                                                               ║
║  ASSETS  : High-volatility large-caps with strong mean-reversion properties  ║
║            (TSLA, NVDA, AMD, MSTR, COIN, SMCI, META, PLTR)                  ║
║  TIMEFRAME: 5-minute intraday bars                                            ║
║  SESSION : 09:35 – 15:55 EST                                                 ║
║  RISK    : 1.0× ATR Stop | Target = Keltner midline (20-EMA) | R:R ≥ 1.5   ║
║  SIGNALS : Max 2 per ticker per day (allows AM + PM reversal)                ║
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

STRATEGY_ID   = "O1"
STRATEGY_NAME = "Opus (Keltner Exhaust)"
VERSION       = "2.0.0"

SESSION_START = time(9, 35)    # Captures early overextension
SESSION_END   = time(15, 55)   # Captures EOD mean-reversion profit-taking

# Keltner Channel parameters
KC_EMA_PERIOD    = 20          # Midline = 20-bar EMA
KC_ATR_PERIOD    = 14          # ATR for band width
KC_OUTER_MULT    = 2.0         # Outer band = 2.0× ATR (standard exhaustion threshold)
KC_INNER_MULT    = 1.5         # Inner band = 1.5× ATR (confirmation zone)

# Stochastic RSI parameters
STOCH_RSI_PERIOD = 14          # RSI lookback
STOCH_K_PERIOD   = 3           # %K smoothing
STOCH_D_PERIOD   = 3           # %D smoothing
STOCH_OB         = 80          # Overbought threshold
STOCH_OS         = 20          # Oversold threshold

# Volume Climax
VOL_CLIMAX_MULT  = 1.5         # Volume must be ≥ 1.5x 20-bar SMA (elevated institutional activity)
VOL_SMA_PERIOD   = 20

# Risk Management
SL_ATR_MULT      = 1.0         # Tight stop — 1.0× ATR beyond the band
MIN_RR           = 1.5         # Minimum reward:risk ratio
MAX_SIGNALS_DAY  = 2           # Allow AM + PM reversals per ticker
MIN_ATR_DOLLARS  = 0.20        # Skip low-vol tickers


# ─── Strategy Class ──────────────────────────────────────────────────────────


class OpusKeltnerExhaust:
    """
    OPUS — Keltner Exhaustion Reversal.

    Counter-trend mean-reversion strategy. Fades overextended intraday moves
    that breach Keltner outer bands while showing momentum exhaustion
    (StochRSI hook) and volume capitulation/euphoria.

    Target: price reverts to Keltner midline (20-EMA).
    """

    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = tickers or [
            "TSLA", "NVDA", "AMD", "MSTR",
            "COIN", "SMCI", "META", "PLTR"
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

    def _atr(self, df: pd.DataFrame) -> pd.Series:
        """ATR(14)."""
        hl  = df["High"] - df["Low"]
        hcp = (df["High"] - df["Close"].shift()).abs()
        lcp = (df["Low"]  - df["Close"].shift()).abs()
        tr  = pd.concat([hl, hcp, lcp], axis=1).max(axis=1)
        return tr.rolling(KC_ATR_PERIOD).mean()

    def _keltner_channels(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Keltner Channel: EMA(20) ± multiplier × ATR(14).
        Returns df with columns: KC_Mid, KC_Upper_Outer, KC_Lower_Outer,
        KC_Upper_Inner, KC_Lower_Inner.
        """
        df = df.copy()
        df["KC_Mid"] = df["Close"].ewm(span=KC_EMA_PERIOD, adjust=False).mean()
        atr = self._atr(df)
        df["ATR"] = atr

        df["KC_Upper_Outer"] = df["KC_Mid"] + (KC_OUTER_MULT * atr)
        df["KC_Lower_Outer"] = df["KC_Mid"] - (KC_OUTER_MULT * atr)
        df["KC_Upper_Inner"] = df["KC_Mid"] + (KC_INNER_MULT * atr)
        df["KC_Lower_Inner"] = df["KC_Mid"] - (KC_INNER_MULT * atr)

        return df

    def _stochastic_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Stochastic RSI: Stochastic oscillator applied to RSI values.
        Returns df with StochRSI_K and StochRSI_D columns.
        """
        df = df.copy()

        # Step 1: RSI(14)
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0.0).ewm(
            alpha=1.0 / STOCH_RSI_PERIOD, adjust=False
        ).mean()
        loss = (-delta.where(delta < 0, 0.0)).ewm(
            alpha=1.0 / STOCH_RSI_PERIOD, adjust=False
        ).mean()
        rs = gain / loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # Step 2: Stochastic of RSI
        rsi_min = rsi.rolling(STOCH_RSI_PERIOD).min()
        rsi_max = rsi.rolling(STOCH_RSI_PERIOD).max()
        rsi_range = rsi_max - rsi_min
        rsi_range = rsi_range.replace(0, np.nan)  # prevent division by zero

        stoch_rsi = ((rsi - rsi_min) / rsi_range) * 100.0

        # Step 3: Smooth to get %K and %D
        df["StochRSI_K"] = stoch_rsi.rolling(STOCH_K_PERIOD).mean()
        df["StochRSI_D"] = df["StochRSI_K"].rolling(STOCH_D_PERIOD).mean()

        return df

    def _volume_climax(self, df: pd.DataFrame) -> pd.Series:
        """
        Volume climax detection.
        Returns boolean Series: True where current volume ≥ VOL_CLIMAX_MULT × SMA(20).
        """
        vol_sma = df["Volume"].rolling(VOL_SMA_PERIOD).mean()
        return df["Volume"] >= (VOL_CLIMAX_MULT * vol_sma)

    def _calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all indicators in one pass."""
        df = self._keltner_channels(df)
        df = self._stochastic_rsi(df)
        df["Vol_Climax"] = self._volume_climax(df)
        return df

    # ── Signal Detection ──────────────────────────────────────────────────────

    def _stochrsi_hook_bullish(self, session_df: pd.DataFrame, i: int) -> bool:
        """
        Bullish StochRSI zone + direction (v2.0):
        - StochRSI_K was below 25 within the last 3 bars
        - AND K is now rising (current K > previous K)
        """
        if i < 3:
            return False
        current_k = session_df.iloc[i].get("StochRSI_K", np.nan)
        prev_k = session_df.iloc[i - 1].get("StochRSI_K", np.nan)
        if pd.isna(current_k) or pd.isna(prev_k):
            return False

        # Check if K was in oversold zone within last 3 bars
        was_in_zone = False
        for lookback in range(1, 4):
            if i - lookback < 0:
                break
            hist_k = session_df.iloc[i - lookback].get("StochRSI_K", np.nan)
            if not pd.isna(hist_k) and float(hist_k) < 25:
                was_in_zone = True
                break

        # K is now rising
        k_rising = float(current_k) > float(prev_k)
        return was_in_zone and k_rising

    def _stochrsi_hook_bearish(self, session_df: pd.DataFrame, i: int) -> bool:
        """
        Bearish StochRSI zone + direction (v2.0):
        - StochRSI_K was above 75 within the last 3 bars
        - AND K is now falling (current K < previous K)
        """
        if i < 3:
            return False
        current_k = session_df.iloc[i].get("StochRSI_K", np.nan)
        prev_k = session_df.iloc[i - 1].get("StochRSI_K", np.nan)
        if pd.isna(current_k) or pd.isna(prev_k):
            return False

        # Check if K was in overbought zone within last 3 bars
        was_in_zone = False
        for lookback in range(1, 4):
            if i - lookback < 0:
                break
            hist_k = session_df.iloc[i - lookback].get("StochRSI_K", np.nan)
            if not pd.isna(hist_k) and float(hist_k) > 75:
                was_in_zone = True
                break

        # K is now falling
        k_falling = float(current_k) < float(prev_k)
        return was_in_zone and k_falling

    # ── Main Signal Generator ─────────────────────────────────────────────────

    def generate_signals(self, ticker: str, period: str = "5d") -> List[Dict]:
        """
        Scan a single ticker for Keltner Exhaustion Reversal setups.
        Returns Dexter-compatible signal dicts.
        """
        df = self._fetch(ticker, period=period)
        if df.empty or len(df) < KC_EMA_PERIOD + STOCH_RSI_PERIOD + 10:
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
        daily_counts: Dict[date, int] = {}

        for i in range(1, len(session_df)):
            row  = session_df.iloc[i]
            prev = session_df.iloc[i - 1]
            ts   = session_df.index[i]
            trade_date = ts.date()

            # Enforce max signals per day
            if daily_counts.get(trade_date, 0) >= MAX_SIGNALS_DAY:
                continue

            # Skip if indicators not warm
            if any(pd.isna(row.get(col, np.nan)) for col in
                   ["ATR", "KC_Mid", "KC_Upper_Outer", "KC_Lower_Outer",
                    "StochRSI_K", "StochRSI_D"]):
                continue

            close = float(row["Close"])
            atr   = float(row["ATR"])

            if atr < MIN_ATR_DOLLARS:
                continue

            kc_mid   = float(row["KC_Mid"])
            kc_upper = float(row["KC_Upper_Outer"])
            kc_lower = float(row["KC_Lower_Outer"])
            vol_climax = bool(row["Vol_Climax"])

            # ── SHORT REVERSAL: Price breached UPPER outer band ──────────
            #    Euphoria blow-off → fade back to mean
            if (close >= kc_upper                                # breached upper band
                    and vol_climax                               # volume spike (euphoria)
                    and self._stochrsi_hook_bearish(session_df, i)):  # momentum hooking down

                stop_loss   = round(close + (SL_ATR_MULT * atr), 2)
                take_profit = round(kc_mid, 2)                   # target = midline (20-EMA)
                risk = stop_loss - close
                reward = close - take_profit

                if risk <= 0 or reward <= 0:
                    continue

                rr = round(reward / risk, 2)
                if rr < MIN_RR:
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
                    "kc_upper"     : round(kc_upper, 2),
                    "kc_mid"       : round(kc_mid, 2),
                    "stoch_k"      : round(float(row["StochRSI_K"]), 2),
                    "stoch_d"      : round(float(row["StochRSI_D"]), 2),
                    "atr"          : round(atr, 4),
                    "reversal_type": "EUPHORIA_FADE",
                    "model"        : f"Opus O1 v{VERSION}",
                })
                daily_counts[trade_date] = daily_counts.get(trade_date, 0) + 1
                print(f"  [{ticker}] 🔴 SHORT (Euphoria Fade) @ ${close:.2f}"
                      f" | TP ${take_profit:.2f} | SL ${stop_loss:.2f}"
                      f" | R:R {rr} | {ts}")

            # ── LONG REVERSAL: Price breached LOWER outer band ───────────
            #    Capitulation sell-off → mean reversion bounce
            elif (close <= kc_lower                              # breached lower band
                    and vol_climax                               # volume spike (capitulation)
                    and self._stochrsi_hook_bullish(session_df, i)):  # momentum hooking up

                stop_loss   = round(close - (SL_ATR_MULT * atr), 2)
                take_profit = round(kc_mid, 2)                   # target = midline (20-EMA)
                risk = close - stop_loss
                reward = take_profit - close

                if risk <= 0 or reward <= 0:
                    continue

                rr = round(reward / risk, 2)
                if rr < MIN_RR:
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
                    "kc_lower"     : round(kc_lower, 2),
                    "kc_mid"       : round(kc_mid, 2),
                    "stoch_k"      : round(float(row["StochRSI_K"]), 2),
                    "stoch_d"      : round(float(row["StochRSI_D"]), 2),
                    "atr"          : round(atr, 4),
                    "reversal_type": "CAPITULATION_BOUNCE",
                    "model"        : f"Opus O1 v{VERSION}",
                })
                daily_counts[trade_date] = daily_counts.get(trade_date, 0) + 1
                print(f"  [{ticker}] 🟢 LONG  (Capitulation Bounce) @ ${close:.2f}"
                      f" | TP ${take_profit:.2f} | SL ${stop_loss:.2f}"
                      f" | R:R {rr} | {ts}")

        return signals

    # ── Multi-Ticker Scanner ──────────────────────────────────────────────────

    def scan_all(self, period: str = "5d") -> List[Dict]:
        """Scan entire ticker universe and aggregate signals."""
        all_signals = []

        print("=" * 72)
        print(f"  OPUS O1 — Keltner Exhaustion Reversal Scanner")
        print(f"  Orchestrator: Antigravity | Agent: Dexter | v{VERSION}")
        print(f"  Edge: Mean-Reversion from Keltner Breach + StochRSI Hook")
        print("=" * 72)

        for ticker in self.tickers:
            try:
                sigs = self.generate_signals(ticker, period=period)
                all_signals.extend(sigs)
                if not sigs:
                    print(f"  [{ticker}] — No exhaustion setups found.")
            except Exception as e:
                print(f"  [{ticker}] ERROR: {e}")

        return all_signals

    # ── Signal Emitter ────────────────────────────────────────────────────────

    def emit_signals(self, signals: List[Dict]) -> None:
        """Write signals to standard Dexter log format."""
        output_dir  = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
        output_file = os.path.join(output_dir, "opus_o1_signals.json")

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
    strat   = OpusKeltnerExhaust()
    signals = strat.scan_all(period="5d")

    total_long  = sum(1 for s in signals if s["type"] == "LONG_ENTRY")
    total_short = sum(1 for s in signals if s["type"] == "SHORT_ENTRY")

    print(f"\n{'=' * 72}")
    print(f"  Scan Complete — {len(signals)} total signal(s)")
    print(f"  Long (Capitulation Bounce): {total_long}")
    print(f"  Short (Euphoria Fade):      {total_short}")
    print(f"{'=' * 72}\n")

    if signals:
        strat.emit_signals(signals)

        print(f"\n  {'TICKER':<8} {'TYPE':<14} {'REVERSAL':<22} "
              f"{'ENTRY':>8} {'SL':>8} {'TP':>8} {'R:R':>5}  TIMESTAMP")
        print(f"  {'-' * 90}")
        for sig in signals:
            icon = "🟢 LONG " if sig["type"] == "LONG_ENTRY" else "🔴 SHORT"
            print(
                f"  {sig['ticker']:<8} {icon:<14} {sig['reversal_type']:<22} "
                f"${sig['entry']:>7.2f}  ${sig['stop_loss']:>7.2f}  "
                f"${sig['take_profit']:>7.2f}  {sig['rr']:>4.1f}  "
                f"{sig['timestamp']}"
            )
    else:
        print("  No exhaustion setups detected in the lookback period.")
        print("  (This strategy is selective — it waits for extreme moves.)")
