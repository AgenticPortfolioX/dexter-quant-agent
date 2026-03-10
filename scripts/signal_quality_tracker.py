"""
Signal Quality Feedback Loop Agent (Proposal 8)
==============================================
Analyzes 'execution.log' to calculate:
- Strategy Win Rate (%)
- Average Profit/Loss ($)
- Total Trades
- Last Strategy Performance
Saves results to 'signal_quality.json'.
"""
import os
import sys
import json
import re
from datetime import datetime
import pytz

# Project paths
PROJECT_ROOT = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
REPORTING_ROOT = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\logs"
EXECUTION_LOG = os.path.join(REPORTING_ROOT, 'live_trading', 'execution.log')
QUALITY_FILE = os.path.join(PROJECT_ROOT, 'signal_quality.json')

EST = pytz.timezone('US/Eastern')

def parse_execution_log():
    """Parse execution.log and group by strategy."""
    if not os.path.exists(EXECUTION_LOG):
        print(f"  ❌ Log file not found at {EXECUTION_LOG}")
        return {}

    trades = {}
    count = 0
    try:
        with open(EXECUTION_LOG, 'r', encoding='utf-8') as f:
            for line in f:
                if "[LIVE-EXEC]" not in line: continue
                
                try:
                    # Line format: [LIVE-EXEC] [TS] STRAT | TICKER | ACTION @ $PRICE
                    # Step 1: Remove prefix
                    line_clean = line.replace("[LIVE-EXEC]", "").strip()
                    
                    # Step 2: Split by first "]" to get timestamp
                    if "]" not in line_clean: continue
                    ts_part, content = line_clean.split("]", 1)
                    ts_str = ts_part.replace("[", "").strip()
                    
                    # Step 3: Split content by "|"
                    parts = content.split("|")
                    if len(parts) < 3: continue
                    
                    strategy = parts[0].strip()
                    ticker = parts[1].strip()
                    action_part = parts[2].strip() # "EXIT @ $608.81"
                    
                    # Step 4: Parse action and price
                    if " @ $" not in action_part: continue
                    action, price_str = action_part.split(" @ $")
                    
                    action = action.upper().strip()
                    price_match = re.search(r"(\d+\.?\d*)", price_str)
                    if not price_match: continue
                    price = float(price_match.group(1))
                    
                    key = (strategy, ticker)
                    if key not in trades: trades[key] = []
                    trades[key].append({
                        "time": ts_str,
                        "action": action,
                        "price": price
                    })
                    count += 1
                except:
                    continue
    except Exception as e:
        print(f"Error parsing log: {e}")
    
    print(f"  🔍 Found {count} raw events in log.")
    return trades

def calculate_stats(trades):
    """Analyze trade pairs to determine performance."""
    stats = {}
    
    for (strategy, ticker), history in trades.items():
        if strategy not in stats:
            stats[strategy] = {"wins": 0, "losses": 0, "total_pnl": 0.0, "count": 0, "win_amt": 0.0, "loss_amt": 0.0}
            
        # Robust pairing: Sort by time
        history.sort(key=lambda x: x['time'])
        
        entries = [] # Stack of entries for this ticker/strat
        for event in history:
            action = event['action']
            if "LONG" in action or "SHORT" in action or "BUY" in action:
                entries.append(event)
            elif ("EXIT" in action or "SELL" in action or "CLOSE" in action) and entries:
                # Pair with the most recent entry (LIFO)
                entry = entries.pop()
                pnl = 0
                if "LONG" in entry['action'] or "BUY" in entry['action']:
                    pnl = event['price'] - entry['price']
                else: # Short
                    pnl = entry['price'] - event['price']
                
                stats[strategy]["count"] += 1
                stats[strategy]["total_pnl"] += pnl
                if pnl > 0:
                    stats[strategy]["wins"] += 1
                    stats[strategy]["win_amt"] += pnl
                else:
                    stats[strategy]["losses"] += 1
                    stats[strategy]["loss_amt"] += abs(pnl)
                
    # Finalize win rates
    final_stats = {}
    for strat, data in stats.items():
        total = data["wins"] + data["losses"]
        win_rate = (data["wins"] / total * 100) if total > 0 else 0
        avg_win = data["win_amt"] / data["wins"] if data["wins"] > 0 else 0
        avg_loss = data["loss_amt"] / data["losses"] if data["losses"] > 0 else 0
        
        final_stats[strat] = {
            "win_rate": round(win_rate, 2),
            "avg_pnl": round(data["total_pnl"] / total, 4) if total > 0 else 0,
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "total_trades": total,
            "score": round(win_rate * (total ** 0.5), 2) # Weighted score
        }
        
    return final_stats

def run_feedback_loop():
    print(f"[{datetime.now(EST).strftime('%H:%M:%S')}] 📉 SIGNAL QUALITY AGENT — Processing logs...")
    
    trades = parse_execution_log()
    if not trades:
        print("  ⚠️ No trades found in execution.log.")
        return
        
    stats = calculate_stats(trades)
    
    with open(QUALITY_FILE, 'w') as f:
        json.dump({
            "last_updated": datetime.now(EST).isoformat(),
            "strategies": stats
        }, f, indent=4)
        
    print(f"  ✅ Analyzed {len(stats)} strategies.")
    for strat, s in stats.items():
        print(f"  - {strat}: {s['win_rate']}% Win Rate | {s['total_trades']} Trades")
    print(f"  ✅ Report saved to {QUALITY_FILE}")

if __name__ == '__main__':
    run_feedback_loop()
