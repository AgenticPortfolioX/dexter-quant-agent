"""
Pre-open earnings scanner for the PEAD (post-earnings drift) strategy.

Runs at 09:15 ET, before the open, and writes cache/pead_candidates.json:

    {"generated": "...", "candidates": {
        "AAPL": {"announcement_date": "2026-10-29",
                 "reaction_date": "2026-10-30",
                 "surprise_pct": 6.2}
    }}

Only tickers that reported in the last two calendar days become candidates.
The live engine then computes today's gap and volume ratio from the daily bar
at the 15:45 evaluation and decides whether to enter.

This is an earnings-gap proxy for full PEAD: it uses yfinance's reported
earnings dates and surprise %, with a graceful fallback to "no surprise known"
when that endpoint is unavailable.
"""
import json
import os
import sys
from datetime import datetime, timedelta

import pytz
import yfinance as yf

PROJECT_ROOT = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
OUT_PATH = os.path.join(PROJECT_ROOT, "cache", "pead_candidates.json")
EST = pytz.timezone("US/Eastern")

# Liquid, optionable, widely covered names. Kept small on purpose: every name
# here is an extra yfinance series in the live engine's daily fetch loop.
UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META",
    "TSLA", "AVGO", "JPM", "XOM", "NFLX", "AMD",
]

LOOKBACK_DAYS = 2  # report within the last two calendar days


def _recent_earnings(ticker_obj, today):
    """Return (announcement_date, surprise_pct) for a report in the window."""
    try:
        dates = ticker_obj.get_earnings_dates(limit=8)
    except Exception as exc:
        print(f"    [warn] earnings dates unavailable: {exc}")
        return None
    if dates is None or len(dates) == 0:
        return None

    cutoff = today - timedelta(days=LOOKBACK_DAYS)
    for idx, row in dates.iterrows():
        try:
            when = idx.to_pydatetime()
        except Exception:
            continue
        when_date = when.date()
        if cutoff <= when_date <= today:
            surprise = None
            for col in ("Surprise(%)", "Surprise (%)", "surprise_pct"):
                if col in row and row[col] is not None:
                    try:
                        surprise = float(row[col])
                    except (TypeError, ValueError):
                        surprise = None
                    break
            return when_date, surprise
    return None


def scan():
    today = datetime.now(EST).date()
    candidates = {}

    for symbol in UNIVERSE:
        try:
            t = yf.Ticker(symbol)
            hit = _recent_earnings(t, today)
            if not hit:
                continue
            announcement, surprise = hit
            candidates[symbol] = {
                "announcement_date": announcement.isoformat(),
                "reaction_date": today.isoformat(),
                "surprise_pct": surprise,
            }
            print(f"  ✅ {symbol}: reported {announcement} "
                  f"(surprise {surprise if surprise is not None else 'n/a'})")
        except Exception as exc:
            print(f"  ⚠️  {symbol}: {exc}")

    payload = {
        "generated": datetime.now(EST).isoformat(),
        "universe": UNIVERSE,
        "candidates": candidates,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, OUT_PATH)

    print(f"[PEAD] {len(candidates)} candidate(s) -> {OUT_PATH}")
    return candidates


if __name__ == "__main__":
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    scan()
