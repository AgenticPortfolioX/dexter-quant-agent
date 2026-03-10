import json
import os
from datetime import datetime
import pytz

ROOT = os.path.dirname(os.path.abspath(__file__))
PILOT_PATH = os.path.join(ROOT, "..", "PILOT_LIGHT.json")
# PILOT_LIGHT.json is in root, so .. from /dashboard/ is correct.
EST = pytz.timezone('US/Eastern')

def toggle():
    if not os.path.exists(PILOT_PATH):
        state = {"enabled": True, "last_toggle": datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")}
    else:
        with open(PILOT_PATH, 'r') as f:
            state = json.load(f)
    
    # Flip the state
    state["enabled"] = not state["enabled"]
    state["last_toggle"] = datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S EST")
    
    with open(PILOT_PATH, 'w') as f:
        json.dump(state, f, indent=4)
    
    status_str = "ENABLED (🟢 Green Light)" if state["enabled"] else "DISABLED (🔴 Red Light)"
    print(f"PILOT LIGHT is now: {status_str}")
    
    # Optionally trigger a rebuild or monitor refresh here
    # For now, the monitor will pick it up on the next loop (60s)

if __name__ == "__main__":
    toggle()
