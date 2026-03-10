
import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import subprocess
import json
import time
import winsound

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from strategies.incubator.smc_btc_plus import SmartMoneyStrategy

# Configuration
FOCAL_PORTFOLIO = ["AAPL", "DIA", "JNJ", "WMT", "GS"]
POSITION_SIZE_USD = 25.0
MAX_CONCURRENT_TRADES = 3
BRIDGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'quant_scripts', 'robinhood_bridge.py')
LOG_DIR = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\live_trading"
TRACKING_BOARD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'dashboard', 'LIVE_TRACKING_BOARD.md')

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def get_active_trade_count():
    """Checks Robinhood for current open positions."""
    try:
        result = subprocess.run(
            [sys.executable, BRIDGE_PATH, "get_positions"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # count keys in data['stocks'] where quantity > 0
            return len([k for k, v in data.get('stocks', {}).items() if float(v.get('quantity', 0)) > 0])
    except Exception as e:
        print(f"Error checking positions: {e}")
    return 0

def play_trade_notification():
    """Plays an audible alert when a trade is executed."""
    try:
        # Professional "Double-Chirp" (1500Hz -> 2000Hz)
        winsound.Beep(1500, 80)
        winsound.Beep(2000, 120)
    except:
        try:
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
        except:
            pass

def update_live_tracking_board(strategy_name, ticker, side):
    """Adds a new trade entry to the LIVE_TRACKING_BOARD.md."""
    try:
        if not os.path.exists(TRACKING_BOARD_PATH): return
        
        now_est = datetime.now().strftime("%Y-%m-%d %H:%M:%S EST")
        new_entry = f"| **{strategy_name}** | {ticker} | {now_est} | {side} |\n"
        
        with open(TRACKING_BOARD_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        header_end_idx = 0
        for i, line in enumerate(lines):
            if ":---" in line:
                header_end_idx = i + 1
                break
        
        if header_end_idx > 0:
            lines.insert(header_end_idx, new_entry)
        else:
            lines.append(new_entry)
            
        with open(TRACKING_BOARD_PATH, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    except Exception as e:
        print(f"Error updating tracking board: {e}")

def execute_trade(ticker, side, price):
    """Calls the Robinhood Bridge to execute a trade."""
    print(f"EXECUTING {side.upper()} order for {ticker} at ${price:.2f}")
    
    # Calculate quantity
    quantity = round(POSITION_SIZE_USD / price, 4)
    if quantity <= 0:
        print("Quantity too small.")
        return
    
    action = f"{side.lower()}_stock"
    cmd = [
        sys.executable, BRIDGE_PATH, action,
        "--symbol", ticker,
        "--quantity", str(quantity),
        "--order_type", "limit",
        "--price", str(round(price, 2))
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        log_entry = f"[{datetime.now()}] {ticker} {side} {quantity} @ {price}: {result.stdout}\n"
        with open(os.path.join(LOG_DIR, "trade_execution.log"), "a") as f:
            f.write(log_entry)
        print(f"Bridge Response: {result.stdout}")
        
        # Update Tracking Board and Sound Notification
        update_live_tracking_board("SMC Live", ticker, side)
        play_trade_notification()
    except Exception as e:
        print(f"Bridge Execution Error: {e}")

def run_live_smc_scanner():
    print(f"--- SMC LIVE AUTO-TRADER STARTED [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ---")
    print(f"Risk Profile: ${POSITION_SIZE_USD} per trade | Max: {MAX_CONCURRENT_TRADES} trades")
    
    strategy = SmartMoneyStrategy()
    
    # 1. Check Portfolio Capacity
    active_count = get_active_trade_count()
    print(f"Active Trades Count: {active_count}/{MAX_CONCURRENT_TRADES}")
    
    if active_count >= MAX_CONCURRENT_TRADES:
        print("Max concurrent trades reached. Scanning for exits/info only.")

    for ticker in FOCAL_PORTFOLIO:
        print(f"Scanning {ticker}...")
        try:
            # Fetch latest 1h data
            df = yf.download(ticker, period="7d", interval="1h", progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            if df.empty: continue
            
            # Apply Logic
            df = strategy.add_indicators(df)
            df = strategy.process_logic(df)
            
            # Get latest candle with closed status
            # We look at the last 2 candles to ensure we catch a transition
            latest_rows = df.tail(2)
            
            for idx, row in latest_rows.iterrows():
                sig = row['entry_signal']
                if sig in ["BUY", "SELL"]:
                    print(f"!!! SIGNAL DETECTED: {ticker} -> {sig} !!!")
                    
                    if active_count < MAX_CONCURRENT_TRADES:
                        price = row['bullish_fvg_top'] if sig == "BUY" else row['bearish_fvg_bottom']
                        execute_trade(ticker, sig, price)
                        active_count += 1 # Optimistic increment for the scan
                    else:
                        print(f"Signal ignored for {ticker} (Max trades hit).")
                
                elif row['mss_signal']:
                    print(f"[{ticker}] Structure Shift: {row['mss_signal']}. Pending FVG retrace.")

        except Exception as e:
            print(f"Error scanning {ticker}: {e}")

    print(f"Scan Finished at {datetime.now()}. Waiting for next cycle.")

if __name__ == "__main__":
    run_live_smc_scanner()
