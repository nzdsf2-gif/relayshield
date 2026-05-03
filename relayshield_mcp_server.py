#!/usr/bin/env python3
"""
RelayShield MCP Server

Exposes RelayShield security intelligence as callable tools for Claude
and other MCP-compatible AI agents.

Configuration (environment variables):
  RELAYSHIELD_API_URL  — API Gateway invoke URL, e.g.
                         https://xhh3tfrhng.execute-api.us-east-1.amazonaws.com/prod
  RELAYSHIELD_API_KEY  — x-api-key value from API Gateway

Usage:
  python relayshield_mcp_server.py          # stdio transport (Claude Desktop / Claude Code)
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

API_BASE = os.environ.get("RELAYSHIELD_API_URL", "").rstrip("/")
API_KEY  = os.environ.get("RELAYSHIELD_API_KEY", "")

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
                "Use before allowing high-risk actions that depend on credential integrity."
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
            name="scan_url",
            description=(
                "Submit a URL for malware and phishing analysis across 70+ security engines. "
                "Returns an analysis_id immediately (async). "
                "Call check_scan_result with the analysis_id every 5 seconds until verdict is returned. "
                "Verdicts: malicious | suspicious | clean | timeout. "
                "Use before navigating to an unfamiliar URL or when a user forwards a suspicious link."
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
                "Use when a user receives an email attachment and forwards the download link."
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
                "or {status: pending} if the scan is still running."
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
        types.Tool(
            name="check_sim_swap",
            description=(
                "Detect whether a SIM swap or eSIM provisioning event has occurred on a phone number "
                "in the last 24 hours. Uses Twilio Lookup v2 with live carrier data. "
                "Returns swapped (bool), swap timestamp, and current carrier. "
                "Use when a user reports losing mobile service, or before completing a high-risk "
                "action that depends on SMS-based authentication."
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
                "link that resembles a company domain."
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
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if not API_BASE or not API_KEY:
        return _error(
            "RELAYSHIELD_API_URL and RELAYSHIELD_API_KEY environment variables must be set. "
            "See MCP_SETUP.md for configuration instructions."
        )

    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=28.0) as client:
            if name == "check_breach":
                r = await client.post(
                    f"{API_BASE}/v1/breach",
                    headers=headers,
                    json={"email": arguments["email"]},
                )

            elif name == "scan_url":
                r = await client.post(
                    f"{API_BASE}/v1/scan-url",
                    headers=headers,
                    json={"url": arguments["url"]},
                )

            elif name == "scan_file":
                body: dict = {"file_url": arguments["file_url"]}
                if "filename" in arguments:
                    body["filename"] = arguments["filename"]
                r = await client.post(
                    f"{API_BASE}/v1/scan-file",
                    headers=headers,
                    json=body,
                )

            elif name == "check_scan_result":
                analysis_id = arguments["analysis_id"]
                r = await client.get(
                    f"{API_BASE}/v1/result/{analysis_id}",
                    headers=headers,
                )

            elif name == "check_sim_swap":
                r = await client.post(
                    f"{API_BASE}/v1/sim-swap",
                    headers=headers,
                    json={"phone": arguments["phone"]},
                )

            elif name == "check_domain_lookalikes":
                r = await client.post(
                    f"{API_BASE}/v1/domain",
                    headers=headers,
                    json={"domain": arguments["domain"]},
                )

            else:
                return _error(f"Unknown tool: {name}")

    except httpx.TimeoutException:
        return _error("Request timed out — the upstream API did not respond within 28 seconds.")
    except httpx.RequestError as exc:
        return _error(f"Network error: {exc}")

    return [types.TextContent(type="text", text=r.text)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
