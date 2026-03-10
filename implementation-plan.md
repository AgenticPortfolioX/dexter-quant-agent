# Implementation Plan - Fix Fractional Order Rejections & Data Integrity

## Problem Statement
The Dexter agent is attempting to place fractional orders for `CLNK` and other assets that are being rejected by Robinhood with the error: `"Fractional orders must be at least $1."` 
Despite a target trade size of $25 (or $12.50 in Caution Mode), the calculated quantities are resulting in sub-$1 notional values. This is likely caused by:
1.  **Data Contamination**: Concurrent `yfinance` calls in a thread pool are leading to incorrect price data being assigned to tickers (e.g., `CLNK` getting price data from a higher-priced asset).
2.  **Missing Notional Guard**: The execution layer lacks a final check to ensure the calculated order value meets the broker's minimum.
3.  **Ticker Ambiguity**: `CLNK` is a new ETF and might be causing issues with `yfinance` heuristics.

## Proposed Changes

### 1. Execution Layer Protection (`strategies/validation/alpha_autotrader.py`)
- Add a `MIN_NOTIONAL_USD = 2.0` constant to ensure all orders have a safety margin above the $1 limit.
- Update `execute_trade` to abort if `quantity * price < MIN_NOTIONAL_USD`.
- Improve error logging to specifically flag "Sub-Minimum Notional" attempts.

### 2. Data Integrity Engine (`strategies/validation/alpha_autotrader.py`)
- **De-parallelize `yfinance`**: Change the data fetching strategy from `ThreadPoolExecutor` to a sequential loop with a small delay (`time.sleep(0.1)`) to prevent session/buffer collisions.
- **Enhanced Validation**: In `fetch_worker`, explicitly check if the downloaded data's ticker metadata (if available) matches the requested ticker.
- **Sanity Check**: Add a check to compare the currentFetchedPrice with the last 24h average. If it deviates by >50%, flag it as a data anomaly and skip the signal.

### 3. Ticker Optimization (`strategy_registry.json`)
- Evaluate if `CLNK` should be replaced with `LINK-USD` for more reliable data fetching if the ETF is problematic. (For now, we will focus on the logic fixes).

## Step-by-Step Checklist
- [x] 1. Modify `alpha_autotrader.py`: Add `MIN_NOTIONAL_USD` and implement guard in `execute_trade`.
- [x] 2. Modify `alpha_autotrader.py`: Replace `ThreadPoolExecutor` in `run_alpha_autotrader` with a robust sequential or throttled producer.
- [x] 3. Modify `alpha_autotrader.py`: Add price sanity checking in `process_signal_and_execute`.
- [x] 4. Verify the fix by running a test scan.

## Failure Prevention
- **Process Monitoring**: `live_monitor.py` will continue to check for "Stuck" processes.
- **Detailed Logging**: `bridge_raw.log` visibility is already improved; we will monitor it for further rejections.
