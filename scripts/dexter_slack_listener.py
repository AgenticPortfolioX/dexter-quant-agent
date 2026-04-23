import os
import sys
import logging
import json
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

# Path setup
DEXTER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(DEXTER_ROOT)
load_dotenv(os.path.join(DEXTER_ROOT, ".env"))

# Import Dexter's core functions
from strategies.validation.alpha_autotrader import generate_daily_pnl_report, execute_trade, get_active_positions, find_entry_price, INVERSE_MAP
import yfinance as yf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Bolt App
app = App(token=os.environ.get("DEXTER_SLACK_BOT_TOKEN"))

@app.event("app_mention")
def handle_mentions(event, say):
    text = event.get("text", "").lower()
    
    # --- 🧵 THREAD RESOLUTION LOGIC ---
    # 1. If explicitly forced via .env, always use thread_ts
    force_thread = os.getenv("REPLY_IN_THREAD", "false").lower() == "true"
    
    # 2. Get the thread_ts from the event if it exists (meaning the mention is ALREADY in a thread)
    existing_thread_ts = event.get("thread_ts")
    
    # 3. Resolve the target thread_ts
    # - If we are forcing threads, or if we are already in a thread, use that thread_ts.
    # - Otherwise, use None (posts to main channel).
    target_thread_ts = None
    if force_thread:
        target_thread_ts = event.get("ts")
    elif existing_thread_ts:
        target_thread_ts = existing_thread_ts
        
    def dexter_say(message):
        """Helper to ensure consistent threading behavior."""
        if target_thread_ts:
            return say(text=message, thread_ts=target_thread_ts)
        else:
            return say(text=message)

    def get_latest_bias():
        """Reads the latest morning report to extract technical bias."""
        briefings_dir = r"C:\Users\jmgra\antigravityagents\.agent\skills\agentic-skills\15-morning-market-report\briefings"
        if not os.path.exists(briefings_dir):
            return "❌ Briefings directory not found."
            
        files = [f for f in os.listdir(briefings_dir) if f.endswith(".md")]
        if not files:
            return "❌ No report briefings found."
            
        latest_file = sorted(files)[-1]
        filepath = os.path.join(briefings_dir, latest_file)
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Extract Technical Bias section
            import re
            es_match = re.search(r"### \[ES\] S&P 500 Futures\s+```text\s+(.*?)\s+```", content, re.DOTALL)
            nq_match = re.search(r"### \[NQ\] Nasdaq 100 Futures\s+```text\s+(.*?)\s+```", content, re.DOTALL)
            verdict_match = re.search(r"## 🎯 STRATEGIC VERDICT\s+(.*?)\n\n", content, re.DOTALL)
            
            report = f"📊 *DEXTER SENTIMENT ANALYSIS* ({latest_file.replace('.md','')})\n"
            
            if es_match:
                bias_text = es_match.group(1).strip()
                # Find the "Daily Bias: ..." line
                bias_val = re.search(r"Daily Bias:\s+(\w+)", bias_text)
                if bias_val:
                    report += f"• *ES Bias*: `{bias_val.group(1)}`\n"
            
            if nq_match:
                bias_text = nq_match.group(1).strip()
                bias_val = re.search(r"Daily Bias:\s+(\w+)", bias_text)
                if bias_val:
                    report += f"• *NQ Bias*: `{bias_val.group(1)}`\n"
                    
            if verdict_match:
                verdict = verdict_match.group(1).strip()
                # Clean up formatting for Slack
                verdict = verdict.replace("1. ", "\n1. ").replace("2. ", "\n2. ").replace("3. ", "\n3. ")
                report += f"\n*Strategic Verdict*:{verdict}"
            
            return report
        except Exception as e:
            return f"❌ Error parsing report: {e}"

    # Simple Command Router
    if "ping" in text:
        dexter_say(f"Pong! Dexter is active on PID {os.getpid()}.")
        
    elif "status" in text:
        try:
            from live_monitor import MarketScheduler
            scheduler = MarketScheduler()
            state, status_msg = scheduler.get_market_state()
            report = f"📊 *DEXTER STATUS REPORT*\n- *Market State*: `{state}`\n- *Message*: {status_msg}\n- *PID*: {os.getpid()}"
            dexter_say(report)
        except Exception as e:
            dexter_say(f"⚠️ Error fetching status: {e}")
            
    elif "pnl" in text or "performance" in text:
        dexter_say("💹 *Generating P&L Post-Mortem Report...*")
        try:
            generate_daily_pnl_report()
            dexter_say("✅ Report triggered and sent to home base.")
        except Exception as e:
            dexter_say(f"❌ Failed to generate report: {e}")
            
    elif "signals" in text:
        dexter_say("🛰️ *Scanned Signals Summary* (Executing Signal Monitor...)")
        try:
            python_exe = sys.executable
            monitor_script = os.path.join(DEXTER_ROOT, "dexter_signal_monitor.py")
            os.system(f'"{python_exe}" "{monitor_script}"')
            dexter_say("📡 Scanners complete. Results pushed to Slack.")
        except Exception as e:
            dexter_say(f"❌ Scanner failed: {e}")

    elif "positions" in text:
        try:
            pos = get_active_positions()
            if not pos:
                dexter_say("📦 *No active positions.* (100% Cash)")
            else:
                dexter_say("⏳ *Building Live Portfolio Dashboard...*")
                
                # Load strategy mappings
                strat_map = {}
                try:
                    with open(os.path.join(DEXTER_ROOT, "cache", "active_strategies.json"), "r") as f:
                        strat_map = json.load(f)
                except: pass
                
                registry = {}
                try:
                    with open(os.path.join(DEXTER_ROOT, "strategy_registry.json"), "r") as f:
                        registry = json.load(f)
                except: pass
                
                # Build lookup dict from registry
                reg_lookup = {}
                for cat in ["live_trading", "active_testing"]:
                    for s in registry.get(cat, []):
                        reg_lookup[s["name"]] = s

                report = "📦 *CURRENT PORTFOLIO DASHBOARD*\n\n"
                
                for ticker, qty in pos.items():
                    # Identify Strategy
                    strat_name = strat_map.get(ticker, "Unknown")
                    is_inverse = False
                    
                    # If unknown, try inverse fallback
                    if strat_name == "Unknown":
                        for base_ticker, inv_ticker in INVERSE_MAP.items():
                            if inv_ticker == ticker and base_ticker in strat_map:
                                strat_name = strat_map[base_ticker]
                                is_inverse = True
                                break

                    # If still unknown, scan registry
                    if strat_name == "Unknown":
                        for name, s in reg_lookup.items():
                            if ticker in s.get("assets", []):
                                strat_name = name
                                break
                    
                    strat_data = reg_lookup.get(strat_name, {})
                    freq = strat_data.get("frequency", 3600)
                    tf = "5m" if freq == 300 else "1h" if freq == 3600 else "1d" if freq == 86400 else f"{freq}s"
                    
                    tp_str = "Dynamic (Algorithmic)"
                    sl_str = "Dynamic (ATR/Signal)"
                    
                    # P&L Calc
                    entry_price = find_entry_price(ticker)
                    if not entry_price and is_inverse:
                        # Sometimes entry logs record the base ticker instead of the inverse
                        for base, inv in INVERSE_MAP.items():
                            if inv == ticker:
                                entry_price = find_entry_price(base)
                                break
                                
                    current_price = 0.0
                    pnl_pct = 0.0
                    try:
                        hist = yf.Ticker(ticker).history(period="1d")
                        if not hist.empty:
                            current_price = hist['Close'].iloc[-1]
                            if entry_price and entry_price > 0:
                                pnl_pct = ((current_price / entry_price) - 1) * 100
                    except: pass
                    
                    # Formatting
                    status_icon = "🟢" if pnl_pct >= 0 else "🔴"
                    if not entry_price: status_icon = "⚪"
                    
                    strat_label = f"*{strat_name}*" if strat_name != "Unknown" else "*Unknown*"
                    if is_inverse: strat_label += " (INVERSE)"
                    
                    report += f"{status_icon} *{ticker}* ({qty} units)\n"
                    report += f"├ Strategy: {strat_label} [{tf}]\n"
                    if entry_price and current_price:
                        report += f"├ P&L: *{pnl_pct:+.2f}%* (${entry_price:.2f} ➔ ${current_price:.2f})\n"
                    else:
                        report += f"├ P&L: *N/A* (Current: ${current_price:.2f})\n"
                        
                    report += f"└ Plan: TP {tp_str} | SL {sl_str}\n\n"

                dexter_say(report)
        except Exception as e:
            dexter_say(f"❌ Failed to fetch positions: {e}")

    elif "close all" in text:
        dexter_say("⚠️ *EMERGENCY: CLOSING ALL POSITIONS...*")
        try:
            pos = get_active_positions()
            count = len(pos)
            if count == 0:
                dexter_say("📦 No active positions to close.")
            else:
                for ticker, qty in pos.items():
                    # Fetch current price for logging/guard bypass
                    price = 0.0
                    try:
                        hist = yf.Ticker(ticker).history(period="1d")
                        if not hist.empty:
                            price = hist['Close'].iloc[-1]
                    except: pass
                    
                    if price == 0.0: price = 100.0 # Bypasses notional guard
                    
                    execute_trade("Slack Emergency Close", ticker, "SELL", price, quantity_override=qty)
                dexter_say(f"✅ Emergency cleanup complete. Closed {count} positions.")
        except Exception as e:
            dexter_say(f"❌ Emergency exit failed: {e}")

    elif "close" in text:
        # Handle 'close <ticker>'
        import re
        ticker = None
        # Look for ticker after 'close'
        match = re.search(r"close\s+([A-Z0-9.]+)", text.upper())
        if match:
            ticker = match.group(1)
            
        if ticker:
            dexter_say(f"⏳ *Exiting position for {ticker}...*")
            try:
                pos = get_active_positions()
                if ticker in pos:
                    qty = pos[ticker]
                    # Fetch price
                    price = 0.0
                    try:
                        hist = yf.Ticker(ticker).history(period="1d")
                        if not hist.empty:
                            price = hist['Close'].iloc[-1]
                    except: pass
                    
                    if price == 0.0: price = 100.0 # Bypasses notional guard
                    
                    execute_trade("Slack Manual Close", ticker, "SELL", price, quantity_override=qty)
                    dexter_say(f"✅ Closed {ticker} ({qty} units).")
                else:
                    dexter_say(f"❌ No active position found for `{ticker}`.")
            except Exception as e:
                dexter_say(f"❌ Failed to close {ticker}: {e}")
        else:
            dexter_say("❓ Please specify a ticker (e.g., `close NVDA`).")

    elif "bias" in text or "sentiment" in text:
        dexter_say("🔍 *Consulting the Quantitative Oracle...*")
        bias_report = get_latest_bias()
        dexter_say(bias_report)

    else:
        commands = [
            "`status` - Check market phase & health",
            "`pnl` - Generate performance report",
            "`signals` - Run signal scanners",
            "`positions` - View current portfolio",
            "`bias` - Get daily technical sentiment",
            "`close <ticker>` - Exit specific position",
            "`close all` - Emergency portfolio liquidation"
        ]
        help_msg = "👋 *I'm Dexter. Here is what I can do for you:*\n" + "\n".join(commands)
        dexter_say(help_msg)

if __name__ == "__main__":
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not app_token:
        print("Error: SLACK_APP_TOKEN not found in environment.")
        sys.exit(1)
        
    print("Dexter Slack Listener is starting in Socket Mode...")
    handler = SocketModeHandler(app, app_token)
    handler.start()
