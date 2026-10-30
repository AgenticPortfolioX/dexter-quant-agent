import os
import sys
import traceback
from dotenv import load_dotenv

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

try:
    import robin_stocks.robinhood as r
    from robin_stocks.robinhood.authentication import login_url, request_post, generate_device_token
    load_dotenv()
    
    username = os.getenv("ROBINHOOD_USERNAME")
    password = os.getenv("ROBINHOOD_PASSWORD")
    device_token = generate_device_token()
    
    url = login_url()
    payload = {
        'client_id': 'c82SH0WZOsabOXGP2sxqcj34FxkvfnWRZBKlBjFS',
        'expires_in': 86400,
        'grant_type': 'password',
        'password': password,
        'scope': 'internal',
        'username': username,
        'device_token': device_token,
        'try_passkeys': False,
    }

    print(f"DEBUG: Manually hitting login endpoint for: {username}")
    data = request_post(url, payload)
    
    if 'verification_workflow' in data:
        print(f"DEBUG: VERIFICATION REQUIRED! ID: {data['verification_workflow']['id']}")
        print(f"DEBUG: FULL RESPONSE: {data}")
    elif 'access_token' in data:
        print("DEBUG: WOW - Logged in directly!")
    else:
        print(f"DEBUG: Unknown response: {data}")

except Exception as e:
    print("DEBUG: CRITICAL ERROR")
    traceback.print_exc()
    sys.exit(1)
