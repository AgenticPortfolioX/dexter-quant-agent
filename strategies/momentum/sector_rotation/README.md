# Momentum Strategy 2: Sector Rotation (Narrative)

## Goal
Own the strongest sectors when the market is in an uptrend, using momentum to catch rotations early.

## Universe
- **11 SPDR Sector ETFs**: XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY.
- **Benchmark**: SPY.

## Data Sources
- **yfinance**: (daily OHLC, volume, adjusted close).
- **CRITICAL**: Always use **Adjusted Close** for all price and ROC calculations (accounts for dividends).

## Storage
SQLite table `sector_rankings` with columns:
`date`, `sector`, `roc_20d`, `rank`, `correlation_matrix` (optional).

## Logic Steps
1. **Fetch adjusted closes** for all 11 ETFs and SPY for 21 days (to compute 20d ROC).
2. **Market Filter**: Trade only if SPY is above its **200-day SMA**. Otherwise, hold cash.
3. **Momentum Calculation**: Compute 20-day Rate of Change (ROC) for each ETF.
4. **Ranking**: Rank by ROC_20d. Keep top 3.
5. **Diversification Rule**: 
    - Compute 1-month rolling correlation between top two candidates.
    - If correlation > 0.85, skip #2 and take #3 instead. Repeat until two positions have correlation ≤ 0.85.
6. **Entry**: First trading day of month at open. Buy top 2 qualified sectors (50% each).

## Exit / Rebalance
- **Monthly**: Rebalance on the first trading day of next month.
- **Intra-month**: Sell immediately if a sector price falls below its **200-day SMA**.
- **Market Fail**: Hold cash if SPY falls below 200-day SMA.

## API Requirements
**Primary API: yfinance (FREE)**
- **Why it fits**: Free, open-source Python library. Handles adjusted close prices correctly.
- **Note**: While yfinance is free, this strategy is currently categorized for **FUTURE DEPLOYMENT** to maintain separation from funded live strategies.

**Alternative (Reliability)**: Alpha Vantage
- **Cost**: Paid plans start around $50/mo for high volume.
