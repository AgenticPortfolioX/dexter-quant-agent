# Implementation Plan - Basket Backtest (20 Assets, 2 Years)

## 1. Goal
Evaluate the "Wickless Candle" strategy's robustness across a diverse basket of 20 assets over a 2-year period (2024-2026) to confirm cross-market viability.

## 2. Trinity Basket (Live Testing Focused)
Optimized for the highest win rate and profit factor:
- **USDJPY=X** (62.9% WR)
- **EURJPY=X** (66.7% WR)
- **GC=F (Gold)** (54.8% WR)

## 3. Deployment Phase: Forward Testing
- **Environment**: Forward-testing (Paper Trading logic).
- **Scanner**: Real-time signal identification via `trinity_test_scanner.py`.
- **Interval**: 1h (Hourly checks).

## 3. Technical Adjustments
- **Timeframe**: Upgraded to **1h** (required for 2-year data retention on yfinance).
- **Data Fetching**: Automated loop with error handling for split/missing data.
- **Aggregation**: New `BasketBacktester` class to track individual asset performance and global equity curve.
- **Performance**: Metrics for Total Basket Win Rate, Profit Factor, and Asset-Specific Strengths.

## 4. Execution Steps
- [ ] Step 1: Refactor `wickless_candle_strategy.py` into a multi-asset engine.
- [ ] Step 2: Implement `fetch_basket_data` with 2-year/1h parameters.
- [ ] Step 3: Execute global backtest.
- [ ] Step 4: Generate Multi-Asset Performance Dashboard.
