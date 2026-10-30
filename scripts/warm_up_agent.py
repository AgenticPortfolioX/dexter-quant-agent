"""
Pre-Market Cache Warm-Up Agent (Proposal 6)
=============================================
Runs at 9:00 AM EST, 30 minutes before market open.
Pre-downloads all required asset data and saves to disk so that
the first alpha_autotrader scan at 9:30 AM loads instantly (zero cold-boot lag).
"""
import os
import sys
import json
import pickle
import time
import concurrent.futures
from datetime import datetime
import pytz

# Prevent UnicodeEncodeError when printing emojis in Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# Add project root to path
PROJECT_ROOT = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
import yfinance as yf

# Paths
EST              = pytz.timezone('US/Eastern')
REGISTRY_PATH    = os.path.join(PROJECT_ROOT, 'strategy_registry.json')
WARM_CACHE_DIR   = os.path.join(PROJECT_ROOT, 'cache')
WARM_CACHE_FILE  = os.path.join(WARM_CACHE_DIR, 'warm_cache.pkl')
WARM_CACHE_MAXAGE_SECS = 5400  # 90 minutes — discard stale warm caches

# Interval → full lookback period mapping
PERIOD_MAP = {
    '1m': '5d',
    '5m': '10d',
    '15m': '15d',
    '1h': '30d',
    '1d': '2y',
}

# Strategy name → (interval) map (mirrors _STRAT_INTERVAL_MAP in alpha_autotrader)
STRAT_INTERVAL_MAP = {
    'apex':                '1h',
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
    # Systematic daily book
    'sys_ibs3':            '1d',
    'sys_vix_rsi2':        '1d',
    'sys_turn_of_month':   '1d',
    'sys_dual_momentum':   '1d',
    'sys_pead':            '1d',
}

def _get_strat_type(name: str):
    n = name.lower()
    if 'ibs-3' in n or 'ibs3' in n or 'index dip' in n: return 'sys_ibs3'
    if 'vix panic' in n: return 'sys_vix_rsi2'
    if 'turn-of-month' in n or 'turn of month' in n: return 'sys_turn_of_month'
    if 'dual momentum' in n or 'sector rotation' in n: return 'sys_dual_momentum'
    if 'pead' in n or 'earnings gap drift' in n: return 'sys_pead'
    if 'apex' in n or 'pivot' in n: return 'apex'
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
    if 'london' in n:          return 'london'
    if 'po3' in n:             return 'po3'
    if 'ny orb' in n:          return 'ny_orb'
    if 'wickless' in n:        return 'wickless'
    if 'macd' in n:            return 'macd'
    if 'gemini velocity' in n: return 'gemini_velocity'
    if 'volcanix' in n:        return 'volcanix'
    return None

def _download_one(task):
    """Worker: download (ticker, interval) pair and return (key, DataFrame)."""
    ticker, interval, period = task
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            return (ticker, interval), None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated()]
        if df.index.tz is None:
            df = df.tz_localize('UTC').tz_convert(EST)
        else:
            df = df.tz_convert(EST)
        return (ticker, interval), df
    except Exception as e:
        print(f"  [WARN] {ticker}@{interval}: {e}")
        return (ticker, interval), None

def audit_fail_log():
    """Reads FailLog.md and alerts on unchecked morning items."""
    fail_log_path = os.path.join(PROJECT_ROOT, 'FailLog.md')
    if os.path.exists(fail_log_path):
        print(f"\n[WARM-UP] 🔍 Auditing FailLog.md...")
        try:
            with open(fail_log_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for 9:00 AM checklist section
            if "### 🚨 9:00 AM PRE-MARKET FINAL CHECKLIST" in content:
                checklist_part = content.split("### 🚨 9:00 AM PRE-MARKET FINAL CHECKLIST")[1]
                if "[ ]" in checklist_part:
                    print(f"[WARM-UP] 🚨 ATTENTION: Unchecked items found in FailLog.md Pre-Market Checklist!")
                else:
                    print(f"[WARM-UP] ✅ FailLog.md Pre-Market Checklist is clear.")
        except Exception as e:
            print(f"[WARM-UP] ⚠️ FailLog Audit Error: {e}")

def run_warm_up():
    """Main entry point: builds task list, downloads in parallel, saves cache."""
    start_ts = time.perf_counter()
    now_str = datetime.now(EST).strftime('%H:%M:%S EST')
    print(f"[{now_str}] 🔥 PRE-MARKET WARM-UP AGENT — Starting download run...")
    
    # --- Proposal 23: Audit FailLog ---
    audit_fail_log()

    # --- Build unique (ticker, interval) task list from registry ---
    tasks = {}  # (ticker, interval) → period
    try:
        with open(REGISTRY_PATH, 'r') as f:
            registry = json.load(f)
    except Exception as e:
        print(f"[WARM-UP] ❌ Cannot load registry: {e}")
        return

    for category in ['live_trading', 'active_testing']:
        for strat in registry.get(category, []):
            name  = strat['name']
            assets = strat['assets']
            stype = _get_strat_type(name)
            if not stype:
                continue
            interval = STRAT_INTERVAL_MAP.get(stype, '1h')
            period   = PERIOD_MAP.get(interval, '10d')
            tickers  = ['QQQ', 'SPY'] if stype == 'noon_curve' else assets
            for t in tickers:
                key = (t, interval)
                # Keep the longer of any duplicate period requests
                if key not in tasks or tasks[key] < period:
                    tasks[key] = period
                if stype == 'apex':
                    d_key = (t, '1d')
                    if d_key not in tasks or tasks[d_key] < '60d':
                        tasks[d_key] = '60d'
                if stype == 'sys_dual_momentum':
                    # SPY is the risk-on/risk-off regime filter
                    spy_key = ('SPY', '1d')
                    if spy_key not in tasks or tasks[spy_key] < '2y':
                        tasks[spy_key] = '2y'

    download_tasks = [(t, i, p) for (t, i), p in tasks.items()]
    print(f"[WARM-UP] Queuing {len(download_tasks)} asset/interval pairs...")

    # --- Parallel download ---
    cache = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_download_one, task) for task in download_tasks]
        for future in concurrent.futures.as_completed(futures):
            key, df = future.result()
            ticker, interval = key
            if df is not None:
                cache[key] = df
                print(f"  ✅ {ticker} @ {interval}: {len(df)} bars")
            else:
                print(f"  ⚠️  {ticker} @ {interval}: no data")

    # --- Save to disk ---
    os.makedirs(WARM_CACHE_DIR, exist_ok=True)
    payload = {
        'timestamp': datetime.now(EST).isoformat(),
        'cache': cache
    }
    with open(WARM_CACHE_FILE, 'wb') as f:
        pickle.dump(payload, f)

    elapsed = time.perf_counter() - start_ts
    now_str = datetime.now(EST).strftime('%H:%M:%S EST')
    print(f"[{now_str}] ✅ WARM-UP COMPLETE — {len(cache)}/{len(download_tasks)} pairs cached in {elapsed:.1f}s")
    print(f"[WARM-UP] Cache → {WARM_CACHE_FILE}")
    return len(cache)

if __name__ == '__main__':
    run_warm_up()
