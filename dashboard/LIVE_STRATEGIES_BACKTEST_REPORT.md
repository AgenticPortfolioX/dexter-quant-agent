# 📊 DEXTER QUANT ENGINE: LIVE STRATEGIES BACKTEST REPORT
**Generated**: 2026-10-25 02:10:33 EST | **Orchestrator**: Antigravity Gemini 3.8 Flash | **Worker Agent**: Dexter Quant Specialist

> [!NOTE]
> Comprehensive multi-timeframe backtest across all **13 live trading strategies** registered in `strategy_registry.json`.
> Bitcoin strategies utilize calibrated 2% stop-loss and 4% take-profit rules executing on **BITU** (2x Long) and **SBIT** (2x Short).

## 🏆 EXECUTIVE PERFORMANCE SUMMARY

| Strategy Name | Timeframe | Trades | Win Rate (%) | Profit Factor | Total Return (%) | Max Drawdown (%) | Sharpe |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Apex (Pivot Bounce)** | 1h | 739 | 82.0% | 4.22 | 597326.67% | 12.25% | 10.46 |
| **Apex Bearish (Short ETF Bounce)** | 1h | 183 | 81.4% | 3.94 | 6400.09% | 15.99% | 8.99 |
| **Price Retreat (S1)** | 1h | 43 | 69.8% | 1.38 | 7.73% | 6.78% | 1.88 |
| **Turnaround Tuesday (S2)** | 1h | 42 | 81.0% | 2.69 | 31.62% | 6.56% | 4.79 |
| **Low Close IBS (S3)** | 1h | 38 | 84.2% | 2.98 | 39.34% | 8.82% | 6.32 |
| **DeMarker (S4)** | 1h | 32 | 84.4% | 2.62 | 26.37% | 6.56% | 5.03 |
| **High of 10 Days IBS (S5)** | 1h | 18 | 72.2% | 1.86 | 7.51% | 7.13% | 3.74 |
| **Inside Candle (2x Leveraged BTC)** | 1h | 96 | 30.2% | 0.87 | -19.44% | 30.82% | N/A |
| **Liquidity Sweep (2x Leveraged BTC)** | 1D | 98 | 53.1% | 1.32 | 25.02% | 11.46% | 1.85 |
| **Power of 3 (2x Leveraged BTC)** | 5m | 87 | 47.1% | 1.28 | 20.92% | 14.69% | 1.71 |
| **RSI Reversion (2x Leveraged BTC)** | 1h | 62 | 48.4% | 1.88 | 69.92% | 14.92% | 4.78 |
| **SMC Bitcoin (2x Leveraged)** | 1h | 87 | 27.6% | 0.76 | -28.21% | 31.95% | N/A |
| **Tech Level EMA Touch (2x Leveraged BTC)** | 1h | 36 | 38.9% | 1.27 | 11.03% | 18.29% | 1.81 |
| **SFP Swing Failure (2x Leveraged BTC)** | 1h | 42 | 40.5% | 1.36 | 17.55% | 15.02% | 2.31 |

---

## 🪙 LEVERAGED BITCOIN ETF STRATEGIES (BITU / SBIT)
All Bitcoin strategies enforce calibrated brackets on the 2x ETFs:
- **Execution**: Long -> Buy **BITU** (2x Ultra) | Short -> Buy **SBIT** (2x UltraShort)
- **Stop-Loss**: -2.0% on ETF price
- **Take-Profit**: +4.0% on ETF price
- **Circuit Breaker**: Daily 4.5% drawdown halts
- **Prohibition**: Direct trading of IBIT and BTC-USD is strictly prohibited.

### Inside Candle (2x Leveraged BTC)
- **Total Trades**: 96
- **Win Rate**: 30.2%
- **Profit Factor**: 0.87
- **Cumulative Return**: -19.44%
- **Max Drawdown**: 30.82%

### Liquidity Sweep (2x Leveraged BTC)
- **Total Trades**: 98
- **Win Rate**: 53.1%
- **Profit Factor**: 1.32
- **Cumulative Return**: 25.02%
- **Max Drawdown**: 11.46%

### Power of 3 (2x Leveraged BTC)
- **Total Trades**: 87
- **Win Rate**: 47.1%
- **Profit Factor**: 1.28
- **Cumulative Return**: 20.92%
- **Max Drawdown**: 14.69%

### RSI Reversion (2x Leveraged BTC)
- **Total Trades**: 62
- **Win Rate**: 48.4%
- **Profit Factor**: 1.88
- **Cumulative Return**: 69.92%
- **Max Drawdown**: 14.92%

### SMC Bitcoin (2x Leveraged)
- **Total Trades**: 87
- **Win Rate**: 27.6%
- **Profit Factor**: 0.76
- **Cumulative Return**: -28.21%
- **Max Drawdown**: 31.95%

### Tech Level EMA Touch (2x Leveraged BTC)
- **Total Trades**: 36
- **Win Rate**: 38.9%
- **Profit Factor**: 1.27
- **Cumulative Return**: 11.03%
- **Max Drawdown**: 18.29%

### SFP Swing Failure (2x Leveraged BTC)
- **Total Trades**: 42
- **Win Rate**: 40.5%
- **Profit Factor**: 1.36
- **Cumulative Return**: 17.55%
- **Max Drawdown**: 15.02%


---

## 📈 STRATEGY CATEGORY BREAKDOWN

### 1. Leveraged Bitcoin ETF Models (BITU / SBIT)
- **Inside Candle**: Mother bar breakout into trend with tight 2% SL / 4% TP.
- **Liquidity Sweep**: 15m liquidity pool sweep with FVG recovery targeting intraday momentum.
- **Power of 3 (PO3/AMD)**: Accumulation-Manipulation-Distribution sweep around midnight EST open.
- **RSI Reversion**: 1h RSI oversold/overbought candlestick mean reversion on 2x ETFs.
- **SMC Bitcoin**: Smart money market structure shifts and displacement candle entries.
- **Tech Level EMA Touch**: Dynamic EMA touch pullback with anchor trend filter & volume surge.
- **SFP Swing Failure**: Swing failure pattern targeting institutional stop-hunts on high-volume hourly candles.

### 2. Equities & Index Intraday / Swing Models
- **Apex (Pivot Bounce)**: Forward structural floor-trader pivots (PP, S1/S2, R1/R2) with RSI divergence.

### 3. Daily S-Series Mean Reversion
- **Price Retreat (S1), Turnaround Tuesday (S2), Low Close IBS (S3), DeMarker (S4), High of 10 Days IBS (S5)**: Tested over 2 years of daily market regimes targeting high-probability bounces.
