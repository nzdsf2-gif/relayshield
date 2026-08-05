"""RelayShield security tools for smolagents.

Nine agent-specific security checks from RelayShield (https://api.relayshield.net/developers),
a live threat-intelligence API. Mirrors the tools shipped as the "RelayShield Agentic Attack
Surface" MCP server on Hugging Face Spaces
(https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface).

v2 (2026-07-19) — response to community feedback on the v1 release: added five new tools
(oauth_watchlist, supply_chain, session_risk, nhi_exposure, secret_scan — grouped as an
"agent authority / credential exposure" family alongside the original four), and switched
every tool from a human-formatted string to a typed structured result:

    {
      "outcome": "finding" | "no_known_finding" | "error",
      "recommended_action": "allow" | "review" | "deny" | "defer",
      "reason_codes": [...],
      "evidence": [...],
      "coverage": {"complete": bool, "scope": "what was actually checked"},
      "freshness": {"observed_at": "...", "expires_at": null},
      "error": {"kind": "...", "message": "...", "retryable": bool} | null
    }

"no_known_finding" deliberately does not mean "safe" — it means nothing was found in the
sources and scope actually queried. A caller using these as a pre-action gate should check
"error" before trusting "outcome", since a failed check is not the same as a clean one.

Setup:
    pip install smolagents requests

    No signup required to try these tools: if RELAYSHIELD_API_KEY isn't set, they
    fall back automatically to a shared, quota-capped demo key (20 calls/day,
    shared across everyone using the default — plenty to try a few tools, not
    enough for production use). Every result carries a "_demo_notice" field
    while the fallback is active, pointing at real signup.

    export RELAYSHIELD_API_KEY="your-key-here"   # optional — unlocks your own quota

Usage:
    from relayshield_smolagents_tool import RelayShieldSupplyChainTool

    tool = RelayShieldSupplyChainTool()
    result = tool.forward(vendor_domains=["vendor.example.com"])

Get a key at https://api.relayshield.net/developers?source=hf-smolagents ($499/mo for 10,000 calls,
or pay-per-call via x402 USDC with no key required for the equivalent /v1/payg/* routes).
"""

import os

import requests
from smolagents import Tool

API_BASE_URL: str = "https://api.relayshield.net"

# Shared, quota-capped (20 calls/day, all callers combined) fallback key — lets
# these tools work with zero signup. Deliberately a separate, low-privilege key
# from any server-side-only demo key elsewhere in RelayShield's stack: this one
# lives in a public pip package and public HF Space file, so it must be safe to
# have scraped and reused by anyone, hence the shared daily cap rather than an
# unlimited key. Get your own uncapped key at
# https://api.relayshield.net/developers?source=hf-smolagents
_DEMO_API_KEY = "rs_demo_729639c084f7a638"
_DEMO_NOTICE = (
    "This call used RelayShield's free shared demo key (20 calls/day, shared across "
    "everyone using the default — no signup required). Get your own key for reliable, "
    "unshared access: https://api.relayshield.net/developers?source=hf-smolagents"
)


def _relayshield_headers(api_key: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "X-RS-API-KEY": api_key}


def _get_api_key() -> str:
    return os.environ.get("RELAYSHIELD_API_KEY") or _DEMO_API_KEY


def _using_demo_key() -> bool:
    return not bool(os.environ.get("RELAYSHIELD_API_KEY"))


def _post(path: str, payload: dict) -> tuple[dict | None, dict | None]:
    """POSTs to a RelayShield metered endpoint. Returns (data, error).

    error is None on success, or a schema-shaped
    {"kind": ..., "message": ..., "retryable": bool} dict on failure — distinguishing
    auth/rate_limited/timeout/upstream/malformed_response/other so a caller using these
    tools as a policy gate can tell "the check failed" apart from "the check found nothing."
    """
    api_key = _get_api_key()

    try:
        resp = requests.post(
            f"{API_BASE_URL}{path}",
            json=payload,
            headers=_relayshield_headers(api_key),
            timeout=15,
        )
    except requests.Timeout:
        return None, {
            "kind": "timeout",
            "message": f"RelayShield API call to {path} timed out after 15s.",
            "retryable": True,
        }
    except requests.RequestException as exc:
        return None, {
            "kind": "upstream",
            "message": f"RelayShield API call to {path} failed: {exc}",
            "retryable": True,
        }

    if resp.status_code in (401, 403):
        return None, {
            "kind": "auth",
            "message": f"RelayShield API call to {path} returned {resp.status_code} — check RELAYSHIELD_API_KEY.",
            "retryable": False,
        }
    if resp.status_code == 429:
        message = f"RelayShield API call to {path} was rate-limited."
        if _using_demo_key():
            message += (
                " The shared demo key's daily quota (20 calls/day, shared across everyone "
                "using the default) is exhausted for today. Get your own key: "
                "https://api.relayshield.net/developers?source=hf-smolagents"
            )
        return None, {"kind": "rate_limited", "message": message, "retryable": True}
    if resp.status_code >= 500:
        return None, {
            "kind": "upstream",
            "message": f"RelayShield API call to {path} returned {resp.status_code}.",
            "retryable": True,
        }
    if resp.status_code >= 400:
        return None, {
            "kind": "other",
            "message": f"RelayShield API call to {path} returned {resp.status_code}: {resp.text[:200]}",
            "retryable": False,
        }

    try:
        response_json = resp.json()
    except ValueError:
        return None, {
            "kind": "malformed_response",
            "message": f"RelayShield API call to {path} returned non-JSON content.",
            "retryable": False,
        }

    # A valid-but-non-dict JSON body (list/string) is treated as malformed rather than
    # crashing on .get() — same class of bug CodeRabbit caught in the CrewAI PR's first
    # review pass on this project's earlier tools.
    if not isinstance(response_json, dict):
        return None, {
            "kind": "malformed_response",
            "message": f"RelayShield API call to {path} returned an unexpected response shape.",
            "retryable": False,
        }

    return response_json.get("data", {}), None


def _outcome_for_severity(highest_severity: str | None, found: bool = True) -> tuple[str, str]:
    """Maps a RelayShield severity string to (outcome, recommended_action).

    CRITICAL escalates to a deny recommendation; HIGH/MEDIUM/LOW are surfaced as findings
    for human/agent review rather than an automatic block, since these are enrichment
    signals, not a certified detection.
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
) -> dict:
    result = {
        "outcome": outcome,
        "recommended_action": recommended_action,
        "reason_codes": reason_codes or [],
        "evidence": evidence or [],
        "coverage": {"complete": coverage_complete, "scope": scope},
        "freshness": {"observed_at": observed_at, "expires_at": None},
        "error": None,
    }
    if _using_demo_key():
        result["_demo_notice"] = _DEMO_NOTICE
    return result


def _error_result(error: dict) -> dict:
    result = {
        "outcome": "error",
        "recommended_action": "defer",
        "reason_codes": [],
        "evidence": [],
        "coverage": {"complete": False, "scope": ""},
        "freshness": {"observed_at": None, "expires_at": None},
        "error": error,
    }
    if _using_demo_key():
        result["_demo_notice"] = _DEMO_NOTICE
    return result


class RelayShieldMCPRiskTool(Tool):
    """Typosquat / reputation / registration-age risk check for MCP servers
    and agent tool registries, backed by RelayShield's live threat-intel API."""

    name = "relayshield_mcp_registry_risk"
    description = (
        "Checks an MCP server URL or package name for typosquat risk against known MCP "
        "ecosystem domains, presence in RelayShield's criminal IOC corpus, and domain-"
        "registration age. Use this before connecting an agent to an unfamiliar MCP server "
        "or tool registry. Returns a structured result with outcome/recommended_action, "
        "not just a verdict string."
    )
    inputs = {
        "server_url": {
            "type": "string",
            "description": "Full URL of the MCP server to check, e.g. 'https://example.com/mcp'. Provide this or package_name.",
            "nullable": True,
        },
        "package_name": {
            "type": "string",
            "description": "Package name of the MCP server if no server_url is available. Checks are more limited without a server_url.",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(self, server_url: str | None = None, package_name: str | None = None) -> dict:
        if not server_url and not package_name:
            return _error_result({
                "kind": "other",
                "message": "Provide either server_url or package_name.",
                "retryable": False,
            })

        payload: dict[str, str] = {}
        if server_url:
            payload["server_url"] = server_url
        if package_name:
            payload["package_name"] = package_name

        data, error = _post("/v1/metered/mcp-registry-risk", payload)
        if error:
            return _error_result(error)

        findings = data.get("findings", [])
        outcome, action = _outcome_for_severity(data.get("verdict"), found=bool(findings))
        return _structured_result(
            outcome, action,
            reason_codes=[f.get("type", "unknown") for f in findings],
            evidence=findings,
            scope=f"Checked {data.get('queried', server_url or package_name)!r} against known-MCP-domain typosquat "
                  "distance, RelayShield's criminal IOC corpus, and RDAP registration age.",
        )


class RelayShieldPromptInjectionBreachTool(Tool):
    """Checks whether an email's credentials were exposed via a breach specifically
    sourced from a prompt-injection attack against an AI agent, as opposed to
    traditional phishing/malware-sourced breaches."""

    name = "relayshield_prompt_injection_breach"
    description = (
        "Checks an email address for credential exposure sourced specifically from "
        "prompt-injection attacks against AI agents (distinct from ordinary breach/phishing "
        "sources). Use this to vet an agent identity or user account before granting it "
        "elevated trust or access."
    )
    inputs = {
        "email": {
            "type": "string",
            "description": "Email address to check for credential exposure sourced from prompt-injection attacks against AI agents.",
        },
    }
    output_type = "object"

    def forward(self, email: str) -> dict:
        data, error = _post("/v1/metered/prompt-injection-breach", {"email": email})
        if error:
            return _error_result(error)

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


class RelayShieldTechStackCVETool(Tool):
    """Checks a declared technology stack (or a domain's stored stack) against
    actively-exploited CVEs and high-EPSS-score vulnerabilities."""

    name = "relayshield_tech_stack_cve"
    description = (
        "Checks a declared technology stack (e.g. nginx, WordPress, LangChain, CrewAI, n8n) "
        "against actively-exploited CVEs (CISA KEV) and high-EPSS-score vulnerabilities. Covers "
        "AI agent orchestration frameworks and their common companion infrastructure. Use this "
        "before deploying or continuing to run a given technology stack in production."
    )
    inputs = {
        "tech_stack": {
            "type": "array",
            "description": "List of declared technology product names, e.g. ['nginx', 'wordpress', 'cisco ios']. Provide this or domain.",
            "nullable": True,
        },
        "domain": {
            "type": "string",
            "description": "Alternative: pull the declared tech_stack from a domain's stored profile instead of listing it inline.",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(self, tech_stack: list[str] | None = None, domain: str | None = None) -> dict:
        if not tech_stack and not domain:
            return _error_result({
                "kind": "other",
                "message": "Provide either tech_stack or domain.",
                "retryable": False,
            })

        payload: dict = {}
        if tech_stack:
            payload["tech_stack"] = tech_stack
        if domain:
            payload["domain"] = domain

        data, error = _post("/v1/metered/tech-stack-cve", payload)
        if error:
            return _error_result(error)

        # v1 shipped tool read data["matched_cves"], a key the API has never returned —
        # the real keys are all_matches/critical_cves. Fixed here.
        matched = data.get("all_matches", [])
        critical = data.get("critical_cves", [])
        highest = "CRITICAL" if critical else ("HIGH" if matched else None)
        outcome, action = _outcome_for_severity(highest, found=bool(matched))
        return _structured_result(
            outcome, action,
            reason_codes=[c.get("cve_id", "unknown") for c in critical] if critical else [],
            evidence=matched,
            scope=f"Checked {data.get('tech_stack_queried', tech_stack or domain)} against CISA KEV and "
                  "high-EPSS-score CVEs.",
        )


class RelayShieldBulkIdentityRiskTool(Tool):
    """Scores up to 10 organizational domains, each with up to 5 associated agent/
    employee emails, for combined breach/infostealer/session/CVE risk in one call."""

    name = "relayshield_bulk_identity_risk"
    description = (
        "Scores up to 10 organizational domains, each with up to 5 associated agent or "
        "employee emails, for combined breach/infostealer/session/CVE risk in one call. Built "
        "for AI agent governance and identity-posture use cases — the entry point for scoring "
        "many identities per organization in one pass rather than N sequential calls."
    )
    inputs = {
        "targets": {
            "type": "array",
            "description": (
                "Up to 10 objects, each shaped like "
                "{'domain': 'acme.com', 'agents': ['ceo@acme.com']} — 'agents' is optional, up to 5 per domain."
            ),
        },
    }
    output_type = "object"

    def forward(self, targets: list[dict]) -> dict:
        data, error = _post("/v1/metered/bulk-identity-risk", {"targets": targets})
        if error:
            return _error_result(error)

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


class RelayShieldOAuthWatchlistTool(Tool):
    """Checks an email for OAuth-app exposure via breach history and active
    stealer-log corpus matches — connected SaaS apps and delegated access risk."""

    name = "relayshield_oauth_watchlist"
    description = (
        "Checks an email address for OAuth-connected-app exposure: apps matched against breach "
        "history, plus stolen OAuth/session tokens found in criminal stealer logs. Use this to "
        "assess risk inherited from an agent or user's connected SaaS applications and delegated "
        "access before trusting that identity's current authority."
    )
    inputs = {
        "email": {
            "type": "string",
            "description": "Email address to check for OAuth app exposure.",
        },
    }
    output_type = "object"

    def forward(self, email: str) -> dict:
        data, error = _post("/v1/metered/oauth-watchlist", {"email": email})
        if error:
            return _error_result(error)

        matched_apps = data.get("matched_apps", [])
        stolen_tokens = data.get("stolen_tokens", [])
        outcome, action = _outcome_for_severity(
            data.get("highest_severity"), found=bool(matched_apps or stolen_tokens)
        )
        return _structured_result(
            outcome, action,
            reason_codes=(["oauth_app_breach_match"] if matched_apps else [])
                         + (["stolen_oauth_token"] if stolen_tokens else []),
            evidence=matched_apps + stolen_tokens,
            scope=f"Checked {email} against HIBP breach history for OAuth-app matches and RelayShield's "
                  "stealer-log corpus for stolen session/OAuth tokens.",
            observed_at=data.get("checked_at"),
        )


class RelayShieldSupplyChainTool(Tool):
    """Checks up to 10 vendor domains for breach/infostealer exposure — third-party
    and supply-chain risk inherited through vendor relationships."""

    name = "relayshield_supply_chain"
    description = (
        "Checks up to 10 vendor domains (or vendor emails) for breach and infostealer exposure, "
        "returning a per-vendor risk level and an aggregate dark-web exposure score. Use this to "
        "vet third-party vendors, MCP server operators, or supply-chain dependencies before an "
        "agent integrates with or grants access to them."
    )
    inputs = {
        "vendor_domains": {
            "type": "array",
            "description": "Up to 10 vendor domains to check, e.g. ['vendor.example.com']. Provide this or vendor_emails.",
            "nullable": True,
        },
        "vendor_emails": {
            "type": "array",
            "description": "Alternative: vendor email addresses — the domain portion is extracted automatically.",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(self, vendor_domains: list[str] | None = None, vendor_emails: list[str] | None = None) -> dict:
        if not vendor_domains and not vendor_emails:
            return _error_result({
                "kind": "other",
                "message": "Provide either vendor_domains or vendor_emails.",
                "retryable": False,
            })

        payload: dict = {}
        if vendor_domains:
            payload["vendor_domains"] = vendor_domains
        if vendor_emails:
            payload["vendor_emails"] = vendor_emails

        data, error = _post("/v1/metered/supply-chain", payload)
        if error:
            return _error_result(error)

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


class RelayShieldSessionRiskTool(Tool):
    """Checks an email for active/reusable stolen session material found in
    RelayShield's stealer-log corpus — session hijack and AiTM (adversary-in-the-middle)
    exposure that can bypass normal authentication controls."""

    name = "relayshield_session_risk"
    description = (
        "Checks an email address for active or reusable stolen session material (cookies, "
        "tokens) found in criminal stealer logs — exposure that can bypass MFA/authentication "
        "entirely, not just a password. Use this to assess whether an agent or user identity "
        "currently has hijackable sessions in circulation."
    )
    inputs = {
        "email": {
            "type": "string",
            "description": "Email address to check for active session/AiTM exposure.",
        },
    }
    output_type = "object"

    def forward(self, email: str) -> dict:
        data, error = _post("/v1/metered/session-risk", {"email": email})
        if error:
            return _error_result(error)

        sessions = data.get("sessions", [])
        outcome, action = _outcome_for_severity(data.get("highest_severity"), found=data.get("found", False))
        return _structured_result(
            outcome, action,
            reason_codes=[s.get("service_category", "unknown") for s in sessions],
            evidence=sessions,
            scope=f"Checked {email} against RelayShield's stolen-session corpus for reusable session/cookie material.",
        )


class RelayShieldNHIExposureTool(Tool):
    """Checks a domain (or vendor domains) for exposed non-human-identity credentials —
    API keys, service-account tokens, PATs, and other machine credentials found in
    criminal stealer logs."""

    name = "relayshield_nhi_exposure"
    description = (
        "Checks a domain, or up to 10 vendor domains, for exposed non-human-identity (NHI) "
        "credentials — API keys, service-account tokens, personal access tokens, and other "
        "machine identities found in criminal stealer logs. Use this to assess exposure of the "
        "machine credentials an agent or its supply chain actually runs on, not just human logins."
    )
    inputs = {
        "domain": {
            "type": "string",
            "description": "Your own domain to check. Provide this or vendor_domains (or both).",
            "nullable": True,
        },
        "vendor_domains": {
            "type": "array",
            "description": "Up to 10 vendor/supply-chain domains to check.",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(self, domain: str | None = None, vendor_domains: list[str] | None = None) -> dict:
        if not domain and not vendor_domains:
            return _error_result({
                "kind": "other",
                "message": "Provide either domain or vendor_domains.",
                "retryable": False,
            })

        payload: dict = {}
        if domain:
            payload["domain"] = domain
        if vendor_domains:
            payload["vendor_domains"] = vendor_domains

        data, error = _post("/v1/metered/nhi-exposure", payload)
        if error:
            return _error_result(error)

        findings = data.get("findings", [])
        outcome, action = _outcome_for_severity(data.get("highest_severity"), found=data.get("found", False))
        return _structured_result(
            outcome, action,
            reason_codes=[f.get("type", "unknown") for f in findings],
            evidence=findings,
            scope=f"Checked {data.get('domains_checked', 0)} domain(s) against RelayShield's stealer-log "
                  "corpus for exposed non-human-identity credentials.",
            observed_at=data.get("checked_at"),
        )


class RelayShieldSecretScanTool(Tool):
    """Checks a domain (or vendor domains) for secrets/credentials exposed in
    public GitHub repositories."""

    name = "relayshield_secret_scan"
    description = (
        "Checks a domain, or up to 5 vendor domains, for secrets and credentials exposed in "
        "public GitHub repositories. Use this to assess whether an agent's own domain, or "
        "a vendor/supply-chain dependency's domain, has leaked credentials sitting in indexed "
        "public source code."
    )
    inputs = {
        "domain": {
            "type": "string",
            "description": "Your own domain to check. Provide this or vendor_domains (or both).",
            "nullable": True,
        },
        "vendor_domains": {
            "type": "array",
            "description": "Up to 5 vendor domains to check.",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(self, domain: str | None = None, vendor_domains: list[str] | None = None) -> dict:
        if not domain and not vendor_domains:
            return _error_result({
                "kind": "other",
                "message": "Provide either domain or vendor_domains.",
                "retryable": False,
            })

        payload: dict = {}
        if domain:
            payload["domain"] = domain
        if vendor_domains:
            payload["vendor_domains"] = vendor_domains

        data, error = _post("/v1/metered/secret-scan", payload)
        if error:
            return _error_result(error)

        findings = data.get("findings", [])
        outcome, action = _outcome_for_severity(data.get("highest_severity"), found=data.get("found", False))
        return _structured_result(
            outcome, action,
            reason_codes=[f.get("severity", "unknown") for f in findings],
            evidence=findings,
            scope=f"Checked {data.get('domains_checked', 0)} domain(s) against public GitHub "
                  "repositories for exposed secrets.",
            observed_at=data.get("checked_at"),
        )
