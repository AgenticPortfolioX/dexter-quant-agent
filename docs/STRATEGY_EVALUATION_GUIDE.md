# How to Evaluate Daily vs Intraday Strategies Correctly

Most backtests look great and most live books look mediocre, and the gap is almost
never "the strategy stopped working." It is measurement error. This guide is the
checklist we apply to every strategy in `strategy_registry.json` before we trust a
number, plus how the engine now enforces the important parts automatically.

---

## 1. The three clocks

Every signal has three distinct timestamps. Conflating them is the #1 source of
inflated backtest returns.

| Clock | Meaning | Where it lives |
|-------|---------|----------------|
| **Bar close** | When the candle the signal reads actually finished | `df.index[-1]` |
| **Decision time** | When the engine evaluated it | `datetime.now(EST)` in the worker |
| **Fill time** | When the broker filled the order | `execution.log` timestamp |

A signal may only be trusted when **bar close ≤ decision time**, and P&L may only
be booked from **fill time** forward. If decision time is inside the bar being read,
the bar is partial and the number is fiction.

### Daily strategies — the partial-bar trap

`yfinance` returns today's daily bar from 09:30 onward, containing only the first
few minutes of trade. A strategy reading `close` at 10:00 is reading a number that
will be different by 16:00. Classic backtests read 16:00 closes; the live engine
reading a 10:00 pseudo-close produces signals that do not exist in the backtest.

**What we do instead:** daily strategies only evaluate in the **15:45–15:59 ET**
window (`active_window: "15:45-15:59"` in the registry). The bar is ~99% formed, so
the live decision matches the backtest decision. This is wired through
`live_bar = is_in_window("15:45-15:59")` in the task builder, which **bypasses the
anti-flicker truncation** (`df.iloc[:-1]`) that intraday strategies rely on.

Outside that window, daily strategies still compute (so the board shows a state),
but price-triggered entries (IBS-3, VIX RSI-2, PEAD) are **suppressed** when
`df.index[-1].date() != today` — a stale-bar gate. Calendar-driven strategies
(turn-of-month, dual momentum) are exempt: their trigger comes from the date, and a
one-day data lag should not kill a monthly rebalance.

### Intraday strategies

The opposite rule applies: **always truncate the in-progress bar.** `df.iloc[:-1]`
is applied unless `live_bar` is set. A 5-minute strategy must never read the candle
it is standing inside. It also must not read a bar that closed more than one
interval ago — if the newest bar is 20 minutes old on a 5-minute strategy, the feed
is stale and the signal should be dropped, not acted on.

---

## 2. Measure the strategy, not the market

### Use percentage return per round trip, not dollar P&L

The signal-quality tracker (`scripts/signal_quality_tracker.py`) pairs BUY→SELL on
the same ticker (LIFO) and computes:

```
return_pct = (sell_price / buy_price - 1) * 100
```

Why not dollars: position size changes (`POSITION_SIZE_USD` is $10 today, $100
later), and a strategy that trades a $500 ETF vs a $40 stock produces wildly
different dollar P&L for identical edge. Percentage return normalises both and is
what lets one `profit_factor` be compared across strategies.

**One consequence to know about:** dollar-weighted P&L and percentage-return P&L
disagree when size varies. Trust the percentage number for *strategy quality* and
the dollar number for *account performance*. Never mix them in one table.

### Win rate alone is a trap

A 70% win rate with 0.4:1 payoff loses money. Rank strategies on **expectancy**:

```
expectancy = win_rate * avg_win - loss_rate * avg_loss
profit_factor = gross_win / gross_loss
```

`signal_quality.json` stores `win_rate`, `profit_factor`, `avg_return_pct`,
`gross_win_pct`, `gross_loss_pct`, `total_trades`, `score`. `profit_factor` is the
primary gate — see §5.

### Sample size

| Trades | What you may conclude |
|--------|----------------------|
| < 10 | Nothing. Size neutral (multiplier 1.0). |
| 10–19 | Directional hint only. No demotion, no boost. |
| ≥ 20 | Enough to act on: demote below PF 0.80, boost above PF 1.30. |

The tracker tracks 500+ trades, so for a strategy trading a few times a month you
are looking at 12–24 months of live data before the numbers are meaningful. Do not
"fix" a strategy on 6 trades.

---

## 3. Costs must be in the number

Every backtest number quoted for these strategies is **gross**. Real fills are not.

- **Commission:** $0 on Robinhood, so this is not a factor here.
- **Spread:** ~1 bp on SPY/QQQ, 2–5 bp on sector SPDRs, 5–15 bp on small/mid caps.
- **Slippage on the open/close:** the close auction is where our daily entries land;
  assume 2–5 bp.
- **Gap risk:** a stop at `close - 2*ATR` does not fill at the stop if the stock gaps
  through it overnight. Model stops as filling at `min(stop, next_open)`.
- **T+1 settlement:** a cash account cannot redeploy sale proceeds same-day. This
  does not change P&L, it changes *how many* trades the book can take — which is why
  `MAX_CONCURRENT_TRADES` matters as much as edge.

Rule of thumb: subtract **10–20 bp per round trip** from any backtest number before
comparing it to live. A daily strategy claiming 0.15% average edge per trade is
probably at zero after costs.

---

## 4. Walk-forward, not single-path

A parameter set chosen by looking at the whole history is fitted to that history.
The correct protocol:

1. **In-sample:** choose parameters on 2010–2017.
2. **Out-of-sample:** test unchanged on 2018–2022. If performance collapses, the
   parameters were curve-fit.
3. **Live:** 2023–present, which is the only number that cannot be contaminated.

Additional honesty checks:

- **Survivorship:** the PEAD universe and sector list are today's liquid names. If
  the backtest used today's list over ten years, it is biased upward. Keep the
  universe definition *static as of the test start date* when backtesting.
- **Look-ahead in earnings dates:** yfinance earnings dates are revised after the
  fact. A backtest that keys off "surprise %" must use the value known *on the
  announcement date*, not the final revised number.
- **Regime count:** 2008, 2011, 2015–16, 2018, 2020, 2022 were different regimes.
  A strategy tested only on 2017–2019 has seen one regime.

---

## 5. Live-vs-backtest reconciliation

This is the check that actually tells you whether the system works. Run monthly:

1. Pull `signal_quality.json` `avg_return_pct` for the strategy.
2. Pull the backtest's average return per trade over the same window.
3. Compute `live / backtest`.

| Ratio | Reading | Action |
|-------|---------|--------|
| 0.8 – 1.2 | Tracking. Backtest is a fair model. | None. |
| 0.4 – 0.8 | Cost/slippage drag, or fill degradation. | Audit `execution.log` fills vs signal prices. |
| < 0.4 | Broken. Signal, data, or execution is not what you tested. | Stop the strategy, diff one signal bar-by-bar. |
| > 1.5 | Regression to the mean incoming, or a biased sample. | Do not increase size on this evidence alone. |

**The fill-vs-signal gap is the diagnostic.** `execution.log` records
`[LIVE-EXEC] [TS] STRAT | TICKER | ACTION @ $PRICE`. Compare `$PRICE` to the bar
close the signal fired on. Mean absolute difference is your realised slippage — if
it exceeds 15 bp on SPY/QQQ class instruments, something in the path is slow (bridge
latency, monitor loop timing) and that is a bug, not a cost.

---

## 6. How the engine implements this (map)

| Principle | Implementation |
|-----------|----------------|
| Daily bars near-final, not partial | `active_window: "15:45-15:59"`; `live_bar` bypasses `df.iloc[:-1]` |
| No stale-bar entries | `df.index[-1].date() != today` suppression for IBS-3 / VIX RSI-2 / PEAD |
| Calendar strategies survive data lag | TOM/DM gate on `is_first_trading_day_of_month(today, df.index[-2])` |
| Percentage-return measurement | `scripts/signal_quality_tracker.py`, `method: percent_return_per_round_trip` |
| Per-strategy attribution | `execution.log` lines keyed by strategy name; daily EOD exits are **not** logged as a separate strategy, so pairing stays correct |
| Size from measured quality | `quality_verdict()` in `alpha_autotrader.py` → 0.0 (block), 0.5, 1.0, or 1.25× |
| Time-based exits independent of the loop | `position_book.decide_exit()` (stop / target / max-hold) sweeps each live cycle **and** at 16:05 via `scripts/run_systematic_exits.py` |
| Two strategies may hold the same ticker | position book keyed `(strategy, ticker)`, not ticker alone |

---

## 7. The evaluation cadence

| Frequency | Check | Where |
|-----------|-------|-------|
| Every trade | Fill price within tolerance of signal price; phantom-fill guard confirms the position exists | `execution.log`, bridge `/positions` |
| Daily 16:05 | Post-mortem: signals fired vs trades taken vs blocked-and-why | `scripts/post_mortem_report.py` |
| Weekly | Strategies with ≥20 trades: PF, win rate, expectancy; any PF < 0.80 gets demoted automatically | `quality_verdict()` |
| Monthly | Live-vs-backtest ratio per strategy (§5); regime check vs SPY 200SMA | manual |
| Quarterly | Walk-forward re-validation; retire strategies with 40+ trades and PF < 1.0 | manual |

---

## 8. What "good" looks like for this book

Realistic targets for the five systematic daily strategies at 1× exposure, net of
costs, blended:

- **Win rate 60–65%** — driven by IBS-3 and TOM, which are high-hit-rate/low-payoff.
- **Profit factor 1.3–1.6.**
- **CAGR 8–14%** at 1× exposure; scaling exposure scales this roughly linearly
  until drawdowns become intolerable.
- **Max drawdown 12–18%.** Dual momentum's SPY-200SMA filter is what keeps this
  from being 30%+; it is also what gives up the first few percent of every recovery.

A strategy claiming a 90% win rate or 40% CAGR with these rules is mis-measured, not
exceptional. The first thing to check is always §1.
