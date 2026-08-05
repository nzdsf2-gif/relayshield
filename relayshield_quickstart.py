"""
RelayShield API — breach + infostealer check in sequence.

Sign up for an API key: https://api.relayshield.net/developers
Docs: https://api.relayshield.net/developers#api-reference
"""

import urllib.request
import json

API_KEY = "YOUR_RELAYSHIELD_API_KEY"
BASE    = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"

def rs_post(path, payload):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json", "X-RS-API-KEY": API_KEY},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

email = "user@example.com"

breach = rs_post("/v1/metered/breach", {"email": email})
print(f"Breaches found: {breach.get('breach_count', 0)}")

if breach.get("breach_count", 0) > 0:
    stealer = rs_post("/v1/metered/infostealer", {"email": email})
    print(f"Active infostealer exposure: {stealer.get('exposed', False)}")
    if stealer.get("exposed"):
        print(f"  Markets: {stealer.get('markets', [])}")
        print("  ACTION: credential reset + session revocation recommended")
