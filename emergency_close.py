import requests
import json
import time

BRIDGE_URL = "http://localhost:5005"

def close_all():
    print("--- DEXTER EMERGENCY LIQUIDATION ---")
    try:
        # 1. Fetch current positions from bridge to be absolutely sure
        resp = requests.get(f"{BRIDGE_URL}/positions", timeout=15)
        if resp.status_code != 200:
            print(f"Error fetching positions: {resp.text}")
            return
        
        data = resp.json()
        stocks = data.get("stocks", {})
        
        if not stocks:
            print("No active stock positions found.")
        
        for ticker, pos in stocks.items():
            qty = float(pos.get('quantity', 0))
            if qty <= 0:
                continue
            
            print(f"Liquidating {ticker}: {qty} units...")
            
            payload = {
                "type": "stock",
                "action": "sell",
                "symbol": ticker,
                "quantity": qty,
                "order_type": "market"
            }
            
            try:
                order_resp = requests.post(f"{BRIDGE_URL}/order", json=payload, timeout=20)
                if order_resp.status_code == 200:
                    print(f"SUCCESS: {ticker} sell order submitted.")
                else:
                    print(f"FAILED: {ticker} liquidation failed: {order_resp.text}")
            except Exception as e:
                print(f"ERROR: Exception during {ticker} liquidation: {e}")
            
            time.sleep(1) # Breather between orders
            
        print("--- LIQUIDATION COMPLETE ---")
    
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    close_all()
