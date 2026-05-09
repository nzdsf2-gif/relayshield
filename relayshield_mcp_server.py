#!/usr/bin/env python3
"""
RelayShield MCP Server

Exposes RelayShield security intelligence as callable tools for Claude
and other MCP-compatible AI agents.

Configuration (environment variables):
  RELAYSHIELD_API_URL   — API Gateway invoke URL (required)
                          https://xhh3tfrhng.execute-api.us-east-1.amazonaws.com/prod
  RELAYSHIELD_API_KEY   — x-api-key for subscription access (RapidAPI / API Gateway)
  RELAYSHIELD_X_PAYMENT — x402 payment proof for pay-as-you-go access (USDC on Base)

Access modes:
  Subscription  — set RELAYSHIELD_API_KEY. All tools available.
  Pay-as-you-go — set RELAYSHIELD_X_PAYMENT with x402 payment proof. 4 tools available.
  Discovery     — set neither. Tool call returns payment requirements and pricing.

x402 PAYG pricing (USDC on Base):
  check_breach            $0.10
  check_sim_swap          $0.25
  check_domain_lookalikes $0.50
  check_oauth_watchlist   $0.15
  check_scan_result       $0.00  (free — poll a paid scan result)
  scan_url / scan_file    coming soon (VT commercial licensing pending)
"""

import asyncio
import json
import os

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE  = os.environ.get("RELAYSHIELD_API_URL", "").rstrip("/")
API_KEY   = os.environ.get("RELAYSHIELD_API_KEY", "")
X_PAYMENT = os.environ.get("RELAYSHIELD_X_PAYMENT", "")

PAYG_PRICING: dict[str, str] = {
    "check_breach":            "$0.10 USDC",
    "check_sim_swap":          "$0.25 USDC",
    "check_domain_lookalikes": "$0.50 USDC",
    "check_oauth_watchlist":   "$0.15 USDC",
    "check_scan_result":       "$0.00 USDC (free — poll result of a paid scan)",
    "scan_url":                "coming soon",
    "scan_file":               "coming soon",
}

VT_COMING_SOON = {"scan_url", "scan_file"}

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

app = Server("relayshield")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="check_breach",
            description=(
                "Check whether an email address appears in known data breaches. "
                "Uses Have I Been Pwned (HIBP) — 13 billion+ compromised accounts. "
                "Returns breach count and details (breach name, date, exposed data classes). "
                "Use before allowing high-risk actions that depend on credential integrity. "
                "Pay-as-you-go: $0.10 USDC per check (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "required": ["email"],
                "properties": {
                    "email": {
                        "type": "string",
                        "format": "email",
                        "description": "Email address to check",
                    }
                },
            },
        ),
        types.Tool(
            name="check_sim_swap",
            description=(
                "Detect whether a SIM swap or eSIM provisioning event has occurred on a phone number "
                "in the last 24 hours. Uses Twilio Lookup v2 with live carrier data. "
                "Returns swapped (bool), swap timestamp, and current carrier. "
                "Use when a user reports losing mobile service, or before completing a high-risk "
                "action that depends on SMS-based authentication. "
                "Pay-as-you-go: $0.25 USDC per check (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "required": ["phone"],
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Phone number in E.164 format (e.g. +14155551234)",
                        "pattern": "^\\+[1-9]\\d{6,14}$",
                    }
                },
            },
        ),
        types.Tool(
            name="check_domain_lookalikes",
            description=(
                "Detect typosquat and lookalike domains impersonating a brand. "
                "Generates hundreds of permutations (TLD swaps, character typos, homoglyphs, "
                "phishing prefixes/suffixes), resolves them in parallel via DNS, and enriches "
                "live results with Certificate Transparency data (cert count, recent issuance). "
                "Returns all lookalike domains that are currently registered and resolving. "
                "Use to find domains impersonating your brand, or before an employee clicks a "
                "link that resembles a company domain. "
                "Pay-as-you-go: $0.50 USDC per scan (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "required": ["domain"],
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Root domain to scan (e.g. acme.com — no scheme or path needed)",
                    }
                },
            },
        ),
        types.Tool(
            name="check_oauth_watchlist",
            description=(
                "Check whether any high-risk OAuth-capable SaaS apps connected to an email account "
                "have appeared in recent data breaches. Monitors a curated watchlist of apps "
                "(Slack, Notion, GitHub, Zapier, Vercel, Loom, HubSpot, AI tools, and more). "
                "An attacker who breaches these services may obtain OAuth tokens granting access "
                "to your Google Workspace or Microsoft 365 without touching your password. "
                "Returns matched breached apps and recommended revocation steps. "
                "Pay-as-you-go: $0.15 USDC per check (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "required": ["email"],
                "properties": {
                    "email": {
                        "type": "string",
                        "format": "email",
                        "description": "Email address whose connected OAuth apps to check",
                    }
                },
            },
        ),
        types.Tool(
            name="scan_url",
            description=(
                "Submit a URL for malware and phishing analysis across 70+ security engines. "
                "Returns an analysis_id immediately (async). "
                "Call check_scan_result with the analysis_id every 5 seconds until verdict is returned. "
                "Verdicts: malicious | suspicious | clean | timeout. "
                "Use before navigating to an unfamiliar URL or when a user forwards a suspicious link. "
                "Requires subscription API key — coming soon for pay-as-you-go. "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "format": "uri",
                        "description": "URL to scan (must start with http:// or https://)",
                    }
                },
            },
        ),
        types.Tool(
            name="scan_file",
            description=(
                "Submit a file for binary malware analysis across 70+ AV engines. "
                "Provide a publicly accessible download URL — RelayShield handles the download. "
                "Returns an analysis_id immediately (async). "
                "Call check_scan_result with the analysis_id every 5 seconds until verdict is returned. "
                "Verdicts: malicious | suspicious | clean | timeout. "
                "Use when a user receives an email attachment and forwards the download link. "
                "Requires subscription API key — coming soon for pay-as-you-go. "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "required": ["file_url"],
                "properties": {
                    "file_url": {
                        "type": "string",
                        "format": "uri",
                        "description": "Publicly accessible URL to download the file from",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional filename hint (e.g. invoice_march.pdf)",
                    },
                },
            },
        ),
        types.Tool(
            name="check_scan_result",
            description=(
                "Poll for the result of a previously submitted URL or file scan. "
                "Call every 5 seconds after scan_url or scan_file until status is 'completed'. "
                "Returns verdict (malicious/suspicious/clean) and engine vote counts, "
                "or {status: pending} if the scan is still running. "
                "Free with a paid scan (no additional charge)."
            ),
            inputSchema={
                "type": "object",
                "required": ["analysis_id"],
                "properties": {
                    "analysis_id": {
                        "type": "string",
                        "description": "analysis_id returned by scan_url or scan_file",
                    }
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if not API_BASE:
        return _error(
            "RELAYSHIELD_API_URL environment variable must be set. "
            "See MCP_SETUP.md for configuration instructions."
        )

    # VT-licensed tools require a subscription key — return coming soon for PAYG callers
    if not API_KEY and name in VT_COMING_SOON:
        return [types.TextContent(type="text", text=json.dumps({
            "ok": False,
            "tool": name,
            "status": "coming_soon",
            "message": (
                f"{name} requires a subscription API key. "
                "VT commercial licensing is pending for pay-as-you-go access. "
                "Subscribe at rapidapi.com/relayshield for early access."
            ),
        }))]

    # Build request headers — subscription key takes priority over x402 payment proof
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["x-api-key"] = API_KEY
    elif X_PAYMENT:
        headers["X-PAYMENT"] = X_PAYMENT
    # If neither is set, the API Gateway will return 402 with payment requirements

    payg = not API_KEY  # PAYG callers route to /v1/payg/ — API Gateway enforces key on /v1/
    try:
        async with httpx.AsyncClient(timeout=28.0) as client:
            r = await _dispatch(client, name, arguments, headers, payg)
    except httpx.TimeoutException:
        return _error("Request timed out — upstream API did not respond within 28 seconds.")
    except httpx.RequestError as exc:
        return _error(f"Network error: {exc}")

    if r.status_code == 402:
        return _payment_required(name, r)

    # Append conversion advisory on successful PAYG calls
    if not API_KEY and r.status_code == 200:
        return _payg_success(r.text, name)

    return [types.TextContent(type="text", text=r.text)]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

async def _dispatch(
    client: httpx.AsyncClient,
    name: str,
    arguments: dict,
    headers: dict,
    payg: bool,
) -> httpx.Response:
    # Subscription routes use /v1/, PAYG routes use /v1/payg/
    # API Gateway enforces API key on /v1/ — unauthenticated callers must use /v1/payg/
    base = f"{API_BASE}/v1/payg" if payg else f"{API_BASE}/v1"

    if name == "check_breach":
        return await client.post(
            f"{base}/breach",
            headers=headers,
            json={"email": arguments["email"]},
        )

    if name == "check_sim_swap":
        return await client.post(
            f"{base}/sim-swap",
            headers=headers,
            json={"phone": arguments["phone"]},
        )

    if name == "check_domain_lookalikes":
        return await client.post(
            f"{base}/domain",
            headers=headers,
            json={"domain": arguments["domain"]},
        )

    if name == "check_oauth_watchlist":
        return await client.post(
            f"{base}/oauth-watchlist",
            headers=headers,
            json={"email": arguments["email"]},
        )

    if name == "scan_url":
        return await client.post(
            f"{base}/scan-url",
            headers=headers,
            json={"url": arguments["url"]},
        )

    if name == "scan_file":
        body: dict = {"file_url": arguments["file_url"]}
        if "filename" in arguments:
            body["filename"] = arguments["filename"]
        return await client.post(
            f"{base}/scan-file",
            headers=headers,
            json=body,
        )

    if name == "check_scan_result":
        result_base = f"{API_BASE}/v1/payg" if payg else f"{API_BASE}/v1"
        return await client.get(
            f"{result_base}/result/{arguments['analysis_id']}",
            headers=headers,
        )

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _payment_required(tool_name: str, response: httpx.Response) -> list[types.TextContent]:
    price = PAYG_PRICING.get(tool_name, "see payment requirements")
    return [types.TextContent(type="text", text=json.dumps({
        "ok": False,
        "payment_required": True,
        "tool": tool_name,
        "price": price,
        "network": "Base (USDC)",
        "payment_requirements": response.headers.get("PAYMENT-REQUIRED", ""),
        "instructions": [
            f"1. Send {price} USDC on Base to the address in payment_requirements.",
            "2. Set env var RELAYSHIELD_X_PAYMENT=<payment_proof> and retry the tool call.",
            "3. Or subscribe for 96%+ lower per-check cost: rapidapi.com/relayshield",
        ],
    }))]


def _payg_success(response_text: str, tool_name: str) -> list[types.TextContent]:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        data = {"result": response_text}
    data["_advisory"] = (
        f"Pay-as-you-go rate: {PAYG_PRICING.get(tool_name, 'see pricing')}. "
        "Subscribe at rapidapi.com/relayshield for 96%+ lower per-check cost on monthly plans."
    )
    return [types.TextContent(type="text", text=json.dumps(data))]


def _error(message: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps({"ok": False, "error": message}))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
