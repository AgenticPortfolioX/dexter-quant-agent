> 🕒 Last Updated: 2026-02-24 02:00 EST

# 🏆 Successful Strategies (Hall of Fame)

This directory contains strategies that have passed rigorous backtesting and validation. Logic that graduates to **Live Trading** is moved to the root `strategies/live_trading/` directory for operational clarity.

## 📁 Master Strategy Index

### 🚀 Graduated to [Live Trading](../live_trading/)
*These strategies are currently executing in production.*
- **[London Displacement](../live_trading/london_displacement/)**: Institutional liquidity sweep (85.7% WR).
- **[Initial Balance 80](../live_trading/initial_balance_80/)**: SPY-optimized IB retrace logic.
- **[Noon Curve Lunchbox](../live_trading/noon_curve_lunchbox/)**: QQQ/SPY intermarket divergence logic.
- **[MACD 200 Bounce (Refined)](../live_trading/macd_200_bounce/)**: Optimized EMA baseline recovery (62.5% WR).
- **[SMC Focal Portfolio](../live_trading/smc_focal_portfolio/)**: Institutional flow autotrader.

### 🟠 Bitcoin Core Portfolio (`BTC-Success/`)
*Dedicated focus on BTC-USD volatility and market structure.*
- **[Power of 3 (AMD)](BTC-Success/power_of_3/)**: Accumulation, Manipulation, Distribution logic.
- **[RSI-Candlestick Reversion](BTC-Success/rsi_btc/)**: BTC-optimized RSI extreme reversals.
- **[Liquidity Sweep](BTC-Success/liquidity_sweep_btc/)**: H4 liquidity grab logic.
- **[Smart Money Concepts](BTC-Success/smc_btc/)**: Base SMC engine for BTC.
- **`BTC-Success/smc_btc_plus.py`**: Advanced SMC refinements.
- **[Inside Candle Breakout](BTC-Success/inside_candle_btc/)**: BTC volatility contraction play.
- **[Tech Level EMA](BTC-Success/btc_tech_level_ema/)**: Baseline EMA support/resistance.
- **`BTC-Success/link_pilled.py`**: Inter-asset correlation engine.

### 🟢 Trading Excellence (Incubator/Testing)
*Vetted logic currently in final validation or baseline testing.*
*(Empty - All primary strategies promoted or purged)*

---

## 🛠 Support Artifacts
Each strategy folder contains:
- `*_strategy.py`: The core logic script.
- `*_prompts.jsonl`: The logic breakdown used during development.
- (Optional) `*_results.csv`: Local validation data.

---
**Disclaimer**: All strategies are subject to market conditions. Graduation to `live_trading/` is the final stage of the Dexter Quant lifecycle.
