"""RelayShield MCP server over Streamable HTTP, hosted on AWS (Lambda).

WHY THIS EXISTS (2026-10-25)
----------------------------
The AWS Foundational Technical Review is blocked on the prerequisite "AWS
Marketplace product is deployed on AWS" for prod-kkvurtspreofy (Consumption
Security API Bundles). That listing's registered MCP endpoint was a Hugging
Face Space, which is outside AWS and receives the caller's API key and the
domains and emails they query. AWS's SaaS guidelines (read as a search
summary; docs.aws.amazon.com is unreachable from the container) say third-party
services that transmit, store or process application data must run on AWS.

This module is the SAME 13 tools as hf-space-mcp-server/app.py, speaking the
MCP Streamable HTTP transport (POST JSON-RPC) from a Lambda in the RelayShield
account. It calls the RelayShield REST API exactly as the Space does, so billing,
metering and rate limits are untouched.

THE HF SPACE IS NOT RETIRED. Other listings, the MCP registries and Smithery may
point at the public Space. Only the AWS listing's endpoint moves.

PARITY IS TESTED, NOT ASSERTED. test_relayshield_mcp_http.py loads app.py with
gradio and requests stubbed and runs every tool through both implementations
against the same canned upstream responses. If app.py changes and this file does
not, that test fails.

AWS MARKETPLACE MODE IS ALWAYS ON HERE. AWS's Tier-1 audit failed Bundle D's
visibility twice over a reachable link to the self-serve signup page, even one
buried in a tool parameter description. So every "Get one at
api.relayshield.net/developers..." phrase is replaced, in the tool manifest and
in error text, exactly as app.py does when AWS_MARKETPLACE_MODE=true.

ENV
---
RS_DEMO_API_KEY  the shared free-tier demo key used by check_llm_credential_exposure
                 when the caller passes no key. Same value as _DEMO_API_KEY in
                 app.py; set from there by tools/setup_mcp_http.sh so the key is
                 not copied into a second source file. Unset means that one tool
                 requires a caller key.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.request

API_BASE_URL = "https://api.relayshield.net"
SERVER_NAME = "relayshield-consumption-security"
SERVER_VERSION = "1.0.0"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

_KEY_URL_RE = re.compile(
    r"(?:Get (?:a(?:\s+key)?|one|your own(?:\s+key)?)|get your own key)\s+at\s+"
    r"(?:https?://)?api\.relayshield\.net/developers(?:#[\w-]+)?\.?",
)
_AWS_KEY_TEXT = "Included with your AWS Marketplace subscription, issued automatically by email"


def _scrub(text):
    if not text:
        return text
    return _KEY_URL_RE.sub(_AWS_KEY_TEXT, text)


class _Timeout(Exception):
    pass


class _NetError(Exception):
    pass


def _http_request(method, url, body=None, headers=None, timeout=15):
    """Returns (status_code, text). The one network seam; tests replace it."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (TimeoutError, urllib.error.URLError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            raise _Timeout(str(reason))
        raise _NetError(str(reason))


def _headers(api_key):
    # X-RS-Source keeps the label the weekly report already counts as MCP
    # traffic (both API dispatchers match it by exact string). Changing it
    # would make this endpoint's usage vanish from that report, and renaming it
    # means editing a live 18,000-line Lambda. Revisit when the dispatchers
    # accept a second label.
    return {
        "Content-Type": "application/json",
        "X-RS-API-KEY": api_key,
        "X-RS-Source": "hf-mcp-space",
    }


def _outcome_for_severity(highest_severity, found=True):
    if not found or highest_severity in (None, "NONE", "CLEAN"):
        return "no_known_finding", "allow"
    if highest_severity == "CRITICAL":
        return "finding", "deny"
    return "finding", "review"


def _structured_result(outcome, recommended_action, *, reason_codes=None, evidence=None,
                       scope, coverage_complete=True, observed_at=None):
    return json.dumps({
        "outcome": outcome,
        "recommended_action": recommended_action,
        "reason_codes": reason_codes or [],
        "evidence": evidence or [],
        "coverage": {"complete": coverage_complete, "scope": scope},
        "freshness": {"observed_at": observed_at, "expires_at": None},
        "error": None,
    }, indent=2)


def _error_result(kind, message, retryable=False):
    return json.dumps({
        "outcome": "error",
        "recommended_action": "defer",
        "reason_codes": [],
        "evidence": [],
        "coverage": {"complete": False, "scope": ""},
        "freshness": {"observed_at": None, "expires_at": None},
        "error": {"kind": kind, "message": message, "retryable": retryable},
    }, indent=2)


def _call(path, payload, api_key):
    """POST to a RelayShield metered endpoint. Returns (data, error_json_or_None)."""
    try:
        status, text = _http_request("POST", f"{API_BASE_URL}{path}", payload, _headers(api_key), 15)
    except _Timeout:
        return None, _error_result("timeout", f"RelayShield API call to {path} timed out after 15s.", retryable=True)
    except _NetError as exc:
        return None, _error_result("upstream", f"RelayShield API call to {path} failed: {exc}", retryable=True)

    if status in (401, 403):
        return None, _error_result("auth", f"RelayShield API call to {path} returned {status} — check api_key.", retryable=False)
    if status == 429:
        return None, _error_result("rate_limited", f"RelayShield API call to {path} was rate-limited.", retryable=True)
    if status >= 500:
        return None, _error_result("upstream", f"RelayShield API call to {path} returned {status}.", retryable=True)
    if status >= 400:
        return None, _error_result("other", f"RelayShield API call to {path} returned {status}: {text[:200]}", retryable=False)

    try:
        response_json = json.loads(text)
    except ValueError:
        return None, _error_result("malformed_response", f"RelayShield API call to {path} returned non-JSON content.", retryable=False)

    if not isinstance(response_json, dict):
        return None, _error_result("malformed_response", f"RelayShield API call to {path} returned an unexpected response shape.", retryable=False)

    return response_json.get("data", {}), None


def _no_key(anchor, what=""):
    return _error_result("auth", _scrub(f"api_key is required{what}. Get one at https://api.relayshield.net/developers#{anchor}"))


def check_mcp_server_risk(server_url, api_key):
    if not server_url:
        return _error_result("other", "server_url is required.")
    if not api_key:
        return _no_key("ep-mcp-registry-risk")

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


def check_prompt_injection_breach(email, api_key):
    if not email or "@" not in email:
        return _error_result("other", "a valid email address is required.")
    if not api_key:
        return _no_key("ep-prompt-injection-breach")

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


def check_tech_stack_cve(tech_stack, api_key):
    stack_list = [t.strip() for t in tech_stack.split(",") if t.strip()]
    if not stack_list:
        return _error_result("other", "tech_stack is required (comma-separated list of products).")
    if not api_key:
        return _no_key("ep-tech-stack-cve")

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


def check_bulk_identity_risk(domain, agent_emails, api_key):
    if not domain:
        return _error_result("other", "domain is required.")
    if not api_key:
        return _no_key("ep-bulk-identity-risk")

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


def check_oauth_watchlist(email, api_key):
    if not email or "@" not in email:
        return _error_result("other", "a valid email address is required.")
    if not api_key:
        return _no_key("ep-oauth-watchlist")

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


def check_supply_chain(vendor_domains, api_key):
    domains = [d.strip() for d in vendor_domains.split(",") if d.strip()][:10]
    if not domains:
        return _error_result("other", "vendor_domains is required (comma-separated list, up to 10).")
    if not api_key:
        return _no_key("ep-supply-chain")

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


def check_session_risk(email, api_key):
    if not email or "@" not in email:
        return _error_result("other", "a valid email address is required.")
    if not api_key:
        return _no_key("ep-session-risk")

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


def check_nhi_exposure(domain, vendor_domains, api_key):
    domain = (domain or "").strip()
    domains = [d.strip() for d in (vendor_domains or "").split(",") if d.strip()][:10]
    if not domain and not domains:
        return _error_result("other", "domain or vendor_domains is required.")
    if not api_key:
        return _no_key("ep-nhi-exposure")

    payload = {}
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


def check_secret_scan(domain, vendor_domains, api_key):
    domain = (domain or "").strip()
    domains = [d.strip() for d in (vendor_domains or "").split(",") if d.strip()][:5]
    if not domain and not domains:
        return _error_result("other", "domain or vendor_domains is required.")
    if not api_key:
        return _no_key("ep-secret-scan")

    payload = {}
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


def check_llm_credential_exposure(domain, api_key=""):
    if not domain:
        return _error_result("other", "domain is required.")

    demo_key = os.environ.get("RS_DEMO_API_KEY", "")
    used_key = (api_key or "").strip() or demo_key
    if not used_key:
        return _no_key("ep-llm-credential-exposure")
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
              f"API keys (OpenAI, Anthropic, Google, Groq, xAI, Replicate).{' Used the shared free demo key -- get your own for unlimited use.' if used_key == demo_key else ''}",
        observed_at=data.get("checked_at"),
    )


def check_agent_risk_summary(domain, email, tech_stack, api_key):
    if not api_key:
        return _no_key("ep-agent-risk-summary")
    if not domain and not email and not tech_stack:
        return _error_result("other", "at least one of domain, email, or tech_stack is required.")

    severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    sub_results = {}
    highest_seen = None
    all_evidence = []
    reason_codes = []
    any_error = None

    def _note(check_name, data, err, sev_key, evidence_key):
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
        parsed = json.loads(result)
        parsed["coverage"]["complete"] = False
        parsed["coverage"]["scope"] += " One or more sub-checks failed to complete -- see logs."
        return json.dumps(parsed, indent=2)
    return result


def get_stix_indicators(limit, api_key):
    if not api_key:
        return _error_result("auth", _scrub("api_key is required (must be a TI subscription key). Get one at https://api.relayshield.net/developers#ti-subscription"))

    page_size = limit if limit and 0 < limit <= 2000 else 50
    url = f"{API_BASE_URL}/v1/intel/taxii/collections/iocs/objects/?limit={page_size}"
    try:
        status, text = _http_request("GET", url, None, _headers(api_key), 20)
    except (_Timeout, _NetError) as exc:
        return _error_result("upstream", f"TAXII request failed: {exc}", retryable=True)

    if status in (401, 403):
        return _error_result("auth", f"TAXII endpoint returned {status} -- this endpoint requires a TI subscription key, not a standard metered key.", retryable=False)
    if status >= 400:
        return _error_result("other", f"TAXII endpoint returned {status}: {text[:200]}", retryable=status >= 500)

    try:
        body = json.loads(text)
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


def check_server_status():
    tool_names = [t["name"] for t in TOOLS]
    try:
        status, _ = _http_request("GET", f"{API_BASE_URL}/developers", None, {}, 8)
        upstream_reachable = status < 500
    except (_Timeout, _NetError):
        upstream_reachable = False

    return _structured_result(
        "no_known_finding", "allow",
        evidence=[{"tools_available": tool_names, "tool_count": len(tool_names), "upstream_reachable": upstream_reachable}],
        scope="Introspection check -- lists available tools and confirms the RelayShield API is reachable. "
              "Not a security finding; 'outcome' is always no_known_finding for this tool.",
    )


# The tool manifest. GENERATED from hf-space-mcp-server/app.py's _SERVER_CARD_RAW
# with the AWS scrub applied; test_relayshield_mcp_http.py fails if it drifts.
_TOOLS_JSON = r'''[
  {
    "name": "check_mcp_server_risk",
    "description": "Check an MCP server URL for typosquat risk, presence in RelayShield's criminal IOC corpus, and domain-registration age. Returns a structured outcome/recommended_action result with evidence.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "server_url": {
          "type": "string",
          "description": "Full URL of the MCP server to check, e.g. https://example.com/mcp"
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "server_url",
        "api_key"
      ]
    }
  },
  {
    "name": "check_prompt_injection_breach",
    "description": "Check an email address for credential exposure sourced specifically from prompt-injection attacks against AI agents, distinct from ordinary phishing/malware-sourced breaches.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "email": {
          "type": "string",
          "description": "Email address to check, e.g. agent@example.com"
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "email",
        "api_key"
      ]
    }
  },
  {
    "name": "check_tech_stack_cve",
    "description": "Check a declared AI agent framework / tech stack for CISA KEV or high-EPSS CVEs actively being exploited. Covers AI agent orchestration frameworks and common companion infrastructure.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "tech_stack": {
          "type": "string",
          "description": "Comma-separated list of products, e.g. \"langchain, nacos, minio\""
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "tech_stack",
        "api_key"
      ]
    }
  },
  {
    "name": "check_bulk_identity_risk",
    "description": "Hierarchical org + AI-agent-identity risk scoring for a domain and up to 5 agent/service-account identities. A critically-exposed agent automatically elevates the organizational risk rating.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "domain": {
          "type": "string",
          "description": "Organization domain to score, e.g. example.com"
        },
        "agent_emails": {
          "type": "string",
          "description": "Comma-separated agent/service-account emails, up to 5"
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "domain",
        "api_key"
      ]
    }
  },
  {
    "name": "check_oauth_watchlist",
    "description": "Check an email for OAuth-connected-app exposure: apps matched against breach history, plus stolen OAuth/session tokens found in criminal stealer logs. Part of the oauth_watchlist/nhi_exposure/session_risk agent-authority family.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "email": {
          "type": "string",
          "description": "Email address to check, e.g. agent@example.com"
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "email",
        "api_key"
      ]
    }
  },
  {
    "name": "check_supply_chain",
    "description": "Check up to 10 vendor domains for breach and infostealer exposure — third-party and supply-chain risk inherited through vendor relationships.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "vendor_domains": {
          "type": "string",
          "description": "Comma-separated vendor domains, up to 10"
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "vendor_domains",
        "api_key"
      ]
    }
  },
  {
    "name": "check_session_risk",
    "description": "Check an email for active or reusable stolen session material (cookies, tokens) found in criminal stealer logs — exposure that can bypass MFA entirely. Part of the oauth_watchlist/nhi_exposure/session_risk agent-authority family.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "email": {
          "type": "string",
          "description": "Email address to check, e.g. agent@example.com"
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "email",
        "api_key"
      ]
    }
  },
  {
    "name": "check_nhi_exposure",
    "description": "Check a domain, or up to 10 vendor domains, for exposed non-human-identity credentials — API keys, service-account tokens, PATs, and other machine identities. Part of the oauth_watchlist/nhi_exposure/session_risk agent-authority family.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "domain": {
          "type": "string",
          "description": "Your own domain to check (optional if vendor_domains supplied)"
        },
        "vendor_domains": {
          "type": "string",
          "description": "Comma-separated vendor domains, up to 10 (optional if domain supplied)"
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "api_key"
      ]
    }
  },
  {
    "name": "check_secret_scan",
    "description": "Check a domain, or up to 5 vendor domains, for secrets and credentials exposed in public GitHub repositories.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "domain": {
          "type": "string",
          "description": "Your own domain to check (optional if vendor_domains supplied)"
        },
        "vendor_domains": {
          "type": "string",
          "description": "Comma-separated vendor domains, up to 5 (optional if domain supplied)"
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "api_key"
      ]
    }
  },
  {
    "name": "check_llm_credential_exposure",
    "description": "Check a domain for exposed LLM/AI provider API keys (OpenAI, Anthropic, Google, Groq, xAI, Replicate) in criminal stealer logs -- LLMjacking, a live billing liability, not just a data exposure. Free to try (no api_key required, shared demo quota); pass your own key for unlimited use.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "domain": {
          "type": "string",
          "description": "Domain to check, e.g. example.com"
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Optional -- leave blank to try for free (shared 20/day demo quota). Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "domain"
      ]
    }
  },
  {
    "name": "check_agent_risk_summary",
    "description": "Composite check -- one call instead of four. Runs breach exposure, LLM credential exposure, and tech-stack CVE checks together and returns a single fused risk verdict.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "domain": {
          "type": "string",
          "description": "Domain to check (LLM credential exposure + tech-stack CVE). Optional."
        },
        "email": {
          "type": "string",
          "description": "Email to check for breach exposure. Optional."
        },
        "tech_stack": {
          "type": "string",
          "description": "Comma-separated tech stack for CVE matching. Optional."
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "api_key"
      ]
    }
  },
  {
    "name": "get_stix_indicators",
    "description": "Fetch RelayShield's IOC corpus as STIX 2.1 Indicator objects via the TAXII 2.1 feed, for SIEM/TIP ingestion. Requires a TI subscription API key, not a standard metered key.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "limit": {
          "type": "integer",
          "description": "Number of STIX objects to return, up to 2000. Defaults to 50."
        },
        "api_key": {
          "type": "string",
          "description": "Your RelayShield TI subscription API key. Included with your AWS Marketplace subscription, issued automatically by email"
        }
      },
      "required": [
        "api_key"
      ]
    }
  },
  {
    "name": "check_server_status",
    "description": "Lists available tools on this MCP server and confirms upstream RelayShield API connectivity. No API key required.",
    "inputSchema": {
      "type": "object",
      "properties": {},
      "required": []
    }
  }
]'''
TOOLS = json.loads(_TOOLS_JSON)

# name -> (callable, argument names in call order, defaults for missing args)
_DISPATCH = {
    "check_mcp_server_risk":         (check_mcp_server_risk, ("server_url", "api_key")),
    "check_prompt_injection_breach": (check_prompt_injection_breach, ("email", "api_key")),
    "check_tech_stack_cve":          (check_tech_stack_cve, ("tech_stack", "api_key")),
    "check_bulk_identity_risk":      (check_bulk_identity_risk, ("domain", "agent_emails", "api_key")),
    "check_oauth_watchlist":         (check_oauth_watchlist, ("email", "api_key")),
    "check_supply_chain":            (check_supply_chain, ("vendor_domains", "api_key")),
    "check_session_risk":            (check_session_risk, ("email", "api_key")),
    "check_nhi_exposure":            (check_nhi_exposure, ("domain", "vendor_domains", "api_key")),
    "check_secret_scan":             (check_secret_scan, ("domain", "vendor_domains", "api_key")),
    "check_llm_credential_exposure": (check_llm_credential_exposure, ("domain", "api_key")),
    "check_agent_risk_summary":      (check_agent_risk_summary, ("domain", "email", "tech_stack", "api_key")),
    "get_stix_indicators":           (get_stix_indicators, ("limit", "api_key")),
    "check_server_status":           (check_server_status, ()),
}


def _run_tool(name, arguments):
    fn, arg_names = _DISPATCH[name]
    args = []
    for a in arg_names:
        v = arguments.get(a)
        if a == "limit":
            try:
                v = int(v) if v not in (None, "") else 0
            except (TypeError, ValueError):
                v = 0
        elif v is None:
            v = ""
        elif not isinstance(v, str):
            v = str(v)
        args.append(v)
    return fn(*args)


# ---------------------------------------------------------------------------
# JSON-RPC / Streamable HTTP
# ---------------------------------------------------------------------------

def _rpc_error(rpc_id, code, message):
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _handle_rpc(msg):
    """One JSON-RPC message in, one response dict out, or None for a notification."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return _rpc_error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")

    method = msg["method"]
    rpc_id = msg.get("id")
    params = msg.get("params") or {}

    if "id" not in msg:
        return None  # notification (notifications/initialized, notifications/cancelled, ...)

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        if name not in _DISPATCH:
            return _rpc_error(rpc_id, -32602, f"Unknown tool: {name}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _rpc_error(rpc_id, -32602, "arguments must be an object")
        text = _run_tool(name, arguments)
        try:
            is_error = json.loads(text).get("outcome") == "error"
        except ValueError:
            is_error = False
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        }}
    if method in ("resources/list", "prompts/list"):
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {method.split("/")[0]: []}}
    return _rpc_error(rpc_id, -32601, f"Method not found: {method}")


_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Mcp-Session-Id, Mcp-Protocol-Version, Accept",
}


def _resp(status, body=None, extra=None):
    headers = {"Content-Type": "application/json", **_CORS, **(extra or {})}
    return {"statusCode": status, "headers": headers,
            "body": "" if body is None else json.dumps(body)}


def lambda_handler(event, context):
    # Function URL and HTTP API (payload v2) share this shape; a REST API proxy
    # event carries httpMethod/path instead, so accept both.
    http = (event.get("requestContext") or {}).get("http") or {}
    method = (http.get("method") or event.get("httpMethod") or "").upper()
    path = (event.get("rawPath") or event.get("path") or "/").rstrip("/") or "/"

    if method == "OPTIONS":
        return _resp(204)

    if method == "GET" and path in ("/", "/health"):
        return _resp(200, {"status": "ok", "server": SERVER_NAME, "tools": len(TOOLS)})
    if method == "GET" and path == "/.well-known/mcp/server-card.json":
        return _resp(200, {"serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                           "tools": TOOLS, "resources": [], "prompts": []})

    if path.endswith("/mcp") or path == "/":
        if method != "POST":
            # No server-initiated stream is offered, which the spec allows.
            return _resp(405, {"error": "POST a JSON-RPC message to this endpoint."}, {"Allow": "POST, OPTIONS"})

        raw = event.get("body") or ""
        if event.get("isBase64Encoded"):
            try:
                raw = base64.b64decode(raw).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return _resp(400, _rpc_error(None, -32700, "Parse error"))
        try:
            payload = json.loads(raw)
        except ValueError:
            return _resp(400, _rpc_error(None, -32700, "Parse error"))

        if isinstance(payload, list):
            out = [r for r in (_handle_rpc(m) for m in payload) if r is not None]
            return _resp(200, out) if out else _resp(202)
        out = _handle_rpc(payload)
        return _resp(200, out) if out is not None else _resp(202)

    return _resp(404, {"error": "not found"})
