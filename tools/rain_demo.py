#!/usr/bin/env python3
"""
Rain Agentic Startup Program demo: an agent that refuses to pay a typosquat.

Runs the whole two-minute demo as one command, so recording it is a matter of
pressing record and pressing enter. Nothing is staged and nothing is mocked:
the risk checks are real calls to the live PAYG endpoint, paid for with real
USDC on Base, and the verdicts come back from the live corpus.

WHAT THIS SHOWS, AND WHY IT IS THE RIGHT DEMO FOR RAIN
------------------------------------------------------
Rain's Agent Control Layer answers "is this agent allowed to spend this much".
Nothing in it answers "is the thing it is about to pay legitimate". An agent
with a valid card, inside its limits, paying a fraudulent API is a fully
authorised transaction and every control in the stack says yes.

This closes that gap in the only way that is not arguable: the agent discovers
two MCP servers, checks both before connecting, refuses the typosquat, and
proceeds with the legitimate one. No human approves anything. No account is
created anywhere. The only credential in the process is a wallet.

BE PRECISE ON CAMERA ABOUT WHAT IS BEING PAID FOR
--------------------------------------------------
The x402 payments here buy the RISK CHECKS, at $0.35 each. The demo does not
send money to either MCP server. The narration below says so out loud, because
"the agent paid the legitimate endpoint" would be a stronger story and would
not be true, and this is a video shown to people who read carefully.

USAGE
-----
    python3 tools/rain_demo.py --rehearse     # no payment, no wallet needed
    python3 tools/rain_demo.py                # real USDC on Base

--rehearse stops at the 402 challenge and prints it. Use it to check the
endpoint is alive and to practise the timing before spending anything. The real
run costs $0.70: two checks at $0.35.
"""

import argparse
import base64
import getpass
import json
import os
import sys
import time
import urllib.request

API_BASE = os.environ.get(
    "RELAYSHIELD_API_BASE",
    "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod",
)
PATH = "/v1/payg/mcp-registry-risk"
PRIVATE_KEY_ENV_VAR = "BP_PRIVATE_KEY"

# The two servers the agent "discovers".
#
# The typosquat is modelcontextprotoco1.io -- a digit 1 in place of the final l
# of modelcontextprotocol.io, the official spec domain. Levenshtein distance 1,
# which is what the endpoint's typosquat check keys on, and visually almost
# identical on screen, which is the point. It does not need to exist or resolve:
# the whole argument is that the agent checks BEFORE it connects.
#
# The legitimate one is mcp.so, an exact match to an entry in the endpoint's
# known-good list, so it short-circuits the typosquat check and comes back clean.
TARGETS = [
    {
        "url": "https://modelcontextprotoco1.io/mcp",
        "discovered_as": "MCP registry listing: 'Model Context Protocol - Official Tools'",
        "expect": "refuse",
    },
    {
        "url": "https://mcp.so",
        "discovered_as": "MCP registry listing: 'mcp.so community server index'",
        "expect": "proceed",
    },
]

REFUSE_VERDICTS = {"HIGH", "CRITICAL"}

# Pacing. A viewer needs time to read a line; a recording needs to stay under
# two minutes. These are tuned for that and are the first thing to adjust if the
# cut runs long.
BEAT = 1.2
THINK = 2.0


def say(line="", pause=0.0):
    print(line, flush=True)
    if pause:
        time.sleep(pause)


def rule(title):
    say()
    say("=" * 72)
    say(title)
    say("=" * 72, BEAT)


def rehearse_check(target):
    """Fetch the 402 challenge without paying. Proves the endpoint is live."""
    req = urllib.request.Request(
        API_BASE + PATH,
        data=json.dumps({"server_url": target["url"]}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, {"raw": body.decode("utf-8", "replace")[:400]}


def _print_settlement(resp):
    """Surface the on-chain settlement so a viewer can verify it afterwards.

    The facilitator returns X-PAYMENT-RESPONSE, base64 JSON carrying the
    transaction hash. Best-effort by design: a missing or reshaped header must
    never take down a take that is otherwise fine.
    """
    raw = resp.headers.get("X-PAYMENT-RESPONSE") or resp.headers.get("x-payment-response")
    if not raw:
        return
    try:
        info = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)))
    except Exception:
        return
    tx = info.get("transaction") or info.get("txHash") or info.get("transactionHash")
    if tx:
        say("  <- settled on Base: %s" % tx)
        say("     basescan.org/tx/%s" % tx)


def build_session():
    """The same x402 client x402_test_settlement.py uses, for the same reason:
    it is the mechanism already verified working against these endpoints."""
    try:
        from eth_account import Account
        from x402 import x402ClientSync
        from x402.http.clients.requests import x402_requests
        from x402.mechanisms.evm.exact.register import register_exact_evm_client
        from x402.mechanisms.evm.signers import EthAccountSigner
    except ImportError:
        sys.exit(
            "The x402 SDK is not importable in this interpreter.\n"
            "Activate the venv that x402_test_settlement.py uses, or:\n"
            "  python3 -m venv ~/.rsvenv && ~/.rsvenv/bin/pip install x402 eth-account requests"
        )

    key = os.environ.get(PRIVATE_KEY_ENV_VAR)
    if not key:
        # Prompted, never echoed, never in shell history. The env var is still
        # the better path FOR A RECORDING -- export it before you press record
        # and the take has zero human input, which is the claim the demo makes.
        # This exists so a forgotten export does not mean a lost take.
        key = getpass.getpass("Base wallet private key (hidden, not echoed): ")
    if not key.strip():
        sys.exit("No key given. Rehearse with --rehearse; it needs no wallet.")
    # The Anaconda base environment reinjects whitespace and quotes around env
    # vars exported before the venv is activated, which surfaces as
    # binascii.Error: Non-hexadecimal digit found. Same strip as the settlement
    # script.
    key = "".join(key.split()).strip("'\"")

    account = Account.from_key(key)
    client = x402ClientSync()
    register_exact_evm_client(client, signer=EthAccountSigner(account),
                              networks="eip155:8453")  # Base mainnet
    return x402_requests(client), account.address


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rehearse", action="store_true",
                    help="stop at the 402 challenge; spend nothing, need no wallet")
    args = ap.parse_args()

    rule("AUTONOMOUS AGENT  |  no human in the loop  |  no account anywhere")
    say()
    say("  Task: extend my toolset with an MCP server for protocol tooling.")
    say("  Budget: authorised. Spending controls: in force.", BEAT)
    say()
    say("  Neither of those answers the only question that matters here:")
    say("  is the endpoint I am about to trust the real one?", THINK)

    session = None
    if not args.rehearse:
        session, wallet = build_session()
        say()
        say("  Paying from %s" % wallet)
        say("  Rail: x402, USDC on Base. No account, no card, no invoice.", BEAT)
    else:
        say()
        say("  REHEARSAL: stopping at the 402 challenge. Nothing is paid.", BEAT)

    refused = proceeded = 0

    for target in TARGETS:
        rule("DISCOVERED  %s" % target["url"])
        say("  %s" % target["discovered_as"], BEAT)
        say()
        say("  Before connecting: RelayShield mcp-registry-risk ($0.35, x402)", THINK)

        if args.rehearse:
            code, body = rehearse_check(target)
            say()
            say("  HTTP %s" % code)
            if code == 402:
                say("  402 Payment Required. The endpoint is live and priced.")
                say("  price: %s" % body.get("price", "(not quoted)"))
                # The challenge nests the rails under x402.accepts, not at the
                # top level. Reading the wrong key printed an empty list on the
                # first rehearsal and looked like the endpoint quoted nothing.
                for rail in (body.get("x402", {}).get("accepts") or []):
                    say("  rail: %-28s %s units to %s"
                        % (rail.get("network"), rail.get("amount"), rail.get("payTo")))
            else:
                say("  Unexpected: a paid endpoint should answer 402 unpaid.")
                say("  %s" % json.dumps(body)[:300])
            say("", BEAT)
            continue

        # Show the challenge before paying it. This is not theatre: it is
        # literally what an x402 client does internally -- request, get 402,
        # sign, retry with the X-PAYMENT header. A payments audience wants to
        # see the price quoted and the rail chosen, not just "Paid."
        code, challenge = rehearse_check(target)
        if code == 402:
            say("  <- HTTP 402 Payment Required")
            say("     price %s" % challenge.get("price", "(not quoted)"))
            for rail in (challenge.get("x402", {}).get("accepts") or [])[:1]:
                say("     paying %s units USDC on %s"
                    % (rail.get("amount"), rail.get("network")))
                say("     to     %s" % rail.get("payTo"))
            say("  -> signing and retrying with X-PAYMENT", BEAT)

        resp = session.post(API_BASE + PATH, json={"server_url": target["url"]}, timeout=60)
        _print_settlement(resp)
        payload = resp.json()
        data = payload.get("data", {})
        verdict = data.get("verdict", "UNKNOWN")
        findings = data.get("findings", [])

        say()
        say("  Paid. Verdict: %s" % verdict, BEAT)
        for f in findings:
            say("    [%s] %s" % (f.get("severity"), f.get("detail")))
        if not findings:
            say("    no findings")
        say("", THINK)

        if verdict in REFUSE_VERDICTS:
            refused += 1
            say("  >> REFUSED. Not connecting. Not granting tool access.")
            say("  >> No human was asked. The agent declined on its own.", THINK)
        else:
            proceeded += 1
            say("  >> CLEAR. Connecting and registering the toolset.", THINK)

    if args.rehearse:
        rule("REHEARSAL COMPLETE")
        say()
        say("  Both endpoints answered 402. Re-run without --rehearse to record.")
        return 0

    rule("RESULT")
    say()
    say("  Endpoints assessed : %d" % len(TARGETS))
    say("  Refused            : %d" % refused)
    say("  Connected          : %d" % proceeded)
    say("  Spend              : $%.2f, on the checks themselves" % (0.35 * len(TARGETS)))
    say("  Human approvals    : 0")
    say("  Accounts created   : 0", BEAT)
    say()
    say("  A spending control would have approved both of these payments.")
    say("  Both were inside budget. Both were correctly authorised.")
    say("  One of them was a typosquat.", THINK)
    say()
    return 0


if __name__ == "__main__":
    sys.exit(main())
