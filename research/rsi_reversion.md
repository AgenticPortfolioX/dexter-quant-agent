# Research Blueprint: RSI-Candlestick Mean Reversion

**Objective**: Capture snap-back moves from RSI extremes (Overbought/Oversold) using Candlestick patterns as the trigger confirmation.
**Philosophy**: "Do not trade the extreme; trade the turn."

## 📊 Indicators & Settings
- **RSI**: Period = 14
- **Overbought**: 75 (Standard is 70) -> Short Zone
- **Oversold**: 25 (Standard is 30) -> Long Zone
- **Timeframes**: 15m, 1h (Day Trading Focus)

## 🚦 Entry Logic

### Long (Buy) Signal
1.  **Setup**: RSI < 25 within the last 3 candles.
2.  **Trigger**: RSI Hooks Up (Current > Prev > Prev-2).
3.  **Confirmation**: **Bullish Engulfing** OR **Hammer** pattern on the current candle.
4.  **Filter**: "Golden Rule" - Avoid if strong bearish momentum (3 consecutive bearish candles with increasing body size).

### Short (Sell) Signal
1.  **Setup**: RSI > 75 within the last 3 candles.
2.  **Trigger**: RSI Hooks Down (Current < Prev < Prev-2).
3.  **Confirmation**: **Bearish Engulfing** OR **Shooting Star** pattern on the current candle.
4.  **Filter**: "Golden Rule" - Avoid if strong bullish momentum (3 consecutive bullish candles with increasing body size).

## 🛡️ Risk Management (The Exit)

### Stop Loss (Dynamic)
- **Long**: Trigger Low - (0.5 * ATR 14)
- **Short**: Trigger High + (0.5 * ATR 14)

### Take Profit (Split Targets)
- **TP1 (50%)**: RSI crosses **50** (Midline). **Move SL to Breakeven.**
- **TP2 (50%)**:
    - Longs: RSI crosses **75** (Overbought).
    - Shorts: RSI crosses **25** (Oversold).

## 🧪 Validation Plan
- **Asset**: EUR/USD (High liquidity, mean reverting) or BTC/USD (Volatility).
- **Backtest**: Last 3 months on 15m timeframe.
- **Success Criteria**: Win Rate > 55%, Profit Factor > 1.5.
