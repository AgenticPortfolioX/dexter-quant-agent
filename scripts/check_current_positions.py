import requests
import json
import os

def check_positions():
    try:
        resp = requests.get("http://localhost:5005/positions", timeout=10)
        if resp.status_code == 200:
            stocks = resp.json().get('stocks', {})
            active = {k: float(v.get('quantity', 0)) for k, v in stocks.items() if float(v.get('quantity', 0)) > 0}
            print(f"ACTIVE STOCKS: {active}")
            return active
        else:
            print(f"Error fetching positions: {resp.status_code}")
    except Exception as e:
        print(f"Connection error: {e}")
    return {}

if __name__ == "__main__":
    check_positions()
