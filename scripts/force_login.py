"""
force_login.py — Wraps robin_stocks login with retry logic for 429 push challenge.
Monkeypatches the challenge responder to sleep between polls.
"""
import os, sys, time
import robin_stocks.robinhood as r
import robin_stocks.robinhood.authentication as rh_auth
import requests
from dotenv import load_dotenv

load_dotenv()

USERNAME = os.getenv("ROBINHOOD_USERNAME")
PASSWORD = os.getenv("ROBINHOOD_PASSWORD")

print("Logging in as:", USERNAME)

# --- Monkeypatch: wrap respond_to_challenge to add 429-tolerant retry ---
_original_respond = rh_auth.respond_to_challenge

def _patched_respond(challenge_id, sms_code):
    """Retry the challenge response up to 10 times with backoff on 429."""
    for attempt in range(10):
        try:
            result = _original_respond(challenge_id, sms_code)
            return result
        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                wait = 8 + (attempt * 3)
                print(f"  [attempt {attempt+1}/10] 429 rate limit hit. Waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise Exception("Max retries exceeded on challenge response.")

rh_auth.respond_to_challenge = _patched_respond

# --- Monkeypatch: patch get_prompts_status poller if it exists ---
try:
    import robin_stocks.robinhood.helper as rh_helper
    _orig_request = rh_helper.request_get

    def _safe_request_get(url, *args, **kwargs):
        for attempt in range(8):
            try:
                result = _orig_request(url, *args, **kwargs)
                return result
            except Exception as e:
                if "429" in str(e) and "get_prompts_status" in url:
                    wait = 10 + (attempt * 5)
                    print(f"  [push poll {attempt+1}/8] 429 on status check, sleeping {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        return None

    rh_helper.request_get = _safe_request_get
    print("Push poller patched (429-tolerant).")
except Exception as patch_err:
    print(f"Could not patch request_get: {patch_err}")

# --- Main login ---
print("Sending login request (device push will fire to your Robinhood app)...")
print("Please APPROVE the login in your Robinhood app when prompted.")
print()

try:
    login = r.login(USERNAME, PASSWORD, expiresIn=86400, store_session=True)
    if login is None:
        print("Login returned None — push likely timed out or was rate limited.")
    else:
        print("Login Response:", login)
        print()
        print("SUCCESS - session persisted.")
except Exception as e:
    print(f"ERROR during login: {e}")
