import robin_stocks.robinhood as r
import pyotp
import os
from dotenv import load_dotenv
import json

load_dotenv()

def check_account_status():
    username = os.getenv("ROBINHOOD_USERNAME")
    password = os.getenv("ROBINHOOD_PASSWORD")
    totp_secret = os.getenv("ROBINHOOD_TOTP_SECRET")
    
    try:
        if totp_secret:
            totp = pyotp.TOTP(totp_secret).now()
            login_data = r.login(username, password, mfa_code=totp)
        else:
            login_data = r.login(username, password)
            
        if not login_data or 'access_token' not in login_data:
            print("ERROR: Login failed. No access token returned.", file=sys.stderr)
            sys.exit(1)

        profile = r.load_account_profile()
        if not profile:
            print("ERROR: Could not load account profile. Session may be invalid.", file=sys.stderr)
            sys.exit(1)

        day_trades = r.get_day_trades()
        
        status = {
            "account_type": profile.get("type"),
            "is_pdt": profile.get("is_pdt", False),
            "day_trades": len(day_trades.get("equity_day_trades", [])),
            "margin_buying_power": profile.get("margin_buying_power"),
            "locked": profile.get("locked", False)
        }
        print(json.dumps(status, indent=2))
    except Exception as e:
        print(f"ERROR: Exception during account status check: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    import sys
    check_account_status()
