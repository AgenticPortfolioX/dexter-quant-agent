import sys
import os
from datetime import datetime
import pytz
import json

# Add project root to path
sys.path.append(r"C:\Users\jmgra\antigravityagents\dexter-quant-agent")

from live_monitor import MarketScheduler

def verify_fix():
    scheduler = MarketScheduler()
    # Mocking is_pilot_light_on to return False (like it is currently)
    # Actually, the scheduler reads from disk, and we know PILOT_LIGHT.json is false.
    
    EST = pytz.timezone('US/Eastern')
    now = datetime.now(EST)
    
    print(f"Current Time (EST): {now}")
    print(f"Weekday: {now.weekday()} (0=Mon, 5=Sat, 6=Sun)")
    
    state, msg = scheduler.get_market_state()
    print(f"Reported State: {state}")
    print(f"Status Message: {msg}")
    
    if now.weekday() >= 5:
        if state == "DORMANT":
            print("SUCCESS: Weekend detected and correctly assigned DORMANT state.")
        else:
            print(f"FAILURE: Expected DORMANT on weekend, but got {state}.")
    else:
        print("Note: This script is running on a weekday, check manually.")

if __name__ == "__main__":
    verify_fix()
