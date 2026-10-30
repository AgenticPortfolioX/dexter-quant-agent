> 🕒 Last Updated: 2026-10-30 03:25:00 EST

# 📉 DEXTER FAILURE LOG: POST-MORTEM & PREVENTION

---

### 📅 APRIL 23, 2026: THE WHIPSAW DISASTER (0/13 FAILURE)

| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **0/13 Win Rate & Cluster Risk** | Correlated sector risk + Market Regime Mismatch. The system shorted the entire Tech/SaaS sector in the morning, then flipped to Long during a midday reversal. Most critically, `CAUTION_MODE` was loaded but ignored by the engine. | Patched `alpha_autotrader.py` to strictly enforce `CAUTION_MODE`, blocking new entries during high-risk regimes. Set `PILOT_LIGHT` to False. | **Caution Enforcement**: The engine now verifies `CAUTION_MODE` status before every new entry. **Fusion Protocol**: Dexter now utilizes a qualitative "Advisory Gate" (Item 1, 2, 3) to cross-reference technical signals with institutional analyst consensus, providing a final 'Human-in-the-loop' style validation via Slack before high-conviction trades. |

---

### 📅 APRIL 21, 2026: THE LOCAL SCOPE TRAP (PORTFOLIO DETACHMENT)

| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **Unbounded Position Sizing & Missing Exits** | The background thread fetching portfolio data stored `active_positions` in its own local memory scope. The main engine's logic loop kept a separate, empty `{}` cache, forcing it to believe it owned 0 assets. It completely bypassed position sizing limits and ignored all mathematical exit signals. | Implemented a thread-safe `GLOBAL_ACTIVE_POSITIONS` cache in `alpha_autotrader.py` to correctly bind the bridge state to the main execution loop. Manually liquidated 5 stale short-term positions. | **Global Portfolio State Binding**: The Alpha Engine now strictly copies its position map from the bound global dictionary, ensuring mathematical exits properly reference live holdings. |
| **Missing Timeframes & TP/SL on Slack Dashboard** | `@dexter positions` failed to translate raw `frequency` (e.g. 3600) to human timeframes, and attempted to parse non-existent TP/SL keys from the registry. | Upgraded `dexter_slack_listener.py` to format timeframes cleanly and properly surface that Dexter uses "Dynamic (Algorithmic)" exits instead of static percentages. | **Dashboard Syncing**: Slack outputs now accurately reflect Dexter's dynamic, algorithmic risk management models rather than static price boundaries. |
| **Impossible P&L Math Glitch** | `find_entry_price` was hardcoded to only search logs for `"EXEC-BUY"`. Because inverse ETFs are logged as `"EXEC-SHORT"`, the Slack Listener failed to find the entry price. It then fell back to pulling the entry price of the underlying asset (e.g. SMCI) and calculated P&L by dividing the SOXS current price by the SMCI entry price. | Patched `find_entry_price` in `alpha_autotrader.py` to correctly identify `"EXEC-SHORT"` log lines and retrieve the proper entry price. | **Regex Completeness**: Entry price parsing must account for both Long and Short execution strings. |
| **Orphaned Hedge Assets (Zombie Trades)** | Due to the Local Scope Trap wiping the active positions cache, Dexter abandoned a `SOXS` short when reversing to an `SMCI` long, resulting in the account holding BOTH the Long and the Inverse asset simultaneously. | Fixed via the `GLOBAL_ACTIVE_POSITIONS` patch. Reversal logic will automatically clean up the orphaned SOXS position on the next scan. | **Reversal Dependency**: Engine must have 100% accurate position cache before buying an asset, ensuring it can liquidate its inverse counterpart. |

---

### 📅 APRIL 17, 2026: WEEK-LONG SESSION BLACKOUT & ZOMBIE DEADLOCK

| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **Week-Long Trading Stagnation** | Robinhood session expired on Monday. Stale `bridge_server.py` processes entered a "Zombie" state, holding Port 5005 and preventing automated self-healing from binding a new, authenticated bridge. | Manually terminated all Port 5005 zombies. Re-authenticated via `manual_login.py`. Restarted Bridge. | **Kill-Before-Restart**: `live_monitor.py` now executes `kill_zombies.ps1` before every Bridge restart attempt. |
| **Silent Login Failure** | Startup sequence assumed authentication was valid. `live_monitor.py` launched into a failed state and didn't provide enough friction to alert the user. | Implemented "Pre-Flight Gate" in `start.bat` using `check_account_status.py`. | **Pre-Flight Gate**: `start.bat` now aborts with a critical error if Robinhood authentication is not verified at launch. |

---

### 📅 MARCH 24, 2026: MAINTENANCE AUDIT & SYSTEM HARDENING

| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **UnicodeEncodeError on Startup** | Port 5007 lock-collision handler tried to `print("⚠️...")` — emoji crashed cp1252 terminal. `monitor_debug.err` confirmed traceback. | Wrapped stdout/stderr with UTF-8 in `main()`. Also added `SET PYTHONIOENCODING=utf-8` to `start.bat`. | **Emoji Safety**: All print paths now use `errors='replace'` fallback. |
| **Zombie Killer Self-Termination** | `kill_zombies.ps1` matched all `dexter-quant-agent` Python PIDs, including the monitor that just launched it. | Added `-ExcludePid` param to script; `live_monitor.py` passes `os.getpid()` at both startup and 9:00 AM calls. | **Self-Exclusion Pattern**: PID always protected during zombie sweeps. |
| **Wrong Python Venv in Subprocesses** | `live_monitor.py` used `sys.executable` for subprocess calls. If launched from system Python, all subprocesses would fail to import `yfinance`, `robin_stocks`, etc. | Resolved `quant-env/Scripts/python.exe` path explicitly as `VENV_PYTHON` at startup with fallback. | **VENV_PYTHON**: Single resolved path used for all 6 subprocess call sites. |
| **Infinite-Loop Risk in Bridge Auth Retry** | `bridge_server.py` called `return place_order()` (recursive) on auth failure. A persistent error would recurse infinitely. | Replaced with one-shot inline retry block after re-login. Options not retried (too risky without manual review). | **No Recursion for Auth**: Auth retry always uses inline re-execution, never recurse. |
| **Malformed Dashboard Board** | Orphan `:--- \|` row present in ACTIVE TESTING section — broken markdown table. | Removed orphan row. Board re-validated. | **Board Validation**: `rebuild_board.py` can detect and fix these at any time. |
| **Strategy Registry Mismatch** | `active_testing` array was empty; 16 strategies referencing `active_testing/` scripts were in `live_trading`. EOD cleanup logic and board sectioning were incorrect. | Moved 16 `active_testing/` strategies to correct array. 5 core live strategies remain in `live_trading`. | **Registry Hygiene**: script path must match the registry category bucket. |
| **Bloated Logs / Scratch Files** | `bridge_stderr.log` at 862 KB, `pre_market_audit.log` at 430 KB; 6 diagnostic `dexter_procs*.txt` in `tmp/`. | Rotated both logs (kept 200 lines each, archived ~16K lines total). Deleted scratch files. Moved `temp_log.txt`, `clean_log.txt` to `logs/`. Moved `heikin_ashi_btc.py` to `strategies/incubator/`. | **Weekly Rotation**: Logs should be rotated weekly. Consider adding a cron in `live_monitor.py` at 5:00 PM Sunday. |


### 🚨 9:00 AM PRE-MARKET FINAL CHECKLIST
Before the market opens, Dexter MUST verify:
- [x] **FailLog Audit**: Read [FailLog.md](file:///C:/Users/jmgra/antigravityagents/dexter-quant-agent/FailLog.md) and confirm all past issues are mitigated (Check off items).
- [x] **Process Audit**: Run `tasklist /FI "IMAGENAME eq python.exe"`. Ensure ONLY 2 processes (1 Bridge, 1 Monitor) are running.
- [x] **Zombie Extraction**: Terminate any duplicate `python.exe` PIDs immediately.
- [x] **Bridge Handshake**: Run `Invoke-RestMethod -Uri http://localhost:5005/positions`. Confirm JSON response.
- [x] **Heartbeat Check**: Verify [LIVE_STRATEGY_BOARD.md](file:///C:/Users/jmgra/antigravityagents/dexter-quant-agent/dashboard/LIVE_STRATEGY_BOARD.md) heartbeat is within the last 30 seconds.

---

### 📅 MARCH 11, 2026: SESSION EXPIRY & DIAGNOSTIC GAP
| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **MFA Trade Block** | Robinhood session expired requiring manual Device Approval. `live_monitor.py` triggered morning reports but ignored the "Bridge Offline" status. | Manually approved device and patched Bridge for resilient position fetching. | **Hard Handshake**: `live_monitor.py` now probes Bridge health/auth every 5m and fails **LOUDLY** on board if unauthorized. |
| **TOTP Secret Gap** | User confirmed `TOTP_SECRET` is not available in `.env` for privacy/dynamic reasons. | Manual approval is the current standard. | **Manual Approval SOP**: If dashboard shows `🚨 CRITICAL`, user must approve on mobile RH app immediately. |
| **Zombie Deadlock** | Duplicate Python processes from stale sessions locked file handles (`signal_cache.pkl`) & stalled execution at 9:30 AM. | Terminated all duplicate PIDs & manually cleared stale dashboard. | **9:30 AM Audit**: Added mandatory process audit to SOP to clear deadlocks before open. |
| **Stale Data Block** | Aggressive 8h stale limit for daily data and 1.5x threshold for intraday data discarded all signals. | Patched limits (36h for daily, 2.5x for intraday) & fixed BigD/MACD pathing/math crashes. | **Signal Audit**: Alpha Engine now tracks "Drop Rate" and alerts if 100% of signals are rejected as STALE. |


---

### 📅 MARCH 10, 2026: RETIRING SHORT-TERM STRATEGIES (< 5 MIN)
| Issue | Root Cause | Resolution | Prevention Strategy |
| :--- | :--- | :--- | :--- |
| **High Frequency Slippage** | 1-min & 2-min strategies (Double Break, Matt-Rapid, SMC, etc.) suffered from high execution slippage. | Moved all < 5m strategies to `strategies/short-term` archive. | **Timeframe Filter**: Dexter now focuses on 5m+ timeframes as the "Hard Floor" for trading. |

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
