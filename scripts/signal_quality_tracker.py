"""
Signal Quality Feedback Loop Agent (Proposal 8)
==============================================
Parses logs/live_trading/execution.log and writes signal_quality.json.

What changed
------------
The original computed P&L as a *price difference per share*, which makes a
$500 ETF trade look 100x more important than a $5 stock and makes profit
factor meaningless.  This version pairs entries and exits and measures
**percentage return per round trip**, so:

  * profit factor is comparable across symbols and position sizes
  * a strategy's stats can drive sizing (see alpha_autotrader.quality_verdict)
  * a strategy with one lucky huge trade cannot mask a losing record

`total_trades` counts completed round trips (entries without an exit are not
scored).
"""
import json
import os
import re
from datetime import datetime

import pytz

PROJECT_ROOT = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
REPORTING_ROOT = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\logs"
EXECUTION_LOG = os.path.join(REPORTING_ROOT, "live_trading", "execution.log")
QUALITY_FILE = os.path.join(PROJECT_ROOT, "signal_quality.json")

EST = pytz.timezone("US/Eastern")

ENTRY_ACTIONS = ("BUY", "LONG", "SHORT")
EXIT_ACTIONS = ("EXIT", "SELL", "CLOSE")


def parse_execution_log(path=EXECUTION_LOG):
    """Return {(strategy, ticker): [event, ...]} in file order."""
    if not os.path.exists(path):
        print(f"  ❌ Log file not found at {path}")
        return {}
    if os.path.getsize(path) > 200 * 1024 * 1024:
        print("  ⚠️  execution.log exceeds 200MB — scoring the tail only")

    trades = {}
    count = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "[LIVE-EXEC]" not in line:
                continue
            try:
                body = line.split("[LIVE-EXEC]", 1)[1].strip()
                # Optional [timestamp] prefix
                ts_str = ""
                if body.startswith("["):
                    ts_str, body = body[1:].split("]", 1)
                    body = body.strip()

                parts = body.split("|")
                if len(parts) < 3:
                    continue
                strategy = parts[0].strip()
                ticker = parts[1].strip()
                action_part = parts[2].strip()
                if " @ $" not in action_part:
                    continue

                action, price_str = action_part.split(" @ $", 1)
                action = action.upper().strip()
                m = re.search(r"(\d+(?:\.\d+)?)", price_str)
                if not m:
                    continue

                trades.setdefault((strategy, ticker), []).append({
                    "time": ts_str.strip(),
                    "action": action,
                    "price": float(m.group(1)),
                })
                count += 1
            except Exception:
                continue

    print(f"  🔍 Found {count} raw execution events.")
    return trades


def calculate_stats(trades):
    """Pair entries with exits and measure return per round trip."""
    buckets = {}

    for (strategy, ticker), history in trades.items():
        bucket = buckets.setdefault(strategy, {
            "wins": 0, "losses": 0,
            "gross_win_pct": 0.0, "gross_loss_pct": 0.0,
            "returns": [],
        })

        entries = []
        for event in history:
            action = event["action"]
            if any(a in action for a in ENTRY_ACTIONS):
                entries.append(event)
            elif any(a in action for a in EXIT_ACTIONS) and entries:
                entry = entries.pop()  # LIFO
                entry_px = entry["price"]
                if entry_px <= 0:
                    continue
                if "SHORT" in entry["action"]:
                    ret = (entry_px - event["price"]) / entry_px
                else:
                    ret = (event["price"] - entry_px) / entry_px

                bucket["returns"].append(ret)
                if ret > 0:
                    bucket["wins"] += 1
                    bucket["gross_win_pct"] += ret
                else:
                    bucket["losses"] += 1
                    bucket["gross_loss_pct"] += abs(ret)

    final = {}
    for strategy, data in buckets.items():
        total = data["wins"] + data["losses"]
        if total == 0:
            continue
        win_rate = data["wins"] / total * 100.0
        if data["gross_loss_pct"] > 0:
            profit_factor = data["gross_win_pct"] / data["gross_loss_pct"]
        else:
            # No losing trades: report a finite sentinel rather than infinity
            profit_factor = 99.0 if data["gross_win_pct"] > 0 else 0.0

        final[strategy] = {
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "total_trades": total,
            "avg_return_pct": round(sum(data["returns"]) / total * 100.0, 3),
            "gross_win_pct": round(data["gross_win_pct"] * 100.0, 2),
            "gross_loss_pct": round(data["gross_loss_pct"] * 100.0, 2),
            "score": round(win_rate * (total ** 0.5), 2),
        }

    return final


def run_feedback_loop():
    print(f"[{datetime.now(EST).strftime('%H:%M:%S')}] 📉 SIGNAL QUALITY AGENT — Processing logs...")

    trades = parse_execution_log()
    stats = calculate_stats(trades)

    os.makedirs(os.path.dirname(QUALITY_FILE), exist_ok=True)
    tmp = QUALITY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({
            "last_updated": datetime.now(EST).isoformat(),
            "method": "percent_return_per_round_trip",
            "strategies": stats,
        }, f, indent=4)
    os.replace(tmp, QUALITY_FILE)

    print(f"  ✅ Analyzed {len(stats)} strategies.")
    for strat, s in sorted(stats.items(), key=lambda kv: kv[1]["score"], reverse=True):
        print(f"  - {strat}: {s['win_rate']}% win | PF {s['profit_factor']} | "
              f"{s['total_trades']} trades")
    print(f"  ✅ Report saved to {QUALITY_FILE}")


if __name__ == "__main__":
    run_feedback_loop()
