import requests
import json
import time

BASE_URL = "http://localhost:5005"

def test_settlement_data():
    print("--- Testing /cash endpoint ---")
    try:
        resp = requests.get(f"{BASE_URL}/cash")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(json.dumps(resp.json(), indent=2))
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_settlement_data()
