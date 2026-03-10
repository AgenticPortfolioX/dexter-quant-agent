import robin_stocks.robinhood as r
import os
from dotenv import load_dotenv
import json

load_dotenv()

def debug_pdt():
    r.login(os.getenv("ROBINHOOD_USERNAME"), os.getenv("ROBINHOOD_PASSWORD"))
    day_trades = r.get_day_trades()
    print(json.dumps(day_trades, indent=2))

if __name__ == "__main__":
    debug_pdt()
