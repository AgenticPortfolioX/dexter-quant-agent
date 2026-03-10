
import os

BOARD_PATH = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent\dashboard\LIVE_STRATEGY_BOARD.md"

template = """# 🏦 ALPHA COMMAND CENTER: LIVE STRATEGY BOARD
**PILOT LIGHT: 🟢** | **Status: LIVE_MARKET: 🚀 TRADING (Full Alpha Mode)** (Last Heartbeat: 2026-02-24 16:05:00 EST)

## 🔋 MONITOR HEALTH
- **Last Active Scan**: 2026-02-24 16:05:00 EST
- **System Status**: NOMINAL


## 📈 ACTIVE PORTFOLIO
| Asset | Quantity | Status |
| :--- | :--- | :--- |
| None | 0.0 | CASH |


## 🟢 LIVE TRADING
| Strategy Name | Active Assets | Status | Latest Signal |
| :--- | :--- | :--- | :--- |
| **London Displacement** | USDJPY=X | 🚀 LIVE | None |
| **Initial Balance (80%)** | SPY | 🚀 LIVE | None |
| **Noon-Curve (Lunchbox)** | QQQ, SPY | 🚀 LIVE | None |
| **MACD 200 Bounce (Refined)** | SPY, QQQ | 🚀 LIVE | None |
| **SMC Focal Portfolio** | AAPL, DIA, JNJ, WMT, GS | 🚀 LIVE | None |
| **Trinity Basket** | GLD, FXY, FXE | 🚀 LIVE | None |
| **Nasdaq-Day** | QQQ | 🚀 LIVE | None |

## 🟡 ACTIVE TESTING
| Strategy Name | Active Assets | Status | Latest Signal |
| :--- | :--- | :--- | :--- |
| **PO3 + IFVG** | SPY, QQQ | 🧪 TEST | None |
| **NY ORB** | SPY, QQQ | 🧪 TEST | None |
| **Wickless Candles** | USDJPY=X, AUDUSD=X, USDCAD=X, QQQ, IWM, GC=F | 🧪 TEST | None |
| **Dynamic + Daily Bias** | NVDA, GOOGL, TSLA, QQQ, PLTR, MSTR, COIN, SMCI | 🧪 TEST | None |
| **Price Retreat (S1)** | SPY | 🧪 TEST | None |
| **Turnaround Tuesday (S2)** | SPY, QQQ | 🧪 TEST | None |
| **Low Close IBS (S3)** | SPY, QQQ | 🧪 TEST | None |
| **DeMarker (S4)** | SPY, QQQ | 🧪 TEST | None |
| **High of 10 Days IBS (S5)** | SPY, QQQ | 🧪 TEST | None |
"""

with open(BOARD_PATH, "w", encoding='utf-8') as f:
    f.write(template)

print(f"Board restored accurately at {BOARD_PATH}")
