"""RelayShield Agentic Attack Surface MCP Server — Hugging Face Space.

Exposes 13 of RelayShield's agent-security checks as MCP tools via Gradio's
mcp_server=True mode:
  - check_mcp_server_risk: typosquat/reputation/registration-age risk for
    an MCP server URL.
  - check_prompt_injection_breach: credential breach exposure sourced
    specifically from prompt-injection attacks against AI agents.
  - check_tech_stack_cve: CISA KEV / high-EPSS CVEs targeting a declared
    AI agent framework / tech stack, now with a bounded public-PoC/exploit-
    availability signal on top-ranked non-KEV matches.
  - check_bulk_identity_risk: hierarchical org + AI-agent-identity risk
    scoring for a domain and its agent/service-account identities.
  - check_oauth_watchlist: OAuth-app breach + stolen-token exposure.
  - check_supply_chain: up to 10 vendor domains checked for breach/
    infostealer exposure.
  - check_session_risk: active/reusable stolen session (cookie/token)
    exposure.
  - check_nhi_exposure: non-human-identity credential exposure (API keys,
    service tokens, PATs).
  - check_secret_scan: secrets exposed in public GitHub repos.
  - check_llm_credential_exposure: exposed LLM/AI provider API keys
    (LLMjacking) — free to try, no api_key required (shared demo quota).
  - check_agent_risk_summary: composite check — breach + LLM credential
    exposure + tech-stack CVE in one call instead of four.
  - get_stix_indicators: RelayShield's IOC corpus as STIX 2.1 objects via
    the TAXII 2.1 feed (requires a TI subscription key).
  - check_server_status: introspection — which tools/sources are live, no
    api_key required.

v3 (2026-07-26) — LLMjacking + MCP enhancement sprint: added the last 4
tools above (check_llm_credential_exposure, check_agent_risk_summary,
get_stix_indicators, check_server_status), a zero-key free tier on
check_llm_credential_exposure specifically, and a bounded PoC/exploit-
availability signal on check_tech_stack_cve's top non-KEV matches.

v2 (2026-07-19) — response to community feedback: added 5 tools, and every
tool now returns a typed structured result instead of a human-formatted
string:

    {
      "outcome": "finding" | "no_known_finding" | "error",
      "recommended_action": "allow" | "review" | "deny" | "defer",
      "reason_codes": [...],
      "evidence": [...],
      "coverage": {"complete": bool, "scope": "what was actually checked"},
      "freshness": {"observed_at": "...", "expires_at": null},
      "error": {"kind": "...", "message": "...", "retryable": bool} | null
    }

"no_known_finding" deliberately does not mean "safe" — it means nothing was
found in the sources and scope actually queried.

Each caller supplies their own RelayShield API key as a tool argument —
this Space is a single shared server handling many remote MCP callers at
once, so there is no per-caller "environment" to read a key from. Get a
key at https://api.relayshield.net/developers.
"""

import json
import os
import re

import gradio as gr
import requests

# ---------------------------------------------------------------------------
# AWS Marketplace mode — added 2026-07-27. This same file is deployed as two
# separate HF Spaces: the original public Space (this env var unset) keeps
# directing callers to the public self-serve signup page exactly as before;
# a second Space (AWS_MARKETPLACE_MODE=true, registered as Bundle D's MCP
# endpoint URL on AWS Marketplace) scrubs every reference to that page. AWS's
# Tier-1 audit treats any reachable link to an external payment-collecting
# page as a violation, even one buried in a tool parameter description
# rather than the AWS listing text itself — this is what caused Bundle D's
# visibility request to fail a second time after the listing text itself was
# already fixed. Keep both Spaces' code identical except for this one env
# var; redeploy both whenever this file changes.
# ---------------------------------------------------------------------------
AWS_MARKETPLACE_MODE = os.environ.get("AWS_MARKETPLACE_MODE", "").lower() == "true"

_KEY_URL_RE = re.compile(
    r"(?:Get (?:a(?:\s+key)?|one|your own(?:\s+key)?)|get your own key)\s+at\s+"
    r"(?:https?://)?api\.relayshield\.net/developers(?:#[\w-]+)?\.?",
)
_AWS_KEY_TEXT = "Included with your AWS Marketplace subscription, issued automatically by email"


def _scrub(text: str) -> str:
    """No-op unless AWS_MARKETPLACE_MODE is set — see comment above."""
    if not AWS_MARKETPLACE_MODE or not text:
        return text
    return _KEY_URL_RE.sub(_AWS_KEY_TEXT, text)


__doc__ = _scrub(__doc__)

API_BASE_URL = "https://api.relayshield.net"


def _headers(api_key: str) -> dict[str, str]:
    # All endpoints (hosted across relayshield_agentic_api.py and the main
    # relayshield_api.py) accept X-RS-API-KEY as the primary header —
    # confirmed by reading both dispatchers directly, not assumed.
    # X-RS-Source lets the backend attribute billed usage to this Space
    # specifically in the weekly metrics report (both dispatchers log a
    # tagged row to relayshield_payg_settlements when this header is present).
    return {
        "Content-Type": "application/json",
        "X-RS-API-KEY": api_key,
        "X-RS-Source": "hf-mcp-space",
    }


def _outcome_for_severity(highest_severity: str | None, found: bool = True) -> tuple[str, str]:
    """Maps a RelayShield severity string to (outcome, recommended_action).

    CRITICAL escalates to a deny recommendation; HIGH/MEDIUM/LOW are surfaced as
    findings for human/agent review rather than an automatic block, since these
    are enrichment signals, not a certified detection.
    """
    if not found or highest_severity in (None, "NONE", "CLEAN"):
        return "no_known_finding", "allow"
    if highest_severity == "CRITICAL":
        return "finding", "deny"
    return "finding", "review"


def _structured_result(
    outcome: str,
    recommended_action: str,
    *,
    reason_codes: list[str] | None = None,
    evidence: list | None = None,
    scope: str,
    coverage_complete: bool = True,
    observed_at: str | None = None,
) -> str:
    return json.dumps({
        "outcome": outcome,
        "recommended_action": recommended_action,
        "reason_codes": reason_codes or [],
        "evidence": evidence or [],
        "coverage": {"complete": coverage_complete, "scope": scope},
        "freshness": {"observed_at": observed_at, "expires_at": None},
        "error": None,
    }, indent=2)


def _error_result(kind: str, message: str, retryable: bool = False) -> str:
    return json.dumps({
        "outcome": "error",
        "recommended_action": "defer",
        "reason_codes": [],
        "evidence": [],
        "coverage": {"complete": False, "scope": ""},
        "freshness": {"observed_at": None, "expires_at": None},
        "error": {"kind": kind, "message": message, "retryable": retryable},
    }, indent=2)


def _call(path: str, payload: dict, api_key: str) -> tuple[dict | None, str | None]:
    """POSTs to a RelayShield metered endpoint. Returns (data, error_json_string).
    error_json_string is None on success, or a ready-to-return _error_result() on
    failure."""
    try:
        resp = requests.post(
            f"{API_BASE_URL}{path}",
            json=payload,
            headers=_headers(api_key),
            timeout=15,
        )
    except requests.Timeout:
        return None, _error_result("timeout", f"RelayShield API call to {path} timed out after 15s.", retryable=True)
    except requests.RequestException as exc:
        return None, _error_result("upstream", f"RelayShield API call to {path} failed: {exc}", retryable=True)

    if resp.status_code in (401, 403):
        return None, _error_result("auth", f"RelayShield API call to {path} returned {resp.status_code} — check api_key.", retryable=False)
    if resp.status_code == 429:
        return None, _error_result("rate_limited", f"RelayShield API call to {path} was rate-limited.", retryable=True)
    if resp.status_code >= 500:
        return None, _error_result("upstream", f"RelayShield API call to {path} returned {resp.status_code}.", retryable=True)
    if resp.status_code >= 400:
        return None, _error_result("other", f"RelayShield API call to {path} returned {resp.status_code}: {resp.text[:200]}", retryable=False)

    try:
        response_json = resp.json()
    except ValueError:
        return None, _error_result("malformed_response", f"RelayShield API call to {path} returned non-JSON content.", retryable=False)

    if not isinstance(response_json, dict):
        return None, _error_result("malformed_response", f"RelayShield API call to {path} returned an unexpected response shape.", retryable=False)

    return response_json.get("data", {}), None


def check_mcp_server_risk(server_url: str, api_key: str) -> str:
    """Check an MCP server URL for typosquat risk, presence in RelayShield's
    criminal IOC corpus, and domain-registration age.

    Args:
        server_url: Full URL of the MCP server to check, e.g. https://example.com/mcp
        api_key: Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-mcp-registry-risk

    Returns:
        A structured result: outcome/recommended_action plus evidence and reason codes.
    """
    if not server_url:
        return _error_result("other", "server_url is required.")
    if not api_key:
        return _error_result("auth", _scrub("api_key is required. Get one at https://api.relayshield.net/developers#ep-mcp-registry-risk"))

    data, error = _call("/v1/metered/mcp-registry-risk", {"server_url": server_url}, api_key)
    if error:
        return error

    findings = data.get("findings", [])
    outcome, action = _outcome_for_severity(data.get("verdict"), found=bool(findings))
    return _structured_result(
        outcome, action,
        reason_codes=[f.get("type", "unknown") for f in findings],
        evidence=findings,
        scope=f"Checked {data.get('queried', server_url)!r} against known-MCP-domain typosquat distance, "
              "RelayShield's criminal IOC corpus, and RDAP registration age.",
    )


def check_prompt_injection_breach(email: str, api_key: str) -> str:
    """Check an email address for credential exposure sourced specifically
    from prompt-injection attacks against AI agents, distinct from ordinary
    phishing/malware-sourced breaches.

    Args:
        email: Email address to check, e.g. agent@example.com
        api_key: Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-prompt-injection-breach

    Returns:
        A structured result: outcome/recommended_action plus evidence and reason codes.
    """
    if not email or "@" not in email:
        return _error_result("other", "a valid email address is required.")
    if not api_key:
        return _error_result("auth", _scrub("api_key is required. Get one at https://api.relayshield.net/developers#ep-prompt-injection-breach"))

    data, error = _call("/v1/metered/prompt-injection-breach", {"email": email}, api_key)
    if error:
        return error

    sessions = data.get("sessions", [])
    severities = [s.get("severity") for s in sessions if s.get("severity")]
    highest = max(severities, key=lambda s: {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(s, 0), default=None)
    outcome, action = _outcome_for_severity(highest, found=data.get("found", False))
    return _structured_result(
        outcome, action,
        reason_codes=["prompt_injection_sourced_breach"] if data.get("found") else [],
        evidence=sessions,
        scope=f"Checked {email} against stolen-session records flagged as prompt-injection-sourced "
              "(heuristic keyword classifier over dump-announcement text, not confirmed attribution).",
    )


def check_tech_stack_cve(tech_stack: str, api_key: str) -> str:
    """Check a declared AI agent framework / tech stack for CISA KEV or
    high-EPSS CVEs actively being exploited. Covers AI agent orchestration
    frameworks (LangChain, CrewAI, AutoGPT, Flowise, n8n self-hosted) and
    common companion infrastructure (Nacos, MinIO).

    Args:
        tech_stack: Comma-separated list of products, e.g. "langchain, nacos, minio"
        api_key: Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-tech-stack-cve

    Returns:
        A structured result: outcome/recommended_action plus evidence and reason codes.
    """
    stack_list = [t.strip() for t in tech_stack.split(",") if t.strip()]
    if not stack_list:
        return _error_result("other", "tech_stack is required (comma-separated list of products).")
    if not api_key:
        return _error_result("auth", _scrub("api_key is required. Get one at https://api.relayshield.net/developers#ep-tech-stack-cve"))

    data, error = _call("/v1/metered/tech-stack-cve", {"tech_stack": stack_list}, api_key)
    if error:
        return error

    matched = data.get("all_matches", [])
    critical = data.get("critical_cves", [])
    highest = "CRITICAL" if critical else ("HIGH" if matched else None)
    outcome, action = _outcome_for_severity(highest, found=bool(matched))
    return _structured_result(
        outcome, action,
        reason_codes=[c.get("cve_id", "unknown") for c in critical] if critical else [],
        evidence=matched,
        scope=f"Checked {data.get('tech_stack_queried', stack_list)} against CISA KEV and high-EPSS-score CVEs.",
    )


def check_bulk_identity_risk(domain: str, agent_emails: str, api_key: str) -> str:
    """Hierarchical org + AI-agent-identity risk scoring for a domain and up
    to 5 agent/service-account identities. A critically-exposed agent
    automatically elevates the organizational risk rating.

    Args:
        domain: Organization domain to score, e.g. example.com
        agent_emails: Comma-separated agent/service-account emails, up to 5, e.g. "ai-agent@example.com, svc@example.com"
        api_key: Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-bulk-identity-risk

    Returns:
        A structured result: outcome/recommended_action plus evidence and reason codes.
    """
    if not domain:
        return _error_result("other", "domain is required.")
    if not api_key:
        return _error_result("auth", _scrub("api_key is required. Get one at https://api.relayshield.net/developers#ep-bulk-identity-risk"))

    agents = [e.strip() for e in agent_emails.split(",") if e.strip()][:5]

    data, error = _call("/v1/metered/bulk-identity-risk", {"targets": [{"domain": domain, "agents": agents}]}, api_key)
    if error:
        return error

    results = data.get("results", [])
    critical = data.get("critical_count", 0)
    high = data.get("high_count", 0)
    highest = "CRITICAL" if critical else ("HIGH" if high else None)
    outcome, action = _outcome_for_severity(highest, found=bool(critical or high))
    return _structured_result(
        outcome, action,
        reason_codes=[r.get("domain", "unknown") for r in results
                      if r.get("domain_risk") in ("CRITICAL", "HIGH") or r.get("highest_agent_risk") in ("CRITICAL", "HIGH")],
        evidence=results,
        scope=f"Scored {data.get('queried', len(results))} domain(s) for combined breach/infostealer/session/CVE risk.",
    )


def check_oauth_watchlist(email: str, api_key: str) -> str:
    """Check an email for OAuth-connected-app exposure: apps matched against
    breach history, plus stolen OAuth/session tokens found in criminal
    stealer logs.

    Args:
        email: Email address to check for OAuth app exposure, e.g. agent@example.com
        api_key: Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-oauth-watchlist

    Returns:
        A structured result: outcome/recommended_action plus evidence and reason codes.
    """
    if not email or "@" not in email:
        return _error_result("other", "a valid email address is required.")
    if not api_key:
        return _error_result("auth", _scrub("api_key is required. Get one at https://api.relayshield.net/developers#ep-oauth-watchlist"))

    data, error = _call("/v1/metered/oauth-watchlist", {"email": email}, api_key)
    if error:
        return error

    matched_apps = data.get("matched_apps", [])
    stolen_tokens = data.get("stolen_tokens", [])
    outcome, action = _outcome_for_severity(data.get("highest_severity"), found=bool(matched_apps or stolen_tokens))
    return _structured_result(
        outcome, action,
        reason_codes=(["oauth_app_breach_match"] if matched_apps else []) + (["stolen_oauth_token"] if stolen_tokens else []),
        evidence=matched_apps + stolen_tokens,
        scope=f"Checked {email} against HIBP breach history for OAuth-app matches and RelayShield's "
              "stealer-log corpus for stolen session/OAuth tokens.",
        observed_at=data.get("checked_at"),
    )


def check_supply_chain(vendor_domains: str, api_key: str) -> str:
    """Check up to 10 vendor domains for breach and infostealer exposure —
    third-party and supply-chain risk inherited through vendor relationships.

    Args:
        vendor_domains: Comma-separated vendor domains, up to 10, e.g. "vendor1.com, vendor2.com"
        api_key: Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-supply-chain

    Returns:
        A structured result: outcome/recommended_action plus evidence and reason codes.
    """
    domains = [d.strip() for d in vendor_domains.split(",") if d.strip()][:10]
    if not domains:
        return _error_result("other", "vendor_domains is required (comma-separated list, up to 10).")
    if not api_key:
        return _error_result("auth", _scrub("api_key is required. Get one at https://api.relayshield.net/developers#ep-supply-chain"))

    data, error = _call("/v1/metered/supply-chain", {"vendor_domains": domains}, api_key)
    if error:
        return error

    results = data.get("results", [])
    highest = data.get("highest_risk")
    outcome, action = _outcome_for_severity(highest if highest != "CLEAN" else None, found=highest not in (None, "CLEAN"))
    return _structured_result(
        outcome, action,
        reason_codes=data.get("critical_vendors", []) + data.get("high_risk_vendors", []),
        evidence=results,
        scope=f"Checked {data.get('domains_checked', 0)} vendor domain(s) for breach and infostealer exposure.",
        observed_at=data.get("checked_at"),
    )


def check_session_risk(email: str, api_key: str) -> str:
    """Check an email for active or reusable stolen session material
    (cookies, tokens) found in criminal stealer logs — exposure that can
    bypass MFA/authentication entirely, not just a password.

    Args:
        email: Email address to check for active session/AiTM exposure, e.g. agent@example.com
        api_key: Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-session-risk

    Returns:
        A structured result: outcome/recommended_action plus evidence and reason codes.
    """
    if not email or "@" not in email:
        return _error_result("other", "a valid email address is required.")
    if not api_key:
        return _error_result("auth", _scrub("api_key is required. Get one at https://api.relayshield.net/developers#ep-session-risk"))

    data, error = _call("/v1/metered/session-risk", {"email": email}, api_key)
    if error:
        return error

    sessions = data.get("sessions", [])
    outcome, action = _outcome_for_severity(data.get("highest_severity"), found=data.get("found", False))
    return _structured_result(
        outcome, action,
        reason_codes=[s.get("service_category", "unknown") for s in sessions],
        evidence=sessions,
        scope=f"Checked {email} against RelayShield's stolen-session corpus for reusable session/cookie material.",
    )


def check_nhi_exposure(domain: str, vendor_domains: str, api_key: str) -> str:
    """Check a domain, or up to 10 vendor domains, for exposed non-human-
    identity (NHI) credentials — API keys, service-account tokens, personal
    access tokens, and other machine identities found in criminal stealer logs.

    Args:
        domain: Your own domain to check. Leave blank if only using vendor_domains.
        vendor_domains: Comma-separated vendor/supply-chain domains, up to 10. Leave blank if only using domain.
        api_key: Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-nhi-exposure

    Returns:
        A structured result: outcome/recommended_action plus evidence and reason codes.
    """
    domain = (domain or "").strip()
    domains = [d.strip() for d in (vendor_domains or "").split(",") if d.strip()][:10]
    if not domain and not domains:
        return _error_result("other", "domain or vendor_domains is required.")
    if not api_key:
        return _error_result("auth", _scrub("api_key is required. Get one at https://api.relayshield.net/developers#ep-nhi-exposure"))

    payload: dict = {}
    if domain:
        payload["domain"] = domain
    if domains:
        payload["vendor_domains"] = domains

    data, error = _call("/v1/metered/nhi-exposure", payload, api_key)
    if error:
        return error

    findings = data.get("findings", [])
    outcome, action = _outcome_for_severity(data.get("highest_severity"), found=data.get("found", False))
    return _structured_result(
        outcome, action,
        reason_codes=[f.get("type", "unknown") for f in findings],
        evidence=findings,
        scope=f"Checked {data.get('domains_checked', 0)} domain(s) against RelayShield's stealer-log corpus "
              "for exposed non-human-identity credentials.",
        observed_at=data.get("checked_at"),
    )


def check_secret_scan(domain: str, vendor_domains: str, api_key: str) -> str:
    """Check a domain, or up to 5 vendor domains, for secrets and
    credentials exposed in public GitHub repositories.

    Args:
        domain: Your own domain to check. Leave blank if only using vendor_domains.
        vendor_domains: Comma-separated vendor domains, up to 5. Leave blank if only using domain.
        api_key: Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-secret-scan

    Returns:
        A structured result: outcome/recommended_action plus evidence and reason codes.
    """
    domain = (domain or "").strip()
    domains = [d.strip() for d in (vendor_domains or "").split(",") if d.strip()][:5]
    if not domain and not domains:
        return _error_result("other", "domain or vendor_domains is required.")
    if not api_key:
        return _error_result("auth", _scrub("api_key is required. Get one at https://api.relayshield.net/developers#ep-secret-scan"))

    payload: dict = {}
    if domain:
        payload["domain"] = domain
    if domains:
        payload["vendor_domains"] = domains

    data, error = _call("/v1/metered/secret-scan", payload, api_key)
    if error:
        return error

    findings = data.get("findings", [])
    outcome, action = _outcome_for_severity(data.get("highest_severity"), found=data.get("found", False))
    return _structured_result(
        outcome, action,
        reason_codes=[f.get("severity", "unknown") for f in findings],
        evidence=findings,
        scope=f"Checked {data.get('domains_checked', 0)} domain(s) against public GitHub repositories "
              "for exposed secrets.",
        observed_at=data.get("checked_at"),
    )


# Shared demo key for the zero-key free tier below (mcp_space_demo source,
# 20 calls/day shared across ALL callers, enforced server-side by the
# RelayShield API itself -- see DEMO_QUOTA_SOURCES in relayshield_api.py).
# Same established pattern as the hf_smolagents_demo key already embedded
# in relayshield_smolagents_tool.py; the cap bounds worst-case abuse to a
# small fixed daily amount regardless of who has this string.
_DEMO_API_KEY = "rs_live_9797cff2e80b407eae16a12c8faac71e"


def check_llm_credential_exposure(domain: str, api_key: str = "") -> str:
    """Check a domain for exposed LLM/AI provider API keys (OpenAI, Anthropic,
    Google, Groq, xAI, Replicate) in criminal stealer logs -- LLMjacking, a
    fast-growing threat where a leaked key becomes a live, uncapped billing
    liability rather than just a data exposure. Real incidents have run from
    tens of thousands of dollars per day to a $500K single-month bill from
    one leaked, unthrottled key.

    Args:
        domain: Domain to check, e.g. example.com
        api_key: Your RelayShield API key. Leave blank to try this specific
            tool for free (shared demo quota, 20 calls/day across all users --
            get your own key at https://api.relayshield.net/developers#ep-llm-credential-exposure
            for unlimited use and access to the other 12 tools on this server).

    Returns:
        A structured result: outcome/recommended_action plus evidence and reason codes.
    """
    if not domain:
        return _error_result("other", "domain is required.")

    used_key = (api_key or "").strip() or _DEMO_API_KEY
    data, error = _call("/v1/metered/llm-credential-exposure", {"domain": domain}, used_key)
    if error:
        return error

    findings = data.get("findings", [])
    providers = data.get("providers_affected", [])
    outcome, action = _outcome_for_severity(data.get("highest_severity"), found=bool(findings))
    return _structured_result(
        outcome, action,
        reason_codes=providers,
        evidence=findings,
        scope=f"Checked {domain} against RelayShield's stealer-log corpus for exposed LLM/AI provider "
              f"API keys (OpenAI, Anthropic, Google, Groq, xAI, Replicate).{' Used the shared free demo key -- get your own for unlimited use.' if used_key == _DEMO_API_KEY else ''}",
        observed_at=data.get("checked_at"),
    )


def check_agent_risk_summary(domain: str, email: str, tech_stack: str, api_key: str) -> str:
    """Composite risk check -- one call instead of four. Runs breach exposure,
    LLM credential exposure, and tech-stack CVE checks together and returns a
    single fused risk verdict, so a calling agent doesn't have to make
    multiple tool calls and reason about how to combine their results itself.

    Args:
        domain: Domain to check (used for LLM credential exposure and tech-stack CVE lookup). Leave blank to skip these.
        email: Email address to check for breach exposure. Leave blank to skip this check.
        tech_stack: Comma-separated tech stack for CVE matching, e.g. "langchain, nacos". Leave blank to skip.
        api_key: Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-agent-risk-summary

    Returns:
        A structured result combining all sub-checks that were run, with the
        highest severity found across them driving the overall outcome.
    """
    if not api_key:
        return _error_result("auth", _scrub("api_key is required. Get one at https://api.relayshield.net/developers#ep-agent-risk-summary"))
    if not domain and not email and not tech_stack:
        return _error_result("other", "at least one of domain, email, or tech_stack is required.")

    severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    sub_results: dict = {}
    highest_seen = None
    all_evidence: list = []
    reason_codes: list = []
    any_error = None

    def _note(check_name: str, data: dict | None, err: str | None, sev_key: str, evidence_key: str):
        nonlocal highest_seen, any_error
        if err:
            sub_results[check_name] = {"error": True}
            any_error = any_error or err
            return
        sub_results[check_name] = data
        sev = data.get(sev_key)
        if sev and severity_rank.get(sev, 0) > severity_rank.get(highest_seen, 0):
            highest_seen = sev
        ev = data.get(evidence_key) or []
        if ev:
            all_evidence.extend(ev if isinstance(ev, list) else [ev])

    if email and "@" in email:
        data, err = _call("/v1/metered/breach", {"email": email}, api_key)
        _note("breach", data, err, "highest_severity", "breaches")
        if not err and data.get("breach_count"):
            reason_codes.append("email_breach_exposure")

    if domain:
        data, err = _call("/v1/metered/llm-credential-exposure", {"domain": domain}, api_key)
        _note("llm_credential_exposure", data, err, "highest_severity", "findings")
        if not err and data.get("found"):
            reason_codes.append("llm_credential_exposure")

    if tech_stack.strip():
        stack_list = [t.strip() for t in tech_stack.split(",") if t.strip()]
        data, err = _call("/v1/metered/tech-stack-cve", {"tech_stack": stack_list}, api_key)
        if not err:
            highest = "CRITICAL" if data.get("critical_count") else ("HIGH" if data.get("total_matches") else None)
            sub_results["tech_stack_cve"] = data
            if highest and severity_rank.get(highest, 0) > severity_rank.get(highest_seen, 0):
                highest_seen = highest
            if data.get("critical_count"):
                reason_codes.append("tech_stack_cve_critical")
            all_evidence.extend(data.get("critical_cves", []))
        else:
            sub_results["tech_stack_cve"] = {"error": True}
            any_error = any_error or err

    outcome, action = _outcome_for_severity(highest_seen, found=bool(reason_codes))
    result = _structured_result(
        outcome, action,
        reason_codes=reason_codes,
        evidence=all_evidence[:20],
        scope=f"Composite check across: {', '.join(k for k in sub_results if sub_results[k] and not sub_results[k].get('error'))}.",
    )
    if any_error and not reason_codes and outcome == "no_known_finding":
        # At least one sub-check failed and nothing was found elsewhere -- don't
        # silently report a clean bill of health when part of the check didn't run.
        parsed = json.loads(result)
        parsed["coverage"]["complete"] = False
        parsed["coverage"]["scope"] += " One or more sub-checks failed to complete -- see logs."
        return json.dumps(parsed, indent=2)
    return result


def get_stix_indicators(limit: int, api_key: str) -> str:
    """Fetch RelayShield's IOC corpus as STIX 2.1 Indicator objects via the
    TAXII 2.1 feed -- for agents/tools that consume threat intel in STIX
    format directly (SIEM/TIP ingestion, correlation engines) rather than
    RelayShield's own JSON shape. Requires a TI (Threat Intelligence)
    subscription API key, not just any metered key -- a standard metered
    key will get an auth error here, that's expected.

    Args:
        limit: Number of STIX objects to return, up to 2000. Defaults to 50 if 0 or not set.
        api_key: Your RelayShield TI subscription API key. Get one at https://api.relayshield.net/developers#ti-subscription

    Returns:
        A structured result with STIX 2.1 Indicator objects as evidence.
    """
    if not api_key:
        return _error_result("auth", _scrub("api_key is required (must be a TI subscription key). Get one at https://api.relayshield.net/developers#ti-subscription"))

    page_size = limit if limit and 0 < limit <= 2000 else 50
    try:
        resp = requests.get(
            f"{API_BASE_URL}/v1/intel/taxii/collections/iocs/objects/",
            params={"limit": page_size},
            headers=_headers(api_key),
            timeout=20,
        )
    except requests.RequestException as exc:
        return _error_result("upstream", f"TAXII request failed: {exc}", retryable=True)

    if resp.status_code in (401, 403):
        return _error_result("auth", f"TAXII endpoint returned {resp.status_code} -- this endpoint requires a TI subscription key, not a standard metered key.", retryable=False)
    if resp.status_code >= 400:
        return _error_result("other", f"TAXII endpoint returned {resp.status_code}: {resp.text[:200]}", retryable=resp.status_code >= 500)

    try:
        body = resp.json()
    except ValueError:
        return _error_result("malformed_response", "TAXII endpoint returned non-JSON content.", retryable=False)

    objects = body.get("objects", [])
    return _structured_result(
        "finding" if objects else "no_known_finding",
        "review" if objects else "allow",
        reason_codes=["stix_indicator_bundle"] if objects else [],
        evidence=objects,
        scope=f"Fetched {len(objects)} STIX 2.1 Indicator object(s) from RelayShield's TAXII 2.1 feed "
              "(/v1/intel/taxii/collections/iocs/objects/).",
    )


def check_server_status() -> str:
    """Check which RelayShield tools and data sources are currently live on
    this MCP server -- a lightweight introspection call for an agent (or a
    human debugging) to confirm connectivity and see what's available before
    making a real check. Requires no API key.

    Returns:
        A structured result listing available tools and a live upstream connectivity check.
    """
    tool_names = [t["name"] for t in _SERVER_CARD["tools"]]
    try:
        resp = requests.get(f"{API_BASE_URL}/developers", timeout=8)
        upstream_reachable = resp.status_code < 500
    except requests.RequestException:
        upstream_reachable = False

    return _structured_result(
        "no_known_finding", "allow",
        evidence=[{"tools_available": tool_names, "tool_count": len(tool_names), "upstream_reachable": upstream_reachable}],
        scope="Introspection check -- lists available tools and confirms the RelayShield API is reachable. "
              "Not a security finding; 'outcome' is always no_known_finding for this tool.",
    )


mcp_risk_tab = gr.Interface(
    fn=check_mcp_server_risk,
    inputs=[
        gr.Textbox(label="MCP Server URL", placeholder="https://example.com/mcp"),
        gr.Textbox(label="RelayShield API Key", type="password", placeholder=_scrub("Get one at api.relayshield.net/developers#ep-mcp-registry-risk")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="MCP Server Risk Check",
    description="Typosquat, IOC-corpus, and registration-age risk check for an MCP server URL.",
)

breach_tab = gr.Interface(
    fn=check_prompt_injection_breach,
    inputs=[
        gr.Textbox(label="Email Address", placeholder="agent@example.com"),
        gr.Textbox(label="RelayShield API Key", type="password", placeholder=_scrub("Get one at api.relayshield.net/developers#ep-prompt-injection-breach")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="Prompt-Injection Breach Check",
    description="Checks for credential breaches sourced from prompt-injection attacks against AI agents.",
)

tech_stack_tab = gr.Interface(
    fn=check_tech_stack_cve,
    inputs=[
        gr.Textbox(label="Tech Stack (comma-separated)", placeholder="langchain, nacos, minio"),
        gr.Textbox(label="RelayShield API Key", type="password", placeholder=_scrub("Get one at api.relayshield.net/developers#ep-tech-stack-cve")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="Tech Stack CVE Check",
    description="CISA KEV / high-EPSS CVEs targeting a declared AI agent framework or tech stack.",
)

bulk_identity_tab = gr.Interface(
    fn=check_bulk_identity_risk,
    inputs=[
        gr.Textbox(label="Domain", placeholder="example.com"),
        gr.Textbox(label="Agent Emails (comma-separated, up to 5)", placeholder="ai-agent@example.com, svc@example.com"),
        gr.Textbox(label="RelayShield API Key", type="password", placeholder=_scrub("Get one at api.relayshield.net/developers#ep-bulk-identity-risk")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="Bulk Identity Risk Check",
    description="Hierarchical org + AI-agent-identity risk scoring for a domain and its agent/service-account identities.",
)

oauth_watchlist_tab = gr.Interface(
    fn=check_oauth_watchlist,
    inputs=[
        gr.Textbox(label="Email Address", placeholder="agent@example.com"),
        gr.Textbox(label="RelayShield API Key", type="password", placeholder=_scrub("Get one at api.relayshield.net/developers#ep-oauth-watchlist")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="OAuth Watchlist Check",
    description="OAuth-connected-app breach exposure plus stolen OAuth/session tokens found in criminal stealer logs.",
)

supply_chain_tab = gr.Interface(
    fn=check_supply_chain,
    inputs=[
        gr.Textbox(label="Vendor Domains (comma-separated, up to 10)", placeholder="vendor1.com, vendor2.com"),
        gr.Textbox(label="RelayShield API Key", type="password", placeholder=_scrub("Get one at api.relayshield.net/developers#ep-supply-chain")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="Supply Chain Risk Check",
    description="Breach and infostealer exposure check for up to 10 vendor domains.",
)

session_risk_tab = gr.Interface(
    fn=check_session_risk,
    inputs=[
        gr.Textbox(label="Email Address", placeholder="agent@example.com"),
        gr.Textbox(label="RelayShield API Key", type="password", placeholder=_scrub("Get one at api.relayshield.net/developers#ep-session-risk")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="Session Risk Check",
    description="Active or reusable stolen session (cookie/token) exposure that can bypass MFA entirely.",
)

nhi_exposure_tab = gr.Interface(
    fn=check_nhi_exposure,
    inputs=[
        gr.Textbox(label="Domain (optional)", placeholder="example.com"),
        gr.Textbox(label="Vendor Domains (comma-separated, up to 10, optional)", placeholder="vendor1.com, vendor2.com"),
        gr.Textbox(label="RelayShield API Key", type="password", placeholder=_scrub("Get one at api.relayshield.net/developers#ep-nhi-exposure")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="Non-Human Identity Exposure Check",
    description="API keys, service-account tokens, PATs, and other machine credentials found in criminal stealer logs.",
)

secret_scan_tab = gr.Interface(
    fn=check_secret_scan,
    inputs=[
        gr.Textbox(label="Domain (optional)", placeholder="example.com"),
        gr.Textbox(label="Vendor Domains (comma-separated, up to 5, optional)", placeholder="vendor1.com, vendor2.com"),
        gr.Textbox(label="RelayShield API Key", type="password", placeholder=_scrub("Get one at api.relayshield.net/developers#ep-secret-scan")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="Secret Scan Check",
    description="Secrets and credentials exposed in public GitHub repositories.",
)

llm_credential_tab = gr.Interface(
    fn=check_llm_credential_exposure,
    inputs=[
        gr.Textbox(label="Domain", placeholder="example.com"),
        gr.Textbox(label="RelayShield API Key (optional — try free, 20 calls/day shared demo)", type="password", placeholder=_scrub("Leave blank to try for free, or get your own key at api.relayshield.net/developers#ep-llm-credential-exposure")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="LLM Credential Exposure (LLMjacking)",
    description="Exposed OpenAI/Anthropic/Google/Groq/xAI/Replicate API keys in criminal stealer logs — a live, uncapped billing liability. Free to try, no key required.",
)

agent_risk_summary_tab = gr.Interface(
    fn=check_agent_risk_summary,
    inputs=[
        gr.Textbox(label="Domain (optional)", placeholder="example.com"),
        gr.Textbox(label="Email Address (optional)", placeholder="agent@example.com"),
        gr.Textbox(label="Tech Stack (comma-separated, optional)", placeholder="langchain, nacos"),
        gr.Textbox(label="RelayShield API Key", type="password", placeholder=_scrub("Get one at api.relayshield.net/developers#ep-agent-risk-summary")),
    ],
    outputs=gr.Textbox(label="Result"),
    title="Agent Risk Summary (Composite)",
    description="One call instead of four — combines breach, LLM credential exposure, and tech-stack CVE checks into a single fused verdict.",
)

stix_tab = gr.Interface(
    fn=get_stix_indicators,
    inputs=[
        gr.Number(label="Limit (up to 2000, default 50)", value=50),
        gr.Textbox(label="RelayShield API Key (TI subscription required)", type="password", placeholder="Requires a TI subscription key, not a standard metered key"),
    ],
    outputs=gr.Textbox(label="Result"),
    title="STIX 2.1 Indicators (TAXII)",
    description="Fetch RelayShield's IOC corpus as STIX 2.1 Indicator objects for SIEM/TIP ingestion. Requires a TI subscription key.",
)

status_tab = gr.Interface(
    fn=check_server_status,
    inputs=[],
    outputs=gr.Textbox(label="Result"),
    title="Server Status",
    description="Lists available tools and confirms upstream connectivity. No API key required.",
)

demo = gr.TabbedInterface(
    [
        mcp_risk_tab, breach_tab, tech_stack_tab, bulk_identity_tab,
        oauth_watchlist_tab, supply_chain_tab, session_risk_tab, nhi_exposure_tab, secret_scan_tab,
        llm_credential_tab, agent_risk_summary_tab, stix_tab, status_tab,
    ],
    [
        "MCP Server Risk", "Prompt-Injection Breach", "Tech Stack CVE", "Bulk Identity Risk",
        "OAuth Watchlist", "Supply Chain", "Session Risk", "NHI Exposure", "Secret Scan",
        "LLM Credential Exposure", "Agent Risk Summary", "STIX Indicators", "Server Status",
    ],
    title="RelayShield Agentic Attack Surface",
)

# Serve a static server-card.json so directories like Smithery can read our
# tool schema directly instead of relying on a live MCP handshake scan
# (their scanner returned a 404 during initialization against the plain
# Gradio MCP endpoint — this is Smithery's own documented workaround:
# https://smithery.ai/docs/build/publish#troubleshooting).
_SERVER_CARD_RAW = {
    "serverInfo": {
        "name": "RelayShield Agentic Attack Surface",
        "version": "3.0.1",
    },
    "authentication": {
        "required": False,
    },
    "tools": [
        {
            "name": "check_mcp_server_risk",
            "description": "Check an MCP server URL for typosquat risk, presence in RelayShield's criminal IOC corpus, and domain-registration age. Returns a structured outcome/recommended_action result with evidence.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "server_url": {"type": "string", "description": "Full URL of the MCP server to check, e.g. https://example.com/mcp"},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-mcp-registry-risk"},
                },
                "required": ["server_url", "api_key"],
            },
        },
        {
            "name": "check_prompt_injection_breach",
            "description": "Check an email address for credential exposure sourced specifically from prompt-injection attacks against AI agents, distinct from ordinary phishing/malware-sourced breaches.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Email address to check, e.g. agent@example.com"},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-prompt-injection-breach"},
                },
                "required": ["email", "api_key"],
            },
        },
        {
            "name": "check_tech_stack_cve",
            "description": "Check a declared AI agent framework / tech stack for CISA KEV or high-EPSS CVEs actively being exploited. Covers AI agent orchestration frameworks and common companion infrastructure.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tech_stack": {"type": "string", "description": "Comma-separated list of products, e.g. \"langchain, nacos, minio\""},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-tech-stack-cve"},
                },
                "required": ["tech_stack", "api_key"],
            },
        },
        {
            "name": "check_bulk_identity_risk",
            "description": "Hierarchical org + AI-agent-identity risk scoring for a domain and up to 5 agent/service-account identities. A critically-exposed agent automatically elevates the organizational risk rating.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Organization domain to score, e.g. example.com"},
                    "agent_emails": {"type": "string", "description": "Comma-separated agent/service-account emails, up to 5"},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-bulk-identity-risk"},
                },
                "required": ["domain", "api_key"],
            },
        },
        {
            "name": "check_oauth_watchlist",
            "description": "Check an email for OAuth-connected-app exposure: apps matched against breach history, plus stolen OAuth/session tokens found in criminal stealer logs. Part of the oauth_watchlist/nhi_exposure/session_risk agent-authority family.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Email address to check, e.g. agent@example.com"},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-oauth-watchlist"},
                },
                "required": ["email", "api_key"],
            },
        },
        {
            "name": "check_supply_chain",
            "description": "Check up to 10 vendor domains for breach and infostealer exposure — third-party and supply-chain risk inherited through vendor relationships.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "vendor_domains": {"type": "string", "description": "Comma-separated vendor domains, up to 10"},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-supply-chain"},
                },
                "required": ["vendor_domains", "api_key"],
            },
        },
        {
            "name": "check_session_risk",
            "description": "Check an email for active or reusable stolen session material (cookies, tokens) found in criminal stealer logs — exposure that can bypass MFA entirely. Part of the oauth_watchlist/nhi_exposure/session_risk agent-authority family.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Email address to check, e.g. agent@example.com"},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-session-risk"},
                },
                "required": ["email", "api_key"],
            },
        },
        {
            "name": "check_nhi_exposure",
            "description": "Check a domain, or up to 10 vendor domains, for exposed non-human-identity credentials — API keys, service-account tokens, PATs, and other machine identities. Part of the oauth_watchlist/nhi_exposure/session_risk agent-authority family.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Your own domain to check (optional if vendor_domains supplied)"},
                    "vendor_domains": {"type": "string", "description": "Comma-separated vendor domains, up to 10 (optional if domain supplied)"},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-nhi-exposure"},
                },
                "required": ["api_key"],
            },
        },
        {
            "name": "check_secret_scan",
            "description": "Check a domain, or up to 5 vendor domains, for secrets and credentials exposed in public GitHub repositories.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Your own domain to check (optional if vendor_domains supplied)"},
                    "vendor_domains": {"type": "string", "description": "Comma-separated vendor domains, up to 5 (optional if domain supplied)"},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-secret-scan"},
                },
                "required": ["api_key"],
            },
        },
        {
            "name": "check_llm_credential_exposure",
            "description": "Check a domain for exposed LLM/AI provider API keys (OpenAI, Anthropic, Google, Groq, xAI, Replicate) in criminal stealer logs -- LLMjacking, a live billing liability, not just a data exposure. Free to try (no api_key required, shared demo quota); pass your own key for unlimited use.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Domain to check, e.g. example.com"},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Optional -- leave blank to try for free (shared 20/day demo quota). Get your own at https://api.relayshield.net/developers#ep-llm-credential-exposure"},
                },
                "required": ["domain"],
            },
        },
        {
            "name": "check_agent_risk_summary",
            "description": "Composite check -- one call instead of four. Runs breach exposure, LLM credential exposure, and tech-stack CVE checks together and returns a single fused risk verdict.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Domain to check (LLM credential exposure + tech-stack CVE). Optional."},
                    "email": {"type": "string", "description": "Email to check for breach exposure. Optional."},
                    "tech_stack": {"type": "string", "description": "Comma-separated tech stack for CVE matching. Optional."},
                    "api_key": {"type": "string", "description": "Your RelayShield API key. Get one at https://api.relayshield.net/developers#ep-agent-risk-summary"},
                },
                "required": ["api_key"],
            },
        },
        {
            "name": "get_stix_indicators",
            "description": "Fetch RelayShield's IOC corpus as STIX 2.1 Indicator objects via the TAXII 2.1 feed, for SIEM/TIP ingestion. Requires a TI subscription API key, not a standard metered key.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of STIX objects to return, up to 2000. Defaults to 50."},
                    "api_key": {"type": "string", "description": "Your RelayShield TI subscription API key. Get one at https://api.relayshield.net/developers#ti-subscription"},
                },
                "required": ["api_key"],
            },
        },
        {
            "name": "check_server_status",
            "description": "Lists available tools on this MCP server and confirms upstream RelayShield API connectivity. No API key required.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    ],
    "resources": [],
    "prompts": [],
}

# Scrub the developers-page reference from the manifest too (no-op in public
# mode) — this is served directly at /.well-known/mcp/server-card.json for
# directories like Smithery, a separate surface from the live MCP handshake.
_SERVER_CARD = json.loads(_scrub(json.dumps(_SERVER_CARD_RAW)))

# Scrub every tool function's docstring (no-op in public mode) — must happen
# before demo.launch() below, since that's the point Gradio reads __doc__ to
# build the live MCP tool schema an MCP client actually sees.
for _fn in (
    check_mcp_server_risk, check_prompt_injection_breach, check_tech_stack_cve,
    check_bulk_identity_risk, check_oauth_watchlist, check_supply_chain,
    check_session_risk, check_nhi_exposure, check_secret_scan,
    check_llm_credential_exposure, check_agent_risk_summary,
    get_stix_indicators, check_server_status,
):
    if _fn.__doc__:
        _fn.__doc__ = _scrub(_fn.__doc__)

# NOTE 2026-07-27: root-caused via gradio's own source (routes.py,
# node_server.py), not guessed. gr.mount_gradio_app()/Blocks.launch() both
# conditionally call start_node_server() when ssr_mode resolves True — this
# spawns an actual Node.js child process for server-side rendering, and its
# default port fallback is ALSO 7860 (node_server.py: INITIAL_PORT_VALUE =
# int(os.getenv("GRADIO_SERVER_PORT", "7860"))). ssr_mode resolves from the
# GRADIO_SSR_MODE env var when not passed explicitly, and HF's Docker Space
# runtime apparently sets it — reproduced both bugs locally by simply
# exporting GRADIO_SSR_MODE=true: (1) the original custom-FastAPI +
# mount_gradio_app + manual uvicorn.run() pattern crashed with "[Errno 98]
# address already in use" because the Node process grabs 7860 first, then
# uvicorn.run() tries to grab the same port; (2) even after switching to
# demo.launch() to dodge that crash, the custom /.well-known/mcp/server-
# card.json route (Smithery's discovery workaround) came back as Gradio's
# generic SPA shell instead of real JSON — the Node server becomes the
# actual thing listening on the port and proxies through to Python, and
# (matching the original 2026-07 comment about "a Node.js frontend proxy
# ... only forwards a fixed whitelist of paths", now in git history) a
# custom Python-side route isn't in that whitelist. Fix: ssr_mode=False
# below, explicit rather than relying on the (HF-overridden) default —
# confirmed locally that no Node process spawns and the custom route
# resolves to real JSON with this set, even with GRADIO_SSR_MODE=true
# forced in the environment.
if __name__ == "__main__":
    import threading

    from fastapi.responses import JSONResponse

    demo.launch(
        server_name="0.0.0.0", server_port=7860, mcp_server=True,
        ssr_mode=False, prevent_thread_lock=True,
    )

    @demo.app.get("/.well-known/mcp/server-card.json")
    async def server_card():
        return JSONResponse(_SERVER_CARD)

    threading.Event().wait()
