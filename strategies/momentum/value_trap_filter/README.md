# Momentum Strategy 3: Value Trap Filter (Quality Gatekeeper)

## Goal
Prevent buying stocks that look cheap but are fundamentally broken. This filter runs before any other strategy’s buy signal is executed.

## Data Sources
- **SimFin (Free Tier)**: Primary for clean, standardized fundamental data (Income Statement, Balance Sheet, Cash Flow).
- **yfinance**: Fallback for price data and basic ticker statistics.

## Key Metrics
- **Interest Coverage Ratio**: EBIT / Interest Expense.
- **FCF Yield**: Free Cash Flow / Market Cap.
- **Altman Z-Score**: Bankruptcy risk assessment.
- **PE vs Historical**: Trailing P/E compared to 5-year median P/E.

## Logic Steps
1. **Trigger Condition**: Only processes stocks down >15% over the last 6 months.
2. **Solvency Check**: Interest Coverage Ratio must be **> 3.0**. (Zero interest expense passes if EBIT is positive).
3. **Cash Flow Check**: FCF Yield must be **> 5%**.
4. **Bankruptcy Risk**: Altman Z-Score must be **> 1.8**.
5. **Valuation Check**: Current Trailing P/E must be **< 5-year Average P/E**.
6. **Nuanced Earnings Quality (Sloan Ratio)**: Disqualify if `(Net Income - Operating CF - Investing CF) / Total Assets` is **> 0.10** (Aggressive accruals).
7. **Asset Bloat Check**: Disqualify if **Inventory** or **Receivables** growth exceeds **Revenue** growth by more than **10%**.
8. **Margin Deterioration**: Disqualify if **Gross Margin** has declined for two consecutive years.
9. **Shareholder Dilution**: Disqualify if **Shares Outstanding** increased by **> 2.0%** year-over-year.
10. **Momentum Floor**: Disqualify if price is **< 200-day SMA** AND the **30-day Price Slope** is negative (Prevents "Falling Knives").

## Selection Criteria
**All conditions must be met.** If any check fails, the stock is disqualified as a "Value Trap."

## API Requirements
**Primary API: SimFin**
- **Why it fits**: Designed for quantitative analysis with standardized financial statements. Reliable for multi-year historical data needed for Z-Score and 5-yr P/E medians.
- **Status**: Generous free tier used for development.
