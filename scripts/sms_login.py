import os
import sys
import traceback
from dotenv import load_dotenv

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

try:
    import robin_stocks.robinhood as r
    load_dotenv()
    
    username = os.getenv("ROBINHOOD_USERNAME")
    password = os.getenv("ROBINHOOD_PASSWORD")
    
    print(f"FORCING SMS LOGIN for: {username}")
    
    # We use mfa_code=None but we will catch the input() if robin_stocks prompts for it
    # OR we can manually trigger the flow.
    # Actually, if we don't have TOTP, robin_stocks should prompt for SMS if push is not approved or not available.
    
    login_data = r.login(username, password, expiresIn=86400, store_session=True)
    
    print(f"SUCCESS: Login Result: {login_data}")

except Exception as e:
    print("CRITICAL ERROR during SMS login trigger")
    traceback.print_exc()
    sys.exit(1)
