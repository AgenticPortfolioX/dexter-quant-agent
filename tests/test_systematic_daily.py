"""
Tests for the systematic daily book.

Run directly:  python tests/test_systematic_daily.py
(Repo convention: standalone run_tests() scripts, not unittest discovery.)
"""
import os
import sys
import tempfile
from datetime import date, timedelta

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategies.live_trading.systematic_daily import systematic_daily as sd
from strategies.live_trading.systematic_daily import position_book as pb


def make_daily(closes, start="2025-01-02", highs=None, lows=None, opens=None,
               volumes=None):
    idx = pd.bdate_range(start, periods=len(closes))
    closes = np.asarray(closes, dtype=float)
    opens = np.asarray(opens, dtype=float) if opens is not None else closes.copy()
    highs = np.asarray(highs, dtype=float) if highs is not None else closes + 1.0
    lows = np.asarray(lows, dtype=float) if lows is not None else closes - 1.0
    volumes = (np.asarray(volumes, dtype=float) if volumes is not None
               else np.full(len(closes), 1_000_000.0))
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows,
         "Close": closes, "Volume": volumes},
        index=idx,
    )


# --------------------------------------------------------------------------- #
def test_ibs3_entry():
    closes = np.linspace(100, 200, 240)
    df = make_daily(closes)
    last = 190.0
    df.iloc[-1, df.columns.get_loc("Close")] = last
    df.iloc[-1, df.columns.get_loc("Low")] = last - 0.2
    df.iloc[-1, df.columns.get_loc("High")] = last + 2.0

    out = sd.signal_ibs3(df)
    assert out is not None, "expected an IBS-3 signal on a deep dip in an uptrend"
    assert out["sig"] == "BUY", out
    assert out["stop_price"] < out["price"]
    assert out["max_hold_days"] == sd.IBS3_MAX_HOLD_DAYS


def test_ibs3_requires_uptrend():
    closes = np.linspace(300, 200, 240)  # downtrend
    df = make_daily(closes)
    last = float(df["Close"].iloc[-1]) - 5
    df.iloc[-1, df.columns.get_loc("Close")] = last
    df.iloc[-1, df.columns.get_loc("Low")] = last - 0.1
    df.iloc[-1, df.columns.get_loc("High")] = last + 2.0
    assert sd.signal_ibs3(df) is None, "no entries below the 200SMA"


def test_vix_rsi2():
    closes = list(np.linspace(100, 200, 237)) + [200.0, 192.0, 185.0]
    df = make_daily(closes)
    out = sd.signal_vix_rsi2(df, vix=25.0)
    assert out is not None and out["sig"] == "BUY", out
    assert sd.signal_vix_rsi2(df, vix=40.0) is None, "VIX above the cap must not fire"
    assert sd.signal_vix_rsi2(df, vix=None) is None, "no VIX -> no signal"


def test_turn_of_month_calendar():
    assert sd.is_last_business_day(pd.Timestamp("2026-10-30")) is True
    assert sd.is_last_business_day(pd.Timestamp("2026-10-29")) is False
    assert sd.is_last_business_day(pd.Timestamp("2026-10-15")) is False
    # Friday before a month-end Saturday/Sunday still counts
    assert sd.is_last_business_day(pd.Timestamp("2026-10-31")) is False  # Saturday

    closes = np.linspace(100, 200, 240)
    df = make_daily(closes)
    out = sd.signal_turn_of_month(df, "2026-10-30")
    assert out is not None and out["sig"] == "BUY", out


def test_dual_momentum_ranking_and_risk_off():
    idx = pd.bdate_range("2025-01-01", "2026-11-02")
    n = len(idx)

    def frame(slope):
        closes = 100 * np.exp(slope * np.arange(n))
        return pd.DataFrame({"Close": closes}, index=idx)

    sectors = {
        "XLK": frame(0.0010), "XLF": frame(0.0008), "XLV": frame(0.0006),
        "XLE": frame(0.0002), "XLI": frame(0.0001), "XLP": frame(0.00005),
        "XLU": frame(0.00001), "XLY": frame(0.00002), "XLB": frame(0.00003),
        "XLRE": frame(0.00004), "XLC": frame(0.00007),
    }
    spy_on = frame(0.0005)

    buy = sd.signal_dual_momentum("XLK", sectors["XLK"], sectors, spy_on,
                                  "2026-11-02")
    assert buy is not None and buy["sig"] == "BUY", buy
    drop = sd.signal_dual_momentum("XLU", sectors["XLU"], sectors, spy_on,
                                   "2026-11-02")
    assert drop is not None and drop["sig"] == "EXIT", drop

    # Risk-off: SPY under its 200SMA -> SH buy, sectors exit
    spy_off = frame(-0.0002)
    sh = sd.signal_dual_momentum("SH", sectors["XLK"], sectors, spy_off,
                                 "2026-11-02")
    assert sh is not None and sh["sig"] == "BUY", sh
    flat = sd.signal_dual_momentum("XLK", sectors["XLK"], sectors, spy_off,
                                   "2026-11-02")
    assert flat is not None and flat["sig"] == "EXIT", flat

    # Mid-month: no rebalance
    mid = sd.signal_dual_momentum("XLK", sectors["XLK"], sectors, spy_on,
                                  "2026-10-15")
    assert mid is None, "rebalances only on the first session of the month"


def test_pead_entry():
    closes = list(np.linspace(100, 120, 39)) + [120.0]
    opens = list(closes[:-1]) + [120.0 * 1.03]
    vols = [1_000_000.0] * 39 + [3_000_000.0]
    df = make_daily(closes, opens=opens, volumes=vols)
    reaction = df.index[-1].strftime("%Y-%m-%d")
    cand = {"reaction_date": reaction, "surprise_pct": 7.5}
    out = sd.signal_pead(df, cand, reaction)
    assert out is not None and out["sig"] == "BUY", out
    assert out["stop_price"] < out["price"] < out["target_price"]

    weak = {"reaction_date": reaction, "surprise_pct": 1.0}
    assert sd.signal_pead(df, weak, reaction) is None, "surprise filter must bite"
    stale = {"reaction_date": "2020-01-02", "surprise_pct": 9.0}
    assert sd.signal_pead(df, stale, reaction) is None, "only the reaction day"


def test_position_book_exits():
    old = (date.today() - timedelta(days=14)).isoformat()
    rec = {"entry_price": 100.0, "stop_price": 95.0, "target_price": 110.0,
           "max_hold_days": 5, "entry_date": old}
    assert pb.decide_exit(rec, 94.0)[0] is True
    assert pb.decide_exit(rec, 111.0)[0] is True
    assert pb.decide_exit(rec, 100.0)[0] is True, "time stop after 5 sessions"

    fresh = dict(rec, entry_date=date.today().isoformat())
    assert pb.decide_exit(fresh, 100.0)[0] is False
    assert pb.decide_exit(fresh, 96.0)[0] is False

    # Persistence round trip in a temp file
    original = pb.BOOK_PATH
    try:
        tmpdir = tempfile.mkdtemp()
        pb.BOOK_PATH = os.path.join(tmpdir, "book.json")
        pb.record_entry("S", "SPY", 1.5, 500.0, stop_price=490.0,
                        max_hold_days=5, note="t")
        book = pb.load_book()
        assert "S|SPY" in book and book["S|SPY"]["qty"] == 1.5
        pb.remove_entry("S", "SPY")
        assert pb.load_book() == {}
    finally:
        pb.BOOK_PATH = original


def test_scheduler_due_windows():
    import live_monitor

    class Now:
        def __init__(self, hhmm):
            self.hhmm = hhmm

        def strftime(self, fmt):
            assert fmt == "%H:%M"
            return self.hhmm

    assert live_monitor.is_due(Now("15:49"), "15:50", "", "2026-10-30",
                               end_hhmm="16:00") is False
    assert live_monitor.is_due(Now("15:50"), "15:50", "", "2026-10-30",
                               end_hhmm="16:00") is True
    assert live_monitor.is_due(Now("15:59"), "15:50", "", "2026-10-30",
                               end_hhmm="16:00") is True
    assert live_monitor.is_due(Now("16:00"), "15:50", "", "2026-10-30",
                               end_hhmm="16:00") is False
    assert live_monitor.is_due(Now("16:05"), "15:50", "2026-10-30",
                               "2026-10-30") is False, "already ran today"
    assert live_monitor.is_due(Now("16:10"), "16:05", "", "2026-10-30") is True


def test_eod_intraday_selection():
    import strategies.validation.alpha_autotrader as a

    registry = {
        "live_trading": [
            {"name": "Scalper", "frequency": 300, "assets": ["SPY"]},
            {"name": "Swing", "frequency": 86400, "assets": ["IWM"]},
        ],
        "active_testing": [],
    }
    names = a._load_intraday_only_strategies(registry)
    assert "Scalper" in names
    assert "Swing" not in names, "daily strategies must survive EOD flattening"


def test_quality_verdict_governance():
    import strategies.validation.alpha_autotrader as a

    original = a.SIGNAL_QUALITY
    try:
        a.SIGNAL_QUALITY = {}
        assert a.quality_verdict("X")[0] == 1.0

        a.SIGNAL_QUALITY = {"X": {"total_trades": 25, "profit_factor": 0.5,
                                  "win_rate": 30.0}}
        mult, blocked, _ = a.quality_verdict("X")
        assert blocked and mult == 0.0

        a.SIGNAL_QUALITY = {"X": {"total_trades": 25, "profit_factor": 1.05,
                                  "win_rate": 55.0}}
        mult, blocked, _ = a.quality_verdict("X")
        assert (not blocked) and mult == 0.5

        a.SIGNAL_QUALITY = {"X": {"total_trades": 25, "profit_factor": 1.9,
                                  "win_rate": 70.0}}
        mult, blocked, _ = a.quality_verdict("X")
        assert (not blocked) and mult == 1.25
    finally:
        a.SIGNAL_QUALITY = original


def run_tests():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if run_tests() else 0)
