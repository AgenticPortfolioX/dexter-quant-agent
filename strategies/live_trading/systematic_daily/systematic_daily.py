"""
Systematic daily strategies (long-only, spot-compatible).

These replace the old partially-formed-daily-bar logic for the new book:

  1. IBS-3 Index Dip Buyer        (sys_ibs3)
  2. VIX Panic RSI-2              (sys_vix_rsi2)
  3. Turn-of-Month                (sys_turn_of_month)
  4. Dual Momentum Sector Rotation(sys_dual_momentum)
  5. Post-Earnings Gap Drift      (sys_pead)

Design notes
------------
* Every function is pure: it takes an OHLCV DataFrame and returns a signal dict
  or None.  No disk, no network, no globals -- so it is unit-testable and safe
  to run inside the ProcessPoolExecutor.
* Signals are emitted on the *daily* bar.  The caller decides whether the last
  bar is closed enough to trust (see `daily_bar_is_fresh`).
* The engine cannot short, so every strategy here is long-only; the bearish
  leg of Dual Momentum is expressed by buying the inverse ETF `SH`.
"""
import pandas as pd
import numpy as np

SIG_TYPE_IBS3 = "sys_ibs3"
SIG_TYPE_VIX_RSI2 = "sys_vix_rsi2"
SIG_TYPE_TOM = "sys_turn_of_month"
SIG_TYPE_DUAL_MOM = "sys_dual_momentum"
SIG_TYPE_PEAD = "sys_pead"

SYSTEMATIC_TYPES = {
    SIG_TYPE_IBS3,
    SIG_TYPE_VIX_RSI2,
    SIG_TYPE_TOM,
    SIG_TYPE_DUAL_MOM,
    SIG_TYPE_PEAD,
}

# Default risk parameters (per-position, price based)
IBS3_STOP_ATR = 2.0
IBS3_MAX_HOLD_DAYS = 5

VIX2_STOP_ATR = 2.0
VIX2_MAX_HOLD_DAYS = 4
VIX_MIN = 20.0
VIX_MAX = 35.0

TOM_MAX_HOLD_DAYS = 5

PEAD_STOP_PCT = 8.0
PEAD_TARGET_PCT = 15.0
PEAD_MAX_HOLD_DAYS = 20
PEAD_MIN_GAP_PCT = 2.0
PEAD_MIN_SURPRISE_PCT = 5.0
PEAD_MIN_VOL_RATIO = 1.5


# --------------------------------------------------------------------------- #
# Indicators
# --------------------------------------------------------------------------- #
def ibs(high, low, close):
    """Internal Bar Strength: where the close sits inside the day's range."""
    rng = (high - low).replace(0, np.nan)
    return ((close - low) / rng).clip(lower=0.0, upper=1.0)


def rsi(series, n=2):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1.0 / n, adjust=False).mean()
    roll_down = down.ewm(alpha=1.0 / n, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def atr(df, n=14):
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift()).abs(),
            (df["Low"] - df["Close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def total_return(close, lookback):
    if len(close) <= lookback:
        return None
    start = float(close.iloc[-lookback - 1])
    if start <= 0:
        return None
    return float(close.iloc[-1]) / start - 1.0


def _result(sig, price, ts, stop_price=None, target_price=None,
            max_hold_days=None, note=""):
    return {
        "sig": sig,
        "price": float(price),
        "tf": "1d",
        "sig_time": ts,
        "stop_price": float(stop_price) if stop_price is not None else None,
        "target_price": float(target_price) if target_price is not None else None,
        "max_hold_days": max_hold_days,
        "note": note,
    }


# --------------------------------------------------------------------------- #
# 1. IBS-3 index dip buyer
# --------------------------------------------------------------------------- #
def signal_ibs3(df):
    """Buy index weakness inside an uptrend; exit on a bounce or time stop."""
    if df is None or len(df) < 210:
        return None
    close, high, low = df["Close"], df["High"], df["Low"]

    ibs_now = float(ibs(high, low, close).iloc[-1])
    close_now = float(close.iloc[-1])
    low5 = float(low.shift(1).rolling(5).min().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1])
    prev_high = float(high.shift(1).iloc[-1])
    atr_now = float(atr(df).iloc[-1])

    if np.isnan(atr_now) or atr_now <= 0:
        return None

    if ibs_now < 0.25 and close_now < low5 and close_now > sma200:
        return _result(
            "BUY", close_now, df.index[-1],
            stop_price=close_now - IBS3_STOP_ATR * atr_now,
            target_price=None,
            max_hold_days=IBS3_MAX_HOLD_DAYS,
            note=f"IBS {ibs_now:.2f} < 0.25, close below 5d low, above 200SMA",
        )

    if close_now > prev_high:
        return _result("EXIT", close_now, df.index[-1], note="Close > prior day high")
    return None


# --------------------------------------------------------------------------- #
# 2. VIX panic RSI-2
# --------------------------------------------------------------------------- #
def signal_vix_rsi2(df, vix):
    """RSI(2) oversold inside an uptrend, only while VIX is elevated but sane."""
    if df is None or len(df) < 210:
        return None
    if vix is None:
        return None
    close = df["Close"]
    sma200 = float(close.rolling(200).mean().iloc[-1])
    sma5 = float(close.rolling(5).mean().iloc[-1])
    rsi2 = float(rsi(close, 2).iloc[-1])
    close_now = float(close.iloc[-1])
    atr_now = float(atr(df).iloc[-1])

    if np.isnan(atr_now) or atr_now <= 0:
        return None

    if (rsi2 < 10.0
            and close_now > sma200
            and VIX_MIN <= float(vix) <= VIX_MAX):
        return _result(
            "BUY", close_now, df.index[-1],
            stop_price=close_now - VIX2_STOP_ATR * atr_now,
            target_price=None,
            max_hold_days=VIX2_MAX_HOLD_DAYS,
            note=f"RSI2 {rsi2:.1f} < 10, close > 200SMA, VIX {float(vix):.1f}",
        )

    if close_now > sma5 or rsi2 > 65.0:
        return _result("EXIT", close_now, df.index[-1],
                       note=f"RSI2 {rsi2:.1f} / close vs 5SMA bounce")
    return None


# --------------------------------------------------------------------------- #
# 3. Turn-of-Month
# --------------------------------------------------------------------------- #
def _next_weekday(d):
    nxt = d + pd.Timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += pd.Timedelta(days=1)
    return nxt


def is_last_business_day(d, holidays=None):
    """True when `d` is a business day and the next business day is a new month."""
    d = pd.Timestamp(d).normalize()
    if d.weekday() >= 5:
        return False
    nxt = _next_weekday(d)
    if holidays:
        while nxt.normalize() in holidays:
            nxt = _next_weekday(nxt)
    return nxt.month != pd.Timestamp(d).month


def signal_turn_of_month(df, today, holidays=None):
    """Buy near the close of the last business day, exit on the 3rd session
    of the new month."""
    if df is None or len(df) < 210:
        return None
    close = df["Close"]
    close_now = float(close.iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1])
    today = pd.Timestamp(today).normalize()

    if is_last_business_day(today, holidays) and close_now > sma200:
        return _result(
            "BUY", close_now, df.index[-1],
            stop_price=None,
            target_price=None,
            max_hold_days=TOM_MAX_HOLD_DAYS,
            note="Last business day of month, above 200SMA",
        )

    # Exit: third (or later) trading session of a month.  The position book
    # only holds TOM entries, so this is unambiguous in practice.
    months = pd.Series(df.index, index=df.index).dt.to_period("M")
    current_month = months.iloc[-1]
    sessions_this_month = int((months == current_month).sum())
    if sessions_this_month >= 3:
        return _result("EXIT", close_now, df.index[-1],
                       note="Third trading session of the month")
    return None


# --------------------------------------------------------------------------- #
# 4. Dual Momentum sector rotation
# --------------------------------------------------------------------------- #
def rank_sectors(sector_frames, lookback=126):
    """Return sector tickers sorted by `lookback`-day total return, best first."""
    scored = []
    for ticker, frame in sector_frames.items():
        if frame is None or len(frame) <= lookback:
            continue
        ret = total_return(frame["Close"], lookback)
        if ret is None:
            continue
        scored.append((ticker, ret))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def is_first_trading_day_of_month(today, prev_bar_date):
    return pd.Timestamp(today).month != pd.Timestamp(prev_bar_date).month


def signal_dual_momentum(ticker, df, sector_frames, spy_df, today,
                         top_n=3, lookback=126):
    """Monthly sector rotation, long-only.  Bearish regime -> SH."""
    if df is None or len(df) < 30 or spy_df is None or len(spy_df) < 210:
        return None

    close_now = float(df["Close"].iloc[-1])
    # Rebalance on the first session of a new month.  Comparing the wall-clock
    # month to the previous bar's month (rather than to the last bar's) keeps
    # the rebalance alive for a day if yfinance lags the current session.
    if len(df) < 2:
        return None
    if not is_first_trading_day_of_month(today, df.index[-2]):
        return None  # rebalance monthly only

    spy_close = float(spy_df["Close"].iloc[-1])
    spy_sma200 = float(spy_df["Close"].rolling(200).mean().iloc[-1])
    risk_on = spy_close > spy_sma200

    if ticker == "SH":
        if not risk_on:
            return _result("BUY", close_now, df.index[-1],
                           max_hold_days=None,
                           note="SPY below 200SMA -> hold inverse ETF")
        return _result("EXIT", close_now, df.index[-1],
                       note="SPY back above 200SMA")

    if not risk_on:
        return _result("EXIT", close_now, df.index[-1],
                       note="Risk-off: rotate to SH")

    ranked = rank_sectors(sector_frames, lookback)
    top = [t for t, ret in ranked[:top_n] if ret > 0]
    if ticker in top:
        return _result("BUY", close_now, df.index[-1], max_hold_days=None,
                       note=f"Top-{top_n} 126d momentum: {', '.join(top)}")
    return _result("EXIT", close_now, df.index[-1],
                   note="Dropped out of top-3 momentum")


# --------------------------------------------------------------------------- #
# 5. Post-earnings gap drift (earnings-gap proxy for PEAD)
# --------------------------------------------------------------------------- #
def signal_pead(df, candidate, today):
    """Enter after a confirmed earnings gap with volume; ride the drift.

    `candidate` is a dict produced by scripts/pead_scanner.py:
        {"reaction_date": "YYYY-MM-DD", "surprise_pct": float,
         "gap_pct": float, "vol_ratio": float}
    """
    if df is None or len(df) < 30 or not candidate:
        return None

    today = pd.Timestamp(today).normalize()
    reaction = pd.Timestamp(candidate.get("reaction_date", "")).normalize()
    if reaction != today:
        return None  # only act on the reaction day itself

    close_now = float(df["Close"].iloc[-1])
    surprise = candidate.get("surprise_pct")

    # Gap and volume are computed from the bars when the scanner did not
    # supply them (the scanner runs pre-open, before today's bar exists).
    gap = candidate.get("gap_pct")
    if gap is None:
        if len(df) < 2:
            return None
        prev_close = float(df["Close"].iloc[-2])
        if prev_close <= 0:
            return None
        gap = (float(df["Open"].iloc[-1]) / prev_close - 1.0) * 100.0

    vol_ratio = candidate.get("vol_ratio")
    if vol_ratio is None:
        if "Volume" not in df.columns or len(df) < 22:
            return None
        vol_ma = float(df["Volume"].shift(1).rolling(20).mean().iloc[-1])
        if vol_ma <= 0:
            return None
        vol_ratio = float(df["Volume"].iloc[-1]) / vol_ma

    gap = float(gap)
    vol_ratio = float(vol_ratio)

    surprise_ok = surprise is None or float(surprise) >= PEAD_MIN_SURPRISE_PCT
    if gap >= PEAD_MIN_GAP_PCT and vol_ratio >= PEAD_MIN_VOL_RATIO and surprise_ok:
        return _result(
            "BUY", close_now, df.index[-1],
            stop_price=close_now * (1.0 - PEAD_STOP_PCT / 100.0),
            target_price=close_now * (1.0 + PEAD_TARGET_PCT / 100.0),
            max_hold_days=PEAD_MAX_HOLD_DAYS,
            note=(f"Earnings gap {gap:+.1f}%, vol {vol_ratio:.1f}x"
                  + (f", surprise {float(surprise):+.1f}%" if surprise is not None else "")),
        )

    low10 = float(df["Low"].shift(1).rolling(10).min().iloc[-1])
    if close_now < low10:
        return _result("EXIT", close_now, df.index[-1],
                       note="Close below 10-day low")
    return None


# --------------------------------------------------------------------------- #
# Dispatch used by the engine worker
# --------------------------------------------------------------------------- #
def evaluate(sig_type, ticker, name, df, context):
    """Route one systematic signal computation.

    `context` keys: vix, today, sectors (dict ticker -> DataFrame), spy_df,
    pead_candidates (dict ticker -> candidate).
    """
    context = context or {}
    if sig_type == SIG_TYPE_IBS3:
        return signal_ibs3(df)
    if sig_type == SIG_TYPE_VIX_RSI2:
        return signal_vix_rsi2(df, context.get("vix"))
    if sig_type == SIG_TYPE_TOM:
        return signal_turn_of_month(df, context.get("today"))
    if sig_type == SIG_TYPE_DUAL_MOM:
        return signal_dual_momentum(
            ticker, df,
            context.get("sectors") or {},
            context.get("spy_df"),
            context.get("today"),
        )
    if sig_type == SIG_TYPE_PEAD:
        candidates = context.get("pead_candidates") or {}
        return signal_pead(df, candidates.get(ticker), context.get("today"))
    return None
