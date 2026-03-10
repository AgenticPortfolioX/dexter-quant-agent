# Momentum Strategy 1: Post‑Earnings Drift (Catalyst)

## Goal
Buy companies that beat earnings and raised guidance, capturing the institutional drift that follows a strong report.

## Data Sources
- **Earnings surprises**: Alpha Vantage EARNINGS API (or Financial Modeling Prep earnings-calendar).
- **Transcripts**: Financial Modeling Prep earning-call-transcript (or SEC EDGAR 8‑K filings).
- **Price/volume**: yfinance for intraday candle and relative volume.

## Storage
SQLite table `earnings_signals` with columns:
`ticker`, `report_date`, `eps_surprise_pct`, `revenue_surprise_pct`, `guidance_sentiment`, `entry_price`, `signal_date`, `status` (active, exited).

## Logic Steps
1. **Fetch yesterday’s earnings** from the API. Calculate % surprises. Keep if EPS > 5% and Revenue > 2%.
2. **Relative Volume (RVOL) check**: Disqualify if RVOL < 2.0.
3. **Guidance extraction**: 
    - Skip first 2,000 chars.
    - Target Q&A section.
    - Use regex to capture paragraphs with: guidance, outlook, future, expect.
    - Use local LLM to output: RAISED, LOWERED, or MAINTAINED.
4. **Entry trigger**: If guidance = RAISED:
    - Gap ≤ 10%: Market open.
    - Gap > 10%: Buy stop at 30-min candle high + $0.05.
5. **Position sizing**: Equal weight, max 5% per position.

## Exit Rules
- **Hold period**: 60 calendar days.
- **Stop loss**: 8% below entry.
- **Take profit**: 20% above entry, or trailing stop after 15% gain (trail by 5%).

## API Requirements (NOT CURRENTLY FUNDED)
**Primary API: Financial Modeling Prep (FMP)**
- **Why it fits**: FMP bundles earnings surprise data with call transcripts.
- **Cost**: Requires Premium ($59/mo) or Ultimate ($149/mo) plan for transcript access.
- **Status**: **NOT DEPLOYED** until subscription is active.
