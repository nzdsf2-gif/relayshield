"""One-off x402 seed settle for POST /v1/passport/issue ($0.50).

The batch seeding script only builds /v1/payg/{slug} URLs, so the
passport route (which lives outside /v1/payg/) gets this dedicated
runner. Same signer loading, same safety shape as the batch script:
fetch the 402 first, assert payTo and amount, check the payer balance,
then sign one EIP-3009 authorization and settle. Prints the HTTP
status, the settlement tx, and the full response body (the issued
passport JSON) for verification.

Payer: X402_BUYER_PRIVATE_KEY (or X402_BUYER_MNEMONIC with
X402_FROM_ADDRESS, or the local seeding wallet file). The payer must
NOT be the payTo wallet. Use the Backpack wallet.

Usage: python3 00-x402-passport-seed.py
"""
import base64
import json
import os
import secrets
import sys
import time
from pathlib import Path

import requests
from eth_account import Account
from eth_account.messages import encode_typed_data

try:
    Account.enable_unaudited_hdwallet_features()
except Exception:
    pass

VERSION = "passport-seed v1 (2026-10-22)"
URL = "https://api.relayshield.net/v1/passport/issue"
EXPECTED_PAYTO = "0x002CfD89c5636F45E3C8576D6E35154748412bAc"
EXPECTED_AMOUNT = 500000
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CHAIN_ID = 8453
RPC_URL = "https://base-rpc.publicnode.com"
WALLET_FILE = Path.home() / "Downloads" / ".rs-seed-wallet.json"
HD_PATH = "m/44'/60'/0'/0/{}"

BODY = {"subject": {"agent_id": "relayshield-seed",
                    "wallet": "0xa26054A4188e6D5c31A4DcdFcA27b0FfE247228d"},
        "verifications": {"tap": {"status": "not_performed"}},
        "screening": {"checks_total": 0, "flags_total": 0,
                      "last_screened_at": "2026-10-22T20:40:00Z"}}


def load_signer():
    expected = os.environ.get("X402_FROM_ADDRESS", "").strip()
    key = os.environ.get("X402_BUYER_PRIVATE_KEY", "").strip()
    if key:
        acct = Account.from_key(key)
        return acct, (expected or acct.address)
    mnemonic = os.environ.get("X402_BUYER_MNEMONIC", "").strip()
    if mnemonic:
        target = (expected or EXPECTED_PAYTO).lower()
        for i in range(20):
            a = Account.from_mnemonic(mnemonic, account_path=HD_PATH.format(i))
            if a.address.lower() == target:
                return a, a.address
        raise SystemExit(f"ABORT: no derived account at indices 0..19 matches {target}.")
    if WALLET_FILE.exists():
        data = json.loads(WALLET_FILE.read_text())
        acct = Account.from_key(data["private_key"])
        return acct, data["address"]
    raise SystemExit("ABORT: no payer credentials found. Set X402_BUYER_PRIVATE_KEY first.")


def usdc_balance(address: str) -> int:
    data = "0x70a08231" + "0" * 24 + address[2:].lower()
    r = requests.post(RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                                     "params": [{"to": USDC_BASE, "data": data}, "latest"]}, timeout=30)
    return int(r.json()["result"], 16)


def main() -> int:
    print(VERSION)
    acct, expected_from = load_signer()
    print("payer:", acct.address)
    if acct.address.lower() != expected_from.lower():
        print("ABORT: signer does not match the expected payer", expected_from)
        return 1
    if acct.address.lower() == EXPECTED_PAYTO.lower():
        print("ABORT: payer is the payTo wallet. Facilitators reject self-payments; use the Backpack wallet.")
        return 1

    r = requests.post(URL, json=BODY, timeout=30)
    if r.status_code != 402:
        print(f"ABORT: issue returned HTTP {r.status_code}, expected 402. Body: {r.text[:400]}")
        return 1
    x = r.json()["x402"]
    if x.get("x402Version") != 2:
        print(f"ABORT: challenge x402Version is {x.get('x402Version')}, expected 2.")
        return 1
    accept = next(a for a in x["accepts"] if a["network"] in ("base", "eip155:8453"))
    amount = int(accept.get("maxAmountRequired") or accept.get("amount"))
    if accept["payTo"].lower() != EXPECTED_PAYTO.lower():
        print(f"ABORT: payTo {accept['payTo']} does not match {EXPECTED_PAYTO}.")
        return 1
    if amount != EXPECTED_AMOUNT:
        print(f"ABORT: amount {amount} does not match expected {EXPECTED_AMOUNT}.")
        return 1

    balance = usdc_balance(acct.address)
    print(f"passport/issue: $0.50; payer balance {balance / 1e6:.2f} USDC")
    if balance < amount:
        print("ABORT: balance is short. Nothing was paid.")
        return 1

    nonce = "0x" + secrets.token_hex(32)
    valid_after = 0
    valid_before = int(time.time()) + int(accept.get("maxTimeoutSeconds", 300)) - 30
    typed = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {"name": accept["extra"]["name"], "version": accept["extra"]["version"],
                   "chainId": CHAIN_ID, "verifyingContract": accept["asset"]},
        "message": {"from": acct.address, "to": accept["payTo"], "value": amount,
                    "validAfter": valid_after, "validBefore": valid_before, "nonce": nonce},
    }
    signed = acct.sign_message(encode_typed_data(full_message=typed))
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature
    authorization = {"from": acct.address, "to": accept["payTo"], "value": str(amount),
                     "validAfter": str(valid_after), "validBefore": str(valid_before), "nonce": nonce}
    envelope = {"x402Version": 2, "accepted": accept,
                "payload": {"signature": signature, "authorization": authorization}}
    header_value = base64.b64encode(json.dumps(envelope).encode()).decode()

    r = requests.post(URL, json=BODY, headers={"PAYMENT-SIGNATURE": header_value}, timeout=90)
    tx = ""
    for h in ("PAYMENT-RESPONSE", "X-PAYMENT-RESPONSE"):
        if r.headers.get(h):
            try:
                tx = json.loads(base64.b64decode(r.headers[h])).get("transaction", "")
            except Exception:
                pass
    print(f"HTTP {r.status_code}" + (f" tx {tx}" if tx else ""))
    print("response body:")
    print(r.text)
    if r.status_code == 200 and tx:
        print("SETTLED. Send the response body above back for check + status verification.")
        return 0
    print("NOT SETTLED as expected; send the output above for diagnosis before retrying.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
