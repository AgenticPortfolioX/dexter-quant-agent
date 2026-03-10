# Momentum Strategy 6: Analyst Consensus Shift (Institutional)

## Goal
Buy stocks that receive multiple upgrades and significant price target hikes, especially when the stock price hasn’t yet reacted. This targets institutional "re-rating" cycles.

## Data Sources
- **Analyst Ratings**: TipRanks via Apify (or Benzinga API).
- **Price Data**: yfinance for current price and historical drift.

## Storage
SQLite table `analyst_clusters` with columns:
`ticker`, `upgrade_count_7d`, `avg_pt`, `upside_pct`, `date`, `status` (active, exited).

## Logic Steps
1. **Cluster Accumulation**: Monitor a 7-day window for Upgrades, Initiations (Buy), and Price Target raises.
2. **Firm De-duplication**: Normalize firm names (e.g., "Goldman Sachs Group" ➔ "Goldman Sachs") to avoid double-counting.
3. **Cluster Threshold**: Require ≥ 3 distinct firms within 7 days.
4. **Upside Requirement**: Average price target must imply > 15% upside from current price.
5. **Divergence Filter**: Price must be "quiet" (5-day change < +2%). We want to buy before the market reacts to the institutional consensus shift.
6. **Sentiment Screen**: Exclude any ticker where reasoning contains speculative keywords (e.g., "M&A rumors", "takeover").

## Execution & Exit
- **Entry**: Buy at next day's open.
- **Position Size**: Max 3% per stock.
- **Take Profit**: 95% of average price target or 60 calendar days.
- **Stop Loss**: 8% below entry.

## API Requirements
**Primary API: TipRanks (via Apify) or Benzinga**
- **Why it fits**: Analyst consensus is "alt-data" that isn't easily accessible via standard free APIs.
- **Cost**: TipRanks via Apify (~$15/mo) or direct Benzinga institutional feed.
- **Status**: **NOT DEPLOYED** until subscription is active.
