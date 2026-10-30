"""
Position book for the systematic daily book.

One record per (strategy, ticker) so two strategies can hold the same symbol
without one strategy's EXIT closing the other's position.  Records are written
by the engine on a verified fill and removed on a verified exit.

File: cache/systematic_positions.json
{
  "IBS-3 Index Dip Buyer|IWM": {
      "strategy": "IBS-3 Index Dip Buyer",
      "ticker": "IWM",
      "qty": 0.5,
      "entry_price": 231.4,
      "entry_date": "2026-10-28",
      "stop_price": 224.1,
      "target_price": null,
      "max_hold_days": 5,
      "note": "..."
  }
}
"""
import json
import os
from datetime import date

import numpy as np

DEXTER_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
BOOK_PATH = os.path.join(DEXTER_ROOT, "cache", "systematic_positions.json")


def book_key(strategy, ticker):
    return f"{strategy}|{ticker}"


def load_book():
    if not os.path.exists(BOOK_PATH):
        return {}
    try:
        with open(BOOK_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_book(book):
    os.makedirs(os.path.dirname(BOOK_PATH), exist_ok=True)
    tmp = f"{BOOK_PATH}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(book, f, indent=2)
    os.replace(tmp, BOOK_PATH)


def record_entry(strategy, ticker, qty, entry_price, stop_price=None,
                 target_price=None, max_hold_days=None, note=""):
    book = load_book()
    book[book_key(strategy, ticker)] = {
        "strategy": strategy,
        "ticker": ticker,
        "qty": float(qty),
        "entry_price": float(entry_price),
        "entry_date": date.today().isoformat(),
        "stop_price": float(stop_price) if stop_price is not None else None,
        "target_price": float(target_price) if target_price is not None else None,
        "max_hold_days": int(max_hold_days) if max_hold_days is not None else None,
        "note": note,
    }
    save_book(book)
    return book[book_key(strategy, ticker)]


def remove_entry(strategy, ticker):
    book = load_book()
    book.pop(book_key(strategy, ticker), None)
    save_book(book)


def held_keys():
    return set(load_book().keys())


def trading_days_held(entry_date_iso, today=None):
    try:
        start = np.datetime64(entry_date_iso, "D")
    except Exception:
        return 0
    end = np.datetime64(today or date.today(), "D")
    if end <= start:
        return 0
    return int(np.busday_count(start, end))


def decide_exit(record, price, today=None):
    """Return (should_exit, reason) for one position record."""
    if record is None or price is None or price <= 0:
        return False, None

    entry = float(record.get("entry_price", 0) or 0)
    if entry <= 0:
        return False, None

    stop = record.get("stop_price")
    target = record.get("target_price")
    max_hold = record.get("max_hold_days")

    if stop is not None and float(price) <= float(stop):
        return True, f"Stop hit ({price:.2f} <= {float(stop):.2f})"
    if target is not None and float(price) >= float(target):
        return True, f"Target hit ({price:.2f} >= {float(target):.2f})"

    entry_date = record.get("entry_date")
    if max_hold and entry_date:
        held = trading_days_held(entry_date, today)
        if held >= int(max_hold):
            return True, f"Time exit ({held} trading days >= {int(max_hold)})"

    return False, None
