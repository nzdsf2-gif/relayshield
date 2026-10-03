#!/usr/bin/env python3
"""Read-only check of GoPlus's Solana token_security response shape.

WHY. _status_on() in relayshield_api.py treats a Solana capability as active
when `status` is the string "1". That convention was mirrored from GoPlus's EVM
API and has NEVER been confirmed against a live Solana response, because
api.gopluslabs.io is not reachable from the build container. This prints the
raw values so the convention is read rather than assumed.

USDC is the default positive control: Circle holds a freeze authority on it, so
`freezable.status` should be "1" there. If it prints "0" or anything else, the
convention is wrong and every Solana scam token is being graded on a guess.

Usage (no AWS, no key, no writes):
    python3 tools/verify_goplus_solana.py
    python3 tools/verify_goplus_solana.py MINT_ADDRESS ...
"""
import json
import sys
import urllib.request

URL = "https://api.gopluslabs.io/api/v1/solana/token_security?contract_addresses="
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
ARJEN = "5aXSfstoUYp4uBEpJoMyMrzLFNFyrMQZ5d2u7yVFD"
CAPABILITIES = ("freezable", "balance_mutable_authority", "mintable", "closable", "metadata_mutable")


def fetch(mint: str) -> dict:
    req = urllib.request.Request(URL + mint, headers={"User-Agent": "RelayShield/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def describe(mint: str, body: dict) -> list[str]:
    """One line per capability, plus a verdict on whether our parser's
    assumption holds. Never raises on a surprising shape: a surprise is the
    finding, so it is printed."""
    lines = [f"== {mint}", f"   code={body.get('code')!r} message={body.get('message')!r}"]
    result = (body.get("result") or {})
    raw = result.get(mint) or result.get(mint.lower()) or {}
    if not raw:
        lines.append("   NO TOKEN RECORD. GoPlus does not know this address as a token "
                     "(or it is mistyped). Our parser would no-op here.")
        return lines
    odd = []
    for name in CAPABILITIES:
        field = raw.get(name)
        if isinstance(field, dict):
            status = field.get("status")
            lines.append(f"   {name:<27} status={status!r} (type {type(status).__name__})"
                         f" authority={field.get('authority')!r}")
            if str(status) not in ("0", "1"):
                odd.append(name)
        else:
            lines.append(f"   {name:<27} NOT A DICT: {field!r}")
            odd.append(name)
    if odd:
        lines.append(f"   SURPRISE: {', '.join(odd)} do not match the {{status: '0'|'1'}} shape "
                     "_status_on() assumes. Paste this whole output back.")
    else:
        lines.append("   shape matches what _status_on() assumes.")
    return lines


def main(argv: list[str]) -> int:
    mints = argv or [USDC, ARJEN]
    rc = 0
    for mint in mints:
        try:
            body = fetch(mint)
        except Exception as exc:
            print(f"== {mint}\n   REQUEST FAILED: {type(exc).__name__}: {exc}")
            rc = 1
            continue
        print("\n".join(describe(mint, body)))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
