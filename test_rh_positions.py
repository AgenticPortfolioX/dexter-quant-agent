
import robin_stocks.robinhood as r
import os
import pyotp
from dotenv import load_dotenv

load_dotenv()

def test_login():
    username = os.getenv("ROBINHOOD_USERNAME")
    password = os.getenv("ROBINHOOD_PASSWORD")
    totp_secret = os.getenv("ROBINHOOD_TOTP_SECRET")
    
    print(f"Attempting login for {username}...")
    try:
        if totp_secret:
            totp = pyotp.TOTP(totp_secret).now()
            res = r.login(username, password, mfa_code=totp)
        else:
            res = r.login(username, password)
        print(f"Login result: {res}")
    except Exception as e:
        print(f"Login exception: {e}")
        return
    
    print("--- Testing Positions ---")
    try:
        holdings = r.build_holdings()
        print(f"build_holdings success: {len(holdings)} assets")
        print(f"Assets: {list(holdings.keys())}")
    except Exception as e:
        print(f"build_holdings failed: {e}")

    try:
        all_pos = r.get_all_positions()
        print(f"get_all_positions success: {len(all_pos)} records")
        for p in all_pos[:3]:
            print(f" - Instrument: {p['instrument']}, Qty: {p['quantity']}")
    except Exception as e:
        print(f"get_all_positions failed: {e}")

    try:
        profile = r.load_account_profile()
        print(f"Account Profile Type: {profile.get('type')}")
        print(f"Full Profile keys: {list(profile.keys())}")
    except Exception as e:
        print(f"load_account_profile failed: {e}")

if __name__ == "__main__":
    test_login()
