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
    
    print(f"DEBUG: Attempting login for {username}")
    
    # This will trigger the verification workflow
    # We use store_session=True to save the pickle
    login_data = r.login(username, password, expiresIn=86400, store_session=True)
    
    print(f"DEBUG: Login Result: {login_data}")

except Exception as e:
    print("DEBUG: CRITICAL ERROR")
    traceback.print_exc()
    sys.exit(1)
