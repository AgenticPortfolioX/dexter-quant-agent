"""
Rebuild dashboard/LIVE_STRATEGY_BOARD.md from strategy_registry.json.

This is the only code that can ADD rows to the board.  The live engine's
`_write_board_signal` can only update rows that already exist, so this script
is invoked whenever the registry changes (see alpha_autotrader.refresh_strategy_board).

It preserves:
  * the ACTIVE PORTFOLIO section exactly as the engine last wrote it
  * each strategy's current Latest Signal
and prefers live signal-quality stats over backtest numbers once a strategy
has enough live trades to mean anything.
"""
import json
import os
import sys
from datetime import datetime

import pytz

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.board_io import read_text, write_text_atomic  # noqa: E402

REGISTRY_PATH = os.path.join(PROJECT_ROOT, "strategy_registry.json")
BOARD_PATH = os.path.join(PROJECT_ROOT, "dashboard", "LIVE_STRATEGY_BOARD.md")
BT_PATH = os.path.join(PROJECT_ROOT, "cache", "live_strategies_backtest_results.json")
QUALITY_PATH = os.path.join(PROJECT_ROOT, "signal_quality.json")
PILOT_PATH = os.path.join(PROJECT_ROOT, "PILOT_LIGHT.json")
EST = pytz.timezone("US/Eastern")

LIVE_MIN_TRADES = 10


def get_timeframe(strat):
    """Prefer an explicit `timeframe`; otherwise derive it from frequency."""
    if isinstance(strat, dict):
        if strat.get("timeframe"):
            return strat["timeframe"]
        freq = strat.get("frequency")
    else:
        freq = strat
    mapping = {60: "1m", 120: "2m", 300: "5m", 900: "15m",
               1800: "30m", 3600: "1h", 7200: "2h", 86400: "1D"}
    if freq in mapping:
        return mapping[freq]
    if freq:
        return f"{freq}s"
    return "N/A"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def parse_existing_signals(content):
    """Extract {strategy_name_lower: latest_signal} from the current board."""
    signals = {}
    for line in content.splitlines():
        if not line.strip().startswith("|"):
            continue
        parts = [p.strip().strip("*") for p in line.split("|")]
        if len(parts) < 7:
            continue
        name = parts[1]
        if not name or name.lower() in ("strategy name", ":---"):
            continue
        signal = parts[-2] if parts[-1] == "" else parts[-1]
        if signal:
            signals[name.lower()] = signal
    return signals


def extract_portfolio_section(content):
    """Return the ACTIVE PORTFOLIO section verbatim, or '' if absent."""
    marker = "## 📈 ACTIVE PORTFOLIO"
    if marker not in content:
        return ""
    start = content.index(marker)
    rest = content[start + len(marker):]
    end = rest.find("\n## ")
    block = marker + (rest if end == -1 else rest[:end])
    return block.strip() + "\n"


def metric_cells(name, bt_results, quality):
    """Win rate / PF: live stats once meaningful, else backtest."""
    q = quality.get(name) or {}
    if int(q.get("total_trades", 0) or 0) >= LIVE_MIN_TRADES:
        wr = q.get("win_rate")
        pf = q.get("profit_factor")
        wr_s = f"{float(wr):.1f}%" if wr is not None else "N/A"
        pf_s = f"{float(pf):.2f}" if pf is not None else "N/A"
        return wr_s, pf_s

    m = (bt_results.get(name) or {}).get("metrics") or {}
    if not m:
        return "N/A", "N/A"
    wr = m.get("win_rate_pct")
    pf = m.get("profit_factor")
    wr_s = f"{float(wr):.1f}%" if wr is not None else "N/A"
    pf_s = f"{float(pf):.2f}" if pf is not None else "N/A"
    return wr_s, pf_s


def rebuild():
    if not os.path.exists(REGISTRY_PATH):
        print(f"Registry not found at {REGISTRY_PATH}")
        return 1

    registry = load_json(REGISTRY_PATH, {})
    bt_results = load_json(BT_PATH, {}).get("strategies", {})
    quality = load_json(QUALITY_PATH, {}).get("strategies", {})
    pilot_on = load_json(PILOT_PATH, {}).get("enabled", True)

    existing = read_text(BOARD_PATH)
    signals = parse_existing_signals(existing)
    portfolio = extract_portfolio_section(existing)

    light = "🟢" if pilot_on else "🔴"
    now_est = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")

    lines = [
        "# 🏦 ALPHA COMMAND CENTER: LIVE STRATEGY BOARD\n",
        f"**PILOT LIGHT: {light}** | **Status: READY: 🟢 LIVE STRATEGIES ARMED** "
        f"(Last Heartbeat: {now_est})\n\n",
        "> [!TIP]\n",
        "> **Full Backtest Report**: "
        "[LIVE_STRATEGIES_BACKTEST_REPORT.md](file:///c:/Users/jmgra/antigravityagents/"
        "dexter-quant-agent/dashboard/LIVE_STRATEGIES_BACKTEST_REPORT.md)\n\n",
        "## 🔋 MONITOR HEALTH\n",
        f"- **Last Active Scan**: {now_est}\n",
        "- **System Status**: NOMINAL\n",
        f"- **Registry**: {len(registry.get('live_trading', []))} live / "
        f"{len(registry.get('active_testing', []))} testing / "
        f"{len(registry.get('meh', []))} decommissioned\n\n",
    ]

    if portfolio:
        lines.append(portfolio)
        lines.append("\n")

    lines.extend([
        "## 🟢 LIVE TRADING\n",
        "| Strategy Name | Active Assets | Timeframe | Win Rate | Profit Factor | Status | Latest Signal |\n",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n",
    ])
    for strat in registry.get("live_trading", []):
        name = strat.get("name", "Unnamed")
        assets = ", ".join(strat.get("assets", []))
        tf = get_timeframe(strat)
        wr, pf = metric_cells(name, bt_results, quality)
        sig = signals.get(name.lower(), "None")
        lines.append(f"| **{name}** | {assets} | {tf} | {wr} | {pf} | 🚀 LIVE | {sig} |\n")

    lines.extend([
        "\n## 🔬 ACTIVE TESTING\n",
        "| Strategy Name | Active Assets | Timeframe | Status | Latest Signal |\n",
        "| :--- | :--- | :--- | :--- | :--- |\n",
    ])
    for strat in registry.get("active_testing", []):
        name = strat.get("name", "Unnamed")
        assets = ", ".join(strat.get("assets", []))
        tf = get_timeframe(strat)
        sig = signals.get(name.lower(), "None")
        lines.append(f"| **{name}** | {assets} | {tf} | 🧪 TEST | {sig} |\n")

    lines.extend([
        "\n## 🛑 DECOMMISSIONED (MEH FOLDER — PF < 1.10)\n",
        "| Strategy Name | Active Assets | Timeframe | Win Rate | Profit Factor | Status | Reason |\n",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n",
    ])
    for strat in registry.get("meh", []):
        name = strat.get("name", "Unnamed")
        assets = ", ".join(strat.get("assets", []))
        tf = get_timeframe(strat)
        wr, pf = metric_cells(name, bt_results, quality)
        reason = strat.get("decommission_reason", "PF < 1.10")
        lines.append(f"| **{name}** | {assets} | {tf} | {wr} | {pf} | 🛑 DECOMMISSIONED | {reason} |\n")

    write_text_atomic(BOARD_PATH, "".join(lines))
    print(f"Rebuilt board: {BOARD_PATH} "
          f"({len(registry.get('live_trading', []))} live rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(rebuild())
