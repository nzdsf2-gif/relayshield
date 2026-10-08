"""OAuth flow protection for the MCP proxy firewall.

Catches the OAuth discovery-tampering attack class disclosed against
MCP SDKs in 2026: a malicious MCP server alters the OAuth discovery
flow so the victim's login still runs at the legitimate identity
provider while the resulting credentials are redirected to attacker
infrastructure.

Three checks:
  1. Endpoint validation: OAuth URLs must belong to a known identity
     provider's legitimate domains. An IdP-specific path on a foreign
     domain is tampering.
  2. Credential exfiltration context: helpers to decide whether a
     domain is trusted IdP infrastructure (used by the screener when
     OAuth credential material appears in tool results).
  3. New-domain caution: OAuth flows toward domains with no reputation
     history are flagged for review instead of trusted silently.
"""

import urllib.parse

# Known identity providers and their legitimate OAuth domains.
# Wildcard entries start with "*." and match any subdomain.
KNOWN_IDPS = {
    "google": ["accounts.google.com"],
    "github": ["github.com"],
    "microsoft": ["login.microsoftonline.com"],
    "auth0": ["*.auth0.com"],
    "okta": ["*.okta.com"],
    "apple": ["appleid.apple.com"],
}

# Path signatures characteristic of each IdP's OAuth flow. An OAuth
# URL whose path matches one of these on a foreign domain is
# masquerading as that IdP.
_IDP_PATH_SIGNATURES = {
    "google": ["/o/oauth2/"],
    "github": ["/login/oauth/"],
    "microsoft": ["/oauth2/v2.0/", "/common/oauth2/",
                  "/organizations/oauth2/"],
    "auth0": ["/oauth/token"],
    "okta": ["/oauth2/v1/"],,
    "apple": ["/auth/authorize"],
}

# Generic OAuth path markers. Any URL carrying one of these is
# treated as OAuth traffic.
_OAUTH_PATH_MARKERS = [
    "/oauth/",
    "/oauth2/",
    "/authorize",
    "/token",
    "/.well-known/openid-configuration",
    "/openid-connect/",
]

# Domain hints suggesting a first-party auth host (a company's own
# login service). OAuth traffic here is unknown but not obviously
# hostile: caution, not tampering.
_AUTH_HOST_HINTS = ("auth", "login", "sso", "oauth", "account",
                    "identity", "idp")


def _domain_matches(domain: str, pattern: str) -> bool:
    domain = (domain or "").lower()
    pattern = (pattern or "").lower()
    if pattern.startswith("*."):
        suffix = pattern[1:]  # ".auth0.com"
        return domain == pattern[2:] or domain.endswith(suffix)
    return domain == pattern


def is_known_idp_domain(domain: str) -> bool:
    """True when the domain is a legitimate IdP OAuth endpoint."""
    for domains in KNOWN_IDPS.values():
        for pattern in domains:
            if _domain_matches(domain, pattern):
                return True
    return False


def idp_for_domain(domain: str):
    """Name of the IdP owning this domain, or None."""
    for name, domains in KNOWN_IDPS.items():
        for pattern in domains:
            if _domain_matches(domain, pattern):
                return name
    return None


def host_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def path_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).path or "").lower()
    except Exception:
        return ""


def is_oauth_url(url: str) -> bool:
    """True when the URL path looks like OAuth traffic."""
    path = path_of(url)
    if not path:
        return False
    return any(marker in path for marker in _OAUTH_PATH_MARKERS)


def redacted_url(url: str) -> str:
    """URL with query and fragment stripped.

    Authorization codes, PKCE verifiers, and tokens travel in query
    strings; they must never appear in reasons or logs.
    """
    try:
        parts = urllib.parse.urlsplit(url)
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:
        return "(unparseable url)"


def check_oauth_url(url: str) -> dict:
    """Classify an OAuth URL.

    Returns {"status": "clean"|"tampered"|"unknown_domain",
             "idp": str|None, "domain": str, "reason": str}.

    - clean: the domain is a known IdP endpoint.
    - tampered: the path mimics a known IdP (or carries OAuth
      markers) on a foreign, unaffiliated domain. High severity.
    - unknown_domain: OAuth traffic toward a plausible first-party
      auth host with no reputation history. Medium severity caution.
    """
    domain = host_of(url)
    path = path_of(url)

    if is_known_idp_domain(domain):
        return {"status": "clean",
                "idp": idp_for_domain(domain),
                "domain": domain,
                "reason": "known identity provider endpoint"}

    # IdP-specific path signature on a foreign domain: masquerading.
    for idp, signatures in _IDP_PATH_SIGNATURES.items():
        for sig in signatures:
            if sig in path:
                return {"status": "tampered",
                        "idp": idp,
                        "domain": domain,
                        "reason": f"OAuth path mimics {idp} on foreign "
                                  f"domain {domain or '(unparseable)'}"}

    # Generic OAuth markers on a foreign domain.
    if any(marker in path for marker in _OAUTH_PATH_MARKERS):
        if any(hint in domain for hint in _AUTH_HOST_HINTS):
            return {"status": "unknown_domain",
                    "idp": None,
                    "domain": domain,
                    "reason": f"OAuth flow toward unaffiliated auth host "
                              f"{domain or '(unparseable)'}; no reputation"}
        return {"status": "tampered",
                "idp": None,
                "domain": domain,
                "reason": f"OAuth flow on unaffiliated domain "
                          f"{domain or '(unparseable)'}"}

    return {"status": "clean", "idp": None, "domain": domain,
            "reason": "not an OAuth URL"}
