# Momentum Strategy 4: Follow the Leader (Insider)

## Goal
Copy significant open‑market purchases by top executives (CEO, CFO, Directors), especially when multiple insiders buy together (clusters).

## Data Sources
- **SEC EDGAR / SEC-API.io**: Primary for Form 4 filings (XML).
- **yfinance**: For current and historical price data.

## Storage
SQLite table `insider_buys` with columns:
`ticker`, `insider`, `role`, `shares`, `price`, `filing_date`, `transaction_value`, `is_cluster`.

## Logic Steps
1. **Fetch Form 4 Filings**: Look for Transaction code "P" (Purchase) in the last 5 days.
2. **Executive Role Check**: Filter for CEO, CFO, or Directors.
3. **Value Threshold**: Minimum transaction value of **$100,000**.
4. **Pitfall Fix**: Filter out 10b5-1 automatic plans; focus on discretionary open-market buys.
5. **Cluster Detection**: Mark as `is_cluster` if ≥2 distinct insiders buy within a 7-day window.
6. **Entry Condition**: Current Price ≤ (**Insider Buy Price × 1.05**).
7. **Position Sizing**:
    - **Base**: 2% of portfolio.
    - **Cluster**: 4% of portfolio.

## Exit Rules
- **Hold Period**: 90 to 180 days.
- **Stop Loss**: 10% below entry.
- **Take Profit**: 25% gain, or time-based exit after 180 days.

## API Requirements
**Primary API: SEC-API.io**
- **Why it fits**: Specific to SEC EDGAR data with a powerful Query API for Form 4 filtering.
- **Where to get it**: [sec-api.io](https://sec-api.io)
- **Subscription Nuance**: Free tier for basic requests; paid plans for high volume and WebSocket alerts.
