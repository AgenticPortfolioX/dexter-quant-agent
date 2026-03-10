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
    
    if totp_secret:
        totp = pyotp.TOTP(totp_secret).now()
        r.login(username, password, mfa_code=totp)
    else:
        r.login(username, password)
        
    profile = r.load_account_profile()
    day_trades = r.get_day_trades()
    
    status = {
        "account_type": profile.get("type"),
        "is_pdt": profile.get("is_pdt", False),
        "day_trades": len(day_trades.get("equity_day_trades", [])),
        "margin_buying_power": profile.get("margin_buying_power"),
        "locked": profile.get("locked", False)
    }
    print(json.dumps(status, indent=2))

if __name__ == "__main__":
    check_account_status()
