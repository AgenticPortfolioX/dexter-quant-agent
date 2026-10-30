
import robin_stocks.robinhood as r
import os
from dotenv import load_dotenv

load_dotenv()

username = os.getenv("ROBINHOOD_USERNAME")
password = os.getenv("ROBINHOOD_PASSWORD")

print(f"Attempting manual login for {username}...")
try:
    # This will prompt for a code if MFA is required
    login = r.login(username, password, expiresIn=86400)
    print("Login Response Metadata:", login)
    print("\nSUCCESS: Session persisted. You can now close this test script.")
except Exception as e:
    print(f"\nERROR: Login failed: {e}")
