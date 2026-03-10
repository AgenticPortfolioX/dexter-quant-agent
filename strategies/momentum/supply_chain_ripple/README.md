# Momentum Strategy 5: Supply Chain Ripple (Second‑Order)

## Goal
Buy a customer when its supplier reports a blowout quarter, anticipating the positive news will ripple through the supply chain before the customer’s own earnings.

## Data Sources
- **Supplier earnings surprises**: Finnhub calendar/earnings.
- **Supply chain map**: `supply_chain_map.json` (Manually maintained).
- **Customer earnings dates**: Finnhub calendar/earnings or yfinance.
- **Price correlation**: yfinance historical data.

## Storage
SQLite table `ripple_signals` with columns:
`ticker`, `supplier`, `entry_date`, `status` (active, exited).

## Logic Steps
1. **Monitor supplier earnings**: Check if any supplier in the map reported earnings yesterday.
2. **Revenue Surprise Threshold**: Require Revenue Surprise > 5%.
3. **Correlation Verification**: Compute 1-year daily return correlation. Disqualify if correlation < 0.5.
4. **Inventory Check**: Disqualify if supplier Inventory Growth > Revenue Growth + 10% (potential channel stuffing).
5. **Earnings Timing**: Next customer earnings must be 2 to 4 weeks away.
6. **Entry**: Buy at open the day after the supplier report.
7. **Position size**: Equal weight, max 2% per customer.

## Exit Rules
- **Pre-Earnings Exit**: Sell 2 trading days before the customer’s earnings date.
- **Stop Loss**: 5% below entry price.

## Disqualification
- If price has already risen > 10% since supplier report.
- If customer earnings is within 5 days.
- If correlation < 0.5.

## API Requirements
**Primary API: Finnhub**
- **Why it fits**: Strong provider for Earnings Surprises and Confirmed Earnings Dates.
- **Cost**: Requires a paid plan (approx. $50-$200/mo) for confirmed dates at scale.
- **Status**: **NOT DEPLOYED** until subscription is active.
