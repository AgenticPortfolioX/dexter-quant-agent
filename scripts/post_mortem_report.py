import os
import sys
import json
import logging
import yfinance as yf
from datetime import datetime
import pytz
import re

# Path setup
DEXTER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(DEXTER_ROOT)

from scripts.slack_notifier import send_dexter_slack_alert
from strategies.validation.alpha_autotrader import get_active_positions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EST = pytz.timezone('US/Eastern')
REPORT_CHANNEL = "C0ASARJ1TLY"

STRATEGY_INFO = {
    "Dual Thrust (DT)": {
        "description": "Volatility-based range breakout strategy.",
        "signal": "Price crosses Opening Price +/- (0.2 * 4-day Range).",
        "plan": "Exit on target fill or inverse signal. Guarded by ATR stop."
    },
    "Heikin Ashi (HA)": {
        "description": "Trend-following using Heikin Ashi candle shifts.",
        "signal": "Color change on 5m/1h HA candles with EMA confirmation.",
        "plan": "Exit on HA color reversal or trailing wick stop."
    },
    "Shooting Star (SS)": {
        "description": "Bearish reversal rejection at resistance.",
        "signal": "Shooting Star candle formation at key resistance levels.",
        "plan": "Target: Prior support. Stop: Above the star's wick."
    },
    "Apex (Pivot Bounce)": {
        "description": "Mean reversion at daily pivot levels.",
        "signal": "RSI Divergence at S1/R1 or S2/R2 pivot points.",
        "plan": "Target: Central Pivot (P). Stop: Below the pivot level."
    },
    "Gemini Velocity": {
        "description": "Momentum scalping with volume delta confirmation.",
        "signal": "RVOL spike > 2x with price velocity exceeding 0.5% in 5m.",
        "plan": "Target: 1.5:1 RR ratio. Tight trailing stop."
    },
    "BigD (PO3/AMD)": {
        "description": "Accumulation/Manipulation/Distribution cycle tracking.",
        "signal": "Liquidity sweep below London Low followed by displacement.",
        "plan": "Target: Opposite liquidity pool. Breakeven at 1:1."
    },
    "LittleD (SFP)": {
        "description": "Swing Failure Pattern liquidity grab detection.",
        "signal": "Sweep of session high/low with immediate close back inside.",
        "plan": "Target: Session midpoint. Stop: Beyond the sweep wick."
    },
    "Sonnet (ORE + Regime)": {
        "description": "Opening Range Expansion with market regime filter.",
        "signal": "Break of 15m Opening Range with SPY > EMA 20.",
        "plan": "Target: Dynamic based on ATR. EOD Exit."
    },
    "Volcanix (VWAP Reclaim)": {
        "description": "Mean reversion focusing on VWAP reclaims.",
        "signal": "Reclaim of VWAP from below with high relative volume.",
        "plan": "Target: VWAP + 1 SD. Stop: VWAP - 0.5 SD."
    }
}

def generate_post_mortem():
    logger.info("Generating Enhanced Daily Post-Mortem...")
    try:
        now = datetime.now(EST)
        today_str = now.strftime("%Y-%m-%d")
        exec_log = os.path.join(DEXTER_ROOT, ".agent", "reporting-repo", "dexter-quant", "logs", "live_trading", "execution.log")
        
        if not os.path.exists(exec_log):
            return "❌ No execution log found for today."

        trades = []
        with open(exec_log, 'r', encoding='utf-8') as f:
            for line in f:
                if today_str in line:
                    try:
                        # Format: [LIVE-EXEC] [Time] Strategy | Ticker | Action @ $Price
                        parts = line.split('|')
                        strat = parts[0].split(']')[-1].strip()
                        ticker = parts[1].strip()
                        action_price = parts[2].strip()
                        action = "BUY" if any(x in action_price.upper() for x in ["BUY", "LONG"]) else "SELL"
                        price = float(action_price.split('$')[-1])
                        trades.append({
                            'strat': strat, 
                            'ticker': ticker, 
                            'action': action, 
                            'price': price,
                            'time': line.split(']')[1].split('[')[1].strip()
                        })
                    except: continue

        if not trades:
            return f"📊 *DAILY POST-MORTEM: {today_str}*\nNo trades executed today."

        # Group by ticker to find pairs
        results = {}
        for t in trades:
            ticker = t['ticker']
            if ticker not in results: results[ticker] = {'trades': []}
            results[ticker]['trades'].append(t)

        report = f"📊 *DEXTER QUANT POST-MORTEM: {today_str}*\n"
        report += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        total_pnl = 0.0
        total_notional = 0.0
        win_count = 0
        trade_count = 0
        
        active_positions = get_active_positions()
        
        detail_section = "🔍 *DETAILED TRADE ANALYSIS*\n"
        
        for ticker, data in sorted(results.items()):
            ticker_trades = data['trades']
            buys = [t for t in ticker_trades if t['action'] == "BUY"]
            sells = [t for t in ticker_trades if t['action'] == "SELL"]
            
            avg_buy = sum([b['price'] for b in buys]) / len(buys) if buys else 0
            avg_sell = sum([s['price'] for s in sells]) / len(sells) if sells else 0
            
            status = "CLOSED"
            if ticker in active_positions:
                status = "OPEN"
                try:
                    hist = yf.Ticker(ticker).history(period="1d")
                    if not hist.empty:
                        avg_sell = hist['Close'].iloc[-1]
                except: pass
            
            if avg_buy > 0 and avg_sell > 0:
                # Assuming standard $25 or $75 size if not specified
                qty = 1.0 # Normalized for P&L % calculation
                pnl_pct = ((avg_sell / avg_buy) - 1) * 100
                
                # Try to get the strategy from the first trade
                strat_name = ticker_trades[0]['strat']
                info = STRATEGY_INFO.get(strat_name, {"description": "Custom Algorithm", "signal": "Proprietary Data Signal", "plan": "Algorithmic Risk/Reward"})
                
                total_pnl += pnl_pct
                trade_count += 1
                if pnl_pct > 0: win_count += 1
                
                icon = "🟢" if pnl_pct >= 0 else "🔴"
                detail_section += f"{icon} *{ticker}* | {strat_name}\n"
                detail_section += f"├ *P&L*: `{pnl_pct:+.2f}%` ({status})\n"
                detail_section += f"├ *Signal*: {info['signal']}\n"
                detail_section += f"└ *Plan*: {info['plan']}\n\n"

        win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0
        
        report += f"💰 *Net Performance*: `{total_pnl:+.2f}%` (Normalized)\n"
        report += f"🎯 *Win Rate*: `{win_rate:.1f}%` ({win_count}/{trade_count})\n\n"
        report += detail_section
        report += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"_Automated Post-Mortem | channel: {REPORT_CHANNEL}_"

        return report

    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return f"❌ Error generating report: {e}"

if __name__ == "__main__":
    report_msg = generate_post_mortem()
    if send_dexter_slack_alert(report_msg, channel=REPORT_CHANNEL):
        print("Post-Mortem delivered to Slack.")
    else:
        print("Failed to deliver Post-Mortem.")
