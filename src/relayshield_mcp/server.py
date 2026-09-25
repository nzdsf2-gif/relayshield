#!/usr/bin/env python3
"""
RelayShield MCP Server

Exposes RelayShield security intelligence as callable tools for Claude
and other MCP-compatible AI agents.

Configuration (environment variables):
  RELAYSHIELD_API_URL   — API Gateway invoke URL (required)
                          https://api.relayshield.net
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
  check_oauth_watchlist   $0.30
  check_infostealer       $0.15
  check_scan_result       $0.00  (free — poll a paid scan result)
  scan_wallet             $0.10
  scan_url                $0.05
  scan_file               $0.10
  check_mcp_registry_risk       $0.35
  check_prompt_injection_breach $0.35
  check_supply_chain      $0.10
  check_session_risk      $0.30
  check_nhi_exposure      $0.40
  check_secret_scan       $0.35
  check_llm_credential_exposure $0.40
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
    "check_oauth_watchlist":   "$0.30 USDC",
    "check_infostealer":       "$0.15 USDC",
    "check_scan_result":       "$0.00 USDC (free — poll result of a paid scan)",
    "scan_wallet":             "$0.10 USDC",
    "scan_url":                "$0.05 USDC",
    "scan_file":               "$0.10 USDC",
    "check_mcp_registry_risk":       "$0.35 USDC",
    "check_prompt_injection_breach": "$0.35 USDC",
    "check_supply_chain":     "$0.10 USDC",
    "check_session_risk":     "$0.30 USDC",
    "check_nhi_exposure":     "$0.40 USDC",
    "check_secret_scan":      "$0.35 USDC",
    "check_llm_credential_exposure": "$0.40 USDC",
}

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

app = Server("relayshield")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    tools = [
        types.Tool(
            name="check_breach",
            description=(
                "Check whether an email address appears in known data breaches. "
                "Draws on 13 billion+ compromised accounts. "
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
            name="check_infostealer",
            description=(
                "Check whether an email address appears in infostealer malware logs. "
                "Draws on a database of credentials harvested directly from "
                "infected computers by infostealer malware (RedLine, Raccoon, Vidar, etc.). "
                "Returns found (bool), stealer count, and per-infection details: date compromised, "
                "operating system, malware path, and number of corporate/personal credentials stolen. "
                "Unlike breach databases, infostealer hits mean the device itself was "
                "compromised — all stored passwords, session cookies, and crypto keys are at risk. "
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
                        "description": "Email address to check for infostealer compromise",
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
                "Pay-as-you-go: $0.05 USDC per scan (x402 on Base). "
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
                "Pay-as-you-go: $0.10 USDC per scan (x402 on Base). "
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
            name="scan_wallet",
            description=(
                "Check an EVM wallet address for on-chain risk signals. "
                "Detects blacklisted addresses, contract risk flags, malicious activity, "
                "phishing associations, and other on-chain threat indicators. "
                "Returns risk_level (LOW/MEDIUM/HIGH), risk_flags list, and raw on-chain data. "
                "Supports Ethereum mainnet (default) and other EVM chains via chain_id. "
                "Use before sending funds to an unknown address or in DeFi due-diligence flows. "
                "Pay-as-you-go: $0.10 USDC per scan (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "required": ["address"],
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "EVM wallet address to scan (0x + 40 hex chars)",
                        "pattern": "^0x[0-9a-fA-F]{40}$",
                    },
                    "chain_id": {
                        "type": "string",
                        "description": "EVM chain ID (default: 1 for Ethereum mainnet). Use 8453 for Base, 137 for Polygon.",
                        "default": "1",
                    },
                },
            },
        ),
        types.Tool(
            name="check_mcp_registry_risk",
            description=(
                "Check an MCP server URL or package name for red flags: known-malicious IOC match, "
                "typosquat/near-miss against well-known MCP ecosystem domains, and domain registration "
                "age. Part of RelayShield's Agentic Attack Surface bundle — early coverage for an "
                "ecosystem with minimal dedicated security tooling as of 2026. "
                "Use before an agent connects to or installs a new, unfamiliar MCP server. "
                "Absence of findings means 'unknown,' not 'verified safe.' "
                "Pay-as-you-go: $0.35 USDC per check (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "format": "uri",
                        "description": "MCP server URL to check (e.g. https://example-mcp-server.com)",
                    },
                    "package_name": {
                        "type": "string",
                        "description": "Package name to check if no server_url is available (limited coverage — no dedicated MCP package registry yet)",
                    },
                },
            },
        ),
        types.Tool(
            name="check_prompt_injection_breach",
            description=(
                "Check whether an email address has exposure in a criminal dump whose own "
                "announcement text suggests an AI agent — rather than a traditional phishing or "
                "malware campaign — was involved in obtaining it. Heuristic v1 classifier over "
                "Telegram dump-announcement text, not a confirmed-attribution guarantee. "
                "Use as an early signal that an AI agent workflow may have been the breach vector. "
                "Pay-as-you-go: $0.35 USDC per check (x402 on Base). "
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
            name="check_supply_chain",
            description=(
                "Check up to 10 vendor domains (or vendor emails, domain extracted automatically) "
                "for breach and infostealer exposure. Returns a per-vendor risk level plus an "
                "aggregate dark-web exposure score. Use to vet a third-party vendor, MCP server "
                "operator, or supply-chain dependency before an agent integrates with or grants "
                "access to it. "
                "Pay-as-you-go: $0.10 USDC per check (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "vendor_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Up to 10 vendor domains to check, e.g. ['vendor.example.com']. Provide this or vendor_emails.",
                    },
                    "vendor_emails": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Alternative: vendor email addresses — the domain portion is extracted automatically.",
                    },
                },
            },
        ),
        types.Tool(
            name="check_session_risk",
            description=(
                "Check an email address for active or reusable stolen session material (cookies, "
                "tokens) found in criminal stealer logs — exposure that can bypass MFA entirely, not "
                "just a password. Use to assess whether an identity currently has hijackable sessions "
                "in circulation. "
                "Pay-as-you-go: $0.30 USDC per check (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "required": ["email"],
                "properties": {
                    "email": {
                        "type": "string",
                        "format": "email",
                        "description": "Email address to check for active session/AiTM exposure",
                    }
                },
            },
        ),
        types.Tool(
            name="check_nhi_exposure",
            description=(
                "Check a domain, or up to 10 vendor domains, for exposed non-human-identity (NHI) "
                "credentials — API keys, service-account tokens, personal access tokens, and other "
                "machine identities found in criminal stealer logs. Use to assess exposure of the "
                "machine credentials an agent or its supply chain actually runs on, not just human "
                "logins. "
                "Pay-as-you-go: $0.40 USDC per check (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Your own domain to check. Provide this or vendor_domains (or both).",
                    },
                    "vendor_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Up to 10 vendor/supply-chain domains to check.",
                    },
                },
            },
        ),
        types.Tool(
            name="check_secret_scan",
            description=(
                "Check a domain, or up to 5 vendor domains, for secrets and credentials exposed in "
                "public GitHub repositories. Use to assess whether an agent's own domain, or "
                "a vendor/supply-chain dependency's domain, has leaked credentials sitting in indexed "
                "public source code. "
                "Pay-as-you-go: $0.35 USDC per check (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Your own domain to check. Provide this or vendor_domains (or both).",
                    },
                    "vendor_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Up to 5 vendor domains to check.",
                    },
                },
            },
        ),
        types.Tool(
            name="check_llm_credential_exposure",
            description=(
                "Check a domain, or up to 10 vendor domains, for exposed LLM/AI provider API keys "
                "in criminal stealer log archives (LLMjacking) — closed-source platforms including "
                "OpenAI, Anthropic Claude, Google Gemini, xAI Grok and Amazon Bedrock, alongside "
                "DeepSeek, Moonshot Kimi, Alibaba Qwen, NVIDIA NIM and Hugging Face. A leaked LLM "
                "provider key is a live, uncapped billing liability — real incidents have run from "
                "tens of thousands of dollars per day to a $500K single-month bill from one "
                "unthrottled key. Use to check your own domain or a vendor/supply-chain dependency. "
                "Pay-as-you-go: $0.40 USDC per check (x402 on Base). "
                "Subscription: rapidapi.com/relayshield"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Your own domain to check. Provide this or vendor_domains (or both).",
                    },
                    "vendor_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Up to 10 vendor/supply-chain domains to check.",
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

    # Per-call credential override (added for multi-tenant HTTP deployments,
    # e.g. the Apify Actor in .actor/ -- one running server, many different
    # calling agents, each paying for their own usage). RELAYSHIELD_API_KEY
    # and RELAYSHIELD_X_PAYMENT are this process's environment-wide default,
    # fine for a single local user, wrong for a shared server: every caller
    # would either bill to one operator's key or share one x402 payment
    # proof, and payment proofs are single-use per request in the first
    # place. Injected onto every tool here rather than duplicated 15 times
    # above, so a new tool gets the same override for free.
    for tool in tools:
        tool.inputSchema.setdefault("properties", {})
        tool.inputSchema["properties"]["rs_api_key"] = {
            "type": "string",
            "description": (
                "Optional. Your own RelayShield subscription API key for this call, "
                "overriding the server's default credential. Use when multiple "
                "callers share one running server (e.g. an Apify Actor) and each "
                "must pay for its own usage rather than share one operator's key."
            ),
        }
        tool.inputSchema["properties"]["x_payment"] = {
            "type": "string",
            "description": (
                "Optional. x402 payment proof for this specific call, overriding "
                "the server's default. Ignored if rs_api_key is also given for "
                "this call (a key is cheaper per-check than paying per-call). "
                "Same use case: per-caller billing on a shared server."
            ),
        }
    return tools


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent] | types.CallToolResult:
    if not API_BASE:
        return _error(
            "RELAYSHIELD_API_URL environment variable must be set. "
            "See README for configuration instructions."
        )

    # Per-call credential wins over this process's env-var default -- see the
    # rs_api_key/x_payment injection in list_tools(). Popped out of arguments
    # so they never leak into the RelayShield API request body itself.
    call_api_key = arguments.pop("rs_api_key", None) or API_KEY
    call_x_payment = arguments.pop("x_payment", None) or X_PAYMENT

    # Build request headers — subscription key takes priority over x402 payment proof
    headers = {"Content-Type": "application/json"}
    if call_api_key:
        headers["x-api-key"] = call_api_key
    elif call_x_payment:
        headers["X-PAYMENT"] = call_x_payment
    # If neither is set, the API Gateway will return 402 with payment requirements

    payg = not call_api_key  # PAYG callers route to /v1/payg/ — API Gateway enforces key on /v1/
    try:
        async with httpx.AsyncClient(timeout=28.0) as client:
            r = await _dispatch(client, name, arguments, headers, payg)
    except httpx.TimeoutException:
        return _error("Request timed out — upstream API did not respond within 28 seconds.")
    except httpx.RequestError as exc:
        return _error(f"Network error: {exc}")

    if r.status_code == 402:
        return _payment_required(name, r)

    # Non-2xx upstream responses (401/429/500/etc.) previously fell through here
    # as a bare list[TextContent], which the SDK wraps as isError=False — a client
    # checking only isError would read "upstream failed" as a clean result. Surface
    # these as an explicit CallToolResult with isError=True instead, same as the
    # SDK's own automatic handling of validation errors and unknown tool names.
    if not (200 <= r.status_code < 300):
        return types.CallToolResult(
            content=[types.TextContent(
                type="text",
                text=json.dumps({"ok": False, "status_code": r.status_code, "body": r.text[:2000]}),
            )],
            isError=True,
        )

    # Defensive check even at a 2xx status: RelayShield's own API never sends
    # ok:false with a 2xx code today (_err() always uses a non-2xx status), but a
    # network intermediary or a future regression could still produce a malformed
    # or ok:false body here — treat that as a failed check, not a clean result.
    try:
        parsed_body = json.loads(r.text)
    except (json.JSONDecodeError, TypeError):
        return types.CallToolResult(
            content=[types.TextContent(
                type="text",
                text=json.dumps({"ok": False, "status_code": r.status_code, "raw_body": r.text[:2000]}),
            )],
            isError=True,
        )
    if isinstance(parsed_body, dict) and parsed_body.get("ok") is False:
        return types.CallToolResult(content=[types.TextContent(type="text", text=r.text)], isError=True)

    # Append conversion advisory on successful PAYG calls
    if not API_KEY:
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

    if name == "check_infostealer":
        return await client.post(
            f"{base}/infostealer",
            headers=headers,
            json={"email": arguments["email"]},
        )

    if name == "scan_wallet":
        body = {"address": arguments["address"]}
        if "chain_id" in arguments:
            body["chain_id"] = arguments["chain_id"]
        return await client.post(
            f"{base}/scan-wallet",
            headers=headers,
            json=body,
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

    if name == "check_supply_chain":
        body: dict = {}
        if "vendor_domains" in arguments:
            body["vendor_domains"] = arguments["vendor_domains"]
        if "vendor_emails" in arguments:
            body["vendor_emails"] = arguments["vendor_emails"]
        return await client.post(
            f"{base}/supply-chain",
            headers=headers,
            json=body,
        )

    if name == "check_session_risk":
        return await client.post(
            f"{base}/session-risk",
            headers=headers,
            json={"email": arguments["email"]},
        )

    if name == "check_nhi_exposure":
        body = {}
        if "domain" in arguments:
            body["domain"] = arguments["domain"]
        if "vendor_domains" in arguments:
            body["vendor_domains"] = arguments["vendor_domains"]
        return await client.post(
            f"{base}/nhi-exposure",
            headers=headers,
            json=body,
        )

    if name == "check_secret_scan":
        body = {}
        if "domain" in arguments:
            body["domain"] = arguments["domain"]
        if "vendor_domains" in arguments:
            body["vendor_domains"] = arguments["vendor_domains"]
        return await client.post(
            f"{base}/secret-scan",
            headers=headers,
            json=body,
        )

    if name == "check_llm_credential_exposure":
        body = {}
        if "domain" in arguments:
            body["domain"] = arguments["domain"]
        if "vendor_domains" in arguments:
            body["vendor_domains"] = arguments["vendor_domains"]
        return await client.post(
            f"{base}/llm-credential-exposure",
            headers=headers,
            json=body,
        )

    # AGENTIC-3/4 (added 2026-07-07) — served from the isolated
    # relayshield-agentic-api Lambda, but reachable through the same
    # API_BASE gateway since its routes are registered there too.
    # PAYG-only for now: no flat-subscription (x-api-key) route exists yet
    # for these two endpoints, only Stripe-metered and x402 PAYG.
    if name == "check_mcp_registry_risk":
        body: dict = {}
        if "server_url" in arguments:
            body["server_url"] = arguments["server_url"]
        if "package_name" in arguments:
            body["package_name"] = arguments["package_name"]
        return await client.post(
            f"{API_BASE}/v1/payg/mcp-registry-risk",
            headers=headers,
            json=body,
        )

    if name == "check_prompt_injection_breach":
        return await client.post(
            f"{API_BASE}/v1/payg/prompt-injection-breach",
            headers=headers,
            json={"email": arguments["email"]},
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


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps({"ok": False, "error": message}))],
        isError=True,
    )


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


def main_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
