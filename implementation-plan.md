# Implementation Plan: Dexter System Audit & Modernization Roadmap

## Overview & Current State
- **Trading Status**: Fully PAUSED / OFFLINE (scheduled tasks disabled, background ports 3000/5005/5007 closed).
- **Core Engine**: Bun/TypeScript (`dexter-core`) + Python live monitor daemon (`live_monitor.py`) + Alpha execution engine (`alpha_autotrader.py`).
- **Broker Interface**: Robinhood via unofficial `robin_stocks` bridge on Port 5005.

---

## 1. AI Layer: DeepSeek API Integration
- [x] Update `dexter-core/src/model/llm.ts` to route DeepSeek calls to official public endpoint `https://api.deepseek.com`.
- [x] Configure `DEEPSEEK_API_KEY` and recommend `deepseek-chat` for fast inference.
- [x] Verified model factory instantiation with Bun.

---

## 2. Bitcoin 2x Leveraged ETF Execution: BITU (2x Long) & SBIT (2x Short)
- [x] **2x Long Mapping**: Implemented `LONG_MAP` in `alpha_autotrader.py`, `big_d.py`, and `little_d.py`. All bullish BTC setups (BTC-USD, IBIT, BITU) automatically execute via **`BITU`** (ProShares Ultra Bitcoin ETF).
- [x] **2x Short Mapping**: Updated `INVERSE_MAP` / `SHORT_MAP`. All bearish/short BTC setups automatically execute via **`SBIT`** (ProShares UltraShort Bitcoin ETF).
- [x] **Dynamic Position Sizing & Price Resolution**: Added automatic price lookup for mapped targets (`BITU` / `SBIT`) to prevent dollar miscalculations when signals originate from high-denomination feeds (`BTC-USD`).
- [x] **Reversal & Holding Tracker**: Updated `is_held`, `EXIT`, and `SHORT`/`LONG` reversal routines to cleanly identify and liquidate the active leg (`BITU` or `SBIT`).
- [x] **Strategy Registry**: Updated `strategy_registry.json` to include `BITU` in active assets for `BigD` and `LittleD`.

---

## 3. Risk Engine: Bracket Exits & Daily Circuit Breaker (Leveraged Bitcoin ETFs)
- [x] **Entry Position Tracker**: On entry, record `entry_price`, `symbol` (`BITU` or `SBIT`), and `side` (`LONG` or `SHORT`) into persistent `cache/etf_positions.json`.
- [x] **15-Second PnL Loop**: In `live_monitor.py` and `alpha_autotrader.py`, calculate unrealized PnL % directly on the ETF price.
- [x] **Price-Based Exits**:
  - Stop Loss: Exit if PnL <= -2.0% (`Stop Loss (-2% on 2x ETF)`).
  - Take Profit: Exit if PnL >= +4.0% (`Take Profit (+4% on 2x ETF)`).
- [x] **Max Hold Period**: Force-exit at maximum holding period (`ETF_MAX_HOLD_MINUTES`, default 240 mins) labeled `Max Hold Period`.
- [x] **Daily Circuit Breaker**: Flatten all ETF positions and pause new entries if daily equity drawdown exceeds threshold (`DAILY_CIRCUIT_BREAKER_PCT`, default 4.5%).
- [x] **Verification**: Unit & simulation testing for all exit scenarios and circuit breaker trip conditions.

---

## 4. Desktop Reliability Hardening: Live Monitor & Bridge Resiliency
- [x] **Heartbeat File & State (`cache/heartbeat_status.json`)**:
  - Updates every 15-second cycle with timestamp (EST), PID, open leveraged ETF positions, broker connectivity, latency, and status.
- [x] **Broker Reconnection & Exponential Backoff**:
  - Active health probing every cycle with fast timeout (3s).
  - Exponential backoff (5s, 10s, 20s, 40s, max 60s) on bridge dropouts.
  - Automatic restart of bridge process with zombie purge.
- [x] **Comprehensive Alerts (Slack)**:
  - Process restart notification with uptime & active state.
  - Broker disconnection alert (>60s) and reconnection alert.
  - Enhanced Stop-Loss, Take-Profit, Max-Hold, and Circuit-Breaker alerts.
- [x] **Isolated Exception Handling**:
  - Ensure main polling loop catches all exceptions, logs tracebacks, and never terminates unexpectedly.
- [x] **Task Scheduler Configuration Guide**:
  - Document auto-restart, sleep prevention, and privilege settings for desktop deployment in `docs/TASK_SCHEDULER_DESKTOP_SETUP.md`.

---

## 5. Broker Migration: Interactive Brokers (IBKR)
- [ ] Develop `ibkr_bridge.py` using `ib_insync` / IBKR TWS API on Port 5006.
- [ ] Support native equity shorting, margin trading, and real-time streaming fills.
- [ ] Switch order routing in `alpha_autotrader.py` from Robinhood (Port 5005) to IBKR (Port 5006).
- [ ] Paper trading validation on IBKR TWS Paper Account.

---

## 6. Infrastructure: Desktop vs VPS Deployment
- [ ] Evaluate Desktop vs 24/7 Cloud VPS (AWS EC2 / Contabo / Vultr Windows Server).
- [ ] Configure IB Gateway + IBC on VPS to automate daily 24-hour IBKR re-authentication.
- [ ] Prevent sleep/power state interrupts and ensure 99.99% uptime during US market hours (8:00 AM - 5:00 PM EST).

---

## 7. Live Strategy Board Rebuild & Multi-Strategy Backtesting Suite
- [x] **Live Strategy Board Rebuild (`dashboard/LIVE_STRATEGY_BOARD.md`)**:
  - Populated all 23 live trading strategies from `strategy_registry.json`.
  - Harmonized column headers (`Asset`, `Strategy`, `Quantity`, `Status`, `Win Rate`, `Profit Factor`) with `alpha_autotrader.py` and `live_monitor.py`.
  - Verified non-destructive regex replacement in `live_monitor.py` preserving strategy entries.
- [x] **Live Strategies Backtesting Suite (`scripts/run_all_live_backtests.py`)**:
  - Universal backtest engine covering all 23 live trading strategies with local market data caching (`cache/backtest_data/`).
  - Executed across appropriate historical timeframes:
    - 5m Intraday (Sonnet S1, Gemini Velocity, Volcanix, BigD): 60 Days.
    - 1h Swing (Apex, LittleD, SMC Bitcoin, NY ORB, Wickless Candles, Dynamic Bias, Nova, AO, MACD, BB, SS, DT, HA, Strategy OS): 180 Days.
    - Daily S-Series Mean Reversion (S1, S2, S3, S4, S5): 2 Years.
  - Applied calibrated leveraged Bitcoin ETF rules (2% SL / 4% TP) for `BITU` and `SBIT`.
  - Evaluated core quant performance metrics: Total Trades, Win Rate (%), Profit Factor, Max Drawdown (%), and Total Return (%).
  - Generated consolidated JSON report (`cache/live_strategies_backtest_results.json`) and Markdown summary report (`dashboard/LIVE_STRATEGIES_BACKTEST_REPORT.md`).
  - Linked and populated backtest metrics directly into `dashboard/LIVE_STRATEGY_BOARD.md`.

---

## 8. Strategy Governance: Decommission Sub-1.10 PF Strategies to `strategies/meh/`
- [x] **Identify & Relocate Sub-1.10 PF Strategies**:
  - Identified all 14 strategies with Profit Factor < 1.10 from empirical backtest results:
    - `Gemini Velocity` (PF 0.97)
    - `BigD (PO3/AMD)` (PF 1.07)
    - `LittleD (SFP)` (PF 1.02)
    - `Volcanix (VWAP Reclaim)` (PF 0.75)
    - `NY ORB` (PF 0.65)
    - `Wickless Candles` (PF 1.06)
    - `Dynamic + Daily Bias` (PF 0.99)
    - `Nova (Optimized)` (PF 0.77)
    - `MACD Oscillator (MACD)` (PF 1.00)
    - `Bollinger Bands (BB)` (PF 0.94)
    - `Shooting Star (SS)` (PF 1.05)
    - `Dual Thrust (DT)` (PF 0.91)
    - `Heikin Ashi (HA)` (PF 1.05)
    - `Strategy OS` (PF 0.94)
  - Executed clean file and folder moves into `strategies/meh/` via `scripts/move_sub110_to_meh.py`.
- [x] **Update Strategy Registry & Decommission Live Trading**:
  - Removed all 14 underperforming strategies from `"live_trading"` in `strategy_registry.json`.
  - Retained exclusively the 9 high-conviction strategies (PF >= 1.10) in `"live_trading"`:
    - `Apex (Pivot Bounce)` (PF 3.18)
    - `Low Close IBS (S3)` (PF 2.98)
    - `Turnaround Tuesday (S2)` (PF 2.69)
    - `DeMarker (S4)` (PF 2.62)
    - `High of 10 Days IBS (S5)` (PF 1.86)
    - `Price Retreat (S1)` (PF 1.38)
    - `SMC Bitcoin (2x Leveraged)` (PF 1.14)
    - `Sonnet (ORE + Regime)` (PF 1.12)
    - `Awesome Oscillator (AO)` (PF 1.10)
  - Archived decommissioned strategies under `"meh"` in `strategy_registry.json`.
- [x] **Update Live Strategy Board & Backtest Synchronization**:
  - Rebuilt `dashboard/LIVE_STRATEGY_BOARD.md` to reflect only the 9 live strategies under `## 🟢 LIVE TRADING`.
  - Added `## 🛑 DECOMMISSIONED (MEH)` section displaying all 14 retired strategies with their reasons and backtest metrics.

---

## 9. Strategy Governance: Decommission Sonnet (ORE + Regime) & Awesome Oscillator (AO)
- [x] **File Migration to `strategies/meh/`**:
  - Moved `strategies/Ai-strats/sonnet_ore_regime.py` to `strategies/meh/sonnet_ore_regime.py`.
  - Moved `strategies/active_testing/awesome_oscillator.py` to `strategies/meh/awesome_oscillator.py`.
- [x] **Strategy Registry (`strategy_registry.json`)**:
  - Removed `Sonnet (ORE + Regime)` and `Awesome Oscillator (AO)` from `"live_trading"`.
  - Added to `"meh"` with updated paths and status `DECOMMISSIONED` with reason `Decommissioned by User Request`.
  - Active live strategies updated to 7 elite models (`Apex`, `SMC Bitcoin`, `S1`, `S2`, `S3`, `S4`, `S5`).
- [x] **Live Strategy Board Rebuild (`dashboard/LIVE_STRATEGY_BOARD.md`)**:
  - Regenerated board showing 7 active live trading strategies and 16 decommissioned strategies in `## 🛑 DECOMMISSIONED (MEH)`.
  - Verified non-destructive live monitor cycle.

---

## 10. Bitcoin Strategy Migration: `btc_success` to `live_trading` (BITU / SBIT Exclusive)
- [x] **Strategy Migration & Relocation**:
  - Moved/copied all 7 strategy packages from `strategies/successful_strategies/btc_success/` into `strategies/live_trading/`:
    1. `inside_candle_btc` -> `strategies/live_trading/inside_candle_btc`
    2. `liquidity_sweep_btc` -> `strategies/live_trading/liquidity_sweep_btc`
    3. `power_of_3` -> `strategies/live_trading/power_of_3`
    4. `rsi_btc` -> `strategies/live_trading/rsi_btc`
    5. `smc_btc` -> `strategies/live_trading/smc_btc`
    6. `btc_tech_level_ema` -> `strategies/live_trading/btc_tech_level_ema`
    7. `link-pilled` -> `strategies/live_trading/sfp_btc`
- [x] **Execution Adapter Modification (BITU / SBIT Exclusive)**:
  - Injected `etf_execution_adapter.py` into every migrated strategy folder defining `LONG_ETF = "BITU"`, `SHORT_ETF = "SBIT"`, and `resolve_etf_target(direction)`.
  - Configured 2.0% Stop Loss and 4.0% Take Profit brackets on the ETF price itself.
  - Strictly banned any direct trading of `IBIT`, `BTC-USD`, or `BTC`.
- [x] **Registry & Board Synchronization**:
  - Registered all 7 Bitcoin strategies under `"live_trading"` in `strategy_registry.json` with active assets `["BITU", "SBIT"]`.
  - Re-ran unified backtests across all 13 live trading strategies via `scripts/run_all_live_backtests.py`.
  - Updated `dashboard/LIVE_STRATEGY_BOARD.md` to reflect all 13 live strategies, active assets, win rates, and profit factors.
  - Verified monitor daemon in test mode (`python live_monitor.py --test`) successfully initialized without errors.

---

## 11. Daily 9:30 AM Market Open & Pre-Market Automation Readiness
- **Current Task**: Robinhood Authentication & Daily 9:30 AM Market Open / Pre-Market Automation Readiness
- **Assigned Agent**: Antigravity Orchestrator & Deepseek Coding/Quant Worker
- **Step-by-Step Checklist**:
  - [x] **Robinhood Authentication & Session**: Verified live session via `robin_stocks` with authenticated profile. Cash balance and buying power confirmed ($51.08 USD, Account #592560015). Token persisted in `robinhood.pickle`.
  - [x] **Broker Bridge Resiliency (Port 5005)**: Tested `/health`, `/positions`, and `/cash` endpoints. Added explicit `.env` pathing and UTF-8 output guards in `quant_scripts/bridge_server.py`.
  - [x] **PILOT_LIGHT.json Fix**: Repaired invalid JSON syntax escape in `PILOT_LIGHT.json` to valid `{"enabled": true}`.
  - [x] **Pre-Market Cache Warm-Up (9:00 AM EST)**: Patched `scripts/warm_up_agent.py` to prevent Windows cp1252 `UnicodeEncodeError`. Verified cache generation (`cache/warm_cache.pkl`) in 0.8s across all live asset/timeframe pairs (`BITU`, `SBIT`, `SPY`, `QQQ`).
  - [x] **Morning Market Report (9:00 AM EST)**: Fixed `NameError: name 'qual_consensus' is not defined` and Unicode encoding in `morning_report.py`. Verified macro report compilation, self-healing check, and successful delivery to Slack (`#quant-channel`).
  - [x] **FailLog.md Pre-Market Checklist**: Completed audit of past failure points, verified process limits, and checked off all 5 pre-market gate criteria.
  - [x] **Windows Task Scheduler Automation (8:55 AM EST)**: Enabled `DexterPreMarketWatchdog` task in Windows Task Scheduler (State: `Ready`, Start: 8:55 AM Daily).
  - [x] **Watchdog Hardening**: Added explicit `-WorkingDirectory` parameters to `scripts/pre_market_watchdog.ps1` to prevent path detachment when launched by Task Scheduler.
  - [x] **Live Monitor Daemon (Port 5007)**: Hardened `live_monitor.py` with `PYTHONIOENCODING=utf-8` and `cwd=DEXTER_ROOT` on all subprocess invocations. Confirmed background execution with active heartbeat and `NOMINAL` status.
  - [x] **Dexter Slack Listener**: Verified Slack Socket Mode listener is connected and responding to commands.
- **Completion Status**: 100% Operational & Verified.

---

## 12. Trade Durations, FailLog Audit, Profitability, and Inverse ETF Short Execution
- **Current Task**: Trade Duration Verification, FailLog Prevention Audit, Strategy Profitability & Inverse ETF Shorting
- **Assigned Agent**: Antigravity Orchestrator Brain & Deepseek Coding/Quant Specialist
- **Step-by-Step Checklist**:
  - [x] **Trade Duration & Exit Rules Verified**:
    - Leveraged Bitcoin ETFs (`BITU` / `SBIT`): Strictly intraday. Managed by `evaluate_etf_exits_and_circuit_breaker()` with hard -2.0% Stop Loss, +4.0% Take Profit, 240-minute (4-hour) Max Hold, and forced 3:50 PM EST EOD liquidation. Never held overnight.
    - Scalp / Short-Term Strategies (<= 10m frequency): Strictly intraday. Liquidated at 3:50 PM EST daily via `close_short_term_positions()`.
    - Apex (Pivot Bounce): 1-hour timeframe with 1.2x ATR stop and daily Central Pivot (PP) target. Duration: 4 to 18 hours (intraday or 1-day overnight swing).
    - S-Series Index Mean Reversion (`S1`, `S2`, `S3`, `S4`, `S5`): Daily timeframe on `SPY` and `QQQ`. Exits when Close > Previous Day High. Duration: 1 to 4 trading days (Multi-day swing).
  - [x] **FailLog.md Audit & Code Safeguards**:
    - *April 23 Whipsaw (0/13 Win Rate)*: Guarded by strict `CAUTION_MODE` sizing (50% size reduction or block), removal of correlated tech cluster risk, and advisor gate.
    - *April 21 Local Scope Trap*: Guarded by thread-safe `GLOBAL_ACTIVE_POSITIONS` cache; `find_entry_price` handles both `"EXEC-BUY"` and `"EXEC-SHORT"`.
    - *April 17 & March 11 Session Blackout / Zombie Deadlock*: Guarded by `kill_zombies.ps1` with `-ExcludePid` before every bridge start, `check_account_status.py` pre-flight gate, and `DexterPreMarketWatchdog` daily 8:55 AM task.
    - *March 06 Data Contamination & Sub-$1 Orders*: Guarded by sequential data fetching (`threads=False`, `df.copy()`) and `MIN_NOTIONAL_USD = 2.0` guard in `execute_trade()`.
    - *March 05 Fractional Orders & Silent Errors*: Guarded by `timeInForce='gfd'` in `bridge_server.py` and strict HTTP 400 error returns on `non_field_errors`.
  - [x] **Profitability Confirmed (11 Live Strategies)**:
    - Decommissioned unprofitable models: `Inside Candle` (PF 0.87, Return -19.4%) and `SMC Bitcoin` (PF 0.76, Return -28.2%) moved to `strategies/meh/`.
    - All 11 remaining live strategies have Profit Factor >= 1.27 (up to 3.18) and positive win rates (38.9% - 84.4%).
  - [x] **Short Exposure via Inverse ETFs Confirmed & Expanded**:
    - Robinhood Cash Accounts cannot execute direct margin short sales.
    - All SHORT signals translate into spot BUY orders of inverse ETFs via `INVERSE_MAP`.
    - Mapped 100% of live universe: `BITU` $\rightarrow$ `SBIT` (2x Short BTC), `SPY` $\rightarrow$ `SH` (-1x S&P), `QQQ` $\rightarrow$ `PSQ` (-1x QQQ), `IWM` $\rightarrow$ `RWM`, `SMCI` $\rightarrow$ `SOXS`, `NVDA` $\rightarrow$ `NVDS`, `AMZN` $\rightarrow$ `AMZS`, `META` $\rightarrow$ `METP`, and added `PLTR` $\rightarrow$ `PLTD`, `MSTR` $\rightarrow$ `MSTZ`, `AMD` $\rightarrow$ `AMDD`.
    - Verified all inverse ETF tickers trade actively on US markets with live quotes.
  - [x] **Live Engine End-to-End Verification**:
    - Tested `warm_up_agent.py`: 23 pairs cached in 1.3s with zero errors.
    - Tested `alpha_autotrader.py` and `live_monitor.py --test`: All 11 strategies evaluated, heartbeats live, broker bridge 200 OK.
- **Completion Status**: 100% Verified & Fully Hardened.

---

## 13. Trade Sizing ($10 / Max 5 Trades), IBIT_Success Backtests, and Buzz Platform Cutover
- **Current Task**: Trade Sizing Configuration, IBIT Folder Backtesting Audit, and Delivery Cutover from Slack to Buzz
- **Assigned Agent**: Antigravity Orchestrator Brain & Deepseek Coding/Quant Specialist
- **Step-by-Step Checklist**:
  - [x] **Trade Sizing & Position Limits Updated**:
    - Updated `POSITION_SIZE_USD = 10.0` (from $5.0) in `strategies/validation/alpha_autotrader.py`.
    - Updated `MAX_CONCURRENT_TRADES = 5` (from 4) in `strategies/validation/alpha_autotrader.py`.
    - Verified settlement guard and notional guard ($2.00 minimum) remain fully active.
  - [x] **Comprehensive Backtest Audit of `iBit_success` Strategies**:
    - Ran unified backtest suite across all 7 strategies in `strategies/successful_strategies/iBit_success/` on `IBIT` benchmark:
      1. `RSI Reversion` (`rsi_ibit`): Win Rate **56.5%**, Profit Factor **2.09**, Return **+44.92%**, Max DD 12.47%.
      2. `Link-Pilled SFP` (`link-pilled`): Win Rate **37.9%**, Profit Factor **1.21**, Return **+4.50%**, Max DD 8.55%.
      3. `Liquidity Sweep` (`liquidity_sweep_ibit`): Win Rate **42.5%**, Profit Factor **1.08**, Return **+1.72%**, Max DD 5.88%.
      4. `Tech Level EMA Touch` (`ibit_tech_level_ema`): Win Rate 33.3%, Profit Factor 1.00, Return -0.42%, Max DD 6.75%.
      5. `Power of 3 (PO3/AMD)` (`power_of_3`): Win Rate 29.9%, Profit Factor 0.84, Return -5.13%, Max DD 7.12%.
      6. `SMC Bitcoin` (`smc_ibit`): Win Rate 45.9%, Profit Factor 0.86, Return -17.18%, Max DD 28.62%.
      7. `Inside Candle` (`inside_candle_ibit`): Win Rate 20.5%, Profit Factor 0.68, Return -22.38%, Max DD 25.33%.
    - Generated [IBIT_SUCCESS_BACKTEST_REPORT.md](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/dashboard/IBIT_SUCCESS_BACKTEST_REPORT.md) and cached JSON results.
  - [x] **Buzz Platform Integration & Identity Minting**:
    - Minted unique Nostr Secp256k1 keypair for **Robinhood Trader** using stdlib keygen.
    - Public NPUB: `npub1092gtlvg4vkdk793g2544vyajyjc74g35pzxau5q7f9u05q34qtqn20ydh`.
    - Public HEX: `795485fd88ab2cdb78b142a95ab09d91258f5511a0446ef280f24bc7d011a816`.
    - Private key strictly isolated in local environment files (`.env` in Hermes profile and `config/buzz.env`); never logged, printed, or committed.
    - Verified Hermes profile `robinhood` with `SOUL.md` rules and `buzz-platform` plugin enabled.
    - Installed `buzz.exe` CLI to `.cargo/bin` in PATH.
    - Tested preflight: returned expected `exit 3` (`relay_membership_required`), validating key/socket connectivity.
  - [x] **Delivery Cutover (Slack Retired -> Buzz #Quantative-Analyst Active)**:
    - Created `scripts/buzz_notifier.py` with flat message enforcement, emoji/hashtag stripping, and stdin pipe delivery to `#Quantative-Analyst` (`3038f9b6-a8b8-4208-9b8b-5a48fc0ffa01`) and `#Triage` (`2d6095df-ae60-40fd-ac04-28bc150b9508`).
    - Redirected legacy `scripts/slack_notifier.py` to route all alerts through Buzz, retiring Slack delivery.
- **Completion Status**: 100% Configured & Awaiting Buzz Community Grant.

---

## 14. Live Positions Audit, Strategy Promotion (RSI Reversion & Link-Pilled SFP), and Buzz 5-Channel Activation
- **Current Task**: Open Position Audit, Strategy Promotion to Live Trading, Profile Card & Avatar Setup, 5-Channel Routing & Test Report Delivery
- **Assigned Agent**: Antigravity Orchestrator Brain & Deepseek Coding/Quant Specialist
- **Step-by-Step Checklist**:
  - [x] **Live Positions & Market Execution Audit**:
    - Queried live Robinhood bridge on Port 5005: Portfolio Cash is `$51.0800` USD, Settled Cash is `$51.0800` USD, Stock Positions is `{}` (0 open positions).
    - Investigated why no trades opened today: `market_context.json` triggered `caution_mode: true` (VIX surged to 22.06, Tech sector XLK fell -6.1%, Sector Rotation: `RISK_OFF`).
    - Signals detected (`META` buy on Apex, `SBIT` shorts on Liquidity Sweep & RSI Reversion) were tagged `META-CAUTION` and `SBIT-CAUTION` by `alpha_autotrader.py` (lines 1167-1169). The system intentionally blocked new entries to preserve capital during an aggressive risk-off selloff.
  - [x] **Strategy Promotion to Live Trading (`RSI Reversion` & `Link-Pilled SFP`)**:
    - Promoted `RSI Reversion` to live trading in `strategy_registry.json` and [LIVE_STRATEGY_BOARD.md](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/dashboard/LIVE_STRATEGY_BOARD.md) with active asset basket `["IBIT", "BITU", "SBIT", "CLNK", "ETHE", "IREN"]` (Win Rate 56.5% on IBIT / 48.4% on 2x BTC, PF 2.09 on IBIT / 1.88 on 2x BTC).
    - Promoted `Link-Pilled SFP` to live trading in `strategy_registry.json` and [LIVE_STRATEGY_BOARD.md](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/dashboard/LIVE_STRATEGY_BOARD.md) with active asset basket `["IBIT", "BITU", "SBIT", "CLNK", "ETHE", "IREN"]` (Win Rate 37.9% on IBIT / 40.5% on 2x BTC, PF 1.21 on IBIT / 1.36 on 2x BTC).
  - [x] **Buzz Profile Card & Avatar Setup**:
    - Created clean circular PNG avatar (`robinhood_avatar_clean.png`) and uploaded to Blossom media store: `https://gramsagency.communities.buzz.xyz/media/f34181d16c817d12aed4f00b4e88af6f84c8af7ec9e12f124dfeb2d524a848b3.png`.
    - Set profile card via `buzz users set-profile --name "Robinhood Trader" --about "US equities trading agent. Pre-market and post-market reports: movers, levels, catalysts, risk." --picture <avatar_url>`.
    - Verified authentication via `buzz users get`: returned clean profile JSON (exit code 0, no `relay_membership_required`).
  - [x] **5-Channel Environment Configuration & Routing**:
    - Configured `BUZZ_CHANNELS` and `BUZZ_HOME_CHANNEL` in `C:\Users\jmgra\AppData\Local\hermes\profiles\robinhood\.env` and `config/buzz.env`:
      - `#Quantative-Analyst` (Home/Reports): `3038f9b6-a8b8-4208-9b8b-5a48fc0ffa01`
      - `#Agency` (Coordination): `e1780684-d98c-5afa-b31c-86bda7971e83`
      - `#Deliverables` (Full reports & files): `41245ad4-b799-438f-8022-01c787feac8d`
      - `#Notifications & Alerts` (Completions): `48a0070d-3596-4d07-92a6-3a9362393d62`
      - `#Triage` (Failures/Errors with cause & fix): `2d6095df-ae60-40fd-ac04-28bc150b9508`
    - Gateway restarted and active (PID 62232).
  - [x] **Test Report Delivery to #Quantative-Analyst**:
    - Delivered test post directly to `#Quantative-Analyst` (`3038f9b6-a8b8-4208-9b8b-5a48fc0ffa01`) confirming pre-market and post-mortem routing readiness (Event ID: `2b124a6514cde4197e9abd28529aa02242702979ed5cc1308f1398ea50898990`).
  - [x] **Slack Delivery Retirement**:
    - Confirmed all Slack deliveries ended and rerouted to Buzz via `scripts/buzz_notifier.py` and `scripts/slack_notifier.py`.
- **Completion Status**: 100% Complete & Verified.

---

## 15. IBIT -> BITU/SBIT Asset Alignment, Asymmetric Volatility Guardrails, and Bridge Outage Hardening
- **Current Task**: Migrate IBIT to BITU (Long) and SBIT (Short), Exempt Short Trades from Volatility Guardrails, Root Cause Analysis & Hardening for 176s Bridge Outage
- **Assigned Agent**: Antigravity Orchestrator Brain & Deepseek Coding/Quant Specialist
- **Step-by-Step Checklist**:
  - [ ] **IBIT to BITU / SBIT Full Asset Alignment**:
    - Update `strategy_registry.json`: remove `IBIT` from active assets for `RSI Reversion` and `Link-Pilled SFP`. Replace with `BITU` (2x Bull) and `SBIT` (2x Bear). Ensure all live Bitcoin strategies trade strictly `BITU` on bullish setups and `SBIT` on bearish setups.
    - Update [dashboard/LIVE_STRATEGY_BOARD.md](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/dashboard/LIVE_STRATEGY_BOARD.md) active assets column for `RSI Reversion` and `Link-Pilled SFP`.
  - [ ] **Asymmetric Volatility Guardrails (Alpha Autotrader)**:
    - Modify `alpha_autotrader.py` (lines 1163-1170): Apply `CAUTION_MODE` blocking ONLY to `BUY`/`LONG` entries.
    - Exempt `SHORT` signals from `CAUTION_MODE` entry blocking. Volatility and market selloffs represent favorable regimes for inverse ETF entries (`SBIT`, `SH`, `PSQ`, `SOXS`, `NVDS`).
    - Modify position sizing (lines 951-953): 50% size reduction applies exclusively to `BUY`/`LONG` trades under `CAUTION_MODE`. Short/inverse trades receive full ($10.00) sizing during elevated volatility.
  - [ ] **Bridge Outage Root Cause Analysis (176s Downtime at 15:43-15:45 EST)**:
    - Document forensic timeline: At 15:42:23 EST, local `/health` request timed out (consecutive failures: 1, duration: 87s).
    - `live_monitor.py` triggered Buzz disconnect alert at 15:43:50 EST and executed `kill_zombies.ps1` to purge stalled PID 71256.
    - Respawned `quant_scripts/bridge_server.py` (PID 73284), which executed Robinhood TOTP authentication handshake (~30-50s).
    - Reconnected at 15:45:19 EST (latency 2051ms) and published reconnection alert (downtime: 176s).
    - Root cause: Single-threaded Flask development server in `bridge_server.py` blocked local `/health` probes during concurrent Robinhood API network I/O, tripping the 3.0s health timeout.
  - [ ] **Bridge Resiliency Hardening**:
    - Update `quant_scripts/bridge_server.py`: enable `app.run(host='0.0.0.0', port=5005, threaded=True)` to handle `/health` concurrently on an independent thread.
    - Update `live_monitor.py`: increase health check timeout from 3.0s to 8.0s to prevent false-positive disconnect triggers during minor network latency spikes.
  - [ ] **End-to-End System Verification**:
    - Verify `alpha_autotrader.py` and `live_monitor.py` evaluate short signals without caution blocking.
    - Confirm live monitor heartbeat and strategy board reflect updated active assets.
- **Completion Status**: In Progress.

---

## 16. Apex (Pivot Bounce) Ticker Universe Expansion & >60% WR / >2.0 PF Strategy Audit
- **Current Task**: Discover High-Conviction Tickers for `Apex (Pivot Bounce)` and Audit All Strategies with >60% Win Rate and Profit Factor > 2.0
- **Assigned Agent**: Antigravity Orchestrator Brain & Dexter [AI Quant Agent]
- **Step-by-Step Checklist**:
  - [x] **54-Ticker Empirical Scan for `Apex (Pivot Bounce)` (`180d`, `1h` + Daily Pivots)**:
    - Audited 54 liquid US equities and ETFs via [scan_apex_tickers.py](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/scratch/scan_apex_tickers.py).
    - Identified 12 elite expansion tickers (`CRWD`, `ABNB`, `SNOW`, `GOOGL`, `XBI`, `TSLA`, `HOOD`, `TQQQ`, `UBER`, `GLD`, `LRCX`, `AAPL`) that elevate overall basket Win Rate from `76.5%` to `82.0%` and Profit Factor from `2.97` to `4.22` across `739` signals.
  - [x] **Cross-Repository Audit of >60% Win Rate & >2.0 Profit Factor Strategies**:
    - Audited live, incubator, and candidate models via [scan_high_wr_pf_strategies.py](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/scratch/scan_high_wr_pf_strategies.py).
    - Confirmed 3 currently live S-Series models (`S2`, `S3`, `S4`) plus 4 high-conviction expansion/incubator models (`S5 Expanded`, `S1 Expanded`, `Triple RSI Mean Reversion`, and `Connors RSI(2) Pullback`) that exceed `60%` Win Rate and `2.0` Profit Factor.
  - [x] **Deployed All 12 New Apex Tickers (20-Ticker Live Basket)**:
    - Updated [strategy_registry.json](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/strategy_registry.json), [pivot_rsi_divergence.py](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/strategies/Ai-strats/pivot_rsi_divergence.py), [alpha_autotrader.py](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/strategies/validation/alpha_autotrader.py), and [LIVE_STRATEGY_BOARD.md](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/dashboard/LIVE_STRATEGY_BOARD.md) with the 20-ticker basket (`82.0%` WR, `4.22` PF).
  - [x] **Short / Inverse ETF Audit for Apex (Bearish Regimes & Short Action)**:
    - Backtested 35 Inverse/Short ETFs via [test_apex_short_etfs.py](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/scratch/test_apex_short_etfs.py).
    - Identified 12 Elite Short ETFs (`MSTZ`, `CONI`, `TSLQ`, `NVDS`, `SARK`, `TZA`, `SOXS`, `LABD`, `SPXU`, `TECS`, `SBIT`, `GLL`) achieving `83.5%` Win Rate / `4.81` PF on `S1` support bounces (`158` signals, `+488.60%` sum return) and `77.2%` Win Rate / `3.78` PF on full bidirectional Apex (`434` signals, `+1,428.10%` sum return).
    - Verified `R1` short signals across the 20 underlying Apex tickers achieve `81.4%` Win Rate and `4.11` PF (`424` signals) and automatically route to Inverse ETFs via `INVERSE_MAP`.
    - Added `INVERSE_BEAR_ETFS` exemption in [alpha_autotrader.py](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/strategies/validation/alpha_autotrader.py) so direct `BUY` signals on Short ETFs are never blocked or size-reduced during `CAUTION_MODE`.
  - [x] **Created & Deployed 2nd Apex Strategy: `Apex Bearish (Short ETF Bounce)`**:
    - Created [apex_short_etf_bounce.py](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/strategies/Ai-strats/apex_short_etf_bounce.py) (`ApexShortETFBounceStrategy`).
    - Excluded low-signal Short S&P 500 (`SPXU`) and deployed the 12 high-conviction Short ETFs (`MSTZ, CONI, SOXS, TSLQ, TZA, NVDS, LABD, GLL, ZSL, TECS, SARK, SBIT`) achieving `81.4%` Win Rate and `3.94` Profit Factor across `183` signals (`180d`, `1h`).
    - Registered in [strategy_registry.json](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/strategy_registry.json), wired `'apex_short_etf'` worker in [alpha_autotrader.py](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/strategies/validation/alpha_autotrader.py), added backtest handler in [run_all_live_backtests.py](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/scripts/run_all_live_backtests.py), and updated [LIVE_STRATEGY_BOARD.md](file:///c:/Users/jmgra/antigravityagents/dexter-quant-agent/dashboard/LIVE_STRATEGY_BOARD.md).
- **Completion Status**: 100% Complete & Deployed.

---

## 17. Backtest Data & Results Relocation to Central Reporting Archive
- **Current Task**: Migrate All Historical Backtest Data Caches and Results Outside Root Workspace to `reporting-repo` to Prevent Bloat
- **Assigned Agent**: Antigravity Orchestrator Brain & Dexter [AI Quant Agent]
- **Target Destination**: `C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\backtests`
- **Step-by-Step Checklist**:
  - [x] Create dedicated subdirectories in reporting-repo: `market_data_cache/` and `results/`.
  - [x] Migrate all 240+ cached market data CSVs (~31.7 MB) from `cache/backtest_data/` to `reporting-repo/dexter-quant/backtests/market_data_cache/`.
  - [x] Migrate `live_strategies_backtest_results.json` and `ibit_success_backtest_results.json` from `cache/` to `reporting-repo/dexter-quant/backtests/results/`.
  - [x] Migrate scratch scan results (`apex_scan_results.json`, `apex_short_etf_results.json`, `high_wr_pf_strategies.json`) to `reporting-repo/dexter-quant/backtests/results/`.
  - [x] Clean up and delete `cache/backtest_data/` directory from `dexter-quant-agent`.
  - [x] Reconfigure `run_all_live_backtests.py`, `run_ibit_folder_backtests.py`, `rebuild_board.py`, and `move_sub110_to_meh.py` to point directly to the centralized reporting-repo archive.
  - [x] Test and verify board generation and script execution with external backtest storage.
- **Completion Status**: 100% Complete & Verified.

---

## 18. Buzz Triage Channel Routing & Broker Bridge Downtime Root-Cause Fix
- **Current Task**: Route All Error/System Alerts to Buzz `#Triage` Channel & Eliminate 15-Minute Broker Bridge Downtime Loop
- **Assigned Agent**: Antigravity Orchestrator Brain & Dexter [AI Quant Agent]
- **Root Causes Identified**:
  1. **Channel Misrouting**: `scripts/slack_notifier.py` forwarded all `send_dexter_slack_alert()` calls to `send_buzz_message()` using default `#Quantative-Analyst` channel (`3038f9b6-a8b8-4208-9b8b-5a48fc0ffa01`) instead of `#Triage` (`2d6095df-ae60-40fd-ac04-28bc150b9508`).
  2. **15-Minute Watchdog Assassination Bug**: `scripts/pre_market_watchdog.ps1` ran every 15 minutes (`15:12`, `15:27`, `15:42`, `15:57`) and checked `Get-NetTCPConnection -LocalPort 5007 -State Listen`. On Windows 11, WMI reported `State = Closed` on loopback port 5007 (`Monitor:False, Bridge:True`), causing the watchdog to execute `kill_zombies.ps1 -Force` — which killed the healthy `bridge_server.py` every 15 minutes and failed to relaunch it because `$bridgeRunning` had evaluated to `$true` prior to the kill.
  3. **2,045ms Windows IPv6 `localhost` Penalty**: Calling `http://localhost:5005` incurred a 2,000ms TCP SYN timeout on IPv6 `[::1]` before falling back to IPv4 `127.0.0.1`.
  4. **Premature Disconnect Duration Calculation**: `BrokerBridgeManager` in `live_monitor.py` computed `disconnect_dur` from the start of the prior cycle (`~80s` earlier during live scans), causing `Consecutive Failures: 1` to immediately report `>60s` downtime.
- **Step-by-Step Checklist**:
  - [x] Update `scripts/buzz_notifier.py` and `scripts/slack_notifier.py` to route all errors, bridge status alerts, restarts, and circuit breaker messages strictly to `#Triage` (`2d6095df-ae60-40fd-ac04-28bc150b9508`).
  - [x] Fix `scripts/pre_market_watchdog.ps1` to verify processes via `Win32_Process`, `heartbeat_status.json`, and `http://127.0.0.1:5005/health` instead of flaky `Get-NetTCPConnection -State Listen`, and never kill healthy `bridge_server.py` processes.
  - [x] Protect `bridge_server.py` and `dexter_slack_listener.py` in `scripts/kill_zombies.ps1` so routine zombie sweeps never terminate active bridge or listener daemons.
  - [x] Replace `http://localhost:5005` with `http://127.0.0.1:5005` across `live_monitor.py`, `alpha_autotrader.py`, `self_healing_agent.py`, and `pre_market_watchdog.ps1` to cut latency from ~2,050ms to <5ms.
  - [x] Harden `BrokerBridgeManager` in `live_monitor.py` with immediate retry, accurate `first_failure_ts` downtime tracking, and targeted bridge restart.
  - [x] Restart clean single instances of `bridge_server.py`, `live_monitor.py`, and `DexterPreMarketWatchdog`, and verify <10ms bridge latency.
- **Completion Status**: 100% Complete & Verified (`2.8ms` bridge latency).
