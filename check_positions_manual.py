import os
import sys
import json
import robin_stocks.robinhood as r
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

def check_positions():
    username = os.getenv("ROBINHOOD_USERNAME")
    password = os.getenv("ROBINHOOD_PASSWORD")
    
    print(f"Attempting login for {username}...")
    try:
        # Use a longer timeout or just one attempt
        login = r.login(username, password)
        print(f"Login successful: {login is not None}")
        
        print("Fetching holdings...")
        holdings = r.build_holdings()
        print(f"Successfully fetched {len(holdings)} stock positions.")
        
        print("Fetching options...")
        options = r.get_all_option_positions()
        print(f"Successfully fetched {len(options)} option positions.")
        
        result = {
            "stocks": holdings,
            "options": options
        }
        
        output_file = os.path.join(PROJECT_ROOT, "current_positions.json")
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=4)
        print(f"Positions saved to {output_file}")
        return result
    except Exception as e:
        print(f"FAILED: {e}")
        return None

if __name__ == "__main__":
    check_positions()
