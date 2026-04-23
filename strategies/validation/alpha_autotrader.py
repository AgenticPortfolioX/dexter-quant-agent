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
MAX_CONCURRENT_TRADES = 4
POSITION_SIZE_USD = 75.0
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

# Inverse Mapping for Shorting on Robinhood (Bearish Proxies for Cash Accounts)
INVERSE_MAP = {
    "SPY": "SH",     # Inverse S&P 500
    "QQQ": "PSQ",    # Inverse Nasdaq 100
    "IWM": "RWM",    # Inverse Russell 2000
    "DIA": "DOG",    # Inverse Dow 30
    "XBI": "LABD",   # 3x Inverse Biotech
    "TSLA": "TSLQ",  # Inverse Tesla
    "NVDA": "NVDS",  # Inverse Nvidia
    "AAPL": "AAPD",  # 2x Inverse Apple
    "AMZN": "AMZS",  # Inverse Amazon
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
}

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
    print(formatted)
    with LOG_BUFFER_LOCK:
        LOG_BUFFER.append(formatted)
        should_flush = len(LOG_BUFFER) >= LOG_BUFFER_LIMIT
    if should_flush:
        flush_log_buffer()

def send_quant_alert(message):
    """Sends an alert to the designated Slack Quant channel."""
    return send_dexter_slack_alert(message)

def close_short_term_positions(timeframes=['1m', '5m', '10m']):
    """Fetches all open positions and closes those that meet the 'short-term' criteria."""
    log_engine("🌅 Starting EOD Close of Short-Term Positions...")
    try:
        # 1. Fetch current positions from bridge
        resp = requests.get("http://localhost:5005/positions", timeout=15)
        if resp.status_code != 200:
            log_engine(f"Error fetching positions: {resp.text}", level="error")
            return
        
        data = resp.json()
        stocks = data.get("stocks", {})
        
        # 2. Filter and Close
        registry = {}
        if os.path.exists(REGISTRY_PATH):
            with open(REGISTRY_PATH, 'r') as f:
                registry = json.load(f)
        
        short_term_strats = []
        # Find strategies that are 1m, 5m, 10m based on registry frequency
        for cat in ['live_trading', 'active_testing']:
            for s in registry.get(cat, []):
                freq = s.get('frequency', 60)
                if freq <= 600: # 10 minutes or less
                    short_term_strats.append(s['name'])
        
        # Also include Volcanix explicitly as per user request
        short_term_strats.append("Volcanix (VWAP Reclaim)")

        closed_count = 0
        for ticker, pos in stocks.items():
            qty = float(pos.get('quantity', 0))
            if qty <= 0: continue
            
            # We exit if the ticker is associated with a short-term strategy
            # or if it was bought today (checking unsettled_positions for a hint)
            should_close = False
            for cat in ['live_trading', 'active_testing']:
                for s in registry.get(cat, []):
                    if s['name'] in short_term_strats and ticker in s.get('assets', []):
                        should_close = True
                        break
                if should_close: break
                
            if should_close:
                log_engine(f"Closing EOD Position: {ticker} ({qty} units)")
                # Fetch recent price for logging
                hist = yf.Ticker(ticker).history(period="1d")
                price = hist['Close'].iloc[-1] if not hist.empty else 0
                execute_trade("EOD Stop", ticker, "SELL", price)
                closed_count += 1
                
        log_engine(f"EOD Cleanup Complete. Closed {closed_count} positions.")
        send_quant_alert(f"🌅 *EOD CLEANUP*\nClosed {closed_count} short-term positions.")
        
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
        with open(target_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
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
        
        with open(target_path, "w", encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        log_engine(f"Portfolio Display Update Failed: {e}", level="error")

def refresh_strategy_board():
    """Proactively ensures all strategies in registry are on the board with correct status."""
    try:
        if not os.path.exists(REGISTRY_PATH) or not os.path.exists(STRATEGY_BOARD_PATH):
            return

        with open(REGISTRY_PATH, 'r') as f:
            registry = json.load(f)
        
        # We just want to make sure they exist, so we'll call update_board_signal with "None"
        # which will refresh the Status column without touching signals.
        for strat in registry.get("live_trading", []):
            update_board_signal(strat["name"], "None")
        for strat in registry.get("active_testing", []):
            update_board_signal(strat["name"], "None")
            
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
                # Handle both old (5 parts) and new (6 parts) formats for resiliency during transition
                if len(parts) >= 6:
                    status_idx = 4
                    signal_idx = 5
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
            with open(target_path, "w", encoding='utf-8') as f:
                f.writelines(lines)
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
            
        url = f"http://localhost:{port}/positions"
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
        url = f"http://localhost:{port}/cash"
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
        if side.upper() in ["SHORT", "BEARISH"] and not target_symbol:
            if ticker in INVERSE_MAP:
                 target_ticker = INVERSE_MAP[ticker]
                 log_engine(f"Bearish Signal Mapped: {ticker} -> {target_ticker}")
            else:
                 log_engine(f"🛡️ EXECUTION GUARD: {strategy_name} signaled SHORT for {ticker}, but no Inverse Mapping found and Cash Account cannot short. Aborting.", level="warning")
                 return
    
    # Position sizing: Use override if provided, otherwise $25/$75 cap per trade
    if quantity_override is not None:
        quantity = quantity_override
    else:
        quantity = round(POSITION_SIZE_USD / price, 4) if price > 0 else 0
        if CAUTION_MODE:
            quantity = round(quantity * 0.5, 4)
            log_engine(f"Execution Sizing (CAUTION MODE): {quantity} units")
    
    if quantity <= 0: return

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

    # --- 🛡️ SETTLEMENT GUARD: BUY PROTECTION ---
    if action == "buy":
        settled_cash = get_settled_cash(port)
        notional_req = quantity * price
        if settled_cash < notional_req:
            log_engine(f"🛡️ SETTLEMENT GUARD: Blocked BUY for {target_ticker}. Required ${notional_req:.2f}, Settled Available: ${settled_cash:.2f}.", level="warning")
            return

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
        url = f"http://localhost:{port}/order"
        
        # Proposal 22: Final Notional Guard
        notional_val = quantity * price
        if notional_val < MIN_NOTIONAL_USD:
            log_engine(f"Execution ABORTED: Notional ${notional_val:.2f} is below MIN_NOTIONAL (${MIN_NOTIONAL_USD}) for {ticker}", level="warning")
            return

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
                return

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

                # Remove from Unsettled Tracker on Success Sell
                if action == "sell":
                    UNSETTLED_POSITIONS.pop(target_ticker, None)
                    save_unsettled_tracker()
                    update_active_strategy_cache(target_ticker, strategy_name, "sell")

                # --- TELEGRAM ALERT ---
                market_label = " [IBKR OVERNIGHT]" if port == 5006 else " [ROBINHOOD CASH]"
                type_label = f"🚀 *LONG OPENED*{market_label}" if side.upper() not in ["SHORT", "SELL", "EXIT"] else f"📉 *SHORT OPENED*{market_label}"
                if side.upper() == "EXIT" or side.upper() == "SELL": type_label = f"🏁 *TRADE CLOSED*{market_label}"
                
                msg = f"{type_label}\nAsset: {ticker} (Target: {target_ticker})\nStrategy: {strategy_name}\nPrice: ${price:.2f}"
                if timeframe: msg += f"\nTimeframe: {timeframe}"
                send_quant_alert(msg)
            else:
                log_engine(f"Phantom Fill Protection (Audit Failed): {ticker} order accepted but position NOT found in audit.", level="warning")
        else:
            error_data = f"Status {resp.status_code}: {resp.text}"
            log_engine(f"Bridge ({port}) Order Rejected: {error_data}", level="error")
    except Exception as e:
        log_engine(f"Bridge ({port}) Execution Error: {e}", level="error")

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
    
    # Check if we hold the asset or its inverse
    is_held = (ticker in active_positions or (ticker in INVERSE_MAP and INVERSE_MAP[ticker] in active_positions))
    
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
                if (sig == "BUY" or sig == "LONG") and not is_held:
                    if active_count < MAX_CONCURRENT_TRADES:
                        execute_trade(name, ticker, sig, price, timeframe=timeframe, mode=mode)
                        active_count += 1
                        active_positions[ticker] = 1.0
                        LAST_TRADE_TIME[cache_key] = now_est
                elif (sig == "EXIT" or sig == "SELL") and is_held:
                    # Determine if we are exiting the base asset or an inverse ETF
                    target = ticker
                    if ticker in INVERSE_MAP and INVERSE_MAP[ticker] in active_positions:
                        target = INVERSE_MAP[ticker]
                    
                    execute_trade(name, ticker, sig, price, timeframe=timeframe, mode=mode, target_symbol=target)
                    if ticker in active_positions: del active_positions[ticker]
                    if ticker in INVERSE_MAP and INVERSE_MAP[ticker] in active_positions: 
                        del active_positions[INVERSE_MAP[ticker]]
                    active_count -= 1
                    LAST_TRADE_TIME[cache_key] = now_est
                elif sig == "SHORT" and not is_held:
                    if active_count < MAX_CONCURRENT_TRADES:
                        # Before going short, ensure no long exists (Reversal Protection)
                        if ticker in active_positions:
                             execute_trade(name, ticker, "EXIT", price, timeframe=timeframe, mode=mode, target_symbol=ticker)
                             del active_positions[ticker]
                             active_count -= 1
                        
                        execute_trade(name, ticker, "SHORT", price, timeframe=timeframe, mode=mode)
                        active_count += 1
                        target = INVERSE_MAP.get(ticker, ticker)
                        active_positions[target] = 1.0
                        LAST_TRADE_TIME[cache_key] = now_est
                elif (sig == "BUY" or sig == "LONG") and is_held:
                    # REVERSAL CASE 1: Hold Inverse -> Want LONG
                    target = INVERSE_MAP.get(ticker, ticker)
                    if target in active_positions and target != ticker:
                         log_engine(f"Reversing SHORT to LONG for {ticker}...")
                         execute_trade(name, ticker, "EXIT", price, timeframe=timeframe, mode=mode, target_symbol=target)
                         del active_positions[target]
                         active_count -= 1
                         LAST_TRADE_TIME[cache_key] = now_est
                         # Re-entry will happen next cycle
                
                elif sig == "SHORT" and is_held:
                    # REVERSAL CASE 2: Hold LONG -> Want SHORT
                    if ticker in active_positions:
                         log_engine(f"Reversing LONG to SHORT for {ticker}...")
                         execute_trade(name, ticker, "EXIT", price, timeframe=timeframe, mode=mode, target_symbol=ticker)
                         del active_positions[ticker]
                         active_count -= 1
                         LAST_TRADE_TIME[cache_key] = now_est
                         # Inverse entry will happen next cycle or can be forced below
                
    return status_update, active_count

# === PROPOSAL 5: MULTIPROCESSING HELPERS (module-level for pickling) ===

_STRAT_INTERVAL_MAP = {
    'smc':             '1h',
    'triple_rsi':      '1d',
    'noon_curve':      '5m',
    'initial_balance': '5m',
    'london':          '5m',
    'po3':             '5m',
    'ny_orb':          '1m',
    'wickless':        '1h',
    'db_v3_elite':     '2m',
    'matt_rapid':      '2m',
    'macd':            '1h',
    'gemini_velocity': '15m',
    'volcanix':        '5m',
    'standard_quant':  '1h',
    'big_d':           '5m',
    'little_d':        '1h',
    'strategy_os':     '1d',
}

def _get_strat_type(name: str):
    """Map a strategy registry name to its internal strat_type key."""
    n = name.lower()
    if 'smc' in n:             return 'smc'
    if 'triple rsi' in n:      return 'triple_rsi'
    if 'noon-curve' in n:      return 'noon_curve'
    if 'initial balance' in n: return 'initial_balance'
    if 'london' in n:          return 'london'
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
    if any(s in n for s in ['s1', 's2', 's3', 's4', 's5', 'retreat', 'tuesday', 'low close', 'demarker', 'high of 10', 'nova']): return 'standard_quant'
    if 'nasdaq-day' in n:      return 'nasdaq_day'
    if 'trinity' in n:         return 'trinity'
    if 'dynamic' in n:         return 'dynamic'
    if 'bigd' in n or 'big d' in n: return 'big_d'
    if 'littled' in n or 'little d' in n: return 'little_d'
    if 'apex' in n or 'pivot' in n: return 'standard_quant'
    if 'strategy os' in n:       return 'strategy_os'
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
                   'sig': None, 'price': 0.0, 'tf': None, 'sig_time': None}
    try:
        # Load data (for all non-multi-asset strategies)
        df = _pickle.loads(task['data_bytes']) if task.get('data_bytes') else None
        
        # --- ANTI-FLICKER BAR TRUNCATION (Proposal 12) ---
        # Trade on CLOSED bars only. This eliminates developing bar noise/spam.
        if df is not None and len(df) > 5:
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

        elif strat_type == 'standard_quant':
            # Handle standard quant entry strategies (S1-S5, Nova, Apex)
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
            for ticker in assets:
                t, i, p = ticker, "1h", "5d" # Default
                if "SMC" in name: t, i, p = ticker, "1h", "10d"
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
                elif "MACD 200" in name: t, i, p = ticker, "1h", "100d" # SMA 200 needs 200 bars, but 100h is ~2 weeks. We might need more.
                elif "Gemini Velocity" in name: t, i, p = ticker, "15m", "30d"
                elif "Volcanix" in name: t, i, p = ticker, "5m", "15d"
                elif "BigD" in name:
                    for ni, np_ in [("5m", "10d"), ("1h", "10d"), ("1d", "30d")]:
                        key = (ticker, ni)
                        data_tasks[key] = max(data_tasks.get(key, "1d"), np_, key=parse_period_to_days)
                    continue
                elif "LittleD" in name: t, i, p = ticker, "1h", "60d"
                elif "Double Break V3" in name or "Matt-Rapid" in name:
                    # Fetch both 2m and 1d for V3
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
                    if df is not None:
                        # Proposal 16: Dynamic Stale Tolerance (60m for scalps, 480m for hourly/swing)
                        stale_limit = 3600 # 60 mins default
                        if interval == "1h": stale_limit = 28800 # 8 hours
                        elif interval == "1d": stale_limit = 129600 # 36 hours
                        elif interval == "15m": stale_limit = 7200 # 2 hours
                        
                        last_ts = df.index[-1].timestamp()
                        if (time.time() - last_ts) > stale_limit:
                            log_engine(f"Warm cache stale ({(time.time()-last_ts)/60:.0f} min) for {ticker} — skipping.", level="warning")
                            df = None

                    daily_df = PERSISTENT_DATA_CACHE.get((ticker, "1d")) if interval in ["2m", "5m"] else None
                    h1_df = PERSISTENT_DATA_CACHE.get((ticker, "1h")) if strat_type == 'big_d' else None
                    
                    tasks.append({
                        'name': name, 'ticker': ticker, 'strat_type': strat_type,
                        'is_live': is_live,
                        'data_bytes': pickle.dumps(df.copy()) if df is not None else None,
                        'daily_bytes': pickle.dumps(daily_df.copy()) if daily_df is not None else None,
                        'h1_bytes': pickle.dumps(h1_df.copy()) if h1_df is not None else None,
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
        if sig:
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
