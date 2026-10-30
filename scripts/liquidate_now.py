import sys
import os
import requests
import yfinance as yf
from datetime import datetime
import pytz

# Add project root to path
sys.path.append(r"C:\Users\jmgra\antigravityagents\dexter-quant-agent")

from strategies.validation.alpha_autotrader import execute_trade, get_active_positions

EST = pytz.timezone('US/Eastern')

def liquidate_all():
    print(f"[{datetime.now()}] STARTING GLOBAL LIQUIDATION FOR WEEKEND...")
    
    # 1. Fetch all positions
    active_positions = get_active_positions(mode="LIVE_MARKET")
    if not active_positions:
        print("No active positions found.")
        return
    
    print(f"Active Positions: {active_positions}")
    
    for asset, qty in active_positions.items():
        print(f"Processing {asset} (Qty: {qty})...")
        try:
            # 2. Get current price
            ticker = yf.Ticker(asset)
            hist = ticker.history(period="1d")
            if hist.empty:
                print(f"Could not fetch price for {asset}, using 0.0 (Market Order will still work)")
                current_price = 0.0
            else:
                current_price = hist['Close'].iloc[-1]
            
            # 3. Execute Sell with explicit quantity override
            # Note: We use the modified execute_trade that now supports quantity_override
            print(f"Closing {asset} at ~${current_price:.2f}...")
            execute_trade(
                strategy_name="Weekend Liquidation",
                ticker=asset,
                side="SELL",
                price=current_price,
                mode="LIVE_MARKET",
                quantity_override=qty
            )
            print(f"Closed {asset}.")
        except Exception as e:
            print(f"Failed to close {asset}: {e}")

    print(f"[{datetime.now()}] LIQUIDATION PROCESS COMPLETE.")

if __name__ == "__main__":
    liquidate_all()
