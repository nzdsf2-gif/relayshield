#!/usr/bin/env python3
"""
RelayShield Free Identity & Scam Checks — MCP Server

Exposes RelayShield's keyless, free threat-intelligence checks as callable
tools for Claude and other MCP-compatible AI agents. No API key, no signup,
no payment: every tool calls a free endpoint.

Live tools:
  check_link    — screen URL(s) for phishing/malware (POST /v1/link-check)
  check_wallet  — screen a crypto wallet before paying it (POST /v1/wallet-risk)
  check_email   — score a parsed phishing email (POST /v1/email-check, keyless)
  check_breach  — email vs 13B+ breached accounts (POST /v1/metered/breach,
                  needs RELAYSHIELD_API_KEY — a partner key)

Configuration (environment variables, all optional):
  RELAYSHIELD_API_URL — override the API base (default https://api.relayshield.net)
  RELAYSHIELD_API_KEY — partner key. Accepted by the free endpoints to lift the
                        per-IP daily allowance; required by check_breach.
                        Run keyless without it — link, wallet and email checks
                        still work on the free tier.
  RS_SOURCE_TAG       — channel label recorded by the API so per-channel usage
                        can be measured (default "mcp-free"). Distributors
                        (Claude, ChatGPT, registries) should set their own tag.
"""

import asyncio
import base64
import json
import os

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE = os.environ.get("RELAYSHIELD_API_URL", "https://api.relayshield.net").rstrip("/")
API_KEY = os.environ.get("RELAYSHIELD_API_KEY", "")
SOURCE_TAG = os.environ.get("RS_SOURCE_TAG", "mcp-free")  # recorded by the API so the channel can be measured

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

app = Server("relayshield-free")


def _error(text: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=text)]


def _summarise_link(data: dict) -> str:
    """One-line-per-link human summary of a /v1/link-check response."""
    lines = []
    if "results" in data:  # batch form
        counts = data.get("counts", {})
        lines.append(
            "Checked {c} link(s): {f} flagged, {i} incomplete.".format(
                c=counts.get("checked", "?"),
                f=counts.get("flagged", "?"),
                i=counts.get("incomplete", "?"),
            )
        )
        for r in data.get("results", []):
            flag = "FLAGGED" if r.get("flagged") else r.get("level", "unknown").upper()
            reasons = "; ".join(r.get("reasons", []))
            lines.append(f"- [{flag}] {r.get('target')}" + (f" — {reasons}" if reasons else ""))
        for u in data.get("incomplete_urls", []) or []:
            lines.append(f"- [NOT CHECKED — retry] {u}")
    else:  # single-link form
        flag = "FLAGGED" if data.get("flagged") else data.get("level", "unknown").upper()
        lines.append(f"[{flag}] {data.get('target')}")
        for reason in data.get("reasons", []):
            lines.append(f"- {reason}")
        sig = data.get("signals", {})
        lines.append(
            "Signals: IOC corpus={} | threat feeds={} | domain age={}d".format(
                sig.get("ioc_corpus"), sig.get("safe_browsing"), sig.get("domain_age_days")
            )
        )
    lines.append("Note: the best verdict this check returns is 'unknown' — absence of evidence is not evidence of absence.")
    return "\n".join(lines)


def _summarise_email(data: dict) -> str:
    """Human summary of a /v1/email-check response."""
    lines = [
        "Claimed sender: {}".format(data.get("claimed_sender") or "(not parsed)"),
        "Risk: {} | Score: {}".format(data.get("risk"), data.get("score")),
    ]
    for flag in data.get("flags") or []:
        lines.append(f"- {flag}")
    for note in data.get("notes") or []:
        lines.append(f"  note: {note}")
    auth = data.get("auth") or {}
    if auth.get("present"):
        lines.append(
            "Auth: SPF={} DKIM={} DMARC={}".format(auth.get("spf"), auth.get("dkim"), auth.get("dmarc"))
        )
    links = data.get("links") or []
    if links:
        lines.append(f"Links checked: {len(links)}")
    lines.append(
        "Note: heuristic verdict over the fields you supplied — it never answers 'safe', "
        "and a 'low' score on a vague forward is 'unknown', not 'legitimate'."
    )
    return "\n".join(lines)


def _summarise_breach(data: dict) -> str:
    """Defensive human summary of a /v1/metered/breach response."""
    breaches = data.get("breaches") or data.get("results") or []
    count = data.get("breach_count", data.get("count", len(breaches) if isinstance(breaches, list) else "?"))
    lines = [
        "Email: {}".format(data.get("email") or data.get("query") or "(unknown)"),
        "Breaches found: {}".format(count),
    ]
    if isinstance(breaches, list):
        for b in breaches[:25]:
            if isinstance(b, dict):
                name = b.get("name") or b.get("source") or b.get("title") or "?"
                date = b.get("date") or b.get("breach_date") or ""
                lines.append(f"- {name}" + (f" ({date})" if date else ""))
            else:
                lines.append(f"- {b}")
    if data.get("degraded"):
        lines.append("Warning: degraded result (incomplete upstream data) — treat as NO VERDICT, never as clean.")
    return "\n".join(lines)


def _summarise_wallet(data: dict) -> str:
    flags = data.get("risk_flags") or []
    lines = [
        "Address: {}".format(data.get("address")),
        "Chain: {} | Risk: {}".format(data.get("chain"), data.get("risk_level")),
    ]
    for f in flags:
        lines.append(f"- {f}")
    if not flags:
        lines.append("- No flags: nothing known against this address (verdict 'unknown', not 'safe').")
    return "\n".join(lines)


# Tool registry: adding a new free check is one entry here plus a summary
# function. `body` maps tool arguments to the API request body.
# `requires_key` short-circuits with setup instructions when no partner key is set.
TOOLS: dict[str, dict] = {
    "check_link": {
        "path": "/v1/link-check",
        "summary": _summarise_link,
        "description": (
            "Check one link — or up to 25 at once — for known phishing, malware and scam abuse. "
            "Free and keyless: no API key, no signup, no payment. Signals: RelayShield's criminal "
            "IOC corpus, threat feeds, and domain registration age. "
            "It never answers 'safe'; the best verdict is 'unknown' (nothing known against the domain). "
            "Use before clicking, forwarding, or quoting a link, and to screen links inside a suspicious message."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "A single link starting with http:// or https://. Omit when sending urls.",
                },
                "urls": {
                    "type": "array",
                    "maxItems": 25,
                    "items": {"type": "string"},
                    "description": "Up to 25 links to check in one call. Omit when sending url.",
                },
            },
        },
        "body": lambda a: {k: v for k, v in {"url": a.get("url"), "urls": a.get("urls")}.items() if v}
        | {"source": SOURCE_TAG},
    },
    "check_wallet": {
        "path": "/v1/wallet-risk",
        "summary": _summarise_wallet,
        "description": (
            "Screen a crypto wallet address BEFORE sending funds to it. Free and keyless: no API key, "
            "no signup, no payment. The chain (EVM, Solana, TON, Bitcoin) is detected from the address "
            "format automatically. Returns a risk level (CRITICAL/HIGH/MEDIUM/LOW/unknown) with the "
            "specific sanctions, scam, drainer and phishing flags behind it. "
            "'unknown' means nothing is known against the address, not that it is safe. "
            "Use whenever a user is about to pay an address they were given."
        ),
        "schema": {
            "type": "object",
            "required": ["address"],
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Wallet address to screen. Chain is auto-detected.",
                },
            },
        },
        "body": lambda a: {"address": a["address"], "source": SOURCE_TAG},
    },
    "check_email": {
        "path": "/v1/email-check",
        "summary": _summarise_email,
        "description": (
            "Score a suspicious email for phishing signals. Free and keyless: no API key, "
            "no signup, no payment. Pass the fields you already parsed (subject, body text, "
            "claimed sender, reply-to, links) — the endpoint returns a risk level, score, "
            "and the specific flags behind it, and checks any links against RelayShield's "
            "IOC corpus, threat feeds, and domain registration age. "
            "It never answers 'safe'; the best verdict is 'unknown'. "
            "Use on a suspicious message before acting on it."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "from_address": {
                    "type": "string",
                    "description": "The claimed sender's address, e.g. alerts@phrase.com.",
                },
                "from_name": {
                    "type": "string",
                    "description": "The claimed sender's display name.",
                },
                "reply_to": {
                    "type": "string",
                    "description": "Reply-To address, if present and different from from_address.",
                },
                "return_path": {
                    "type": "string",
                    "description": "Envelope sender, if available. Informational only.",
                },
                "subject": {"type": "string", "description": "Message subject."},
                "body_text": {
                    "type": "string",
                    "description": "Plain-text body, used for urgency/deadline/threat phrasing.",
                },
                "links": {
                    "type": "array",
                    "maxItems": 25,
                    "items": {"type": "string"},
                    "description": "Links found in the body, up to 25.",
                },
            },
        },
        "body": lambda a: {
            k: v
            for k, v in {
                "from_address": a.get("from_address"),
                "from_name": a.get("from_name"),
                "reply_to": a.get("reply_to"),
                "return_path": a.get("return_path"),
                "subject": a.get("subject"),
                "body_text": a.get("body_text"),
                "links": a.get("links"),
            }.items()
            if v
        }
        | {"source": SOURCE_TAG},
    },
    "check_breach": {
        "path": "/v1/metered/breach",
        "requires_key": True,
        "summary": _summarise_breach,
        "description": (
            "Check whether an email address appears in known data breaches — 13B+ records. "
            "Needs a RelayShield partner API key (set RELAYSHIELD_API_KEY); without one the "
            "tool explains how to get set up instead of failing. Returns the breach count "
            "with the named sources behind it. Use when vetting an identity, a new account, "
            "or credentials that may have been exposed."
        ),
        "schema": {
            "type": "object",
            "required": ["email"],
            "properties": {
                "email": {
                    "type": "string",
                    "format": "email",
                    "description": "Email address to check. Case-insensitive.",
                },
            },
        },
        "body": lambda a: {"email": a["email"], "source": SOURCE_TAG},
    },
}


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=name, description=spec["description"], inputSchema=spec["schema"])
        for name, spec in TOOLS.items()
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent] | types.CallToolResult:
    spec = TOOLS.get(name)
    if spec is None:
        return _error(f"Unknown tool: {name}")

    if spec.get("requires_key") and not API_KEY:
        return _error(
            "check_breach needs a RelayShield partner API key. Set the RELAYSHIELD_API_KEY "
            "environment variable (get a key at https://api.relayshield.net/developers). "
            "The link, wallet, and email checks work keyless without one."
        )

    body = spec["body"](arguments or {})
    if name == "check_link" and not body.get("url") and not body.get("urls"):
        return _error("Send either `url` (one link) or `urls` (up to 25), not neither.")

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        # Accepted by the free endpoints; lifts the per-IP daily allowance.
        headers["X-RS-API-KEY"] = API_KEY

    try:
        async with httpx.AsyncClient(timeout=28.0) as client:
            r = await client.post(API_BASE + spec["path"], json=body, headers=headers)
    except httpx.TimeoutException:
        return _error("Request timed out — upstream API did not respond within 28 seconds.")
    except httpx.RequestError as exc:
        return _error(f"Network error: {exc}")

    if not (200 <= r.status_code < 300):
        return types.CallToolResult(
            content=[types.TextContent(
                type="text",
                text=json.dumps({"ok": False, "status_code": r.status_code, "body": r.text[:2000]}),
            )],
            isError=True,
        )

    try:
        payload = r.json()
    except ValueError:
        return _error(f"Upstream returned non-JSON: {r.text[:500]}")

    if not payload.get("ok"):
        return _error(f"Upstream error: {payload.get('error', 'unknown')}")

    text = spec["summary"](payload.get("data", {}))
    text += "\n\nRaw response:\n" + json.dumps(payload, indent=2)[:4000]
    return [types.TextContent(type="text", text=text)]


async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main_sync() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main_sync()
