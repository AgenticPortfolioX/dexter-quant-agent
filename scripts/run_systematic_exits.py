"""
One-shot systematic exit sweep.

Scheduled by live_monitor at 16:05 (post-close) as a belt-and-braces pass over
cache/systematic_positions.json.  The live loop also evaluates stops every
cycle during market hours, so this mainly catches time-based exits on days the
monitor was started late.

Usage:
    python scripts/run_systematic_exits.py [--dry-run]
"""
import argparse
import os
import sys

PROJECT_ROOT = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would close without placing orders")
    args = parser.parse_args()

    from strategies.live_trading.systematic_daily import position_book
    book = position_book.load_book()
    if not book:
        print("[systematic-exits] book is empty")
        return 0

    if args.dry_run:
        from strategies.validation.alpha_autotrader import _current_marks
        marks = _current_marks()
        for key, rec in book.items():
            px = marks.get(rec.get("ticker"))
            if px is None:
                print(f"  {key}: no mark")
                continue
            should, reason = position_book.decide_exit(rec, px)
            print(f"  {key}: {'EXIT' if should else 'hold'} — {reason or 'no rule hit'}")
        return 0

    from strategies.validation.alpha_autotrader import evaluate_systematic_exits
    closed = evaluate_systematic_exits(mode="POST_MARKET")
    print(f"[systematic-exits] closed {closed} position(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
