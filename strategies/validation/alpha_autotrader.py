import os
import sys
import subprocess
import json
import pandas as pd
import argparse

# Add Project Root to Path
project_root = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
if project_root not in sys.path:
    sys.path.append(project_root)

import numpy as np
import yfinance as yf
from datetime import datetime
import pytz
import time
import requests
import re
import threading
import pickle

# Slack Integration
from scripts.slack_notifier import send_dexter_slack_alert
from scripts.board_io import read_text, write_text_atomic

# Systematic daily book
from strategies.live_trading.systematic_daily import systematic_daily as sysd
from strategies.live_trading.systematic_daily import position_book

# Standard library imports for Winsound if on Windows
try:
    import winsound
except ImportError:
    winsound = None

# Strategy Class Imports
SmartMoneyStrategy = None
TripleRSIStrategy = None
NoonCurveStrategy = None
InitialBalance80Strategy = None
PO3IFVGStrategy = None
NYOrbStrategy = None
LondonDisplacementStrategy = None
wick_signals = None

try:
    from strategies.successful_strategies.btc_success.smc_btc.smc_strategy import SmartMoneyStrategy
except Exception:
    try:
        from strategies.live_trading.smc_focal_portfolio.smc_focal_portfolio import SmartMoneyStrategy
    except Exception:
        SmartMoneyStrategy = None

try:
    from strategies.successful_strategies.triple_rsi_mean_reversion import TripleRSIStrategy
except Exception:
    TripleRSIStrategy = None

try:
    from strategies.live_trading.noon_curve_lunchbox.noon_curve_lunchbox import NoonCurveStrategy
except Exception:
    NoonCurveStrategy = None

try:
    from strategies.live_trading.initial_balance_80.initial_balance_80 import InitialBalance80Strategy
except Exception:
    InitialBalance80Strategy = None

try:
    from strategies.active_strategies.po3_ifvg_strategy import PO3IFVGStrategy
except Exception:
    PO3IFVGStrategy = None

try:
    from strategies.active_strategies.ny_orb_strategy import NYOrbStrategy
except Exception:
    NYOrbStrategy = None

try:
    from strategies.live_trading.london_displacement.london_displacement import LondonDisplacementStrategy
except Exception:
    LondonDisplacementStrategy = None

try:
    from strategies.live_trading.gemini_velocity.gemini_velocity_momentum import GeminiVelocityStrategy
except Exception:
    GeminiVelocityStrategy = None

try:
    from strategies.live_trading.volcanix_vwap_reclaim.vwap_reclaim_rvol import VWAPReclaimRVOLStrategy
except Exception:
    VWAPReclaimRVOLStrategy = None

try:
    from strategies.live_trading.big_d.big_d import BigDStrategy
except Exception:
    BigDStrategy = None

try:
    from strategies.live_trading.little_d.little_d import LittleDStrategy
except Exception:
    LittleDStrategy = None

try:
    from strategies.active_testing.wickless_candle_strategy import generate_trade_signals as wick_signals
except Exception:
    wick_signals = None

# Setup Paths & Config
EST = pytz.timezone('US/Eastern')
MAX_CONCURRENT_TRADES = int(os.getenv("MAX_CONCURRENT_TRADES", "12"))
POSITION_SIZE_USD = float(os.getenv("POSITION_SIZE_USD", "10.0"))
MIN_NOTIONAL_USD = 2.0 # Proposal 22: Reject orders < $2.0 to clear RH $1 minimum

DEXTER_ROOT = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
REPORTING_ROOT = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\logs"
LOG_DIR_LIVE = os.path.join(REPORTING_ROOT, 'live_trading')
LOG_DIR_TEST = os.path.join(REPORTING_ROOT, 'live_testing')
REGISTRY_PATH = os.path.join(DEXTER_ROOT, 'strategy_registry.json')
TRACKING_BOARD_PATH = os.path.join(DEXTER_ROOT, 'dashboard', 'LIVE_TRACKING_BOARD.md')
STRATEGY_BOARD_PATH = os.path.join(DEXTER_ROOT, 'dashboard', 'LIVE_STRATEGY_BOARD.md')
BRIDGE_PATH = os.path.join(DEXTER_ROOT, 'quant_scripts', 'robinhood_bridge.py')
TELEGRAM_ENV_PATH = r"C:\Users\jmgra\antigravityagents\.agent\skills\agentic-skills\telegram-connection\.env"
WARM_CACHE_FILE   = os.path.join(DEXTER_ROOT, 'cache', 'warm_cache.pkl')
MARKET_CONTEXT_FILE = os.path.join(DEXTER_ROOT, 'market_context.json')
SIGNAL_QUALITY_FILE = os.path.join(DEXTER_ROOT, 'signal_quality.json')
SIGNAL_CACHE_FILE   = os.path.join(DEXTER_ROOT, 'cache', 'signal_cache.pkl')
LAST_TRADE_FILE    = os.path.join(DEXTER_ROOT, 'cache', 'last_trade_times.pkl')
UNSETTLED_POSITIONS_FILE = os.path.join(DEXTER_ROOT, 'cache', 'unsettled_positions.json')
ACTIVE_STRATEGIES_FILE = os.path.join(DEXTER_ROOT, 'cache', 'active_strategies.json')

# Global Session Cache
SIGNAL_CACHE = {} 
PERSISTENT_DATA_CACHE = {}
UNSETTLED_POSITIONS = {} # Track assets bought today to prevent Good Faith Violations
CACHE_MAX_SIZE = 500  # Max candles to keep in memory per asset/tf
CAUTION_MODE = False   # Set by Market Intel Agent
SIGNAL_QUALITY = {}    # Loaded from Feedback Loop Agent
LAST_TRADE_TIME = {}  # Track time of last trade per (name, ticker)
REVERSAL_COOLDOWN_SEC = 300 # 5 minute cooldown before allowing a reversal
LUNCHBOX_COOLDOWN_SEC = 900 # 15 minute hard cooldown for Noon-Curve
RAPID_STRAT_COOLDOWN_SEC = 600 # 10 minute cooldown for Matt-Rapid, DB V3, volcanix
SLIPPAGE_TOLERANCE = 0.002 # 0.2% max slippage for market orders

# --- 📊 SIGNAL-QUALITY GOVERNANCE ------------------------------------------
# SIGNAL_QUALITY is refreshed nightly by scripts/signal_quality_tracker.py and
# loaded in run_alpha_autotrader().  It now drives three decisions:
#   * block new entries for a demoted strategy
#   * halve size for a weak strategy
#   * boost size (modestly) for a proven one
# Below QUALITY_MIN_SAMPLE trades we stay neutral rather than starve a new book.
QUALITY_MIN_SAMPLE = 10
QUALITY_BLOCK_PF = 0.80
QUALITY_HALF_PF = 1.20
QUALITY_BOOST_PF = 1.30
QUALITY_LOW_WIN_RATE = 45.0


def quality_verdict(strategy_name):
    """Return (size_multiplier, block_new_entries, reason) for a strategy."""
    stats = SIGNAL_QUALITY.get(strategy_name) or {}
    n = int(stats.get("total_trades", 0) or 0)
    if n < QUALITY_MIN_SAMPLE:
        return 1.0, False, "neutral (insufficient sample)"

    pf = stats.get("profit_factor")
    wr = float(stats.get("win_rate", 50.0) or 50.0)

    if n >= 20 and pf is not None and float(pf) < QUALITY_BLOCK_PF:
        return 0.0, True, f"DEMOTED: PF {float(pf):.2f} over {n} trades"
    if n >= 20 and pf is not None and float(pf) >= QUALITY_BOOST_PF:
        return 1.25, False, f"boosted: PF {float(pf):.2f} over {n} trades"
    if n >= 20 and pf is not None and float(pf) < QUALITY_HALF_PF:
        return 0.5, False, f"half size: PF {float(pf):.2f} over {n} trades"
    if wr < QUALITY_LOW_WIN_RATE:
        return 0.5, False, f"half size: win rate {wr:.1f}% over {n} trades"
    return 1.0, False, "neutral"

# --- 📝 BATCHED I/O LOG BUFFER (Proposal 4) ---
LOG_BUFFER: list = []
LOG_BUFFER_LIMIT = 50    # Flush to disk when this many lines accumulate
LOG_BUFFER_LOCK = threading.Lock()
CACHE_LOCK = threading.Lock() # Final safeguard for parallel data fetching

# --- 🖥️ ASYNC BOARD RENDERER (Proposal 9) ---
import queue as _queue_mod
BOARD_QUEUE: _queue_mod.Queue = _queue_mod.Queue()
_BOARD_THREAD_STARTED = False
GLOBAL_ACTIVE_POSITIONS = {}

# --- 2x LEVERAGED BITCOIN & SHORT ASSET MAPPINGS ---
# Long 2x Bitcoin ETF: BITU (ProShares Ultra Bitcoin ETF)
# Short 2x Bitcoin ETF: SBIT (ProShares UltraShort Bitcoin ETF)
LONG_MAP = {
    "BITU": "BITU",
    "IBIT": "BITU",
    "BTC-USD": "BITU",
    "BTC": "BITU",
    "BITO": "BITU",
}

# Inverse Mapping for Shorting on Cash Accounts (Bearish Proxies)
INVERSE_MAP = {
    "SPY": "SH",     # Inverse S&P 500
    "QQQ": "PSQ",    # Inverse Nasdaq 100
    "IWM": "RWM",    # Inverse Russell 2000
    "DIA": "DOG",    # Inverse Dow 30
    "XBI": "LABD",   # 3x Inverse Biotech
    "TSLA": "TSLQ",  # Inverse Tesla
    "NVDA": "NVDS",  # Inverse Nvidia
    "AAPL": "AAPD",  # 2x Inverse Apple
    "AMZN": "AMZD",  # Direxion Daily AMZN Bear 1X Shares
    "MSFT": "MSFY",  # Inverse Microsoft
    "GOOGL": "SQQQ", # Use Nasdaq Inverse proxy if direct missing
    "META": "METP",  # Inverse Meta
    "SNOW": "SQQQ",  # Nasdaq 100 Proxy (High beta tech)
    "CAT": "SARK",   # Inverse Innovation/Growth (Proxy for high beta mid-caps)
    "COIN": "BITI",  # Inverse Bitcoin Strategy ETF (Bullish crypto-stock counterpart)
    "SMCI": "SOXS",  # 3x Inverse Semiconductors
    "MU": "SOXS",    # 3x Inverse Semiconductors
    "KLAC": "SOXS",  # 3x Inverse Semiconductors
    "TSM": "SOXS",   # 3x Inverse Semiconductors
    "ARM": "SOXS",   # 3x Inverse Semiconductors
    "PLTR": "PLTD",  # Inverse Palantir (Direxion Daily PLTR Bear 1X ETF)
    "MSTR": "MSTZ",  # 2x Inverse MicroStrategy (T-REX 2X Inverse MSTR Daily Target ETF)
    "AMD": "AMDD",   # Inverse AMD (Direxion Daily AMD Bear 1X ETF)
    "LRCX": "SOXS",  # 3x Inverse Semiconductors
    "SMH": "SOXS",   # 3x Inverse Semiconductors
    "SOXL": "SOXS",  # 3x Inverse Semiconductors
    "TQQQ": "SQQQ",  # 3x Inverse Nasdaq 100
    "XLK": "TECS",   # 3x Inverse Technology
    "XLF": "FAZ",    # 3x Inverse Financials
    "CRWD": "SQQQ",  # Nasdaq 100 3x Inverse Proxy
    "ABNB": "SQQQ",  # Nasdaq 100 3x Inverse Proxy
    "HOOD": "SQQQ",  # High-Beta Tech/Fintech Inverse Proxy
    "UBER": "SH",    # S&P 500 Inverse Proxy
    "GLD": "GLL",    # 2x Inverse Gold
    "SLV": "ZSL",    # 2x Inverse Silver
    "SBIT": "BITU",  # Inverse of Short ETF -> Long 2x BTC ETF
    "SQQQ": "TQQQ",  # Inverse of Short QQQ -> Long 3x QQQ ETF
    "SOXS": "SOXL",  # Inverse of Short Semis -> Long 3x Semis ETF
    # 2x Short ProShares UltraShort Bitcoin ETF:
    "BITU": "SBIT",  # Short BITU -> Open SBIT
    "IBIT": "SBIT",  # Short IBIT -> Open SBIT
    "BTC-USD": "SBIT", # Short BTC-USD -> Open SBIT
    "BTC": "SBIT",
    "BITO": "SBIT",
    "ETHE": "SETH",  # Inverse Ethereum
}

# --- ⚡ 2x LEVERAGED BITCOIN ETF RISK ENGINE & CIRCUIT BREAKER ---
LEVERAGED_BTC_ETFS = {"BITU", "SBIT"}
INVERSE_BEAR_ETFS = {
    "SBIT", "BITI", "SETH", "SQQQ", "PSQ", "QID", "SPXS", "SPXU", "SH", "SDS",
    "TZA", "SRTY", "RWM", "SDOW", "DOG", "SOXS", "TECS", "LABD", "FAZ", "DRV",
    "GLL", "ZSL", "SARK", "TSLQ", "NVDS", "NVD", "MSTZ", "PLTD", "AMDD", "AAPD",
    "AMZD", "MSFY", "METP", "CONI"
}
ETF_POSITIONS_FILE = os.path.join(DEXTER_ROOT, 'cache', 'etf_positions.json')
CIRCUIT_BREAKER_FILE = os.path.join(DEXTER_ROOT, 'cache', 'circuit_breaker.json')

# Configurable exit and circuit breaker thresholds
ETF_STOP_LOSS_PCT = float(os.getenv("ETF_STOP_LOSS_PCT", "2.0"))     # Default: 2% Stop Loss on 2x ETF
ETF_TAKE_PROFIT_PCT = float(os.getenv("ETF_TAKE_PROFIT_PCT", "4.0")) # Default: 4% Take Profit on 2x ETF
ETF_MAX_HOLD_MINUTES = int(os.getenv("ETF_MAX_HOLD_MINUTES", "240")) # Default: 240 mins (4 hours)
DAILY_CIRCUIT_BREAKER_PCT = float(os.getenv("DAILY_CIRCUIT_BREAKER_PCT", "4.5")) # Default: 4.5% drawdown

def load_etf_positions():
    """Loads active leveraged Bitcoin ETF positions (BITU / SBIT) from disk cache."""
    if os.path.exists(ETF_POSITIONS_FILE):
        try:
            with open(ETF_POSITIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log_engine(f"Warning: Failed to load ETF positions: {e}", level="warning")
    return {}

def save_etf_positions(positions):
    """Persists active leveraged Bitcoin ETF positions to disk cache."""
    try:
        os.makedirs(os.path.dirname(ETF_POSITIONS_FILE), exist_ok=True)
        with open(ETF_POSITIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(positions, f, indent=4)
    except Exception as e:
        log_engine(f"Error saving ETF positions: {e}", level="error")

def record_etf_entry(symbol, entry_price, side, quantity, strategy_name):
    """Task 1: On entry, record entry_price, symbol (LONG_ETF or SHORT_ETF), and side."""
    positions = load_etf_positions()
    now_est = datetime.now(EST)
    positions[symbol] = {
        "symbol": symbol,
        "entry_price": float(entry_price),
        "side": side.upper(),  # "LONG" (for BITU) or "SHORT" (for SBIT)
        "quantity": float(quantity),
        "entry_time": now_est.strftime("%Y-%m-%d %H:%M:%S EST"),
        "entry_timestamp": time.time(),
        "strategy_name": strategy_name
    }
    save_etf_positions(positions)
    log_engine(f"📌 RECORDED ETF POSITION: {symbol} ({side.upper()}) | Entry: ${float(entry_price):.2f} | Qty: {quantity} | Strat: {strategy_name}")

def remove_etf_position(symbol):
    """Removes an ETF position from active tracking once closed."""
    positions = load_etf_positions()
    if symbol in positions:
        pos = positions.pop(symbol)
        save_etf_positions(positions)
        log_engine(f"🗑️ CLEARED ETF POSITION: {symbol} (Was opened at ${pos.get('entry_price', 0):.2f})")

def get_etf_realtime_price(symbol):
    """Fetches real-time market price for an ETF ticker."""
    try:
        t = yf.Ticker(symbol)
        if hasattr(t, "fast_info") and "lastPrice" in t.fast_info and t.fast_info["lastPrice"] is not None:
            return float(t.fast_info["lastPrice"])
        if hasattr(t, "fast_info") and hasattr(t.fast_info, "last_price") and t.fast_info.last_price is not None:
            return float(t.fast_info.last_price)
        hist = t.history(period="1d", interval="1m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        hist_day = t.history(period="1d")
        if not hist_day.empty:
            return float(hist_day["Close"].iloc[-1])
    except Exception as e:
        log_engine(f"Warning: Could not fetch real-time price for {symbol}: {e}", level="warning")
    return None

def load_circuit_breaker_state():
    """Loads daily circuit breaker state tracking equity drawdown."""
    today_str = datetime.now(EST).strftime("%Y-%m-%d")
    default_state = {
        "date": today_str,
        "starting_equity": 0.0,
        "peak_equity": 0.0,
        "current_equity": 0.0,
        "drawdown_pct": 0.0,
        "tripped": False,
        "trip_time": None,
        "trip_reason": None
    }
    if os.path.exists(CIRCUIT_BREAKER_FILE):
        try:
            with open(CIRCUIT_BREAKER_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                if state.get("date") == today_str:
                    return state
        except Exception as e:
            log_engine(f"Warning: Failed to load circuit breaker state: {e}", level="warning")
    return default_state

def save_circuit_breaker_state(state):
    """Persists circuit breaker state to disk cache."""
    try:
        os.makedirs(os.path.dirname(CIRCUIT_BREAKER_FILE), exist_ok=True)
        with open(CIRCUIT_BREAKER_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        log_engine(f"Error saving circuit breaker state: {e}", level="error")

def is_circuit_breaker_active():
    """Returns True if the daily circuit breaker has been tripped today."""
    state = load_circuit_breaker_state()
    return bool(state.get("tripped", False))

def get_current_portfolio_equity(port=5005):
    """Calculates total portfolio equity (cash + stock market value) from bridge."""
    try:
        # Cash
        cash_url = f"http://127.0.0.1:{port}/cash"
        c_resp = requests.get(cash_url, timeout=5)
        portfolio_cash = 0.0
        if c_resp.status_code == 200:
            c_data = c_resp.json()
            portfolio_cash = float(c_data.get("portfolio_cash") or c_data.get("cash_available_for_withdrawal") or 0.0)

        # Positions
        pos_url = f"http://127.0.0.1:{port}/positions"
        p_resp = requests.get(pos_url, timeout=5)
        stock_equity = 0.0
        if p_resp.status_code == 200:
            p_data = p_resp.json()
            stocks = p_data.get("stocks", {})
            for sym, info in stocks.items():
                qty = float(info.get("quantity", 0))
                if qty > 0:
                    eq = float(info.get("equity") or 0)
                    if eq <= 0:
                        pr = float(info.get("price") or 0)
                        eq = qty * pr
                    stock_equity += eq
        total_equity = portfolio_cash + stock_equity
        return total_equity if total_equity > 0 else None
    except Exception:
        return None

def evaluate_etf_exits_and_circuit_breaker(mode="LIVE_MARKET"):
    """
    Evaluates:
    1. Daily Circuit Breaker: If equity drawdown >= DAILY_CIRCUIT_BREAKER_PCT (default 4.5%),
       flattens all ETF positions and pauses new entries.
    2. Unrealized PnL % on 2x Leveraged Bitcoin ETFs (BITU / SBIT):
       - Stop Loss: PnL <= -2.0% -> 'Stop Loss (-2% on 2x ETF)'
       - Take Profit: PnL >= +4.0% -> 'Take Profit (+4% on 2x ETF)'
       - Max Hold: Duration >= ETF_MAX_HOLD_MINUTES -> 'Max Hold Period'
    """
    now_time = time.time()
    cb_state = load_circuit_breaker_state()

    # 1. Update Portfolio Equity & Circuit Breaker Tracking
    equity = get_current_portfolio_equity()
    if equity is not None and equity > 0:
        if cb_state.get("starting_equity", 0.0) <= 0:
            cb_state["starting_equity"] = equity
            cb_state["peak_equity"] = equity

        if equity > cb_state.get("peak_equity", 0.0):
            cb_state["peak_equity"] = equity

        cb_state["current_equity"] = equity
        peak = cb_state["peak_equity"]
        drawdown_pct = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
        cb_state["drawdown_pct"] = round(drawdown_pct, 2)

        # Check if Circuit Breaker tripped
        if drawdown_pct >= DAILY_CIRCUIT_BREAKER_PCT and not cb_state.get("tripped", False):
            cb_state["tripped"] = True
            cb_state["trip_time"] = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")
            cb_state["trip_reason"] = f"Daily drawdown reached {drawdown_pct:.2f}% (Threshold: {DAILY_CIRCUIT_BREAKER_PCT}%)"
            save_circuit_breaker_state(cb_state)

            trip_msg = (
                f"🚨 *DAILY CIRCUIT BREAKER TRIPPED*\n"
                f"Drawdown: -{drawdown_pct:.2f}% from peak (${peak:.2f} -> ${equity:.2f})\n"
                f"Threshold: {DAILY_CIRCUIT_BREAKER_PCT}%\n"
                f"Action: FLATTENING ALL 2x BITCOIN ETF POSITIONS & PAUSING NEW ENTRIES."
            )
            log_engine(trip_msg, level="error")
            send_quant_alert(trip_msg)

            # Flatten all active ETF positions immediately
            active_etfs = load_etf_positions()
            for sym, pos in list(active_etfs.items()):
                qty = pos.get("quantity")
                curr_px = get_etf_realtime_price(sym) or pos.get("entry_price")
                execute_trade(f"Daily Circuit Breaker (-{drawdown_pct:.1f}% Drawdown)", sym, "SELL", curr_px, mode=mode, quantity_override=qty)
                remove_etf_position(sym)
            return

        save_circuit_breaker_state(cb_state)

    # 2. Check if circuit breaker is active (blocks entries, ensures flattened state)
    if cb_state.get("tripped", False):
        log_engine(f"⏸️ Circuit breaker is active for today ({cb_state.get('trip_reason')}). New entries paused.", level="warning")

    # 3. Fetch Active Positions from Broker to cross-reference
    active_broker_positions = get_active_positions(mode=mode)
    tracked_positions = load_etf_positions()

    # Auto-seed any broker positions that might be missing from tracked_positions
    for sym in LEVERAGED_BTC_ETFS:
        if sym in active_broker_positions and sym not in tracked_positions:
            qty = active_broker_positions[sym]
            entry_px = find_entry_price(sym) or get_etf_realtime_price(sym) or 0.0
            side = "LONG" if sym == "BITU" else "SHORT"
            record_etf_entry(sym, entry_px, side, qty, "Auto-Seeded Broker Position")
            tracked_positions = load_etf_positions()

    # 4. Evaluate Bracket Exits on tracked Leveraged ETFs
    for sym, pos in list(tracked_positions.items()):
        if sym not in LEVERAGED_BTC_ETFS:
            continue

        qty = pos.get("quantity")
        if sym in active_broker_positions:
            qty = active_broker_positions[sym]

        entry_price = float(pos.get("entry_price", 0))
        if entry_price <= 0:
            continue

        curr_price = get_etf_realtime_price(sym)
        if not curr_price or curr_price <= 0:
            log_engine(f"Could not retrieve real-time price for {sym} to calculate exits.", level="warning")
            continue

        # PnL % calculated on the ETF itself (both BITU and SBIT are held long)
        pnl_pct = ((curr_price - entry_price) / entry_price) * 100.0

        entry_ts = pos.get("entry_timestamp", now_time)
        hold_minutes = (now_time - entry_ts) / 60.0

        side_label = pos.get("side", "LONG")
        log_engine(f"🔍 ETF EXIT CHECK: {sym} ({side_label}) | Entry: ${entry_price:.2f} | Current: ${curr_price:.2f} | PnL: {pnl_pct:+.2f}% | Hold: {hold_minutes:.1f}m/{ETF_MAX_HOLD_MINUTES}m")

        exit_label = None
        alert_title = None
        if pnl_pct <= -ETF_STOP_LOSS_PCT:
            exit_label = "Stop Loss (-2% on 2x ETF)"
            alert_title = "🛑 *LEVERAGED ETF STOP-LOSS HIT*"
        elif pnl_pct >= ETF_TAKE_PROFIT_PCT:
            exit_label = "Take Profit (+4% on 2x ETF)"
            alert_title = "🎯 *LEVERAGED ETF TAKE-PROFIT HIT*"
        elif hold_minutes >= ETF_MAX_HOLD_MINUTES:
            exit_label = "Max Hold Period"
            alert_title = "⏰ *LEVERAGED ETF MAX-HOLD EXIT HIT*"

        if exit_label:
            log_engine(f"🚨 TRIGGERING EXIT: {sym} -> {exit_label} (PnL: {pnl_pct:+.2f}%, Held: {hold_minutes:.1f}m)")
            send_quant_alert(
                f"{alert_title}\n"
                f"Symbol: {sym} ({side_label})\n"
                f"Reason: {exit_label}\n"
                f"Entry Price: ${entry_price:.2f}\n"
                f"Exit Price: ${curr_price:.2f}\n"
                f"Unrealized PnL: {pnl_pct:+.2f}%\n"
                f"Hold Duration: {hold_minutes:.1f} min\n"
                f"Strategy: {pos.get('strategy_name', 'Quant Alpha')}"
            )
            execute_trade(exit_label, sym, "SELL", curr_price, mode=mode, quantity_override=qty)
            remove_etf_position(sym)

def is_in_window(window_str):
    """Checks if current EST time is within HH:MM-HH:MM window."""
    if not window_str or window_str == "00:00-23:59": return True
    try:
        now = datetime.now(EST).strftime("%H:%M")
        start_str, end_str = window_str.split("-")
        return start_str <= now <= end_str
    except Exception as e:
        log_engine(f"Window Check Error for {window_str}: {e}", level="error")
        return True

def flush_log_buffer():
    """Flush all buffered log lines to disk in a single write."""
    global LOG_BUFFER
    with LOG_BUFFER_LOCK:
        if not LOG_BUFFER:
            return
        batch = LOG_BUFFER[:]
        LOG_BUFFER = []
    log_path = os.path.join(LOG_DIR_LIVE, "alpha_engine.log")
    try:
        os.makedirs(LOG_DIR_LIVE, exist_ok=True)
        with open(log_path, "a", encoding='utf-8') as f:
            f.write("\n".join(batch) + "\n")
    except Exception as e:
        print(f"[FLUSH ERROR] Could not write log buffer: {e}")

def log_engine(message, level="info"):
    """Buffers log messages and flushes to disk in batches (Proposal 4)."""
    global LOG_BUFFER
    timestamp = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [{level.upper()}] {message}"
    try:
        print(formatted)
    except UnicodeEncodeError:
        print(formatted.encode('ascii', errors='replace').decode('ascii'))
    with LOG_BUFFER_LOCK:
        LOG_BUFFER.append(formatted)
        should_flush = len(LOG_BUFFER) >= LOG_BUFFER_LIMIT
    if should_flush:
        flush_log_buffer()

def send_quant_alert(message, is_error=False):
    """Sends an alert to Buzz (#Quantative-Analyst for trades, #Triage for errors)."""
    return send_dexter_slack_alert(message, is_error=is_error)

def _position_price(ticker, pos):
    """Best available price for an open position, without blocking on a slow feed."""
    try:
        live_px = float(pos.get("price") or 0)
        if live_px > 0:
            return live_px
    except (TypeError, ValueError):
        pass
    try:
        hist = yf.Ticker(ticker).history(period="1d", interval="1m")
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1d")
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return 0.0


def _load_intraday_only_strategies(registry):
    """Names of strategies that must be flat overnight (frequency <= 10 min)."""
    names = set()
    for cat in ['live_trading', 'active_testing']:
        for s in registry.get(cat, []):
            if int(s.get('frequency', 3600) or 3600) <= 600:
                names.add(s['name'])
    names.add("Volcanix (VWAP Reclaim)")
    return names


def close_short_term_positions(timeframes=None):
    """Flatten intraday-only positions at the close.

    Fixes versus the original implementation:
      * sells the position's actual quantity (it used to sell ~$10 worth and
        log "Not enough shares to sell")
      * attributes the exit to the strategy that opened the trade, so the
        signal-quality feedback loop can pair entry and exit
      * never touches multi-day systematic positions, even when their symbol
        also appears in an intraday strategy's asset list
      * uses the broker's mark when available instead of a second yfinance call
    """
    log_engine("🌅 Starting EOD Close of Short-Term Positions...")
    try:
        resp = requests.get("http://127.0.0.1:5005/positions", timeout=15)
        if resp.status_code != 200:
            log_engine(f"Error fetching positions: {resp.text}", level="error")
            return

        stocks = resp.json().get("stocks", {})

        registry = {}
        if os.path.exists(REGISTRY_PATH):
            with open(REGISTRY_PATH, 'r') as f:
                registry = json.load(f)

        intraday_names = _load_intraday_only_strategies(registry)

        # Authoritative ticker -> strategy mapping, written on every fill.
        active_map = {}
        try:
            if os.path.exists(ACTIVE_STRATEGIES_FILE):
                with open(ACTIVE_STRATEGIES_FILE, 'r') as f:
                    active_map = json.load(f)
        except Exception as e:
            log_engine(f"EOD: could not read strategy map: {e}", level="warning")

        # Symbol -> intraday strategy fallback (only when the map is missing).
        symbol_to_intraday = {}
        for cat in ['live_trading', 'active_testing']:
            for s in registry.get(cat, []):
                if s['name'] in intraday_names:
                    for sym in s.get('assets', []):
                        symbol_to_intraday.setdefault(sym, s['name'])

        systematic_book = position_book.load_book()
        systematic_symbols = {rec.get("ticker") for rec in systematic_book.values()}

        closed_count = 0
        skipped_unknown = []

        for ticker, pos in stocks.items():
            try:
                qty = float(pos.get('quantity', 0))
            except (TypeError, ValueError):
                qty = 0.0
            if qty <= 0:
                continue
            if ticker in systematic_symbols:
                log_engine(f"EOD: keeping {ticker} — held by the multi-day systematic book.")
                continue

            strat_name = active_map.get(ticker) or symbol_to_intraday.get(ticker)
            if not strat_name:
                skipped_unknown.append(ticker)
                continue
            if strat_name not in intraday_names:
                log_engine(f"EOD: keeping {ticker} — {strat_name} is not intraday-only.")
                continue

            price = _position_price(ticker, pos)
            if price <= 0:
                log_engine(f"EOD: no usable price for {ticker}; skipping.", level="warning")
                continue

            log_engine(f"Closing EOD Position: {ticker} x{qty} ({strat_name}) @ ${price:.2f}")
            execute_trade(strat_name, ticker, "SELL", price,
                          target_symbol=ticker, quantity_override=qty)
            closed_count += 1

        if skipped_unknown:
            log_engine(f"EOD: left {', '.join(sorted(skipped_unknown))} open — no strategy attribution.",
                       level="warning")

        log_engine(f"EOD Cleanup Complete. Closed {closed_count} positions.")
        send_quant_alert(f"🌅 *EOD CLEANUP*\nClosed {closed_count} intraday positions.")

    except Exception as e:
        log_engine(f"EOD Close Error: {e}", level="error")

def generate_daily_pnl_report():
    """Aggregates all trades for today and sends an enhanced Slack Post-Mortem."""
    log_engine("📊 Triggering Enhanced Post-Mortem Report...")
    try:
        python_exe = os.path.join(DEXTER_ROOT, "quant-env", "Scripts", "python.exe")
        report_script = os.path.join(DEXTER_ROOT, "scripts", "post_mortem_report.py")
        subprocess.run([python_exe, report_script], check=False)
    except Exception as e:
        log_engine(f"Report Trigger Error: {e}", level="error")

def find_entry_price(ticker):
    path = os.path.join(LOG_DIR_LIVE, "execution.log")
    if not os.path.exists(path): return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in reversed(lines):
                if ticker in line and ("EXEC-BUY" in line or "EXEC-SHORT" in line):
                    parts = line.split('|')
                    if len(parts) >= 3:
                        price_str = parts[2].split('$')[-1].strip()
                        return float(price_str)
    except: pass
    return None

def play_trade_notification():
    if winsound:
        try:
            # Shift to a professional "Double-Chirp" (1500Hz -> 2000Hz)
            winsound.Beep(1500, 80)
            winsound.Beep(2000, 120)
        except:
            # Fallback for systems where Beep is disabled/silent
            try:
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
            except: pass

def update_live_tracking_board(strategy_name, ticker, side):
    """Inserts a new trade record at the top of the tracking board table."""
    try:
        now_est = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")
        new_entry = f"| **{strategy_name}** | {ticker} | {now_est} | {side} |\n"
        
        # Absolute path ensure
        target_path = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent\dashboard\LIVE_TRACKING_BOARD.md"
        
        if os.path.exists(target_path):
            with open(target_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        else:
            lines = []

        # Validate/Repair structure
        if len(lines) < 4 or "| Status |" not in "".join(lines[:10]):
            log_engine("Repairing Tracking Board structure...", level="warning")
            lines = [
                "# 📊 LIVE TRADE TRACKING\n",
                "**Orchestrator: Dexter [Quant Agent]**\n",
                "\n",
                "| Strategy Used | Asset Traded | Time Traded (EST) | Status |\n",
                "| :--- | :--- | :--- | :--- |\n"
            ]

        insert_idx = -1
        for i, line in enumerate(lines):
            if "| :---" in line or "|---" in line.replace(" ", ""):
                insert_idx = i + 1
                break
        
        if insert_idx != -1:
            lines.insert(insert_idx, new_entry)
        else:
            lines.append(new_entry)
            
        # Write back
        write_text_atomic(target_path, "".join(lines))
        log_engine(f"Board Updated: {strategy_name} -> {ticker} ({side})")
    except Exception as e:
        log_engine(f"Board Update Failed: {e}", level="error")

def update_portfolio_display(active_positions):
    """Updates the 'ACTIVE PORTFOLIO' section in the Strategy Board with Strategy Names."""
    try:
        target_path = STRATEGY_BOARD_PATH
        if not os.path.exists(target_path): return
        
        # Load Strategy Mapping Cache
        strat_map = {}
        if os.path.exists(ACTIVE_STRATEGIES_FILE):
            try:
                with open(ACTIVE_STRATEGIES_FILE, 'r') as f:
                    strat_map = json.load(f)
            except: pass

        with open(target_path, "r", encoding='utf-8') as f:
            content = f.read()

        # Generate portfolio table - Show all positions with Strategy
        pos_list = list(active_positions.items())
        portfolio_table = "## 📈 ACTIVE PORTFOLIO\n| Asset | Strategy | Quantity | Status |\n| :--- | :--- | :--- | :--- |\n"
        
        if not pos_list:
            portfolio_table += "| None | N/A | 0.0 | CASH |\n"
        else:
            for ticker, qty in pos_list:
                strat_name = strat_map.get(ticker, "Unknown")
                portfolio_table += f"| **{ticker}** | {strat_name} | {qty} | HOLDING |\n"
        
        # Use a more constrained regex to avoid devouring the whole file
        if "## 📈 ACTIVE PORTFOLIO" in content:
            content = re.sub(r"## 📈 ACTIVE PORTFOLIO\n(.*?)(?=\n##\s| \n#|$)", portfolio_table + "\n", content, flags=re.DOTALL)
        else:
            # Insert before LIVE TRADING or at end
            if "## 🟢 LIVE TRADING" in content:
                content = content.replace("## 🟢 LIVE TRADING", portfolio_table + "\n## 🟢 LIVE TRADING")
            else:
                content += "\n\n" + portfolio_table
        
        write_text_atomic(target_path, content)
    except Exception as e:
        log_engine(f"Portfolio Display Update Failed: {e}", level="error")

_BOARD_REBUILD_STAMP = {"mtime": None, "ts": 0.0}


def refresh_strategy_board(force=False):
    """Rebuild the board from the registry when the registry changes.

    `_write_board_signal` can only update rows that already exist, so adding a
    strategy to the registry used to leave it invisible on the board.  This
    runs `scripts/rebuild_board.py`, which owns row creation and preserves the
    live portfolio/signal sections.
    """
    try:
        if not os.path.exists(REGISTRY_PATH):
            return
        mtime = os.path.getmtime(REGISTRY_PATH)
        now = time.time()
        if not force:
            if _BOARD_REBUILD_STAMP["mtime"] == mtime:
                return
            if now - _BOARD_REBUILD_STAMP["ts"] < 300:
                return
        _BOARD_REBUILD_STAMP["mtime"] = mtime
        _BOARD_REBUILD_STAMP["ts"] = now

        script = os.path.join(DEXTER_ROOT, "scripts", "rebuild_board.py")
        if not os.path.exists(script):
            return
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([sys.executable, script], cwd=DEXTER_ROOT,
                         creationflags=flags)
    except Exception as e:
        log_engine(f"Board Refresh Failed: {e}", level="error")

def _write_board_signal(strategy_name, latest_signal):
    """Direct I/O: updates 'Latest Signal' and 'Status' in the Strategy Board (called by renderer thread)."""
    try:
        target_path = STRATEGY_BOARD_PATH
        if not os.path.exists(target_path): return
        
        with open(target_path, "r", encoding='utf-8') as f:
            lines = f.readlines()
        
        updated = False
        is_past_testing_header = False
        
        for i, line in enumerate(lines):
            if "## 🟡 ACTIVE TESTING" in line:
                is_past_testing_header = True
            
            clean_line = line.replace("**", "")
            if strategy_name.lower() in clean_line.lower() and "|" in line:
                parts = line.split("|")
                # Dynamically resolve Status and Latest Signal relative to the table structure
                if len(parts) >= 6:
                    status_idx = len(parts) - 3
                    signal_idx = len(parts) - 2
                    new_status = " 🧪 TEST " if is_past_testing_header else " 🚀 LIVE "
                    
                    if latest_signal == "SLEEP":
                        new_status = " 💤 SLEEP "
                        latest_signal = "DORMANT"
                    
                    has_changes = False
                    if parts[status_idx].strip() != new_status.strip():
                        parts[status_idx] = new_status
                        has_changes = True
                    
                    if latest_signal != "None" and parts[signal_idx].strip() != latest_signal.strip():
                        parts[signal_idx] = f" {latest_signal} "
                        has_changes = True
                    
                    if has_changes:
                        lines[i] = "|".join(parts)
                        updated = True
                    break
                elif len(parts) == 5:
                    # Old format fallback
                    status_idx = 3
                    signal_idx = 4
                    new_status = " 🧪 TEST " if is_past_testing_header else " 🚀 LIVE "
                    if latest_signal == "SLEEP":
                        new_status = " 💤 SLEEP "
                        latest_signal = "DORMANT"
                    has_changes = False
                    if parts[status_idx].strip() != new_status.strip():
                        parts[status_idx] = new_status
                        has_changes = True
                    if latest_signal != "None" and parts[signal_idx].strip() != latest_signal.strip():
                        parts[signal_idx] = f" {latest_signal} "
                        has_changes = True
                    if has_changes:
                        lines[i] = "|".join(parts)
                        updated = True
                    break
        
        if updated:
            write_text_atomic(target_path, "".join(lines))
    except Exception as e:
        log_engine(f"Board Signal Write failed for {strategy_name}: {e}", level="error")

def _board_renderer_worker():
    """Daemon thread: drains BOARD_QUEUE every 1s and batches board writes (Proposal 9)."""
    while True:
        time.sleep(1.0)
        if BOARD_QUEUE.empty():
            continue
        # Drain all pending updates; last signal per strategy wins
        batch: dict = {}
        while not BOARD_QUEUE.empty():
            try:
                name, signal = BOARD_QUEUE.get_nowait()
                batch[name] = signal
                BOARD_QUEUE.task_done()
            except Exception:
                break
        for sname, sig in batch.items():
            _write_board_signal(sname, sig)

def _start_board_thread():
    """Start the board renderer daemon thread once per process."""
    global _BOARD_THREAD_STARTED
    if not _BOARD_THREAD_STARTED:
        t = threading.Thread(target=_board_renderer_worker, daemon=True, name='BoardRenderer')
        t.start()
        _BOARD_THREAD_STARTED = True

def update_board_signal(strategy_name, latest_signal):
    """Queues a board signal update — returns immediately, renderer thread does the I/O (Proposal 9)."""
    BOARD_QUEUE.put((strategy_name, latest_signal))

def log_event(strategy_name, ticker, signal_type, price, is_live=False):
    log_file = "execution.log" if is_live else "signals.log"
    log_dir = LOG_DIR_LIVE if is_live else LOG_DIR_TEST
    path = os.path.join(log_dir, log_file)
    prefix = "[LIVE-EXEC]" if is_live else "[TEST-SCAN]"
    
    # Ensure directory exists
    os.makedirs(log_dir, exist_ok=True)
    
    entry = f"{prefix} [{datetime.now(EST)}] {strategy_name} | {ticker} | {signal_type} @ ${price:.2f}\n"
    with open(path, "a", encoding='utf-8') as f:
        f.write(entry)
    
    log_engine(entry.strip())
    
    # PROMPT: Always update tracking board for live signals
    if is_live:
        update_live_tracking_board(strategy_name, ticker, signal_type)


def get_active_positions(mode="LIVE_MARKET"):
    """Fetches open positions from Bridge via Persistent API Bridge (5005 for RH, 5006 for IBKR)."""
    try:
        # Toggle for IBKR
        enable_ibkr = os.getenv("ENABLE_IBKR_OVERNIGHT", "False").lower() == "true"
        
        # Default to 5005 (Robinhood)
        port = 5005
        if mode == "OVERNIGHT" and enable_ibkr:
            port = 5006
            
        url = f"http://127.0.0.1:{port}/positions"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if port == 5006:
                # IBKR format: [{"account": "...", "symbol": "...", "quantity": 100, "avgCost": ...}]
                positions = {p['symbol']: float(p['quantity']) for p in data if float(p['quantity']) != 0}
            else:
                # Robinhood format: {"stocks": {"AAPL": {"quantity": "1.0", ...}}, "options": ...}
                stocks = data.get('stocks', {})
                positions = {k: float(v.get('quantity', 0)) for k, v in stocks.items() if float(v.get('quantity', 0)) > 0}
            return positions
        else:
            log_engine(f"Bridge API ({port}) Status Error: {response.status_code}", level="error")
    except Exception as e:
         log_engine(f"Persistent Bridge Connection Error (Port {port if 'port' in locals() else 'Unknown'}): {e}. Check if Bridge Server is running.", level="error")
    return {}


def get_settled_cash(port=5005):
    """Fetches settled cash availability from Bridge /cash endpoint."""
    try:
        url = f"http://127.0.0.1:{port}/cash"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # In a Cash Account, we must use 'cash_available_for_withdrawal' or specific 'settled' field if provided
            # Robinhood profile 'cash_available_for_withdrawal' is the most conservative 'settled' proxy.
            return float(data.get('cash_available_for_withdrawal', 0))
    except Exception as e:
        log_engine(f"Error fetching settled cash: {e}", level="error")
    return 0.0

def load_unsettled_tracker():
    global UNSETTLED_POSITIONS
    if os.path.exists(UNSETTLED_POSITIONS_FILE):
        try:
            with open(UNSETTLED_POSITIONS_FILE, 'r') as f:
                UNSETTLED_POSITIONS = json.load(f)
        except: UNSETTLED_POSITIONS = {}

def save_unsettled_tracker():
    try:
        os.makedirs(os.path.dirname(UNSETTLED_POSITIONS_FILE), exist_ok=True)
        with open(UNSETTLED_POSITIONS_FILE, 'w') as f:
            json.dump(UNSETTLED_POSITIONS, f)
    except: pass

def update_active_strategy_cache(ticker, strategy_name, action):
    """Saves or removes strategy mapping for active positions."""
    try:
        os.makedirs(os.path.dirname(ACTIVE_STRATEGIES_FILE), exist_ok=True)
        data = {}
        if os.path.exists(ACTIVE_STRATEGIES_FILE):
            with open(ACTIVE_STRATEGIES_FILE, 'r') as f:
                data = json.load(f)
        
        if action == "buy":
            data[ticker] = strategy_name
        elif action == "sell":
            data.pop(ticker, None)
            
        with open(ACTIVE_STRATEGIES_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        log_engine(f"Failed to update strategy cache: {e}", level="error")

def execute_trade(strategy_name, ticker, side, price, timeframe=None, mode="LIVE_MARKET", target_symbol=None, quantity_override=None):
    """Triggers an actual order on the Bridge (5005 for RH, 5006 for IBKR) with Settlement Guard."""
    load_unsettled_tracker()
    target_ticker = target_symbol if target_symbol else ticker
    
    # Toggle for IBKR
    enable_ibkr = os.getenv("ENABLE_IBKR_OVERNIGHT", "False").lower() == "true"
    
    # Port selection
    port = 5005
    if mode == "OVERNIGHT" and enable_ibkr:
        port = 5006
    else:
        # Bullish 2x Leveraged Mapping (e.g. BTC/IBIT -> BITU)
        if side.upper() in ["BUY", "LONG"] and not target_symbol:
            if ticker in LONG_MAP:
                target_ticker = LONG_MAP[ticker]
                log_engine(f"Bullish 2x Leveraged Mapped: {ticker} -> {target_ticker}")

        # Bearish 2x Short Mapping (e.g. BTC/IBIT/BITU -> SBIT)
        if side.upper() in ["SHORT", "BEARISH"] and not target_symbol:
            if ticker in INVERSE_MAP:
                 target_ticker = INVERSE_MAP[ticker]
                 log_engine(f"Bearish 2x Leveraged Mapped: {ticker} -> {target_ticker}")
            else:
                 log_engine(f"🛡️ EXECUTION GUARD: {strategy_name} signaled SHORT for {ticker}, but no Inverse Mapping found and Cash Account cannot short. Aborting.", level="warning")
                 return {"ok": False, "reason": "no_inverse_mapping"}
    
    # Resolve real execution price for mapped targets (e.g. BTC-USD $65000 -> BITU/SBIT)
    exec_price = price
    if target_ticker != ticker and (exec_price > 1000 or exec_price <= 0):
        try:
            t_hist = yf.Ticker(target_ticker).history(period="1d")
            if not t_hist.empty:
                exec_price = float(t_hist['Close'].iloc[-1])
        except Exception as pe:
            log_engine(f"Warning: Could not fetch real-time price for mapped {target_ticker}: {pe}", level="warning")

    # Position sizing: Use override if provided, otherwise POSITION_SIZE_USD.
    if quantity_override is not None:
        quantity = quantity_override
    else:
        quantity = round(POSITION_SIZE_USD / exec_price, 4) if exec_price > 0 else 0
        if CAUTION_MODE and side.upper() in ["BUY", "LONG"] and target_ticker not in INVERSE_BEAR_ETFS:
            quantity = round(quantity * 0.5, 4)
            log_engine(f"Execution Sizing (CAUTION MODE - LONG): {quantity} units")

        if side.upper() in ["BUY", "LONG"]:
            mult, blocked, reason = quality_verdict(strategy_name)
            if blocked:
                log_engine(f"📊 SIGNAL QUALITY: blocked new entry for {strategy_name} — {reason}",
                           level="warning")
                return {"ok": False, "reason": "quality_demoted"}
            if mult != 1.0:
                quantity = round(quantity * mult, 4)
                log_engine(f"📊 SIGNAL QUALITY: {strategy_name} sized x{mult} — {reason}")

    if quantity <= 0:
        return {"ok": False, "reason": "zero_quantity"}

    action = "buy"
    is_exit = side.upper() in ["EXIT", "SELL"]
    
    if is_exit:
        action = "sell"
        # --- 🛡️ SETTLEMENT GUARD: EXIT PROTECTION ---
        # The user trades exclusively with settled cash, meaning a same-day exit of a position
        # bought earlier today is completely safe under Regulation T and does NOT cause a GFV.
        # We track exits here but we no longer block them.
        today_str = datetime.now(EST).strftime("%Y-%m-%d")
        if target_ticker in UNSETTLED_POSITIONS:
            buy_date = UNSETTLED_POSITIONS[target_ticker]
            if buy_date == today_str:
                log_engine(f"🛡️ SETTLEMENT GUARD: Permitted same-day EXIT for {target_ticker}. Asset bought earlier today ({buy_date}) with settled cash.", level="info")

    elif side.upper() == "SHORT" and port == 5006:
        action = "sell" 

    # --- 🛡️ CIRCUIT BREAKER GUARD: NEW ENTRY PROTECTION ---
    if action == "buy" and is_circuit_breaker_active():
        log_engine(f"🛡️ CIRCUIT BREAKER GUARD: Blocked BUY for {target_ticker}. Daily drawdown threshold exceeded.", level="warning")
        return {"ok": False, "reason": "circuit_breaker"}

    # --- 🛡️ SETTLEMENT GUARD: BUY PROTECTION ---
    if action == "buy":
        settled_cash = get_settled_cash(port)
        notional_req = quantity * price
        if settled_cash < notional_req:
            log_engine(f"🛡️ SETTLEMENT GUARD: Blocked BUY for {target_ticker}. Required ${notional_req:.2f}, Settled Available: ${settled_cash:.2f}.", level="warning")
            return {"ok": False, "reason": "insufficient_settled_cash"}

    payload = {
        "type": "stock",
        "action": action,
        "symbol": target_ticker,
        "quantity": float(quantity),
        "order_type": "market"
    }
    
    if port == 5006:
        payload["outsideRth"] = True

    try:
        url = f"http://127.0.0.1:{port}/order"
        
        # Proposal 22: Final Notional Guard
        notional_val = quantity * price
        if notional_val < MIN_NOTIONAL_USD:
            log_engine(f"Execution ABORTED: Notional ${notional_val:.2f} is below MIN_NOTIONAL (${MIN_NOTIONAL_USD}) for {ticker}", level="warning")
            return {"ok": False, "reason": "below_min_notional"}

        resp = requests.post(url, json=payload, timeout=20)
        
        if resp.status_code == 200:
            order_res = resp.json()
            reject_reason = (
                order_res.get('reject_reason') or 
                order_res.get('detail') or 
                (order_res.get('non_field_errors')[0] if order_res.get('non_field_errors') else None)
            )
            order_state = order_res.get('state')
            
            if order_state == 'rejected' or reject_reason:
                reason = reject_reason if reject_reason else "Immediately Rejected by Robinhood"
                msg = f"Order REJECTED: {ticker} -> {reason}"
                log_engine(msg, level="error")
                send_quant_alert(f"⚠️ *ORDER REJECTED*\nAsset: {ticker}\nReason: {reason}")
                return {"ok": False, "reason": f"rejected: {reason}"}

            # Verification: Check if a position actually exists
            time.sleep(2.5)
            verify_pos = get_active_positions(mode=mode)
            if target_ticker in verify_pos or (ticker in INVERSE_MAP and INVERSE_MAP[ticker] in verify_pos):
                log_event(strategy_name, target_ticker, f"EXEC-{side.upper()}", price, is_live=True)
                play_trade_notification()
                
                # Update Unsettled Tracker on Success Buy
                if action == "buy":
                    UNSETTLED_POSITIONS[target_ticker] = datetime.now(EST).strftime("%Y-%m-%d")
                    save_unsettled_tracker()
                    update_active_strategy_cache(target_ticker, strategy_name, "buy")
                    # Task 1: Record Leveraged ETF Entry
                    if target_ticker in LEVERAGED_BTC_ETFS:
                        etf_side = "LONG" if target_ticker == "BITU" else "SHORT"
                        record_etf_entry(target_ticker, exec_price, etf_side, quantity, strategy_name)

                # Remove from Unsettled Tracker on Success Sell
                if action == "sell":
                    UNSETTLED_POSITIONS.pop(target_ticker, None)
                    save_unsettled_tracker()
                    update_active_strategy_cache(target_ticker, strategy_name, "sell")
                    # Task 1: Clear Leveraged ETF Entry
                    if target_ticker in LEVERAGED_BTC_ETFS:
                        remove_etf_position(target_ticker)

                # --- TELEGRAM ALERT ---
                market_label = " [IBKR OVERNIGHT]" if port == 5006 else " [ROBINHOOD CASH]"
                type_label = f"🚀 *LONG OPENED*{market_label}" if side.upper() not in ["SHORT", "SELL", "EXIT"] else f"📉 *SHORT OPENED*{market_label}"
                if side.upper() == "EXIT" or side.upper() == "SELL": type_label = f"🏁 *TRADE CLOSED*{market_label}"
                
                msg = f"{type_label}\nAsset: {ticker} (Target: {target_ticker})\nStrategy: {strategy_name}\nPrice: ${price:.2f}"
                if timeframe: msg += f"\nTimeframe: {timeframe}"
                send_quant_alert(msg)
                return {"ok": True, "qty": quantity, "price": exec_price,
                        "target": target_ticker, "side": side.upper()}
            log_engine(f"Phantom Fill Protection (Audit Failed): {ticker} order accepted but position NOT found in audit.", level="warning")
            return {"ok": False, "reason": "phantom_fill"}
        else:
            error_data = f"Status {resp.status_code}: {resp.text}"
            log_engine(f"Bridge ({port}) Order Rejected: {error_data}", level="error")
            return {"ok": False, "reason": f"bridge_{resp.status_code}"}
    except Exception as e:
        log_engine(f"Bridge ({port}) Execution Error: {e}", level="error")
        return {"ok": False, "reason": f"exception: {e}"}

def process_signal_and_execute(name, ticker, sig, price, is_live, can_execute, active_count, active_positions, timeframe=None, signal_time=None, mode="LIVE_MARKET"):
    """Central logic to handle signal transitions and trigger trades."""
    # 1. STRICT TIMESTAMP FILTER
    if signal_time:
        try:
            # Standardize signal_time to datetime object if it's a string
            if isinstance(signal_time, str):
                try:
                    signal_time = datetime.strptime(signal_time, '%Y-%m-%d %H:%M:%S').replace(tzinfo=EST)
                except ValueError:
                    signal_dt = pd.to_datetime(signal_time)
                    if signal_dt.tzinfo is None:
                        signal_time = signal_dt.tz_localize('UTC').tz_convert(EST).to_pydatetime()
                    else:
                        signal_time = signal_dt.tz_convert(EST).to_pydatetime()
            elif isinstance(signal_time, (pd.Timestamp, datetime)) and signal_time.tzinfo is None:
                signal_time = signal_time.replace(tzinfo=EST)
            elif isinstance(signal_time, pd.Timestamp):
                signal_time = signal_time.to_pydatetime()
                if signal_time.tzinfo is None: signal_time = signal_time.replace(tzinfo=EST)

            now = datetime.now(EST)
            
            # Only allow signals from today
            if signal_time.date() != now.date():
                return None, active_count
                
            # Dynamic Stale Window: Default 30m, but 2.5x timeframe for longer ones
            stale_threshold = 1800 # 30 mins default
            if timeframe:
                if 'h' in timeframe.lower():
                    stale_threshold = 3600 * 2.5 # 2.5 hours for hourly signals
                elif 'd' in timeframe.lower():
                    stale_threshold = 86400 * 1.5 # ~36 hours for daily
                elif 'm' in timeframe.lower():
                    tf_mins = int(re.search(r'\d+', timeframe).group())
                    stale_threshold = (tf_mins * 60) * 2.5 # 2.5x TF

            if (now - signal_time).total_seconds() > stale_threshold and is_live:
                return f"{ticker}-STALE", active_count
        
        except Exception as e:
            log_engine(f"Timestamp Filter Error: {e}", level="warning")

    # 2. NAN PRICE PROTECTION (Proposal 10)
    if price is None or pd.isna(price) or price <= 0:
        return None, active_count

    cache_key = (name, ticker)
    last_sig = SIGNAL_CACHE.get(cache_key)
    last_trade_at = LAST_TRADE_TIME.get(cache_key)
    now_est = datetime.now(EST)
    
    # Check Reversal Cooldown
    cooldown_active = False
    cooldown_limit = REVERSAL_COOLDOWN_SEC
    l_name = name.lower()
    if 'noon-curve' in l_name:
        cooldown_limit = LUNCHBOX_COOLDOWN_SEC
    elif any(x in l_name for x in ['matt-rapid', 'double break', 'volcanix']):
        cooldown_limit = RAPID_STRAT_COOLDOWN_SEC

    if last_trade_at:
        elapsed = (now_est - last_trade_at).total_seconds()
        if elapsed < cooldown_limit:
            cooldown_active = True
            # log_engine(f"Cooldown active: {elapsed:.0f}/{cooldown_limit}s for {name}-{ticker}")
    
    # Check if we hold the asset, its 2x long target (BITU), or its short target (SBIT)
    long_target = LONG_MAP.get(ticker, ticker)
    short_target = INVERSE_MAP.get(ticker, ticker)
    is_held = (
        ticker in active_positions or 
        long_target in active_positions or 
        (short_target != ticker and short_target in active_positions)
    )
    
    status_update = None
    if sig in ["BUY", "SELL", "EXIT", "SHORT", "LONG"]:
        if sig != last_sig:
            # If flipping side, check cooldown
            is_flipping = False
            if last_sig in ["BUY", "LONG"] and sig in ["SELL", "SHORT", "EXIT"]: is_flipping = True
            if last_sig in ["SELL", "SHORT", "EXIT"] and sig in ["BUY", "LONG"]: is_flipping = True
            
            if is_flipping and cooldown_active:
                # log_engine(f"Reversal Cooldown active for {name}-{ticker}. Blocking move to {sig}.")
                return f"{ticker}-COOLDOWN", active_count

            log_event(name, ticker, sig, price, is_live=is_live)
            SIGNAL_CACHE[cache_key] = sig
            status_update = f"{ticker}-{sig} @ {price:.2f}"
    
            if is_live and can_execute:
                # --- RISK ENFORCEMENT: CIRCUIT BREAKER & CAUTION MODE ---
                if (sig in ["BUY", "LONG", "SHORT"]) and not is_held:
                    if is_circuit_breaker_active():
                        log_engine(f"🛡️ CIRCUIT BREAKER ACTIVE: Blocking NEW entry for {ticker} ({name}) due to daily drawdown protection.", level="warning")
                        return f"{ticker}-CIRCUIT_BREAKER", active_count
                    # Volatility Guardrail: Only block LONG trades during CAUTION_MODE. Short trades thrive on volatility.
                    if CAUTION_MODE and (sig in ["BUY", "LONG"]) and ticker not in INVERSE_BEAR_ETFS:
                        log_engine(f"⚠️ CAUTION MODE ACTIVE: Blocking NEW LONG entry for {ticker} ({name}) due to elevated volatility.", level="warning")
                        return f"{ticker}-CAUTION", active_count

                if (sig == "BUY" or sig == "LONG") and not is_held:
                    if active_count < MAX_CONCURRENT_TRADES:
                        # Map to 2x Long (e.g. BITU) if applicable
                        target = LONG_MAP.get(ticker, ticker)
                        execute_trade(name, ticker, sig, price, timeframe=timeframe, mode=mode, target_symbol=target)
                        active_count += 1
                        active_positions[target] = 1.0
                        LAST_TRADE_TIME[cache_key] = now_est
                elif (sig == "EXIT" or sig == "SELL") and is_held:
                    # Determine which symbol we are actually holding (base, 2x long target, or 2x short target)
                    target = None
                    if long_target in active_positions:
                        target = long_target
                    elif short_target != ticker and short_target in active_positions:
                        target = short_target
                    elif ticker in active_positions:
                        target = ticker
                    
                    if target:
                        execute_trade(name, ticker, sig, price, timeframe=timeframe, mode=mode, target_symbol=target)
                        if target in active_positions: del active_positions[target]
                        active_count -= 1
                        LAST_TRADE_TIME[cache_key] = now_est
                elif sig == "SHORT" and not is_held:
                    if active_count < MAX_CONCURRENT_TRADES:
                        # Before going short, ensure no long exists (Reversal Protection)
                        long_held = long_target if long_target in active_positions else (ticker if ticker in active_positions else None)
                        if long_held:
                             execute_trade(name, ticker, "EXIT", price, timeframe=timeframe, mode=mode, target_symbol=long_held)
                             del active_positions[long_held]
                             active_count -= 1
                        
                        # Map to 2x Short (e.g. SBIT) if applicable
                        target = INVERSE_MAP.get(ticker, ticker)
                        execute_trade(name, ticker, "SHORT", price, timeframe=timeframe, mode=mode, target_symbol=target)
                        active_count += 1
                        active_positions[target] = 1.0
                        LAST_TRADE_TIME[cache_key] = now_est
                elif (sig == "BUY" or sig == "LONG") and is_held:
                    # REVERSAL CASE 1: Hold Short/Inverse (e.g. SBIT) -> Want LONG (BITU)
                    if short_target in active_positions and short_target != ticker:
                         log_engine(f"Reversing SHORT to LONG for {ticker} (Closing {short_target})...")
                         execute_trade(name, ticker, "EXIT", price, timeframe=timeframe, mode=mode, target_symbol=short_target)
                         del active_positions[short_target]
                         active_count -= 1
                         LAST_TRADE_TIME[cache_key] = now_est
                         # Re-entry into BITU will happen next cycle
                
                elif sig == "SHORT" and is_held:
                    # REVERSAL CASE 2: Hold LONG (e.g. BITU) -> Want SHORT (SBIT)
                    long_held = long_target if long_target in active_positions else (ticker if ticker in active_positions else None)
                    if long_held:
                         log_engine(f"Reversing LONG to SHORT for {ticker} (Closing {long_held})...")
                         execute_trade(name, ticker, "EXIT", price, timeframe=timeframe, mode=mode, target_symbol=long_held)
                         del active_positions[long_held]
                         active_count -= 1
                         LAST_TRADE_TIME[cache_key] = now_est
                         # Inverse entry into SBIT will happen next cycle
                
    return status_update, active_count


# === SYSTEMATIC DAILY BOOK =================================================
# These strategies keep their own position book keyed by (strategy, ticker),
# so two strategies may hold the same symbol without one's EXIT closing the
# other's position.  They deliberately bypass the global active_positions /
# is_held logic above.

DUAL_MOMENTUM_SECTORS = ["XLK", "XLF", "XLV", "XLE", "XLI", "XLP",
                         "XLU", "XLY", "XLB", "XLRE", "XLC"]
PEAD_CANDIDATES_FILE = os.path.join(DEXTER_ROOT, "cache", "pead_candidates.json")


def _read_market_context():
    """Small, tolerant read of market_context.json (VIX only)."""
    try:
        with open(MARKET_CONTEXT_FILE, 'r') as f:
            ctx = json.load(f)
        return ctx.get('vix', {}).get('value')
    except Exception:
        return None


def _load_pead_candidates():
    try:
        with open(PEAD_CANDIDATES_FILE, 'r') as f:
            data = json.load(f)
        return data.get("candidates", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _slim_close(df):
    """Reduce a cached frame to Close only — keeps pickled IPC payloads small."""
    if df is None or df.empty:
        return None
    try:
        return df[["Close"]].copy()
    except Exception:
        return None


def _build_systematic_context(strat_type):
    """Picklable context for the systematic workers (VIX, sector closes, PEAD)."""
    ctx = {
        "vix": _read_market_context(),
        "today": datetime.now(EST).strftime("%Y-%m-%d"),
    }
    if strat_type == sysd.SIG_TYPE_DUAL_MOM:
        sectors = {}
        for sym in DUAL_MOMENTUM_SECTORS + ["SH"]:
            slim = _slim_close(PERSISTENT_DATA_CACHE.get((sym, "1d")))
            if slim is not None:
                sectors[sym] = slim
        ctx["sectors"] = sectors
        ctx["spy_bytes"] = pickle.dumps(_slim_close(PERSISTENT_DATA_CACHE.get(("SPY", "1d"))))
    if strat_type == sysd.SIG_TYPE_PEAD:
        ctx["pead_candidates"] = _load_pead_candidates()
    return ctx


def _systematic_strategy_names():
    """Registry names that route through the systematic book."""
    names = set()
    try:
        with open(REGISTRY_PATH, 'r') as f:
            registry = json.load(f)
        for cat in ['live_trading', 'active_testing']:
            for s in registry.get(cat, []):
                if _get_strat_type(s['name']) in sysd.SYSTEMATIC_TYPES:
                    names.add(s['name'])
    except Exception:
        pass
    return names


def _process_systematic_signal(name, ticker, sig, price, is_live, can_execute,
                               meta=None, mode="LIVE_MARKET"):
    """Handle BUY/EXIT for a systematic daily strategy. Returns a board status."""
    meta = meta or {}
    key = position_book.book_key(name, ticker)
    book = position_book.load_book()
    held = book.get(key)

    cache_key = (name, ticker)
    last_sig = SIGNAL_CACHE.get(cache_key)

    if sig in ("SHORT", "SELL") and not held:
        return None
    if sig in ("BUY", "LONG") and held:
        # Already positioned; keep the board honest but do not re-enter.
        if last_sig != "BUY":
            SIGNAL_CACHE[cache_key] = "BUY"
            return f"{ticker}-HOLD"
        return None
    if sig == "EXIT" and not held:
        return None

    if not (is_live and can_execute):
        if last_sig != sig:
            SIGNAL_CACHE[cache_key] = sig
            log_event(name, ticker, sig, price, is_live=is_live)
            return f"{ticker}-{sig} @ {price:.2f} (paper)"
        return None

    if sig in ("BUY", "LONG"):
        # NOTE: no CAUTION_MODE veto here.  The VIX Panic strategy exists
        # precisely to buy elevated-volatility dips, so the global guard would
        # disable the edge it is meant to capture.
        res = execute_trade(name, ticker, "BUY", price, timeframe="1d",
                            mode=mode, target_symbol=ticker)
        if not res or not res.get("ok"):
            log_engine(f"Systematic entry blocked for {name}-{ticker}: {res}", level="warning")
            return f"{ticker}-BLOCKED"
        position_book.record_entry(
            name, ticker, res.get("qty", 0), res.get("price", price),
            stop_price=meta.get("stop_price"),
            target_price=meta.get("target_price"),
            max_hold_days=meta.get("max_hold_days"),
            note=meta.get("note", ""),
        )
        SIGNAL_CACHE[cache_key] = "BUY"
        log_event(name, ticker, sig, price, is_live=is_live)
        return f"{ticker}-ENTRY @ {price:.2f}"

    if sig in ("EXIT", "SELL", "SHORT"):
        qty = float(held.get("qty", 0) or 0)
        if qty <= 0:
            position_book.remove_entry(name, ticker)
            return None
        res = execute_trade(name, ticker, "SELL", price, timeframe="1d",
                            mode=mode, target_symbol=ticker, quantity_override=qty)
        if res and res.get("ok"):
            position_book.remove_entry(name, ticker)
            SIGNAL_CACHE[cache_key] = sig
            log_event(name, ticker, sig, price, is_live=is_live)
            return f"{ticker}-EXIT @ {price:.2f}"
        log_engine(f"Systematic exit failed for {name}-{ticker}: {res}", level="warning")
        return f"{ticker}-EXIT_FAILED"

    return None


def _current_marks(mode="LIVE_MARKET"):
    """Symbol -> current price from the broker, falling back to yfinance."""
    marks = {}
    try:
        resp = requests.get("http://127.0.0.1:5005/positions", timeout=10)
        if resp.status_code == 200:
            for sym, pos in resp.json().get("stocks", {}).items():
                try:
                    px = float(pos.get("price") or 0)
                except (TypeError, ValueError):
                    px = 0.0
                if px > 0:
                    marks[sym] = px
    except Exception:
        pass
    return marks


def evaluate_systematic_exits(mode="LIVE_MARKET"):
    """Check every systematic position against its stop/target/time rule."""
    book = position_book.load_book()
    if not book:
        return 0

    marks = _current_marks(mode)
    closed = 0
    for key, rec in list(book.items()):
        strategy = rec.get("strategy")
        ticker = rec.get("ticker")
        if not strategy or not ticker:
            continue

        price = marks.get(ticker)
        if not price:
            price = _position_price(ticker, {})
        if not price:
            continue

        should_exit, reason = position_book.decide_exit(rec, price)
        if not should_exit:
            continue

        qty = float(rec.get("qty", 0) or 0)
        log_engine(f"🚨 SYSTEMATIC EXIT: {strategy} {ticker} — {reason}")
        res = execute_trade(strategy, ticker, "SELL", price, timeframe="1d",
                            mode=mode, target_symbol=ticker, quantity_override=qty)
        if res and res.get("ok"):
            position_book.remove_entry(strategy, ticker)
            closed += 1
            send_quant_alert(
                f"🏁 *SYSTEMATIC EXIT*\nStrategy: {strategy}\nAsset: {ticker}\n"
                f"Reason: {reason}\nPrice: ${price:.2f}\nQty: {qty}"
            )
        else:
            log_engine(f"Systematic exit failed for {strategy}-{ticker}: {res}", level="warning")

    if closed:
        log_engine(f"Systematic exit sweep closed {closed} position(s).")
    return closed

# === PROPOSAL 5: MULTIPROCESSING HELPERS (module-level for pickling) ===

_STRAT_INTERVAL_MAP = {
    'apex':                '1h',
    'apex_short_etf':      '1h',
    's_series':            '1d',
    'btc_liquidity_sweep': '15m',
    'btc_po3':             '5m',
    'btc_rsi_reversion':   '1h',
    'btc_tech_level_ema':  '1h',
    'btc_sfp':             '1h',
    'smc':                 '1h',
    'triple_rsi':          '1d',
    'noon_curve':          '5m',
    'initial_balance':     '5m',
    'london':              '5m',
    'po3':                 '5m',
    'ny_orb':              '1m',
    'wickless':            '1h',
    'db_v3_elite':         '2m',
    'matt_rapid':          '2m',
    'macd':                '1h',
    'gemini_velocity':     '15m',
    'volcanix':            '5m',
    'standard_quant':      '1h',
    'big_d':               '5m',
    'little_d':            '1h',
    'strategy_os':         '1d',
    'sys_ibs3':            '1d',
    'sys_vix_rsi2':        '1d',
    'sys_turn_of_month':   '1d',
    'sys_dual_momentum':   '1d',
    'sys_pead':            '1d',
}

def _get_strat_type(name: str):
    """Map a strategy registry name to its internal strat_type key."""
    n = name.lower()
    # Systematic daily book — checked first so no legacy substring rule can
    # capture these names.
    if 'ibs-3' in n or 'ibs3' in n or 'index dip' in n: return 'sys_ibs3'
    if 'vix panic' in n: return 'sys_vix_rsi2'
    if 'turn-of-month' in n or 'turn of month' in n: return 'sys_turn_of_month'
    if 'dual momentum' in n or 'sector rotation' in n: return 'sys_dual_momentum'
    if 'pead' in n or 'earnings gap drift' in n: return 'sys_pead'
    if 'apex bearish' in n or 'short etf bounce' in n: return 'apex_short_etf'
    if 'apex' in n or 'pivot bounce' in n or 'pivot' in n: return 'apex'
    if any(s in n for s in ['price retreat', 'turnaround tuesday', 'low close ibs', 'demarker', 'high of 10 days', 's1', 's2', 's3', 's4', 's5']): return 's_series'
    if 'liquidity sweep' in n: return 'btc_liquidity_sweep'
    if 'power of 3' in n and 'btc' in n: return 'btc_po3'
    if 'rsi reversion' in n: return 'btc_rsi_reversion'
    if 'tech level' in n or 'ema touch' in n: return 'btc_tech_level_ema'
    if 'sfp' in n or 'swing failure' in n: return 'btc_sfp'
    if 'smc' in n:             return 'smc'
    if 'triple rsi' in n:      return 'triple_rsi'
    if 'noon-curve' in n:      return 'noon_curve'
    if 'initial balance' in n: return 'initial_balance'
    if 'bigd' in n or 'big d' in n: return 'big_d'
    if 'littled' in n or 'little d' in n: return 'little_d'
    if 'po3' in n:             return 'po3'
    if 'ny orb' in n:          return 'ny_orb'
    if 'wickless' in n:        return 'wickless'
    if 'double break v3' in n: return 'db_v3_elite'
    if 'matt-rapid' in n:      return 'matt_rapid'
    if 'macd oscillator' in n: return 'macd_oscillator'
    if 'macd' in n:            return 'macd'
    if 'awesome' in n or 'ao' in n: return 'awesome_oscillator'
    if 'bollinger' in n or 'bb' in n: return 'bollinger_bands'
    if 'shooting star' in n or 'ss' in n: return 'shooting_star'
    if 'dual thrust' in n or 'dt' in n: return 'dual_thrust'
    if 'heikin ashi' in n or 'ha' in n: return 'heikin_ashi'
    if 'gemini velocity' in n: return 'gemini_velocity'
    if 'volcanix' in n:        return 'volcanix'
    if 'standard_quant' in n:  return 'standard_quant'
    if 'nasdaq-day' in n:      return 'nasdaq_day'
    if 'trinity' in n:         return 'trinity'
    if 'dynamic' in n:         return 'dynamic'
    if 'strategy os' in n:     return 'strategy_os'
    return None

def compute_strategy_signal(task: dict) -> dict:
    """
    Picklable top-level worker for ProcessPoolExecutor (Proposal 5).
    Re-imports strategy classes locally — no module-level state shared.
    """
    import sys, pickle as _pickle, os
    import pandas as pd

    _root = r'C:\Users\jmgra\antigravityagents\dexter-quant-agent'
    if _root not in sys.path:
        sys.path.insert(0, _root)

    name       = task['name']
    ticker     = task.get('ticker')
    strat_type = task.get('strat_type')
    is_live    = task.get('is_live', False)
    result_base = {'name': name, 'ticker': ticker, 'is_live': is_live,
                   'strat_type': strat_type,
                   'sig': None, 'price': 0.0, 'tf': None, 'sig_time': None,
                   'stop_price': None, 'target_price': None,
                   'max_hold_days': None, 'note': ''}
    try:
        # Load data (for all non-multi-asset strategies)
        df = _pickle.loads(task['data_bytes']) if task.get('data_bytes') else None

        # --- ANTI-FLICKER BAR TRUNCATION (Proposal 12) ---
        # Trade on CLOSED bars only. This eliminates developing bar noise/spam.
        # `live_bar` is set for daily strategies evaluated in the 15:45-15:59
        # close window, where today's near-final bar IS the signal bar.
        if df is not None and len(df) > 5 and not task.get('live_bar'):
             df = df.iloc[:-1]
        
        # --- TICKER VALIDATION CHECK (Proposal 21: Data Integrity Guard) ---
        if df is not None and ticker is not None:
            if 'TICKER_ID' in df.columns:
                actual_ticker = df['TICKER_ID'].iloc[-1]
                if actual_ticker != ticker:
                    # LOG THIS CRITICAL FAILURE
                    with open(os.path.join(_root, 'CRITICAL_DATA_MISMATCH.log'), 'a') as f:
                        f.write(f"[{datetime.now()}] MISMATCH: {name} expected {ticker} but got {actual_ticker}\n")
                    return {**result_base, 'error': f"Data Mismatch: Task {ticker} vs Data {actual_ticker}"}
        elif df is None and strat_type not in ['noon_curve', 'big_d']:
             return {**result_base, 'error': f"Missing Data for {ticker}"}

        # --- Special case: Noon-Curve (multi-asset) ---
        if strat_type == 'noon_curve':
            from strategies.live_trading.noon_curve_lunchbox.noon_curve_lunchbox import NoonCurveStrategy
            strat = NoonCurveStrategy()
            qqq_df = _pickle.loads(task['qqq_bytes']) if task.get('qqq_bytes') else None
            spy_df = _pickle.loads(task['spy_bytes']) if task.get('spy_bytes') else None
            # Anti-Flicker truncation
            if qqq_df is not None and len(qqq_df) > 5: qqq_df = qqq_df.iloc[:-1]
            if spy_df is not None and len(spy_df) > 5: spy_df = spy_df.iloc[:-1]

            if qqq_df is not None and spy_df is not None:
                cached_dict = {'QQQ': qqq_df.copy(), 'SPY': spy_df.copy()}
                for k, v in cached_dict.items():
                    if v is not None and not v.empty and 'TICK' not in v.columns:
                        v['TICK'] = 0
                sigs = strat.generate_signals(cached_dict)
                if sigs:
                    # Filter for TODAY's signals and take the literal last one
                    s = sigs[-1]
                    # Robust ticker mapping
                    s_ticker = s.get('ticker') or ticker or 'QQQ'
                    return {**result_base, 'ticker': s_ticker,
                            'sig': s['side'].upper(), 'price': s['entry'],
                            'tf': '5m', 'sig_time': s['time']}

        # --- Standard per-asset strategies ---
        elif strat_type == 'smc':
            try:
                from strategies.live_trading.smc_focal_portfolio.smc_focal_portfolio import SmartMoneyStrategy as S
            except Exception:
                # Use absolute import for renamed folder
                from strategies.successful_strategies.btc_success.smc_btc.smc_strategy import SmartMoneyStrategy as S
            strat = S()
            if df is not None and not df.empty:
                df = strat.add_indicators(df)
                df = strat.process_logic(df)
                if not df.empty:
                    r = df.iloc[-1]
                    return {**result_base, 'sig': r.get('entry_signal'), 'price': r.get('bullish_fvg_top', 0) if r.get('entry_signal') == 'BUY' else r.get('bearish_fvg_bottom', 0),
                            'tf': '1h', 'sig_time': df.index[-1]}

        elif strat_type == 'macd':
            from strategies.live_trading.macd_200_bounce.macd_refined_v2 import MACDRefinedFrequency
            strat = MACDRefinedFrequency()
            signals = strat.generate_signals(df)
            if signals:
                last = signals[-1]
                return {**result_base, 'sig': last['type'].replace('_ENTRY', ''),
                        'price': last['entry'], 'tf': '1h', 'sig_time': last['timestamp']}

        elif strat_type == 'standard_quant':
            # Handle S1-S5 using a generic pattern if they support it, 
            # but for now we just acknowledge they are scanned.
            pass

        elif strat_type == 'triple_rsi':
            from strategies.successful_strategies.triple_rsi_mean_reversion import TripleRSIStrategy
            strat = TripleRSIStrategy()
            if df is not None and not df.empty:
                df = strat.add_indicators(df)
                sig, price = strat.get_signal(df)
                return {**result_base, 'sig': sig, 'price': price, 'tf': '1d', 'sig_time': df.index[-1]}

        elif strat_type == 'initial_balance':
            from strategies.live_trading.initial_balance_80.initial_balance_80 import InitialBalance80Strategy
            strat = InitialBalance80Strategy()
            strat.ticker = ticker
            if df is not None:
                signals = strat.generate_signals(df)
                if signals:
                    last = signals[-1]
                    return {**result_base, 'sig': last['side'].upper(),
                            'price': last['entry'], 'tf': '5m', 'sig_time': last['time']}

        elif strat_type == 'london':
            from strategies.live_trading.london_displacement.london_displacement import LondonDisplacementStrategy
            strat = LondonDisplacementStrategy()
            strat.ticker = ticker
            if df is not None:
                signals = strat.generate_signals(df)
                if signals:
                    last = signals[-1]
                    return {**result_base, 'sig': last['side'].upper(),
                            'price': last['entry'], 'tf': '5m', 'sig_time': last['time']}

        elif strat_type == 'po3':
            try:
                from strategies.active_testing.po3_ifvg_strategy import PO3IFVGStrategy
            except:
                import sys, importlib.util
                spec = importlib.util.spec_from_file_location("PO3IFVGStrategy", "C:/Users/jmgra/antigravityagents/dexter-quant-agent/strategies/short-term/po3_ifvg_strategy.py")
                po3_mod = importlib.util.module_from_spec(spec)
                sys.modules["po3_ifvg_strategy"] = po3_mod
                spec.loader.exec_module(po3_mod)
                PO3IFVGStrategy = po3_mod.PO3IFVGStrategy
            strat = PO3IFVGStrategy()
            strat.ticker = ticker
            if df is not None:
                signals = strat.generate_signals(df)
                if signals:
                    last = signals[-1]
                    return {**result_base, 'sig': last['side'].upper(),
                            'price': last['entry'], 'tf': '5m', 'sig_time': last['time']}

        elif strat_type == 'strategy_os':
            from strategies.active_testing.strategy_os import london_breakout_calculation
            if df is not None and not df.empty:
                results = london_breakout_calculation(df)
                if not results.empty:
                    last_sig = results['signals'].iloc[-1]
                    sig_label = "BUY" if last_sig >= 1 else ("SELL" if last_sig <= -1 else None)
                    return {**result_base, 'sig': sig_label, 'price': results['Close'].iloc[-1],
                            'tf': '1d', 'sig_time': results.index[-1]}
            from strategies.active_testing.ny_orb_strategy import NYOrbStrategy
            strat = NYOrbStrategy()
            if df is not None:
                rdf = strat.run_analysis_for_ticker(df)
                if not rdf.empty:
                    last = rdf.iloc[-1]
                    if last['trade_allowed']:
                        return {**result_base, 'sig': last['outcome'].upper(),
                                'price': last['pnl'], 'tf': '1m', 'sig_time': rdf.index[-1]}

        elif strat_type == 'wickless':
            from strategies.active_testing.wickless_candle_strategy import generate_trade_signals
            if df is not None:
                signals = generate_trade_signals(df)
                if signals:
                    last = signals[-1]
                    return {**result_base, 'sig': last['type'].upper(),
                            'price': last['entry'], 'tf': '1h', 'sig_time': last['time']}

        elif strat_type == 'db_v3_elite':
            from strategies.live_trading.double_break_v3_elite.double_break_v3_elite import DoubleBreakV3Elite
            strat = DoubleBreakV3Elite()
            daily_df = _pickle.loads(task['daily_bytes']) if task.get('daily_bytes') else None
            if df is not None and daily_df is not None:
                signals = strat.generate_signals(ticker, {"2m": df, "daily": daily_df})
                if signals:
                    last = signals[-1]
                    return {**result_base, 'sig': last['type'].replace('_ENTRY',''),
                            'price': last['entry'], 'tf': '2m', 'sig_time': last['timestamp']}

        elif strat_type == 'matt_rapid':
            from strategies.live_trading.matt_rapid_trend.matt_rapid_trend import MattRapidTrend
            strat = MattRapidTrend()
            daily_df = _pickle.loads(task['daily_bytes']) if task.get('daily_bytes') else None
            if df is not None and daily_df is not None:
                signals = strat.generate_signals(ticker, {"2m": df, "daily": daily_df})
                if signals:
                    last = signals[-1]
                    return {**result_base, 'sig': last['type'].replace('_ENTRY',''),
                            'price': last['entry'], 'tf': '2m', 'sig_time': last['timestamp']}

        elif strat_type == 'gemini_velocity':
            from strategies.live_trading.gemini_velocity.gemini_velocity_momentum import GeminiVelocityStrategy
            strat = GeminiVelocityStrategy()
            if df is not None:
                signals = strat.generate_signals(ticker, df)
                if signals:
                    last = signals[-1]
                    return {**result_base, 'sig': last['type'].replace('_ENTRY',''),
                            'price': last['entry'], 'tf': '15m', 'sig_time': last['timestamp']}

        elif strat_type == 'volcanix':
            from strategies.live_trading.volcanix_vwap_reclaim.vwap_reclaim_rvol import VWAPReclaimRVOLStrategy
            strat = VWAPReclaimRVOLStrategy(tickers=[ticker])
            if df is not None:
                signals = strat.generate_signals(ticker, df)
                if signals:
                    last = signals[-1]
                    return {**result_base, 'sig': last['type'].replace('_ENTRY', ''),
                            'price': last['entry'], 'tf': '5m', 'sig_time': last['timestamp']}

        elif strat_type == 'big_d':
            from strategies.live_trading.big_d.big_d import BigDStrategy
            strat = BigDStrategy(ticker)
            # Provision multi-timeframe data from task
            df_5m = df 
            df_daily = _pickle.loads(task['daily_bytes']) if task.get('daily_bytes') else None
            df_1h = _pickle.loads(task['h1_bytes']) if task.get('h1_bytes') else None
            
            signal = strat.scan(df=df_5m, df_daily=df_daily, df_1h=df_1h)
            if signal:
                return {**result_base, 'sig': signal['direction'].upper(),
                        'price': signal['entry'], 'tf': '5m', 'sig_time': signal['timestamp']}

        elif strat_type == 'little_d':
            from strategies.live_trading.little_d.little_d import LittleDStrategy
            strat = LittleDStrategy(ticker)
            signal = strat.scan(df=df)
            if signal:
                return {**result_base, 'sig': signal['direction'].upper(),
                        'price': signal['entry'], 'tf': '1h', 'sig_time': signal['timestamp']}

        elif strat_type == 'awesome_oscillator':
            from strategies.active_testing.awesome_oscillator import calculate_ao_signals
            if df is not None:
                signals = calculate_ao_signals(df)
                if not signals.empty:
                    last_sig = signals['awesome signals'].iloc[-1]
                    sig_label = "BUY" if last_sig == 1 else ("SHORT" if last_sig == -1 else None)
                    return {**result_base, 'sig': sig_label, 'price': signals['Close'].iloc[-1], 'tf': '1h', 'sig_time': signals.index[-1]}

        elif strat_type == 'bollinger_bands':
            from strategies.active_testing.bollinger_bands import generate_bb_signals
            if df is not None:
                signals = generate_bb_signals(df)
                if not signals.empty:
                    last_sig = signals['signals'].iloc[-1]
                    sig_label = "BUY" if last_sig == 1 else ("SHORT" if last_sig == -1 else None)
                    return {**result_base, 'sig': sig_label, 'price': signals['Close'].iloc[-1], 'tf': '1h', 'sig_time': signals.index[-1]}

        elif strat_type == 'shooting_star':
            from strategies.active_testing.shooting_star import generate_ss_signals
            if df is not None:
                signals = generate_ss_signals(df)
                if not signals.empty:
                    last_sig = signals['signals'].iloc[-1]
                    sig_label = "BUY" if last_sig == 1 else ("SHORT" if last_sig == -1 else None)
                    return {**result_base, 'sig': sig_label, 'price': signals['Close'].iloc[-1], 'tf': '1h', 'sig_time': signals.index[-1]}

        elif strat_type == 'dual_thrust':
            from strategies.active_testing.dual_thrust import dual_thrust_calculation
            if df is not None:
                signals = dual_thrust_calculation(df)
                if not signals.empty:
                    last_sig = signals['signals'].iloc[-1]
                    sig_label = "BUY" if last_sig == 1 else ("SHORT" if last_sig == -1 else None)
                    return {**result_base, 'sig': sig_label, 'price': signals['Close'].iloc[-1], 'tf': '1h', 'sig_time': signals.index[-1]}

        elif strat_type == 'heikin_ashi':
            from strategies.active_testing.heikin_ashi import generate_ha_signals
            if df is not None:
                signals = generate_ha_signals(df)
                if not signals.empty:
                    last_sig = signals['signals'].iloc[-1]
                    sig_label = "BUY" if last_sig == 1 else ("SHORT" if last_sig == -1 else None)
                    return {**result_base, 'sig': sig_label, 'price': signals['Close'].iloc[-1], 'tf': '1h', 'sig_time': signals.index[-1]}
                    sig_label = "BUY" if last_sig >= 1 else ("SELL" if last_sig <= -1 else None)
                    return {**result_base, 'sig': sig_label, 'price': signals['Close'].iloc[-1], 'tf': '1h', 'sig_time': signals.index[-1]}

        elif strat_type == 'macd_oscillator':
            from strategies.active_testing.macd_oscillator import macd_oscillator_calculation
            if df is not None:
                signals = macd_oscillator_calculation(df)
                if not signals.empty:
                    last_sig = signals['signals'].iloc[-1]
                    sig_label = "BUY" if last_sig == 1 else ("SELL" if last_sig == -1 else None)
                    return {**result_base, 'sig': sig_label, 'price': signals['Close'].iloc[-1], 'tf': '1h', 'sig_time': signals.index[-1]}

        elif strat_type == 'apex_short_etf':
            # Apex Bearish (Short ETF Bounce) — Long-Only S1/S2 Bounce on Inverse ETFs, Exit on PP/R1
            daily_df = _pickle.loads(task['daily_bytes']) if task.get('daily_bytes') else None
            if df is not None and not df.empty and len(df) >= 20 and daily_df is not None and len(daily_df) >= 3:
                import numpy as np
                prev_d = daily_df.iloc[-2] if len(daily_df) >= 2 else daily_df.iloc[-1]
                pp = (float(prev_d['High']) + float(prev_d['Low']) + float(prev_d['Close'])) / 3.0
                r1 = 2 * pp - float(prev_d['Low'])
                s1 = 2 * pp - float(prev_d['High'])
                s2 = pp - (float(prev_d['High']) - float(prev_d['Low']))

                delta = df['Close'].diff()
                gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
                loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
                rsi_s = 100 - (100 / (1 + (gain / (loss + 1e-9))))
                rsi_val = float(rsi_s.iloc[-1])

                tr = pd.concat([
                    df['High'] - df['Low'],
                    (df['High'] - df['Close'].shift()).abs(),
                    (df['Low'] - df['Close'].shift()).abs()
                ], axis=1).max(axis=1)
                atr_val = float(tr.rolling(14).mean().iloc[-1])
                close_val = float(df['Close'].iloc[-1])

                sig = None
                if (abs(close_val - s1) <= 0.5 * atr_val and close_val > s1 and rsi_val < 45) or (abs(close_val - s2) <= 0.5 * atr_val and close_val > s2 and rsi_val < 45):
                    sig = "BUY"
                elif close_val >= pp or (abs(close_val - r1) <= 0.5 * atr_val and close_val < r1 and rsi_val > 55):
                    sig = "EXIT"

                if sig:
                    return {**result_base, 'sig': sig, 'price': close_val, 'tf': '1h', 'sig_time': df.index[-1]}

        elif strat_type == 'apex':
            # Apex Pivot + RSI Bounce (1h timeframe with Daily Pivots)
            daily_df = _pickle.loads(task['daily_bytes']) if task.get('daily_bytes') else None
            if df is not None and not df.empty and len(df) >= 20 and daily_df is not None and len(daily_df) >= 3:
                import numpy as np
                prev_d = daily_df.iloc[-2] if len(daily_df) >= 2 else daily_df.iloc[-1]
                pp = (float(prev_d['High']) + float(prev_d['Low']) + float(prev_d['Close'])) / 3.0
                r1 = 2 * pp - float(prev_d['Low'])
                s1 = 2 * pp - float(prev_d['High'])
                
                delta = df['Close'].diff()
                gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
                loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
                rsi_s = 100 - (100 / (1 + (gain / (loss + 1e-9))))
                rsi_val = float(rsi_s.iloc[-1])
                
                tr = pd.concat([
                    df['High'] - df['Low'],
                    (df['High'] - df['Close'].shift()).abs(),
                    (df['Low'] - df['Close'].shift()).abs()
                ], axis=1).max(axis=1)
                atr_val = float(tr.rolling(14).mean().iloc[-1])
                close_val = float(df['Close'].iloc[-1])
                
                sig = None
                if abs(close_val - s1) <= 0.5 * atr_val and close_val > s1 and rsi_val < 45:
                    sig = "BUY"
                elif abs(close_val - r1) <= 0.5 * atr_val and close_val < r1 and rsi_val > 55:
                    sig = "SHORT"
                
                if sig:
                    return {**result_base, 'sig': sig, 'price': close_val, 'tf': '1h', 'sig_time': df.index[-1]}

        elif strat_type == 's_series':
            # S1-S5 Daily Mean Reversion on SPY / QQQ
            if df is not None and len(df) >= 25:
                import numpy as np
                close = df['Close']
                high = df['High']
                low = df['Low']
                ibs = (close - low) / ((high - low) + 1e-9)
                prev_high = high.shift(1)
                
                c_val = float(close.iloc[-1])
                ibs_val = float(ibs.iloc[-1])
                prev_h_val = float(prev_high.iloc[-1])
                
                sig = None
                name_l = name.lower()
                if 'price retreat' in name_l or 's1' in name_l:
                    hl_range = high - low
                    avg_hl = float(hl_range.rolling(25).mean().iloc[-1])
                    roll_high = float(high.rolling(10).max().iloc[-1])
                    if c_val < (roll_high - avg_hl) and ibs_val < 0.3:
                        sig = "BUY"
                elif 'turnaround' in name_l or 's2' in name_l:
                    dow = df.index[-1].dayofweek
                    if dow == 0 and c_val < float(close.iloc[-2]) and float(close.iloc[-2]) < float(close.iloc[-3]):
                        sig = "BUY"
                elif 'low close' in name_l or 's3' in name_l:
                    lowest_5 = float(low.shift(1).rolling(5).min().iloc[-1])
                    if c_val < lowest_5 and ibs_val < 0.25:
                        sig = "BUY"
                elif 'demarker' in name_l or 's4' in name_l:
                    demax = np.where(high > prev_high, high - prev_high, 0.0)
                    demin = np.where(low.shift(1) > low, low.shift(1) - low, 0.0)
                    sma_demax = float(pd.Series(demax, index=df.index).rolling(5).mean().iloc[-1])
                    sma_demin = float(pd.Series(demin, index=df.index).rolling(5).mean().iloc[-1])
                    demarker = 100 * (sma_demax / (sma_demax + sma_demin + 1e-9))
                    if demarker < 10:
                        sig = "BUY"
                elif 'high of 10' in name_l or 's5' in name_l:
                    highest_10 = float(high.shift(1).rolling(10).max().iloc[-1])
                    if float(high.iloc[-1]) > highest_10 and ibs_val < 0.15:
                        sig = "BUY"
                
                # Exit condition: Close > Previous Day High
                if c_val > prev_h_val and sig is None:
                    sig = "EXIT"
                
                # Inverse Short Extension: Overbought hedge into SH / PSQ
                if sig is None and ibs_val > 0.85:
                    sig = "SHORT"
                
                if sig:
                    return {**result_base, 'sig': sig, 'price': c_val, 'tf': '1d', 'sig_time': df.index[-1]}

        elif strat_type in ['btc_liquidity_sweep', 'btc_po3', 'btc_rsi_reversion', 'btc_tech_level_ema', 'btc_sfp']:
            # Bitcoin Leveraged ETF Strategies (BITU / SBIT)
            if df is not None and len(df) >= 20:
                close = df['Close']
                high = df['High']
                low = df['Low']
                open_p = df['Open']
                vol = df['Volume']
                
                ema20 = close.ewm(span=20, adjust=False).mean()
                ema50 = close.ewm(span=50, adjust=False).mean()
                vol_ma = vol.rolling(20).mean()
                vol_surge = (float(vol.iloc[-1]) > float(vol_ma.iloc[-1]) * 1.1) if not vol_ma.empty else True
                
                c_val = float(close.iloc[-1])
                c_prev = float(close.iloc[-2])
                sig = None
                
                if strat_type == 'btc_liquidity_sweep':
                    sw_h = float(high.iloc[-16:-1].max())
                    sw_l = float(low.iloc[-16:-1].min())
                    if float(low.iloc[-1]) < sw_l and c_val > sw_l:
                        sig = "BUY"
                    elif float(high.iloc[-1]) > sw_h and c_val < sw_h:
                        sig = "SHORT"
                elif strat_type == 'btc_po3':
                    if c_prev < float(ema20.iloc[-2]) and c_val > float(ema20.iloc[-1]) and c_val > float(ema50.iloc[-1]):
                        sig = "BUY"
                    elif c_prev > float(ema20.iloc[-2]) and c_val < float(ema20.iloc[-1]) and c_val < float(ema50.iloc[-1]):
                        sig = "SHORT"
                elif strat_type == 'btc_rsi_reversion':
                    delta = close.diff()
                    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
                    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
                    rsi_series = 100 - (100 / (1 + (gain / (loss + 1e-9))))
                    rsi = float(rsi_series.iloc[-1])
                    if rsi < 36 and c_val > float(open_p.iloc[-1]) and c_prev < float(open_p.iloc[-2]):
                        sig = "BUY"
                    elif rsi > 64 and c_val < float(open_p.iloc[-1]) and c_prev > float(open_p.iloc[-2]):
                        sig = "SHORT"
                elif strat_type == 'btc_tech_level_ema':
                    if float(low.iloc[-1]) <= float(ema20.iloc[-1]) and c_val > float(ema20.iloc[-1]) and c_val > float(ema50.iloc[-1]) and vol_surge:
                        sig = "BUY"
                    elif float(high.iloc[-1]) >= float(ema20.iloc[-1]) and c_val < float(ema20.iloc[-1]) and c_val < float(ema50.iloc[-1]) and vol_surge:
                        sig = "SHORT"
                elif strat_type == 'btc_sfp':
                    sw_h = float(high.iloc[-11:-1].max())
                    sw_l = float(low.iloc[-11:-1].min())
                    if float(low.iloc[-1]) < sw_l and c_val > sw_l and vol_surge:
                        sig = "BUY"
                    elif float(high.iloc[-1]) > sw_h and c_val < sw_h and vol_surge:
                        sig = "SHORT"
                
                if sig:
                    return {**result_base, 'sig': sig, 'price': c_val, 'tf': _STRAT_INTERVAL_MAP.get(strat_type, '1h'), 'sig_time': df.index[-1]}

        elif strat_type in sysd.SYSTEMATIC_TYPES:
            if df is None or df.empty:
                return result_base

            ctx_raw = {}
            if task.get('context_bytes'):
                try:
                    ctx_raw = _pickle.loads(task['context_bytes'])
                except Exception:
                    ctx_raw = {}

            sectors = {}
            for sym, blob in (ctx_raw.get('sectors') or {}).items():
                try:
                    sectors[sym] = _pickle.loads(blob) if isinstance(blob, (bytes, bytearray)) else blob
                except Exception:
                    continue
            spy_df = None
            if ctx_raw.get('spy_bytes'):
                try:
                    spy_df = _pickle.loads(ctx_raw['spy_bytes'])
                except Exception:
                    spy_df = None

            today = datetime.now(EST).date()
            ctx = {
                'vix': ctx_raw.get('vix'),
                'today': today.strftime('%Y-%m-%d'),
                'sectors': sectors,
                'spy_df': spy_df,
                'pead_candidates': ctx_raw.get('pead_candidates') or {},
            }
            out = sysd.evaluate(strat_type, ticker, name, df, ctx)

            # Price-triggered entries must not act on a stale bar.  Calendar-
            # driven strategies (turn-of-month, dual momentum) derive their
            # trigger from the bars themselves, so a one-day data lag is safe.
            if (out and out.get('sig') in ('BUY', 'LONG')
                    and strat_type in (sysd.SIG_TYPE_IBS3, sysd.SIG_TYPE_VIX_RSI2,
                                       sysd.SIG_TYPE_PEAD)
                    and df.index[-1].date() != today):
                return {**result_base, 'note': 'daily bar stale — entry suppressed'}

            if out:
                return {**result_base, **out}
            return result_base

        elif strat_type == 'standard_quant':
            return result_base


    except Exception as exc:
        return {**result_base, 'error': str(exc)}

    return result_base

# === END PROPOSAL 5 HELPERS ===

def run_alpha_autotrader(mode="LIVE_MARKET"):
    import concurrent.futures

    log_engine(f"--- DEXTER ALPHA ENGINE: SYNC [{mode}] ---")
    can_execute = (mode == "LIVE_MARKET")

    # --- Proposal 9: Start async board renderer thread (once per process) ---
    _start_board_thread()

    # Ensure every registry strategy has a row (non-blocking)
    refresh_strategy_board()

    # --- Evaluate Leveraged ETF Bracket Exits (2% SL / 4% TP / Max Hold) & Circuit Breaker ---
    try:
        evaluate_etf_exits_and_circuit_breaker(mode=mode)
    except Exception as _cb_err:
        log_engine(f"Error evaluating ETF exits / circuit breaker: {_cb_err}", level="error")

    # Systematic book stops/targets/time exits (no-op when the book is empty)
    if mode == "LIVE_MARKET":
        try:
            evaluate_systematic_exits(mode=mode)
        except Exception as _sys_err:
            log_engine(f"Error evaluating systematic exits: {_sys_err}", level="error")

    # --- Proposal 6: Load warm cache if fresh (< 90 min old) ---
    _warm_cache_maxage = 5400
    if os.path.exists(WARM_CACHE_FILE):
        try:
            with open(WARM_CACHE_FILE, 'rb') as _wf:
                _warm_data = pickle.load(_wf)
            _cache_time = datetime.fromisoformat(_warm_data['timestamp'])
            _age_secs = (datetime.now(EST) - _cache_time.replace(tzinfo=EST)).total_seconds()
            if _age_secs < _warm_cache_maxage:
                _loaded = 0
                for _k, _v in _warm_data['cache'].items():
                    if _k not in PERSISTENT_DATA_CACHE:
                        PERSISTENT_DATA_CACHE[_k] = _v
                        _loaded += 1
                log_engine(f"Hot Cache Loaded: {_loaded} pairs from warm-up agent ({_age_secs/60:.0f} min old).")
            else:
                log_engine(f"Warm cache stale ({_age_secs/60:.0f} min) — skipping.", level="warning")
        except Exception as _e:
            log_engine(f"Warm cache load failed: {_e}", level="warning")

    # --- Proposal 7: Load Market Intelligence Context ---
    global CAUTION_MODE
    CAUTION_MODE = False
    if os.path.exists(MARKET_CONTEXT_FILE):
        try:
            with open(MARKET_CONTEXT_FILE, 'r') as _cf:
                _context = json.load(_cf)
            _vix = _context.get('vix', {})
            _rot = _context.get('sectors', {})
            _caution = _context.get('caution_mode', False)
            
            _msg = f"Macro Context: VIX {_vix.get('value')} ({_vix.get('risk_level')}) | Rotation: {_rot.get('rotation')}"
            if _caution:
                CAUTION_MODE = True
                log_engine(f"⚠️ CALLED CAUTION: {_msg}", level="warning")
            else:
                log_engine(_msg)
        except Exception as _e:
            log_engine(f"Market Context load failed: {_e}", level="warning")

    # --- Proposal 8: Load Signal Quality context ---
    global SIGNAL_QUALITY
    SIGNAL_QUALITY = {}
    if os.path.exists(SIGNAL_QUALITY_FILE):
        try:
            with open(SIGNAL_QUALITY_FILE, 'r') as _sf:
                _data = json.load(_sf)
            SIGNAL_QUALITY = _data.get('strategies', {})
            log_engine(f"Feedback Loop: Analyzed {len(SIGNAL_QUALITY)} strategies for win-rate context.")
        except Exception as _e:
            log_engine(f"Signal Quality load failed: {_e}", level="warning")
    
    # --- Proposal 13: Load Persistent Signal Cache ---
    global SIGNAL_CACHE
    if os.path.exists(SIGNAL_CACHE_FILE):
        try:
            with open(SIGNAL_CACHE_FILE, 'rb') as _sf:
                SIGNAL_CACHE = pickle.load(_sf)
            log_engine(f"Signal Cache Restored: {len(SIGNAL_CACHE)} items.")
        except Exception as _e:
            log_engine(f"Signal Cache restoration failed: {_e}", level="warning")
            
    global LAST_TRADE_TIME
    if os.path.exists(LAST_TRADE_FILE):
        try:
            with open(LAST_TRADE_FILE, 'rb') as _tf:
                LAST_TRADE_TIME = pickle.load(_tf)
        except Exception as _e:
            log_engine(f"Last Trade Time restoration failed: {_e}", level="warning")
    
    try:
        with open(REGISTRY_PATH, 'r') as f:
            registry = json.load(f)
    except Exception as e:
        log_engine(f"Critical Registry Error: {e}", level="error")
        return

    # Strategy Inits
    smc_strat = SmartMoneyStrategy() if SmartMoneyStrategy else None
    trsi_strat = TripleRSIStrategy() if TripleRSIStrategy else None
    noon_strat = NoonCurveStrategy() if NoonCurveStrategy else None
    ib80_strat = InitialBalance80Strategy() if InitialBalance80Strategy else None
    po3_strat = PO3IFVGStrategy() if PO3IFVGStrategy else None
    orb_strat = NYOrbStrategy() if NYOrbStrategy else None
    ld_strat = LondonDisplacementStrategy() if LondonDisplacementStrategy else None

    def parse_period_to_days(p):
        if not p or not isinstance(p, str): return 0
        match = re.search(r'(\d+)([dmy])', p.lower())
        if not match: return 1
        val, unit = int(match.group(1)), match.group(2)
        if unit == 'y': return val * 365
        if unit == 'm': return val * 30
        return val

    # --- 🚀 PARALLEL DATA COORDINATOR ---
    data_tasks = {} # (ticker, interval) -> max_period
    for category in ['live_trading', 'active_testing']:
        for strat in registry.get(category, []):
            name, assets = strat['name'], strat['assets']
            strat_kind = _get_strat_type(name)
            for ticker in assets:
                t, i, p = ticker, "1h", "5d" # Default
                if strat_kind in sysd.SYSTEMATIC_TYPES:
                    # Daily OHLCV. PEAD only needs ~30 sessions; the rest need
                    # a 200SMA plus the 126-day momentum window.
                    lookback = "6mo" if strat_kind == sysd.SIG_TYPE_PEAD else "2y"
                    key = (ticker, "1d")
                    data_tasks[key] = max(data_tasks.get(key, "1d"), lookback,
                                          key=parse_period_to_days)
                    if strat_kind == sysd.SIG_TYPE_DUAL_MOM:
                        key_spy = ("SPY", "1d")
                        data_tasks[key_spy] = max(data_tasks.get(key_spy, "1d"), "2y",
                                                  key=parse_period_to_days)
                    continue
                if "Apex" in name or "Pivot" in name:
                    for ni, np_ in [("1h", "30d"), ("1d", "60d")]:
                        key = (ticker, ni)
                        data_tasks[key] = max(data_tasks.get(key, "1d"), np_, key=parse_period_to_days)
                    continue
                elif any(s in name for s in ["Price Retreat", "Turnaround Tuesday", "Low Close IBS", "DeMarker", "High of 10 Days"]):
                    key = (ticker, "1d")
                    data_tasks[key] = max(data_tasks.get(key, "1d"), "60d", key=parse_period_to_days)
                    continue
                elif "Liquidity Sweep" in name: t, i, p = ticker, "15m", "15d"
                elif "Power of 3" in name: t, i, p = ticker, "5m", "10d"
                elif "RSI Reversion" in name: t, i, p = ticker, "1h", "30d"
                elif "Tech Level" in name or "EMA Touch" in name: t, i, p = ticker, "1h", "30d"
                elif "SFP" in name or "Swing Failure" in name: t, i, p = ticker, "1h", "30d"
                elif "SMC" in name: t, i, p = ticker, "1h", "10d"
                elif "Triple RSI" in name: t, i, p = ticker, "1d", "2y"
                elif "Noon-Curve" in name: 
                    for nt in [ticker, "SPY", "QQQ"]:
                        key = (nt, "5m")
                        data_tasks[key] = max(data_tasks.get(key, "1d"), "5d", key=parse_period_to_days)
                    continue
                elif "Initial Balance" in name: t, i, p = ticker, "5m", "5d"
                elif "London" in name: t, i, p = ticker, "5m", "5d"
                elif "PO3" in name: t, i, p = ticker, "5m", "5d"
                elif "NY ORB" in name: t, i, p = ticker, "1m", "5d"
                elif "Wickless" in name: t, i, p = ticker, "1h", "5d"
                elif "MACD 200" in name: t, i, p = ticker, "1h", "100d"
                elif "Gemini Velocity" in name: t, i, p = ticker, "15m", "30d"
                elif "Volcanix" in name: t, i, p = ticker, "5m", "15d"
                elif "BigD" in name:
                    for ni, np_ in [("5m", "10d"), ("1h", "10d"), ("1d", "30d")]:
                        key = (ticker, ni)
                        data_tasks[key] = max(data_tasks.get(key, "1d"), np_, key=parse_period_to_days)
                    continue
                elif "LittleD" in name: t, i, p = ticker, "1h", "60d"
                elif "Double Break V3" in name or "Matt-Rapid" in name:
                    for nt, ni, np_ in [(ticker, "2m", "60d"), (ticker, "1d", "70d")]:
                        key = (nt, ni)
                        data_tasks[key] = max(data_tasks.get(key, "1d"), np_, key=parse_period_to_days)
                    continue
                
                key = (t, i)
                data_tasks[key] = max(data_tasks.get(key, "1d"), p, key=parse_period_to_days)

    def fetch_worker(task_info):
        (t, i), p = task_info
        cache_key = (t, i)
        global PERSISTENT_DATA_CACHE
        
        try:
            with CACHE_LOCK:
                cached_df = PERSISTENT_DATA_CACHE.get(cache_key)
            
            use_prepost = (i in ["1m", "2m", "5m"])
            
            if cached_df is not None and not cached_df.empty:
                new_df = yf.download(t, period="2d", interval=i, progress=False, auto_adjust=True, prepost=use_prepost)
                if new_df is not None and not new_df.empty:
                    if isinstance(new_df.columns, pd.MultiIndex): new_df.columns = new_df.columns.get_level_values(0)
                    new_df = new_df.loc[:, ~new_df.columns.duplicated()]
                    if new_df.index.tz is None: new_df = new_df.tz_localize('UTC').tz_convert(EST)
                    else: new_df = new_df.tz_convert(EST)
                    
                    combined = pd.concat([cached_df, new_df])
                    combined = combined.loc[~combined.index.duplicated(keep='last')]
                    combined = combined.sort_index()
                    combined['TICKER_ID'] = t
                    if len(combined) > CACHE_MAX_SIZE: combined = combined.iloc[-CACHE_MAX_SIZE:]
                    
                    with CACHE_LOCK:
                        PERSISTENT_DATA_CACHE[cache_key] = combined
                    return cache_key, combined
            
            # Fresh Fetch
            df = yf.download(t, period=p, interval=i, progress=False, auto_adjust=True, prepost=use_prepost, threads=False)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df = df.loc[:, ~df.columns.duplicated()]
                if df.index.tz is None: df = df.tz_localize('UTC').tz_convert(EST)
                else: df = df.tz_convert(EST)
                df['TICKER_ID'] = t
                
                with CACHE_LOCK:
                    PERSISTENT_DATA_CACHE[cache_key] = df.copy() # Store copy
                return cache_key, df
        except Exception as e:
            log_engine(f"Fetch failed for {t} @ {i}: {e}", level="error")
        return cache_key, None

    # --- 🚀 SEQUENTIAL DATA COORDINATOR (Fix for Data Contamination) ---
    # Sequential fetch is slower but prevents yfinance session buffer collisions.
    unique_tasks = list(data_tasks.items())
    log_engine(f"Starting Sequential Fetch for {len(unique_tasks)} tasks...")
    for task in unique_tasks:
        fetch_worker(task)
        time.sleep(0.05) # Tiny breather to prevent API throttling

    # --- Portfolio State (must stay in main process) ---
    # --- Portfolio State (Dismantled Blockage) ---
    import threading
    def background_sync():
        global GLOBAL_ACTIVE_POSITIONS
        try:
            positions = get_active_positions(mode=mode)
            GLOBAL_ACTIVE_POSITIONS.clear()
            GLOBAL_ACTIVE_POSITIONS.update(positions)
            log_engine(f"Portfolio Sync: {len(positions)}/{MAX_CONCURRENT_TRADES} open.")
            update_portfolio_display(positions)
        except Exception as e:
            log_engine(f"Background Sync Error: {e}", level="warning")

    # Launch sync without blocking the main engine
    threading.Thread(target=background_sync, daemon=True).start()
    
    # Use cached positions for the immediate scan threshold
    active_positions = GLOBAL_ACTIVE_POSITIONS.copy()
    active_count = len(active_positions)

    # --- ⚡ PARALLEL EXECUTION ENGINE (Proposal 5) ---
    import concurrent.futures as _cf

    # Step 1: Build task list (apply window filter BEFORE spawning workers)
    tasks = []
    sleeping_strats = []

    for category in ['live_trading', 'active_testing']:
        is_live = (category == 'live_trading')
        for strat in registry.get(category, []):
            name   = strat['name']
            assets = strat['assets']
            window = strat.get('active_window')

            if not is_in_window(window):
                sleeping_strats.append(name)
                continue

            strat_type = _get_strat_type(name)
            if strat_type is None:
                log_engine(f"Unknown strat_type for '{name}' — skipping.", level="warning")
                continue

            interval = _STRAT_INTERVAL_MAP.get(strat_type, '1h')

            if strat_type == 'noon_curve':
                qqq_df = PERSISTENT_DATA_CACHE.get(("QQQ", "5m"))
                spy_df = PERSISTENT_DATA_CACHE.get(("SPY", "5m"))
                tasks.append({
                    'name': name, 'ticker': None, 'strat_type': 'noon_curve',
                    'is_live': is_live,
                    'qqq_bytes': pickle.dumps(qqq_df) if qqq_df is not None else None,
                    'spy_bytes': pickle.dumps(spy_df) if spy_df is not None else None,
                })
            else:
                for ticker in assets:
                    df = PERSISTENT_DATA_CACHE.get((ticker, interval))
                    if df is not None and mode not in ["TEST", "OFFLINE"]:
                        # Proposal 16: Dynamic Stale Tolerance (60m for scalps, 480m for hourly/swing)
                        stale_limit = 3600 # 60 mins default
                        if interval == "1h": stale_limit = 28800 # 8 hours
                        elif interval == "1d": stale_limit = 129600 # 36 hours
                        elif interval == "15m": stale_limit = 7200 # 2 hours
                        
                        last_ts = df.index[-1].timestamp()
                        if (time.time() - last_ts) > stale_limit:
                            log_engine(f"Warm cache stale ({(time.time()-last_ts)/60:.0f} min) for {ticker} — skipping.", level="warning")
                            df = None

                    daily_df = PERSISTENT_DATA_CACHE.get((ticker, "1d")) if (interval in ["2m", "5m"] or strat_type in ['apex', 'apex_short_etf', 's_series']) else None
                    h1_df = PERSISTENT_DATA_CACHE.get((ticker, "1h")) if strat_type == 'big_d' else None

                    live_bar = False
                    context_bytes = None
                    if strat_type in sysd.SYSTEMATIC_TYPES:
                        # Daily strategies are evaluated on the near-final bar
                        # in their own window; everywhere else they would be
                        # reading a partially formed bar.
                        live_bar = (is_in_window("15:45-15:59")
                                    or strat_type == sysd.SIG_TYPE_PEAD)
                        context_bytes = pickle.dumps(_build_systematic_context(strat_type))

                    tasks.append({
                        'name': name, 'ticker': ticker, 'strat_type': strat_type,
                        'is_live': is_live,
                        'data_bytes': pickle.dumps(df.copy()) if df is not None else None,
                        'daily_bytes': pickle.dumps(daily_df.copy()) if daily_df is not None else None,
                        'h1_bytes': pickle.dumps(h1_df.copy()) if h1_df is not None else None,
                        'live_bar': live_bar,
                        'context_bytes': context_bytes,
                    })

    # Mark sleeping strategies on board immediately
    for sname in sleeping_strats:
        update_board_signal(sname, "SLEEP")

    log_engine(f"Dispatch: {len(tasks)} tasks across {min(len(tasks), 4)} workers | {len(sleeping_strats)} sleeping.")

    # Step 2: Parallel dispatch
    results = []
    if tasks:
        max_w = max(1, min(len(tasks), 4))
        with _cf.ProcessPoolExecutor(max_workers=max_w) as pool:
            futures = {pool.submit(compute_strategy_signal, t): t for t in tasks}
            for future in _cf.as_completed(futures):
                orig_task = futures[future]
                try:
                    results.append(future.result(timeout=30))
                except Exception as exc:
                    log_engine(f"Worker crashed [{orig_task['name']}-{orig_task.get('ticker')}]: {exc}", level="error")
                    results.append({'name': orig_task['name'], 'ticker': orig_task.get('ticker'),
                                    'is_live': orig_task.get('is_live', False),
                                    'sig': None, 'price': 0.0, 'tf': None, 'sig_time': None})

    # Step 3: Aggregate signals per strategy name (track latest per strategy)
    latest_signals: dict = {}
    signal_audit = {"total": 0, "stale": 0}

    for result in results:
        name     = result['name']
        ticker   = result.get('ticker', '')
        sig      = result.get('sig')
        price    = result.get('price', 0.0)
        tf       = result.get('tf')
        sig_time = result.get('sig_time')
        is_live  = result.get('is_live', False)
        error    = result.get('error')

        if error:
            log_engine(f"Strategy error [{name}-{ticker}]: {error}", level="error")

        # SIGNAL AUDIT TRACKING
        is_stale = False
        if sig and result.get('strat_type') in sysd.SYSTEMATIC_TYPES:
            update = _process_systematic_signal(
                name, ticker, sig, price, is_live, can_execute,
                meta={
                    'stop_price': result.get('stop_price'),
                    'target_price': result.get('target_price'),
                    'max_hold_days': result.get('max_hold_days'),
                    'note': result.get('note', ''),
                },
                mode=mode,
            )
            if update:
                latest_signals[name] = update
        elif sig:
            update, active_count = process_signal_and_execute(
                name, ticker, sig, price, is_live, can_execute,
                active_count, active_positions,
                timeframe=tf, signal_time=sig_time, mode=mode
            )
            if update:
                latest_signals[name] = update
                signal_audit["total"] += 1
                if "-STALE" in str(update):
                    signal_audit["stale"] += 1

        if name not in latest_signals:
            latest_signals[name] = "None"
    
    # ALERT ON MASS STALE (Proposal 22: Signal Audit)
    if signal_audit["total"] > 10:
        stale_rate = signal_audit["stale"] / signal_audit["total"]
        if stale_rate >= 0.9:
            log_engine(f"🚨 CRITICAL SIGNAL AUDIT: {stale_rate*100:.0f}% of signals REJECTED AS STALE. Check system time or yfinance connectivity.", level="error")
            update_board_status("🚨 DATA STALE: 90%+ REJECTION", persistent=True)

    # Step 4: Update board for every registered strategy
    for category in ['live_trading', 'active_testing']:
        for strat in registry.get(category, []):
            sname = strat['name']
            update_board_signal(sname, latest_signals.get(sname, "None"))

    # --- Proposal 13: Save Signal Cache ---
    try:
        os.makedirs(os.path.dirname(SIGNAL_CACHE_FILE), exist_ok=True)
        with open(SIGNAL_CACHE_FILE, 'wb') as _sf:
            pickle.dump(SIGNAL_CACHE, _sf)
    except Exception as _e:
        log_engine(f"Signal Cache save failed: {_e}", level="warning")

    try:
        with open(LAST_TRADE_FILE, 'wb') as _tf:
            pickle.dump(LAST_TRADE_TIME, _tf)
    except Exception as _e:
        log_engine(f"Last Trade Time save failed: {_e}", level="warning")

    # Final flush: write all buffered logs to disk in one batch
    flush_log_buffer()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args, unknown = parser.parse_known_args()
    
    if args.test:
        run_alpha_autotrader(mode="TEST_RUN")
    else:
        run_alpha_autotrader()
