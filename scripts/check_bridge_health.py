import requests
import json

try:
    resp = requests.get("http://localhost:5005/health", timeout=5)
    print(json.dumps(resp.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
