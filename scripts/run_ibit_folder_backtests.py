"""
Comprehensive Backtest Suite for strategies/successful_strategies/iBit_success
--------------------------------------------------------------------------------
Orchestrator: Antigravity | Worker: Dexter Quant Specialist
Audits all 7 strategies in the iBit_success folder across appropriate timeframes:
  1. Inside Candle (1h, 1y)
  2. Liquidity Sweep (15m/1h, 90d)
  3. Link-Pilled SFP (1h, 180d)
  4. Power of 3 - PO3/AMD (5m, 60d)
  5. RSI Reversion (1h, 180d)
  6. Smart Money Concepts - SMC (1h, 1y)
  7. Tech Level EMA Touch (1h, 180d)

Evaluates on IBIT with exact Win Rate, Profit Factor, Total Trades, and P&L.
"""

import os
import sys
import json
import math
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
import yfinance as yf

EST = pytz.timezone('US/Eastern')
DEXTER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IBIT_FOLDER = os.path.join(DEXTER_ROOT, "strategies", "successful_strategies", "iBit_success")
OUTPUT_REPORT = os.path.join(DEXTER_ROOT, "dashboard", "IBIT_SUCCESS_BACKTEST_REPORT.md")
OUTPUT_JSON = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\backtests\results\ibit_success_backtest_results.json"

os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
os.makedirs(os.path.dirname(OUTPUT_REPORT), exist_ok=True)

def fetch_data(ticker: str, period: str, interval: str) -> pd.DataFrame:
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(EST)
        else:
            df.index = df.index.tz_convert(EST)
        return df.dropna()
    except Exception as e:
        print(f"Error downloading {ticker} {period}/{interval}: {e}")
        return pd.DataFrame()

def calc_metrics(trades: list) -> dict:
    if not trades:
        return {
            "trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "total_return": 0.0, "max_dd": 0.0, "avg_trade": 0.0,
            "wins": 0, "losses": 0
        }
    returns = [t['return'] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    
    wr = (len(wins) / len(returns)) * 100.0 if returns else 0.0
    gross_win = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    
    equity = [1.0]
    for r in returns:
        equity.append(equity[-1] * (1.0 + r))
    tot_ret = round((equity[-1] - 1.0) * 100.0, 2)
    
    peak = equity[0]
    max_dd = 0.0
    for val in equity:
        if val > peak: peak = val
        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd: max_dd = dd
        
    return {
        "trades": len(returns),
        "win_rate": round(wr, 1),
        "profit_factor": pf,
        "total_return": tot_ret,
        "max_dd": round(max_dd * 100.0, 2),
        "avg_trade": round(np.mean(returns) * 100.0, 2) if returns else 0.0,
        "wins": len(wins),
        "losses": len(losses)
    }

# 1. Inside Candle Strategy (1h, 1y)
def backtest_inside_candle(ticker="IBIT", period="1y"):
    df = fetch_data(ticker, period=period, interval="1h")
    if df.empty or len(df) < 30: return []
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(10).mean()
    
    trades = []
    in_pos = False
    entry_p, sl, tp, side = 0.0, 0.0, 0.0, None
    
    for i in range(12, len(df)):
        c, h, l = df['Close'].iloc[i], df['High'].iloc[i], df['Low'].iloc[i]
        prev_h, prev_l = df['High'].iloc[i-1], df['Low'].iloc[i-1]
        m_h, m_l = df['High'].iloc[i-2], df['Low'].iloc[i-2]
        atr = df['ATR'].iloc[i]
        
        if in_pos:
            if side == "LONG":
                if l <= sl:
                    trades.append({'return': (sl - entry_p)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif h >= tp:
                    trades.append({'return': (tp - entry_p)/entry_p, 'type': 'TP'})
                    in_pos = False
            elif side == "SHORT":
                if h >= sl:
                    trades.append({'return': (entry_p - sl)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif l <= tp:
                    trades.append({'return': (entry_p - tp)/entry_p, 'type': 'TP'})
                    in_pos = False
        else:
            is_inside = (prev_h < m_h) and (prev_l > m_l)
            if is_inside and not pd.isna(atr):
                if c > m_h:
                    in_pos = True
                    side = "LONG"
                    entry_p = c
                    sl = entry_p - (1.0 * atr)
                    tp = entry_p + (3.0 * atr)
                elif c < m_l:
                    in_pos = True
                    side = "SHORT"
                    entry_p = c
                    sl = entry_p + (1.0 * atr)
                    tp = entry_p - (3.0 * atr)
    return trades

# 2. Liquidity Sweep (15m, 60d)
def backtest_liquidity_sweep(ticker="IBIT", period="60d"):
    df = fetch_data(ticker, period=period, interval="15m")
    if df.empty or len(df) < 30: return []
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()
    
    trades = []
    in_pos = False
    entry_p, sl, tp, side = 0.0, 0.0, 0.0, None
    
    for i in range(25, len(df)):
        c, h, l = df['Close'].iloc[i], df['High'].iloc[i], df['Low'].iloc[i]
        sw_h = df['High'].iloc[i-20:i-1].max()
        sw_l = df['Low'].iloc[i-20:i-1].min()
        atr = df['ATR'].iloc[i]
        
        if in_pos:
            if side == "LONG":
                if l <= sl:
                    trades.append({'return': (sl - entry_p)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif h >= tp:
                    trades.append({'return': (tp - entry_p)/entry_p, 'type': 'TP'})
                    in_pos = False
            elif side == "SHORT":
                if h >= sl:
                    trades.append({'return': (entry_p - sl)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif l <= tp:
                    trades.append({'return': (entry_p - tp)/entry_p, 'type': 'TP'})
                    in_pos = False
        else:
            if not pd.isna(atr):
                if l < sw_l and c > sw_l:
                    in_pos = True
                    side = "LONG"
                    entry_p = c
                    sl = l - (0.5 * atr)
                    tp = entry_p + (2.0 * atr)
                elif h > sw_h and c < sw_h:
                    in_pos = True
                    side = "SHORT"
                    entry_p = c
                    sl = h + (0.5 * atr)
                    tp = entry_p - (2.0 * atr)
    return trades

# 3. Link-Pilled SFP (1h, 180d)
def backtest_link_pilled(ticker="IBIT", period="180d"):
    df = fetch_data(ticker, period=period, interval="1h")
    if df.empty or len(df) < 30: return []
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()
    vol_ma = df['Volume'].rolling(20).mean()
    df['Vol_Surge'] = df['Volume'] > (vol_ma * 1.2)
    
    trades = []
    in_pos = False
    entry_p, sl, tp, side = 0.0, 0.0, 0.0, None
    
    for i in range(25, len(df)):
        c, h, l = df['Close'].iloc[i], df['High'].iloc[i], df['Low'].iloc[i]
        sw_h = df['High'].iloc[i-15:i-1].max()
        sw_l = df['Low'].iloc[i-15:i-1].min()
        atr = df['ATR'].iloc[i]
        surge = df['Vol_Surge'].iloc[i]
        
        if in_pos:
            if side == "LONG":
                if l <= sl:
                    trades.append({'return': (sl - entry_p)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif h >= tp:
                    trades.append({'return': (tp - entry_p)/entry_p, 'type': 'TP'})
                    in_pos = False
            elif side == "SHORT":
                if h >= sl:
                    trades.append({'return': (entry_p - sl)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif l <= tp:
                    trades.append({'return': (entry_p - tp)/entry_p, 'type': 'TP'})
                    in_pos = False
        else:
            if not pd.isna(atr) and surge:
                if l < sw_l and c > sw_l:
                    in_pos = True
                    side = "LONG"
                    entry_p = c
                    sl = l - (0.5 * atr)
                    tp = entry_p + (2.5 * atr)
                elif h > sw_h and c < sw_h:
                    in_pos = True
                    side = "SHORT"
                    entry_p = c
                    sl = h + (0.5 * atr)
                    tp = entry_p - (2.5 * atr)
    return trades

# 4. Power of 3 (5m, 60d)
def backtest_po3(ticker="IBIT", period="60d"):
    df = fetch_data(ticker, period=period, interval="5m")
    if df.empty or len(df) < 50: return []
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()
    
    trades = []
    in_pos = False
    entry_p, sl, tp, side = 0.0, 0.0, 0.0, None
    
    for i in range(25, len(df)):
        c, h, l = df['Close'].iloc[i], df['High'].iloc[i], df['Low'].iloc[i]
        c_prev = df['Close'].iloc[i-1]
        ema20, ema50 = df['EMA20'].iloc[i], df['EMA50'].iloc[i]
        ema20_prev = df['EMA20'].iloc[i-1]
        atr = df['ATR'].iloc[i]
        
        if in_pos:
            if side == "LONG":
                if l <= sl:
                    trades.append({'return': (sl - entry_p)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif h >= tp:
                    trades.append({'return': (tp - entry_p)/entry_p, 'type': 'TP'})
                    in_pos = False
            elif side == "SHORT":
                if h >= sl:
                    trades.append({'return': (entry_p - sl)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif l <= tp:
                    trades.append({'return': (entry_p - tp)/entry_p, 'type': 'TP'})
                    in_pos = False
        else:
            if not pd.isna(atr):
                if c_prev < ema20_prev and c > ema20 and c > ema50:
                    in_pos = True
                    side = "LONG"
                    entry_p = c
                    sl = entry_p - (1.5 * atr)
                    tp = entry_p + (3.0 * atr)
                elif c_prev > ema20_prev and c < ema20 and c < ema50:
                    in_pos = True
                    side = "SHORT"
                    entry_p = c
                    sl = entry_p + (1.5 * atr)
                    tp = entry_p - (3.0 * atr)
    return trades

# 5. RSI Reversion (1h, 180d)
def backtest_rsi(ticker="IBIT", period="180d"):
    df = fetch_data(ticker, period=period, interval="1h")
    if df.empty or len(df) < 30: return []
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()
    
    trades = []
    in_pos = False
    entry_p, sl, tp, side = 0.0, 0.0, 0.0, None
    
    for i in range(20, len(df)):
        c, h, l, o = df['Close'].iloc[i], df['High'].iloc[i], df['Low'].iloc[i], df['Open'].iloc[i]
        c_prev, o_prev = df['Close'].iloc[i-1], df['Open'].iloc[i-1]
        rsi = df['RSI'].iloc[i]
        atr = df['ATR'].iloc[i]
        
        if in_pos:
            if side == "LONG":
                if l <= sl:
                    trades.append({'return': (sl - entry_p)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif h >= tp:
                    trades.append({'return': (tp - entry_p)/entry_p, 'type': 'TP'})
                    in_pos = False
            elif side == "SHORT":
                if h >= sl:
                    trades.append({'return': (entry_p - sl)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif l <= tp:
                    trades.append({'return': (entry_p - tp)/entry_p, 'type': 'TP'})
                    in_pos = False
        else:
            if not pd.isna(atr):
                # Bullish candle while RSI oversold
                if rsi < 36 and c > o and c_prev < o_prev:
                    in_pos = True
                    side = "LONG"
                    entry_p = c
                    sl = entry_p - (1.5 * atr)
                    tp = entry_p + (2.5 * atr)
                elif rsi > 64 and c < o and c_prev > o_prev:
                    in_pos = True
                    side = "SHORT"
                    entry_p = c
                    sl = entry_p + (1.5 * atr)
                    tp = entry_p - (2.5 * atr)
    return trades

# 6. SMC (1h, 1y)
def backtest_smc(ticker="IBIT", period="1y"):
    df = fetch_data(ticker, period=period, interval="1h")
    if df.empty or len(df) < 30: return []
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()
    
    trades = []
    in_pos = False
    entry_p, sl, tp, side = 0.0, 0.0, 0.0, None
    
    for i in range(25, len(df)):
        c, h, l = df['Close'].iloc[i], df['High'].iloc[i], df['Low'].iloc[i]
        sw_h = df['High'].iloc[i-10:i-1].max()
        sw_l = df['Low'].iloc[i-10:i-1].min()
        atr = df['ATR'].iloc[i]
        
        if in_pos:
            if side == "LONG":
                if l <= sl:
                    trades.append({'return': (sl - entry_p)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif h >= tp:
                    trades.append({'return': (tp - entry_p)/entry_p, 'type': 'TP'})
                    in_pos = False
            elif side == "SHORT":
                if h >= sl:
                    trades.append({'return': (entry_p - sl)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif l <= tp:
                    trades.append({'return': (entry_p - tp)/entry_p, 'type': 'TP'})
                    in_pos = False
        else:
            if not pd.isna(atr):
                # Bullish MSS displacement
                if c > sw_h and df['Close'].iloc[i-1] <= sw_h:
                    in_pos = True
                    side = "LONG"
                    entry_p = c
                    sl = l - (1.0 * atr)
                    tp = entry_p + (2.0 * atr)
                elif c < sw_l and df['Close'].iloc[i-1] >= sw_l:
                    in_pos = True
                    side = "SHORT"
                    entry_p = c
                    sl = h + (1.0 * atr)
                    tp = entry_p - (2.0 * atr)
    return trades

# 7. Tech Level EMA Touch (1h, 180d)
def backtest_tech_level_ema(ticker="IBIT", period="180d"):
    df = fetch_data(ticker, period=period, interval="1h")
    if df.empty or len(df) < 30: return []
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()
    vol_ma = df['Volume'].rolling(20).mean()
    df['Vol_Surge'] = df['Volume'] > (vol_ma * 1.1)
    
    trades = []
    in_pos = False
    entry_p, sl, tp, side = 0.0, 0.0, 0.0, None
    
    for i in range(25, len(df)):
        c, h, l = df['Close'].iloc[i], df['High'].iloc[i], df['Low'].iloc[i]
        ema20, ema50 = df['EMA20'].iloc[i], df['EMA50'].iloc[i]
        atr = df['ATR'].iloc[i]
        surge = df['Vol_Surge'].iloc[i]
        
        if in_pos:
            if side == "LONG":
                if l <= sl:
                    trades.append({'return': (sl - entry_p)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif h >= tp:
                    trades.append({'return': (tp - entry_p)/entry_p, 'type': 'TP'})
                    in_pos = False
            elif side == "SHORT":
                if h >= sl:
                    trades.append({'return': (entry_p - sl)/entry_p, 'type': 'SL'})
                    in_pos = False
                elif l <= tp:
                    trades.append({'return': (entry_p - tp)/entry_p, 'type': 'TP'})
                    in_pos = False
        else:
            if not pd.isna(atr) and surge:
                # EMA Touch and bounce in trend
                if l <= ema20 and c > ema20 and c > ema50:
                    in_pos = True
                    side = "LONG"
                    entry_p = c
                    sl = entry_p - (1.2 * atr)
                    tp = entry_p + (2.5 * atr)
                elif h >= ema20 and c < ema20 and c < ema50:
                    in_pos = True
                    side = "SHORT"
                    entry_p = c
                    sl = entry_p + (1.2 * atr)
                    tp = entry_p - (2.5 * atr)
    return trades

def run_all():
    print("=" * 75)
    print("  IBIT_SUCCESS STRATEGY SUITE: COMPREHENSIVE BACKTEST AUDIT")
    print(f"  Execution Time: {datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S EST')}")
    print("=" * 75)
    
    strategies = [
        ("Inside Candle", "inside_candle_ibit", "1h", "1y", backtest_inside_candle),
        ("Liquidity Sweep", "liquidity_sweep_ibit", "15m", "60d", backtest_liquidity_sweep),
        ("Link-Pilled SFP", "link-pilled", "1h", "180d", backtest_link_pilled),
        ("Power of 3 (PO3/AMD)", "power_of_3", "5m", "60d", backtest_po3),
        ("RSI Reversion", "rsi_ibit", "1h", "180d", backtest_rsi),
        ("SMC Bitcoin", "smc_ibit", "1h", "1y", backtest_smc),
        ("Tech Level EMA Touch", "ibit_tech_level_ema", "1h", "180d", backtest_tech_level_ema),
    ]
    
    results = {}
    
    for name, folder, tf, period, func in strategies:
        print(f"\nRunning {name} [{folder}] on IBIT ({tf}, {period})...")
        trades = func("IBIT", period=period)
        metrics = calc_metrics(trades)
        results[name] = {
            "name": name,
            "folder": folder,
            "timeframe": tf,
            "period": period,
            "metrics": metrics
        }
        print(f"  -> Trades: {metrics['trades']} | Win Rate: {metrics['win_rate']}% | "
              f"Profit Factor: {metrics['profit_factor']} | Return: {metrics['total_return']}% | "
              f"Max DD: {metrics['max_dd']}%")

    # Save JSON
    with open(OUTPUT_JSON, "w") as f:
        json.dump(results, f, indent=4)
        
    # Write Markdown Report
    now_est = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")
    lines = [
        "# 🪙 IBIT_SUCCESS FOLDER STRATEGY BACKTEST AUDIT\n",
        f"**Generated**: {now_est} | **Orchestrator**: Antigravity Gemini 3.8 Flash | **Worker Agent**: Dexter Quant Specialist\n\n",
        "## 🏆 PERFORMANCE AUDIT SUMMARY (IBIT BENCHMARK)\n\n",
        "| Strategy Name | Folder | Timeframe | Period | Total Trades | Win Rate (%) | Profit Factor | Total Return (%) | Max Drawdown (%) |\n",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
    ]
    
    for name, data in results.items():
        m = data['metrics']
        lines.append(f"| **{name}** | `{data['folder']}` | {data['timeframe']} | {data['period']} | {m['trades']} | **{m['win_rate']}%** | **{m['profit_factor']}** | **{m['total_return']}%** | {m['max_dd']}% |\n")
        
    lines.append("\n---\n\n## 📝 STRATEGY DEEP DIVE\n")
    for name, data in results.items():
        m = data['metrics']
        lines.append(f"### {name} (`{data['folder']}`)\n")
        lines.append(f"- **Timeframe**: {data['timeframe']} (Period: {data['period']})\n")
        lines.append(f"- **Trades Evaluated**: {m['trades']} ({m['wins']} Wins / {m['losses']} Losses)\n")
        lines.append(f"- **Win Rate**: {m['win_rate']}%\n")
        lines.append(f"- **Profit Factor**: {m['profit_factor']}\n")
        lines.append(f"- **Total Return**: {m['total_return']}%\n")
        lines.append(f"- **Max Drawdown**: {m['max_dd']}%\n")
        lines.append(f"- **Average Trade**: {m['avg_trade']}%\n\n")

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.writelines(lines)
        
    print(f"\nSaved Markdown Report to {OUTPUT_REPORT}")
    print(f"Saved JSON Results to {OUTPUT_JSON}")

if __name__ == "__main__":
    run_all()
