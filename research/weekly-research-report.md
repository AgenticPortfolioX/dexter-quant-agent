
# Weekly Research Report

## 1. NY 15min ORB Strategy (Incubator)
**Status**: Backtested (60-Day Sample) & **Profitable**

### Performance Highlights
- **Total Return**: +6.94% (+$3,471.25)
- **Profit Factor**: 12.77
- **Win Rate**: 42.86%
- **Drawdown**: -0.58% (Very Low Risk)
- **Sample**: 60 Days (5-minute granularity)

### Key Findings
- **Filters Work**: "Expansion Trap" (Filter B) and "Break & Retest" (Filter C) successfully avoided choppy days.
- **Outcome**: Strategy relies on large winners (Target 2) to offset small stops.

---

## 2. London Judas Swing (LJS) Strategy (Active)
**Status**: Signal Validated (7-Day 1m Sample) - **Profitability Unconfirmed**

### Validation Results
- **Sweeps Detected**: 28.5% (2/7 Days)
- **Signal Accuracy**: 100% Reversal into FVG (for the 2 detected sweeps)
- **User Note**: Strategy currently deemed "not profitable" / insufficient sample or frequency compared to NY ORB.

### Comparison
| Feature | NY 15min ORB | London Judas Swing |
| :--- | :--- | :--- |
| **Sample Size** | 60 Days | 7 Days |
| **PnL** | **+$3,471.25** | *Not Backtested for PnL* |
| **Frequency** | ~1 Trade / 8 Days | ~1 Signal / 3.5 Days |
| **Status** | **Promising** | Needs PnL Verification |

---

## 3. Saturday RSI Leaps (Incubator)
**Status**: Pending Implementation
- **Concept**: Weekly RSI < 30 + Institutional Flow -> LEAPS.
- **Next Step**: Implement scan logic.

---

## Maintenance Actions
- **New Strategy Added**: `strategies/incubator/ny_orb_strategy.py`
- **Backtesting Engine**: Created reusable `BacktestEngine` class in validation scripts.
- **Data**: Fetched 60-day 5m ES Futures data for extended backtesting.