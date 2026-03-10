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
    '1h': '30d',
    '1d': '2y',
}

# Strategy name → (interval) map (mirrors _STRAT_INTERVAL_MAP in alpha_autotrader)
STRAT_INTERVAL_MAP = {
    'smc':             '1h',
    'triple_rsi':      '1d',
    'noon_curve':      '5m',
    'initial_balance': '5m',
    'london':          '5m',
    'po3':             '5m',
    'ny_orb':          '1m',
    'wickless':        '1h',
}

def _get_strat_type(name: str):
    if 'SMC' in name:             return 'smc'
    if 'Triple RSI' in name:      return 'triple_rsi'
    if 'Noon-Curve' in name:      return 'noon_curve'
    if 'Initial Balance' in name: return 'initial_balance'
    if 'London' in name:          return 'london'
    if 'PO3' in name:             return 'po3'
    if 'NY ORB' in name:          return 'ny_orb'
    if 'Wickless' in name:        return 'wickless'
    if 'MACD' in name:            return 'macd'
    if 'Gemini Velocity' in name: return 'gemini_velocity'
    if 'Volcanix' in name:        return 'volcanix'
    if any(s in name.lower() for s in ['s1', 's2', 's3', 's4', 's5', 'nova']): return 'standard_quant'
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

def run_warm_up():
    """Main entry point: builds task list, downloads in parallel, saves cache."""
    start_ts = time.perf_counter()
    now_str = datetime.now(EST).strftime('%H:%M:%S EST')
    print(f"[{now_str}] 🔥 PRE-MARKET WARM-UP AGENT — Starting download run...")

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
