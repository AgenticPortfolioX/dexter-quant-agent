> 🕒 Last Updated: 2026-03-09 11:45:00 EST

# 📉 DEXTER FAILURE LOG: POST-MORTEM & PREVENTION

---

### 📅 MARCH 09, 2026: SHORT MAPPING BUG & DIRECTORY TIDY
| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **Short Mapping Bug** | Bearish signals on cash accounts incorrectly defaulted to spot-only long buys. | Updated `INVERSE_MAP` & `execute_trade` to enforce Short-to-Inverse logic or Abort. | **Short-to-Inverse Guard**: Cash accounts now buy inverse ETFs on short signals or block the trade. |
| **Strategy Bloat** | Volcanix was in Live Trading but performing inconsistently. | Moved Volcanix to **Active Testing** and updated registry. | **Triage Lifecycle**: Underperforming strategies are demoted to testing before being sunset. |
| **Directory Noise** | Scratch logs and debug files cluttering the repository. | Purged 3-09-26 scratch files and moved results to central `backtests` root. | **Git hygiene**: Updated `.gitignore` to exclude results and binary artifacts. |

---

### 📋 HISTORICAL KNOWLEDGE (RECURRING FAILURES)
- **Trading Stagnation**: If trading stops despite "Active" heartbeats, it is likely a **stuck yfinance scanner** or a hang during **Market Intelligence** refreshes. (Check process list for `pythonw.exe` hangs).
- **Silent Timeouts**: Sub-processes and network-dependent calls (yfinance/requests) must have explicit timeouts to prevent thread-locking.

---

### 📅 MARCH 06, 2026: DATA CONTAMINATION & SUB-$1 REJECTIONS

| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **Sub-$1 Rejection** (CLNK) | Calculated quantities resulted in <$1 notional on execution, though Dexter expected $12.50. | Implemented `MIN_NOTIONAL_USD = 2.0` guard in `execute_trade`. | **Notional Guard**: Execution layer now aborts any trade calculated to be < $2.0. |
| **Data Cross-Talk** | Parallel `yfinance` fetches in ThreadPool collided, causing `CLNK` (~$16) to inherit `QQQ` price (~$440). | Switched Alpha Engine to **Sequential Fetching** for all assets. | **Buffer Isolation**: Removed ThreadPoolExecutor for `yfinance` to prevent session/buffer leakage. |

---


### 📅 MARCH 05, 2026: FRACTIONAL ORDER LOCK & ERROR SWALLOWING

| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **Phantom Audit Fail** (ROKU/COIN/QQQ) | Fractional stock orders (e.g. 0.36 shares) REJECTED because TIF was set to GTC. | Patched `bridge_server.py` to enforce `timeInForce='gfd'` for all stocks. | **Fractional SOP**: Robinhood ONLY accepts fractional shares if TIF is 'Good For Day' (GFD). |
| **Silent Rejections** | Bridge returned `200 OK` despite RH error in `non_field_errors` key. | Hardened Bridge to return `400` on any error key + added raw logs. | **Audit Log**: `bridge_raw.log` now captures every raw JSON exchange for 100% visibility into Rejection reasons. |
| **Identical Prices** | Thread-unsafe `yfinance` calls in parallel loop shared a data buffer. | Added `threads=False` and `df.copy()` to `fetch_worker`. | **Memory Isolation**: Every strategy now receives a unique, deep-copied data object. |
| **Zombie Bridge** | Port collision on 5005; old server version was still running in background. | Killed PID `2837900` and `3647464`; restarted clean. | **Process Heartbeat**: Monitor now checks for duplicate Python PIDs on startup. |

---

### 📅 MARCH 04, 2026: BOARD DECOUPLING & PHANTOM AUDIT

| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **Phantom Fill (SPY)** | Bridge returned 200 OK for SPY LONG but fill never occurred on-exchange. | Manual bridge audit (`/positions`). Confirmed empty. | **Double-Check Fill**: Added mandatory bridge position verification BEFORE logging EXEC-. |
| **Board Update Deadlock** | Board logic was blocking the engine; tz-naive errors crashed the scanner loop. | Decoupled board updates to background thread ("Iron Lock"). | Dexter now scans 100% of the time, even if the board is stalled or broken. |
| **Timestamp Crash** | Outdated tz-naive data hit the timestamp filter at 11:34 AM. | Standardized all signals to aware EST. | All dash logs now use `signal_dt.tz_localize('UTC').tz_convert(EST)`. |
| **Silent Scanning** | 15m/1h strategies were filtered by aggressive 60m stale data check. | Relaxed stale windows to 480m for higher timeframes. | Higher-timeframe trades (BigD, Gemini Velocity) are now active all morning. |

---

### 📅 MARCH 03, 2026: LIVE TRADING RECOVERY

| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **Bridge Offline** | Robinhood Bridge (Port 5005) stalled on expired session. | Manually re-launched `bridge_server.py`. | **Execution Handshake**: Added mandatory Port 5005 probe to 8:00 AM SOP checks. |
| **Ghost Executions** | System logged `EXEC-` without verifying Bridge success. | Patched `alpha_autotrader.py` to validate `resp.status_code == 200`. | Orders are now ignored and surfaced as `ERROR` on board if Bridge rejects them. |
| **2-Second "Exits"** | Display logic cleared trades because Portfolio sync returned 0. | Patched response validation to prevent "fake" entries. | Fixed via `alpha_autotrader.py` execution layer patch (13:40 EST). |
| **Stale Data Cache** | warm_up data expired (151 min stale), blocking strat signals. | Manually executed `warm_up_agent.py`. | Added auto-refresh trigger to `live_monitor.py` for stale caches > 60m. |
| **Fetch Failed (ROKU)** | `yfinance` throttling or local data prep mismatch. | Forced manual data ingestion for priority assets. | Implemented dynamic stale windows (30m - 90m) based on strategy timeframe. |
