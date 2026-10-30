import os
import pyotp
import robin_stocks.robinhood as r
from dotenv import load_dotenv

def test_login():
    load_dotenv()
    
    username = os.getenv("ROBINHOOD_USERNAME")
    password = os.getenv("ROBINHOOD_PASSWORD")
    totp_secret = os.getenv("ROBINHOOD_TOTP_SECRET")
    
    if not totp_secret:
        print("❌ ERROR: ROBINHOOD_TOTP_SECRET not found in .env")
        print("Please follow the instructions in implementation-plan.md to add it.")
        return

    print(f"--- Robinhood TOTP Login Test ---")
    print(f"Username: {username}")
    
    try:
        # Generate the 6-digit code
        totp = pyotp.TOTP(totp_secret).now()
        print(f"Generated TOTP Code: {totp}")
        
        print("Attempting login...")
        login_data = r.login(username, password, mfa_code=totp, store_session=True)
        
        if login_data and 'access_token' in login_data:
            print("✅ SUCCESS: Login successful!")
            print(f"Token expires in: {login_data.get('expires_in')} seconds")
            
            # Verify we can actually fetch something
            profile = r.load_account_profile()
            print(f"Account Type: {profile.get('type')}")
            print(f"Portfolio Cash: {profile.get('portfolio_cash')}")
        else:
            print(f"❌ FAILED: Login response did not contain access_token.")
            print(f"Response: {login_data}")
            
    except Exception as e:
        print(f"💥 CRITICAL ERROR during login test: {e}")

if __name__ == "__main__":
    test_login()
