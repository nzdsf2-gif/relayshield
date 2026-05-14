"""
RelayShield B2A API Lambda

Exposes RelayShield security intelligence as REST endpoints for
Business-to-Agent (B2A) and third-party developer consumption.

Subscription endpoints (API key required — enforced by API Gateway usage plan):
  POST /v1/breach                   — HIBP email breach check
  POST /v1/scan-url                 — VirusTotal URL malware analysis
  POST /v1/scan-file                — VirusTotal binary/file analysis
  POST /v1/scan-wallet              — GoPlus EVM wallet risk scan (legacy)
  POST /v1/wallet-risk              — Multi-chain wallet risk: EVM/Solana/TON (auto-detect)
  POST /v1/token-security           — GoPlus token risk: honeypot, tax, ownership flags
  POST /v1/nft-security             — GoPlus NFT contract risk scan
  POST /v1/sim-swap                 — Twilio Lookup v2 SIM/eSIM swap detection
  POST /v1/domain                   — Typosquat/lookalike domain scan (DNS + CT + GSB)
  GET  /v1/result/{analysis_id}     — Poll VT scan result

Pay-as-you-go endpoints (no API key — x402 payment verified in Lambda):
  POST /v1/payg/breach              — $0.10 USDC
  POST /v1/payg/sim-swap            — $0.25 USDC
  POST /v1/payg/domain              — $0.50 USDC
  POST /v1/payg/oauth-watchlist     — $0.15 USDC
  POST /v1/payg/scan-wallet         — $0.10 USDC (legacy EVM-only)
  POST /v1/payg/scan-url            — $0.05 USDC
  POST /v1/payg/scan-file           — $0.10 USDC
  POST /v1/payg/wallet-risk         — $0.15 USDC — multi-chain EVM/Solana/TON
  POST /v1/payg/token-security      — $0.10 USDC — token honeypot + tax analysis
  POST /v1/payg/nft-security        — $0.10 USDC — NFT contract risk
  POST /v1/payg/wallet-screen-batch — $0.50 USDC — batch up to 10 addresses
  GET  /v1/payg/result/{id}         — $0.00 (free — poll a paid scan)

x402 payment flow:
  1. Call PAYG endpoint with no X-PAYMENT header → receive 402 + PAYMENT-REQUIRED header
  2. Pay USDC on Base to the address in PAYMENT-REQUIRED
  3. Retry with X-PAYMENT header containing payment proof
  4. Lambda verifies proof via Coinbase x402 facilitator → executes and returns result

Authentication: Subscription routes — API key enforced by API Gateway usage plan.
               PAYG routes — no API key; x402 payment verified inside this Lambda.

Environment variables (set on Lambda):
  RELAYSHIELD_X402_WALLET — Coinbase Exchange USDC deposit address (x402 payTo)

Secrets used (all in Secrets Manager):
  relayshield/hibp_api_key
  relayshield/virustotal_api_key
  relayshield/twilio_account_sid / twilio_auth_token
  relayshield/google_safe_browsing
"""

import base64
import concurrent.futures
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import boto3

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

secrets_client = boto3.client("secretsmanager")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# x402 PAYG configuration
X402_PAYTO_ADDRESS   = os.environ.get("RELAYSHIELD_X402_WALLET", "")
X402_FACILITATOR_URL = "https://x402.org/facilitator/verify"
USDC_BASE_ADDRESS    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base
BASE_CHAIN_ID        = "eip155:8453"

# PAYG pricing in USDC base units (6 decimals): $0.10 = 100000
PAYG_PRICE_UNITS: dict[str, int] = {
    "/v1/payg/breach":                100000,
    "/v1/payg/sim-swap":              250000,
    "/v1/payg/domain":                500000,
    "/v1/payg/oauth-watchlist":       150000,
    "/v1/payg/scan-wallet":           100000,   # legacy — EVM only
    "/v1/payg/scan-url":               50000,
    "/v1/payg/scan-file":             100000,
    # Crypto Shield intelligence endpoints
    "/v1/payg/wallet-risk":           150000,   # $0.15 — multi-chain EVM/Solana/TON
    "/v1/payg/token-security":        100000,   # $0.10 — GoPlus token risk
    "/v1/payg/nft-security":          100000,   # $0.10 — GoPlus NFT risk
    "/v1/payg/wallet-screen-batch":   500000,   # $0.50 — up to 10 addresses
}

GOPLUS_BASE_URL        = "https://api.gopluslabs.io/api/v1/address_security"
GOPLUS_TOKEN_URL       = "https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
GOPLUS_NFT_URL         = "https://api.gopluslabs.io/api/v1/nft_security"
TONAPI_ACCOUNTS_URL    = "https://tonapi.io/v2/accounts/{address}"

# OAuth supply chain watchlist — high-risk OAuth-capable SaaS apps
OAUTH_WATCHLIST = {
    "slack", "notion", "github", "zapier", "linear", "vercel", "loom",
    "hubspot", "okta", "salesforce", "dropbox", "box", "atlassian", "jira",
    "confluence", "asana", "monday", "clickup", "figma", "miro",
    "zoom", "webex", "intercom", "zendesk", "freshdesk",
    "openai", "anthropic", "canva", "jasper", "grammarly", "copy.ai",
}

OAUTH_REVOCATION_URLS: dict[str, str] = {
    "GitHub":     "https://github.com/settings/applications",
    "Slack":      "https://slack.com/apps/manage",
    "Notion":     "https://www.notion.so/my-integrations",
    "Vercel":     "https://vercel.com/account/tokens",
    "Zapier":     "https://zapier.com/app/connections",
    "Linear":     "https://linear.app/settings/api",
    "HubSpot":    "https://app.hubspot.com/integrations-settings",
    "Dropbox":    "https://www.dropbox.com/account/connected_apps",
    "Atlassian":  "https://id.atlassian.com/manage-profile/apps",
    "Salesforce": "https://help.salesforce.com/s/articleView?id=sf.remoteaccess_revoke_token.htm",
}

HIBP_SECRET_NAME  = "relayshield/hibp_api_key"
VT_SECRET_NAME    = "relayshield/virustotal_api_key"
TWILIO_SID_SECRET = "relayshield/twilio_account_sid"
TWILIO_TOK_SECRET = "relayshield/twilio_auth_token"
GSB_SECRET_NAME   = "relayshield/google_safe_browsing"

HIBP_BASE_URL     = "https://haveibeenpwned.com/api/v3/breachedaccount/"
VT_BASE_URL       = "https://www.virustotal.com/api/v3"
TWILIO_LOOKUP_URL = "https://lookups.twilio.com/v2/PhoneNumbers/{phone}"
GSB_URL           = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
CRT_SH_URL        = "https://crt.sh/?q={domain}&output=json"

VT_POLL_INTERVAL  = 3    # seconds between VT status polls
VT_URL_MAX_WAIT   = 30   # max seconds for URL analysis
VT_FILE_MAX_WAIT  = 45   # max seconds for file analysis

# Typosquat generation config (mirrors domain_monitor)
COMMON_TLDS = [
    ".com", ".net", ".org", ".co", ".io", ".biz",
    ".info", ".us", ".co.uk", ".ca", ".com.au",
]
PHISHING_PREFIXES = ["secure-", "login-", "my-", "get-", "support-", "help-"]
PHISHING_SUFFIXES = ["-secure", "-login", "-online", "-support", "-portal", "-verify"]

# ---------------------------------------------------------------------------
# Secrets helpers
# ---------------------------------------------------------------------------

_secret_cache: dict[str, str] = {}


def _get_secret(secret_name: str) -> str:
    if secret_name not in _secret_cache:
        raw = secrets_client.get_secret_value(SecretId=secret_name)["SecretString"].strip()
        _secret_cache[secret_name] = raw
    return _secret_cache[secret_name]


def _get_secret_json(secret_name: str, key: str) -> str:
    raw = _get_secret(secret_name)
    try:
        return json.loads(raw)[key]
    except (json.JSONDecodeError, KeyError):
        return raw


def _hibp_api_key() -> str:
    return _get_secret_json(HIBP_SECRET_NAME, "HIBP_API_KEY")


def _vt_api_key() -> str:
    return _get_secret_json(VT_SECRET_NAME, "virustotal_api_key")


def _twilio_creds() -> tuple[str, str]:
    sid   = _get_secret_json(TWILIO_SID_SECRET, "TWILIO_ACCOUNT_SID")
    token = _get_secret_json(TWILIO_TOK_SECRET, "TWILIO_AUTH_TOKEN")
    return sid, token


def _gsb_api_key() -> str:
    raw = _get_secret(GSB_SECRET_NAME)
    try:
        return json.loads(raw)["google_safe_browsing_api_key"]
    except (json.JSONDecodeError, KeyError):
        return raw


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _ok(data: dict, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": True, "data": data}),
    }


def _err(message: str, status: int = 400) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": False, "error": message}),
    }


def _body(event: dict) -> dict:
    try:
        raw = event.get("body") or "{}"
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/breach
# ---------------------------------------------------------------------------
# Request:  { "email": "user@example.com" }
# Response: { "email": "...", "breach_count": N, "breaches": [...] }
#
# Breaches list contains summarised HIBP objects: Name, Domain, BreachDate,
# DataClasses. Full HIBP schema preserved so callers can apply their own
# filtering logic.

def handle_breach(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    api_key = _hibp_api_key()
    url     = f"{HIBP_BASE_URL}{urllib.parse.quote(email)}?truncateResponse=false"
    req     = urllib.request.Request(
        url,
        headers={"hibp-api-key": api_key, "user-agent": "RelayShield-API"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            breaches = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            breaches = []
        elif exc.code == 429:
            return _err("HIBP rate limit reached — retry in a few seconds", 429)
        else:
            logger.error("HIBP HTTP %d for %s", exc.code, email)
            return _err(f"HIBP returned HTTP {exc.code}", 502)
    except Exception as exc:
        logger.exception("HIBP call failed for %s: %s", email, exc)
        return _err("breach check failed — upstream error", 502)

    summary = [
        {
            "name":         b.get("Name"),
            "domain":       b.get("Domain"),
            "breach_date":  b.get("BreachDate"),
            "data_classes": b.get("DataClasses", []),
            "is_verified":  b.get("IsVerified", False),
        }
        for b in breaches
    ]

    logger.info("breach check — email=%s count=%d", email, len(summary))
    return _ok({
        "email":        email,
        "breach_count": len(summary),
        "breaches":     summary,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/scan-url
# ---------------------------------------------------------------------------
# Request:  { "url": "https://example.com/path" }
# Response: { "status": "pending", "analysis_id": "...", "poll_endpoint": "/v1/result/{id}" }
#
# Submits to VirusTotal and returns immediately with an analysis_id.
# Caller polls GET /v1/result/{analysis_id} for the verdict.

def handle_scan_url(params: dict) -> dict:
    url = (params.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return _err("url is required and must start with http:// or https://")

    api_key = _vt_api_key()
    payload = urllib.parse.urlencode({"url": url}).encode("utf-8")
    req = urllib.request.Request(
        f"{VT_BASE_URL}/urls",
        data=payload,
        headers={
            "x-apikey": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            analysis_id = json.loads(resp.read()).get("data", {}).get("id")
    except Exception as exc:
        logger.error("VT URL submit failed for %s: %s", url, exc)
        return _err("URL submission to VirusTotal failed", 502)

    if not analysis_id:
        return _err("VirusTotal did not return an analysis ID", 502)

    logger.info("scan-url submitted — url=%s analysis_id=%s", url, analysis_id)
    return _ok({
        "status":        "pending",
        "target":        url,
        "analysis_id":   analysis_id,
        "poll_endpoint": f"/v1/result/{analysis_id}",
        "note":          "Poll /v1/result/{analysis_id} every 5s until status is completed",
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/scan-file
# ---------------------------------------------------------------------------
# Request:  { "file_url": "https://cdn.example.com/report.pdf",
#             "filename": "report.pdf" }          ← filename optional
# Response: same shape as /v1/scan-url
#
# RelayShield downloads the file from file_url, then submits the bytes to
# VirusTotal /files. The caller never needs to forward raw bytes — only a URL.

def handle_scan_file(params: dict) -> dict:
    file_url = (params.get("file_url") or "").strip()
    filename = (params.get("filename") or file_url.split("/")[-1] or "upload").strip()

    if not file_url.startswith(("http://", "https://")):
        return _err("file_url is required and must start with http:// or https://")

    # Download the file
    try:
        req = urllib.request.Request(file_url, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            file_bytes   = resp.read()
            content_type = resp.headers.get_content_type() or "application/octet-stream"
    except Exception as exc:
        logger.error("File download failed for %s: %s", file_url, exc)
        return _err(f"could not download file from file_url: {exc}", 400)

    if not file_bytes:
        return _err("downloaded file was empty", 400)

    api_key  = _vt_api_key()
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{VT_BASE_URL}/files",
        data=body,
        headers={
            "x-apikey": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            analysis_id = json.loads(resp.read()).get("data", {}).get("id")
    except Exception as exc:
        logger.error("VT file submit failed: %s", exc)
        return _err("file submission to VirusTotal failed", 502)

    if not analysis_id:
        return _err("VirusTotal did not return an analysis ID", 502)

    logger.info("scan-file submitted — file_url=%s analysis_id=%s", file_url, analysis_id)
    return _ok({
        "status":        "pending",
        "target":        file_url,
        "filename":      filename,
        "analysis_id":   analysis_id,
        "poll_endpoint": f"/v1/result/{analysis_id}",
        "note":          "Poll /v1/result/{analysis_id} every 5s until status is completed",
    })


def _poll_vt(analysis_id: str, api_key: str, max_wait: int) -> dict | None:
    """Poll VT analyses/{id} until completed or timeout. Returns stats dict or None."""
    req = urllib.request.Request(
        f"{VT_BASE_URL}/analyses/{analysis_id}",
        headers={"x-apikey": api_key},
        method="GET",
    )
    waited = 0
    while waited <= max_wait:
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data  = json.loads(resp.read())
                attrs = data.get("data", {}).get("attributes", {})
                if attrs.get("status") == "completed":
                    return attrs.get("stats", {})
        except Exception as exc:
            logger.error("VT poll error %s: %s", analysis_id, exc)
            return None
        time.sleep(VT_POLL_INTERVAL)
        waited += VT_POLL_INTERVAL
    logger.warning("VT analysis %s timed out after %ds", analysis_id, max_wait)
    return None


def _vt_response(target: str, analysis_id: str, stats: dict | None) -> dict:
    if stats is None:
        return _ok({
            "target":       target,
            "analysis_id":  analysis_id,
            "verdict":      "timeout",
            "note":         "analysis did not complete in time — treat as unverified",
        })
    malicious  = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless   = stats.get("harmless", 0)
    undetected = stats.get("undetected", 0)
    total      = malicious + suspicious + harmless + undetected
    if malicious > 0:
        verdict = "malicious"
    elif suspicious > 0:
        verdict = "suspicious"
    else:
        verdict = "clean"
    logger.info("VT result — target=%s verdict=%s malicious=%d/%d",
                target, verdict, malicious, total)
    return _ok({
        "target":         target,
        "analysis_id":    analysis_id,
        "verdict":        verdict,
        "malicious":      malicious,
        "suspicious":     suspicious,
        "harmless":       harmless,
        "undetected":     undetected,
        "total_engines":  total,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/sim-swap
# ---------------------------------------------------------------------------
# Request:  { "phone": "+14155551234" }
# Response: { "phone": "...", "swapped": bool, "swap_timestamp": "...",
#             "carrier": "...", "checked_at": "..." }

def handle_sim_swap(params: dict) -> dict:
    phone = (params.get("phone") or "").strip()
    if not phone.startswith("+"):
        return _err("phone is required in E.164 format (e.g. +14155551234)")

    account_sid, auth_token = _twilio_creds()
    encoded     = urllib.parse.quote(phone, safe="")
    url         = TWILIO_LOOKUP_URL.format(phone=encoded) + "?Fields=sim_swap"
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {credentials}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body         = json.loads(resp.read())
            sim_swap_obj = body.get("sim_swap") or {}
            last_swap    = sim_swap_obj.get("last_sim_swap") or {}
            result = {
                "phone":          phone,
                "swapped":        bool(last_swap.get("swapped_in_period", False)),
                "swap_timestamp": last_swap.get("last_sim_swap_date", ""),
                "carrier":        sim_swap_obj.get("carrier_name", ""),
                "checked_at":     datetime.now(timezone.utc).isoformat(),
            }
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio Lookup HTTP %d for %s: %s", exc.code, phone, error_body)
        return _err(f"Twilio returned HTTP {exc.code}", 502)
    except Exception as exc:
        logger.exception("Twilio Lookup failed for %s: %s", phone, exc)
        return _err("SIM swap check failed — upstream error", 502)

    logger.info("sim-swap check — phone=%s swapped=%s carrier=%s",
                phone, result["swapped"], result["carrier"] or "unknown")
    return _ok(result)


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/domain
# ---------------------------------------------------------------------------
# Request:  { "domain": "acme.com" }
# Response: { "domain": "...", "lookalikes_found": N,
#             "lookalikes": [{ "domain": "...", "gsb_flagged": bool,
#                              "cert_count": N, "cert_recent": bool,
#                              "latest_cert_issued": "..." }],
#             "candidates_checked": N, "checked_at": "..." }

def handle_domain(params: dict) -> dict:
    domain = (params.get("domain") or "").strip().lower()
    if not domain or "." not in domain:
        return _err("domain is required (e.g. acme.com)")
    # Strip scheme if someone passes a full URL
    for prefix in ("https://", "http://", "www."):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]

    candidates  = _generate_typosquat_permutations(domain)
    prioritised = _prioritise_candidates(domain, candidates)
    active      = _find_active_lookalikes(prioritised)

    lookalikes = [{"domain": d} for d in active]

    logger.info("domain scan — domain=%s candidates=%d active=%d",
                domain, len(prioritised), len(active))
    return _ok({
        "domain":             domain,
        "lookalikes_found":   len(active),
        "lookalikes":         lookalikes,
        "candidates_checked": len(prioritised),
        "checked_at":         datetime.now(timezone.utc).isoformat(),
    })


def _generate_typosquat_permutations(domain: str) -> set[str]:
    if "." not in domain:
        return set()
    dot_pos = domain.rfind(".")
    name    = domain[:dot_pos]
    tld     = domain[dot_pos:]
    perms: set[str] = set()

    for i in range(len(name)):
        candidate = name[:i] + name[i + 1:]
        if candidate:
            perms.add(candidate + tld)
    for i, c in enumerate(name):
        perms.add(name[:i] + c + c + name[i + 1:] + tld)
    for i in range(len(name) - 1):
        t = list(name)
        t[i], t[i + 1] = t[i + 1], t[i]
        perms.add("".join(t) + tld)
    for i, c in enumerate(name):
        if c == "o":
            perms.add(name[:i] + "0" + name[i + 1:] + tld)
        elif c == "0":
            perms.add(name[:i] + "o" + name[i + 1:] + tld)
        elif c == "l":
            perms.add(name[:i] + "1" + name[i + 1:] + tld)
            perms.add(name[:i] + "i" + name[i + 1:] + tld)
        elif c == "i":
            perms.add(name[:i] + "1" + name[i + 1:] + tld)
            perms.add(name[:i] + "l" + name[i + 1:] + tld)
        elif c == "1":
            perms.add(name[:i] + "l" + name[i + 1:] + tld)
            perms.add(name[:i] + "i" + name[i + 1:] + tld)
    for i in range(1, len(name)):
        perms.add(name[:i] + "-" + name[i:] + tld)
    if "-" in name:
        perms.add(name.replace("-", "") + tld)
    for alt_tld in COMMON_TLDS:
        if alt_tld != tld:
            perms.add(name + alt_tld)
    for prefix in PHISHING_PREFIXES:
        perms.add(prefix + name + tld)
    for suffix in PHISHING_SUFFIXES:
        perms.add(name + suffix + tld)
    perms.add("www" + domain)
    perms.discard(domain)
    return {p for p in perms if p and len(p) > 2}


def _prioritise_candidates(domain: str, candidates: set[str]) -> list[str]:
    """Return up to 60 candidates, highest-risk first."""
    dot_pos = domain.rfind(".")
    name    = domain[:dot_pos]
    tld     = domain[dot_pos:]
    high, med, low = [], [], []
    for c in candidates:
        if any(c == name + alt for alt in COMMON_TLDS if alt != tld):
            high.append(c)  # TLD swap — most commonly registered by attackers
        elif any(c.startswith(p + name) or c.endswith(name + s)
                 for p in PHISHING_PREFIXES for s in PHISHING_SUFFIXES):
            med.append(c)   # phishing prefix/suffix
        else:
            low.append(c)   # char-level typos
    combined = high + med + low
    return combined[:30]


def _dns_resolves(domain: str, timeout: float = 1.0) -> bool:
    old = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname(domain)
        return True
    except (socket.gaierror, OSError):
        return False
    finally:
        socket.setdefaulttimeout(old)


def _find_active_lookalikes(candidates: list[str], max_workers: int = 50,
                             overall_timeout: float = 12.0) -> list[str]:
    active = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_dns_resolves, d): d for d in candidates}
        done, _ = concurrent.futures.wait(futures, timeout=overall_timeout)
        for fut in done:
            if fut.result():
                active.append(futures[fut])
    return sorted(active)


def _check_gsb(domain: str, api_key: str) -> bool:
    urls    = [f"http://{domain}/", f"https://{domain}/"]
    payload = json.dumps({
        "client": {"clientId": "relayshield", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes":      ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
            "platformTypes":    ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries":    [{"url": u} for u in urls],
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{GSB_URL}?key={api_key}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return bool(json.loads(resp.read()).get("matches"))
    except Exception as exc:
        logger.warning("GSB check failed for %s: %s", domain, exc)
        return False


def _check_ct(domain: str) -> dict:
    url = CRT_SH_URL.format(domain=urllib.parse.quote(domain))
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            certs = json.loads(resp.read())
        if not certs:
            return {"cert_count": 0, "recent": False, "latest_issued": None}
        now   = datetime.now(timezone.utc)
        dates = []
        for cert in certs:
            raw = cert.get("not_before") or cert.get("entry_timestamp", "")
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00").split(".")[0])
                    if not dt.tzinfo:
                        dt = dt.replace(tzinfo=timezone.utc)
                    dates.append(dt)
                except Exception:
                    pass
        if not dates:
            return {"cert_count": len(certs), "recent": False, "latest_issued": None}
        latest   = max(dates)
        days_old = (now - latest).days
        return {
            "cert_count":    len(certs),
            "recent":        days_old <= 30,
            "latest_issued": latest.strftime("%-d %b %Y"),
        }
    except Exception as exc:
        logger.warning("CT check failed for %s: %s", domain, exc)
        return {"cert_count": 0, "recent": False, "latest_issued": None}


# ---------------------------------------------------------------------------
# Endpoint: GET /v1/result/{analysis_id}
# ---------------------------------------------------------------------------
# Polls VirusTotal for the result of a previously submitted scan-url or scan-file.
# Returns verdict once completed, or {"status":"pending"} if still processing.

def handle_result(analysis_id: str) -> dict:
    if not analysis_id:
        return _err("analysis_id is required")
    api_key = _vt_api_key()
    req = urllib.request.Request(
        f"{VT_BASE_URL}/analyses/{analysis_id}",
        headers={"x-apikey": api_key},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data  = json.loads(resp.read())
            attrs = data.get("data", {}).get("attributes", {})
            status = attrs.get("status")
            if status != "completed":
                return _ok({"status": "pending", "analysis_id": analysis_id})
            stats = attrs.get("stats", {})
            return _vt_response(analysis_id, analysis_id, stats)
    except Exception as exc:
        logger.error("VT result poll failed for %s: %s", analysis_id, exc)
        return _err("could not retrieve analysis result", 502)


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/payg/oauth-watchlist  (also callable from subscription path)
# ---------------------------------------------------------------------------
# Request:  { "email": "user@example.com" }
# Response: { "email": "...", "matched_count": N, "matched_apps": [...],
#             "recommendation": "...", "checked_at": "..." }
#
# Checks HIBP breaches for the email and cross-references against the
# OAuth watchlist. Matched apps may have issued tokens granting access
# to Google Workspace / M365 without touching the user's password.

def handle_oauth_watchlist(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    api_key = _hibp_api_key()
    url     = f"{HIBP_BASE_URL}{urllib.parse.quote(email)}?truncateResponse=false"
    req     = urllib.request.Request(
        url,
        headers={"hibp-api-key": api_key, "user-agent": "RelayShield-API"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            breaches = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            breaches = []
        elif exc.code == 429:
            return _err("HIBP rate limit reached — retry in a few seconds", 429)
        else:
            logger.error("HIBP HTTP %d for oauth-watchlist %s", exc.code, email)
            return _err(f"HIBP returned HTTP {exc.code}", 502)
    except Exception as exc:
        logger.exception("oauth-watchlist HIBP call failed for %s: %s", email, exc)
        return _err("oauth watchlist check failed — upstream error", 502)

    matched = []
    for b in breaches:
        name  = (b.get("Name")   or "").lower()
        domain = (b.get("Domain") or "").lower()
        title  = (b.get("Title")  or "").lower()
        for app in OAUTH_WATCHLIST:
            if app in name or app in domain or app in title:
                app_name = b.get("Name", "")
                matched.append({
                    "app":           app_name,
                    "breach_date":   b.get("BreachDate"),
                    "data_classes":  b.get("DataClasses", []),
                    "revoke_url":    OAUTH_REVOCATION_URLS.get(
                                         app_name, "https://myaccount.google.com/permissions"
                                     ),
                })
                break

    logger.info("oauth-watchlist — email=%s matched=%d total_breaches=%d",
                email, len(matched), len(breaches))
    return _ok({
        "email":         email,
        "matched_count": len(matched),
        "matched_apps":  matched,
        "recommendation": (
            "Revoke OAuth access for matched apps immediately using the revoke_url for each. "
            "Also audit all connected apps at myaccount.google.com/permissions and myapps.microsoft.com."
            if matched else
            "No breached OAuth-capable apps detected for this email."
        ),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Endpoint: POST /v1/scan-wallet  (subscription) / POST /v1/payg/scan-wallet (PAYG)
# ---------------------------------------------------------------------------
# Request:  { "address": "0x..." }
# Response: { "address": "...", "chain_id": "1", "risk_level": "LOW|MEDIUM|HIGH",
#             "risk_flags": [...], "raw": {...} }

def handle_scan_wallet(params: dict) -> dict:
    address = (params.get("address") or "").strip()
    if not address:
        return _err("address is required")
    if not re.match(r"^0x[0-9a-fA-F]{40}$", address):
        return _err("address must be a valid EVM address (0x + 40 hex chars)")

    chain_id = (params.get("chain_id") or "1").strip()

    try:
        url = f"{GOPLUS_BASE_URL}/{address}?chain_id={chain_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data     = json.loads(resp.read())
            raw      = data.get("result", {}).get(address.lower(), {})
    except Exception as exc:
        logger.error("GoPlus scan failed for %s: %s", address, exc)
        return _err("wallet scan failed — upstream error", 502)

    risk_flags = [k for k, v in raw.items() if v == "1"]
    risk_level = "HIGH" if len(risk_flags) >= 2 else "MEDIUM" if risk_flags else "LOW"

    logger.info("scan-wallet address=%s chain=%s risk=%s flags=%d", address, chain_id, risk_level, len(risk_flags))
    return _ok({
        "address":    address.lower(),
        "chain_id":   chain_id,
        "risk_level": risk_level,
        "risk_flags": risk_flags,
        "raw":        raw,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/token-security  (subscription) / POST /v1/payg/token-security (PAYG)
# ---------------------------------------------------------------------------
# Request:  { "contract_address": "0x...", "chain_id": "1" }
# Response: { "contract_address": "...", "chain_id": "...", "risk_level": "LOW|MEDIUM|HIGH",
#             "critical_flags": [...], "warning_flags": [...], "raw": {...} }
#
# Supports any GoPlus chain: 1=ETH, 56=BSC, 137=Polygon, 8453=Base, etc.

def handle_token_security(params: dict) -> dict:
    contract = (params.get("contract_address") or "").strip().lower()
    if not contract:
        return _err("contract_address is required")
    if not re.match(r"^0x[0-9a-fA-F]{40}$", contract):
        return _err("contract_address must be a valid EVM address (0x + 40 hex chars)")

    chain_id = str(params.get("chain_id") or "1").strip()

    try:
        url = GOPLUS_TOKEN_URL.format(chain_id=chain_id) + f"?contract_addresses={contract}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        raw = (data.get("result") or {}).get(contract, {})
    except Exception as exc:
        logger.error("GoPlus token security failed contract=%s: %s", contract, exc)
        return _err("token security check failed — upstream error", 502)

    _CRITICAL = {
        "is_honeypot":     "honeypot",
        "is_airdrop_scam": "airdrop scam",
        "fake_token":      "fake token",
    }
    _WARNINGS = {
        "transfer_pausable":       "transfers can be paused",
        "hidden_owner":            "hidden owner",
        "can_take_back_ownership": "owner can reclaim contract",
        "is_mintable":             "mintable supply",
        "external_call":           "external call risk",
    }

    critical_flags = [label for k, label in _CRITICAL.items() if str(raw.get(k, "0")) == "1"]
    warning_flags  = [label for k, label in _WARNINGS.items() if str(raw.get(k, "0")) == "1"]

    # Sell tax — critical if >=50%, warning if >=10%
    try:
        sell_tax = float(raw.get("sell_tax", 0))
        if sell_tax >= 0.5:
            critical_flags.append(f"sell tax {sell_tax*100:.0f}%")
        elif sell_tax >= 0.1:
            warning_flags.append(f"sell tax {sell_tax*100:.0f}%")
    except (TypeError, ValueError):
        pass

    risk_level = "HIGH" if critical_flags else "MEDIUM" if warning_flags else "LOW"

    logger.info("token-security contract=%s chain=%s risk=%s", contract, chain_id, risk_level)
    return _ok({
        "contract_address": contract,
        "chain_id":         chain_id,
        "risk_level":       risk_level,
        "critical_flags":   critical_flags,
        "warning_flags":    warning_flags,
        "token_name":       raw.get("token_name", ""),
        "token_symbol":     raw.get("token_symbol", ""),
        "holder_count":     raw.get("holder_count"),
        "raw":              raw,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/nft-security  (subscription) / POST /v1/payg/nft-security (PAYG)
# ---------------------------------------------------------------------------
# Request:  { "contract_address": "0x...", "chain_id": "1" }
# Response: { "contract_address": "...", "risk_level": "LOW|MEDIUM|HIGH",
#             "risk_flags": [...], "raw": {...} }

def handle_nft_security(params: dict) -> dict:
    contract = (params.get("contract_address") or "").strip().lower()
    if not contract:
        return _err("contract_address is required")
    if not re.match(r"^0x[0-9a-fA-F]{40}$", contract):
        return _err("contract_address must be a valid EVM address (0x + 40 hex chars)")

    chain_id = str(params.get("chain_id") or "1").strip()

    try:
        url = f"{GOPLUS_NFT_URL}?chain_id={chain_id}&contract_addresses={contract}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        raw = (data.get("result") or {}).get(contract, {})
    except Exception as exc:
        logger.error("GoPlus NFT security failed contract=%s: %s", contract, exc)
        return _err("NFT security check failed — upstream error", 502)

    _NFT_FLAGS = {
        "malicious_contract": "malicious contract",
        "privileged_burn":    "owner can burn tokens",
        "can_freeze_transfer": "transfers can be frozen",
        "transfer_without_approval": "transfer without approval",
        "fake_token":         "fake/counterfeit collection",
    }
    risk_flags = [label for k, label in _NFT_FLAGS.items() if str(raw.get(k, "0")) == "1"]
    risk_level = "HIGH" if len(risk_flags) >= 2 else "MEDIUM" if risk_flags else "LOW"

    logger.info("nft-security contract=%s chain=%s risk=%s", contract, chain_id, risk_level)
    return _ok({
        "contract_address": contract,
        "chain_id":         chain_id,
        "risk_level":       risk_level,
        "risk_flags":       risk_flags,
        "nft_name":         raw.get("nft_name", ""),
        "nft_symbol":       raw.get("nft_symbol", ""),
        "raw":              raw,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/wallet-risk  (subscription) / POST /v1/payg/wallet-risk (PAYG)
# ---------------------------------------------------------------------------
# Multi-chain wallet risk: EVM and Solana via GoPlus, TON via TONAPI v2.
# Chain is auto-detected from address format.
#
# Request:  { "address": "0x...|SolanaAddr|EQTonAddr" }
# Response: { "address": "...", "chain": "evm|solana|ton|bitcoin",
#             "risk_level": "LOW|MEDIUM|HIGH", "risk_flags": [...],
#             "metadata": {...} }

_GOPLUS_CHAIN_IDS = {"evm": 1, "solana": 101}

def _detect_chain_api(address: str) -> str:
    if re.match(r"^0x[0-9a-fA-F]{40}$", address):
        return "evm"
    if re.match(r"^[EUeu][Qq][A-Za-z0-9_\-]{46}$", address):
        return "ton"
    if re.match(r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{6,87}$", address):
        return "bitcoin"
    if re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", address):
        return "solana"
    return "unknown"


def handle_wallet_risk(params: dict) -> dict:
    address = (params.get("address") or "").strip()
    if not address:
        return _err("address is required")

    chain = _detect_chain_api(address)
    if chain == "unknown":
        return _err("unrecognised address format — supported: EVM (0x), Solana, TON (EQ.../UQ...), Bitcoin")
    if chain == "bitcoin":
        return _ok({
            "address":    address,
            "chain":      "bitcoin",
            "risk_level": "UNKNOWN",
            "risk_flags": [],
            "metadata":   {"note": "Bitcoin address risk screening not yet supported"},
        })

    risk_flags = []
    metadata   = {}

    if chain in ("evm", "solana"):
        goplus_chain_id = _GOPLUS_CHAIN_IDS[chain]
        try:
            url = f"{GOPLUS_BASE_URL}/{address}?chain_id={goplus_chain_id}"
            req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            raw = data.get("result", {})
            _MALICIOUS = {
                "phishing_activities":  "linked to phishing",
                "blacklist_doubt":      "security blacklisted",
                "darkweb_transactions": "dark web activity",
                "stealing_attack":      "stealing attacks",
                "cybercrime":           "cybercrime",
            }
            risk_flags = [label for k, label in _MALICIOUS.items() if raw.get(k) == "1"]
        except Exception as exc:
            logger.error("GoPlus wallet-risk failed address=%s: %s", address, exc)
            metadata["goplus_error"] = "upstream unavailable"

    elif chain == "ton":
        try:
            ton_url = TONAPI_ACCOUNTS_URL.format(
                address=urllib.parse.quote(address, safe="-_=")
            )
            req = urllib.request.Request(ton_url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                ton_data = json.loads(resp.read())
            if ton_data.get("is_scam"):
                risk_flags.append("flagged as scam in TON community database")
            metadata["contract_type"]  = ton_data.get("interfaces", [])
            metadata["account_status"] = ton_data.get("status", "")
        except Exception as exc:
            logger.error("TONAPI wallet-risk failed address=%s: %s", address, exc)
            metadata["tonapi_error"] = "upstream unavailable"

    risk_level = "HIGH" if len(risk_flags) >= 2 else "MEDIUM" if risk_flags else "LOW"
    logger.info("wallet-risk address=%s chain=%s risk=%s flags=%d", address, chain, risk_level, len(risk_flags))
    return _ok({
        "address":    address.lower() if chain == "evm" else address,
        "chain":      chain,
        "risk_level": risk_level,
        "risk_flags": risk_flags,
        "metadata":   metadata,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/payg/wallet-screen-batch  (PAYG only — $0.50 for up to 10)
# ---------------------------------------------------------------------------
# Screens up to 10 addresses in parallel. Mixed chains supported.
#
# Request:  { "addresses": ["0x...", "SolAddr", "EQTonAddr"] }
# Response: { "results": [ { "address": "...", "chain": "...",
#                             "risk_level": "...", "risk_flags": [...] }, ... ] }

def handle_wallet_screen_batch(params: dict) -> dict:
    addresses = params.get("addresses") or []
    if not isinstance(addresses, list) or not addresses:
        return _err("addresses must be a non-empty list")
    if len(addresses) > 10:
        return _err("maximum 10 addresses per batch request")
    addresses = [str(a).strip() for a in addresses if str(a).strip()]

    def _screen_one(addr: str) -> dict:
        result = handle_wallet_risk({"address": addr})
        body   = json.loads(result.get("body", "{}"))
        data   = body.get("data", {})
        return {
            "address":    data.get("address", addr),
            "chain":      data.get("chain", "unknown"),
            "risk_level": data.get("risk_level", "UNKNOWN"),
            "risk_flags": data.get("risk_flags", []),
            "error":      body.get("error") if not body.get("ok") else None,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_screen_one, addresses))

    high_count = sum(1 for r in results if r["risk_level"] == "HIGH")
    logger.info("wallet-screen-batch count=%d high_risk=%d", len(addresses), high_count)
    return _ok({
        "screened":   len(results),
        "high_risk":  high_count,
        "results":    results,
    })


# ---------------------------------------------------------------------------
# x402 PAYG — payment requirements, verification, 402 response
# ---------------------------------------------------------------------------

def _build_payment_requirements(path: str, price_units: int) -> dict:
    api_base = "https://xhh3tfrhng.execute-api.us-east-1.amazonaws.com/prod"
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme":             "exact",
            "network":            BASE_CHAIN_ID,
            "maxAmountRequired":  str(price_units),
            "resource":           f"{api_base}{path}",
            "description":        f"RelayShield {path.split('/')[-1].replace('-', ' ')} check",
            "mimeType":           "application/json",
            "payTo":              X402_PAYTO_ADDRESS,
            "maxTimeoutSeconds":  300,
            "asset":              USDC_BASE_ADDRESS,
            "extra":              {"name": "USDC", "version": "2"},
        }],
    }


def _x402_payment_required(path: str) -> dict:
    price_units  = PAYG_PRICE_UNITS.get(path, 250000)
    requirements = _build_payment_requirements(path, price_units)
    encoded      = base64.b64encode(json.dumps(requirements).encode()).decode()
    price_usd    = f"${price_units / 1_000_000:.2f}"
    return {
        "statusCode": 402,
        "headers": {
            "Content-Type":                "application/json",
            "PAYMENT-REQUIRED":            encoded,
            "Access-Control-Expose-Headers": "PAYMENT-REQUIRED",
        },
        "body": json.dumps({
            "ok":    False,
            "error": "Payment required",
            "price": f"{price_usd} USDC on Base",
            "x402":  requirements,
            "subscribe_url": "https://rapidapi.com/relayshield/relayshield-security-intelligence",
            "subscribe_note": f"Subscribe for 96%+ lower per-check cost vs {price_usd} PAYG rate.",
        }),
    }


def _verify_x402_payment(x_payment: str, path: str) -> bool:
    if not X402_PAYTO_ADDRESS:
        logger.error("RELAYSHIELD_X402_WALLET env var not set — cannot verify x402 payment")
        return False
    price_units  = PAYG_PRICE_UNITS.get(path, 0)
    requirements = _build_payment_requirements(path, price_units)
    payload      = json.dumps({
        "x402Version":  1,
        "payload":      x_payment,
        "requirements": requirements,
    }).encode("utf-8")
    req = urllib.request.Request(
        X402_FACILITATOR_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            valid  = result.get("isValid", False)
            if not valid:
                logger.warning("x402 payment invalid — reason: %s path=%s",
                               result.get("invalidReason"), path)
            return valid
    except Exception as exc:
        logger.error("x402 facilitator call failed for %s: %s", path, exc)
        return False


def handle_payg_request(path: str, method: str, event: dict) -> dict:
    headers   = event.get("headers") or {}
    x_payment = headers.get("X-PAYMENT") or headers.get("x-payment", "")

    # Free poll endpoint — no payment needed
    if method == "GET" and path.startswith("/v1/payg/result/"):
        analysis_id = path[len("/v1/payg/result/"):]
        return handle_result(analysis_id)

    if method != "POST":
        return _err(f"{path} only accepts POST requests", 405)

    # Require payment proof
    if not x_payment:
        return _x402_payment_required(path)

    if not _verify_x402_payment(x_payment, path):
        return {
            "statusCode": 402,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":    False,
                "error": "Invalid or expired payment proof — pay again and retry.",
            }),
        }

    payg_routes = {
        "/v1/payg/breach":                handle_breach,
        "/v1/payg/sim-swap":              handle_sim_swap,
        "/v1/payg/domain":                handle_domain,
        "/v1/payg/oauth-watchlist":       handle_oauth_watchlist,
        "/v1/payg/scan-wallet":           handle_scan_wallet,       # legacy EVM-only
        "/v1/payg/scan-url":              handle_scan_url,
        "/v1/payg/scan-file":             handle_scan_file,
        "/v1/payg/wallet-risk":           handle_wallet_risk,
        "/v1/payg/token-security":        handle_token_security,
        "/v1/payg/nft-security":          handle_nft_security,
        "/v1/payg/wallet-screen-batch":   handle_wallet_screen_batch,
    }
    handler = payg_routes.get(path)
    if not handler:
        return _err(f"unknown PAYG endpoint: {path}", 404)

    params = _body(event)
    try:
        return handler(params)
    except Exception as exc:
        logger.exception("Unhandled error in PAYG %s: %s", path, exc)
        return _err("internal server error", 500)


# ---------------------------------------------------------------------------
# Router / Lambda handler
# ---------------------------------------------------------------------------

ROUTES = {
    "/v1/breach":           handle_breach,
    "/v1/scan-url":         handle_scan_url,
    "/v1/scan-file":        handle_scan_file,
    "/v1/sim-swap":         handle_sim_swap,
    "/v1/domain":           handle_domain,
    "/v1/oauth-watchlist":  handle_oauth_watchlist,
    "/v1/scan-wallet":      handle_scan_wallet,       # legacy EVM-only
    "/v1/wallet-risk":      handle_wallet_risk,       # multi-chain EVM/Solana/TON
    "/v1/token-security":   handle_token_security,
    "/v1/nft-security":     handle_nft_security,
}

PAYG_PATHS = set(PAYG_PRICE_UNITS.keys()) | {"/v1/payg/result/"}


def lambda_handler(event: dict, context) -> dict:
    path   = event.get("path", "")
    method = event.get("httpMethod", "")

    logger.info("API request — method=%s path=%s", method, path)

    # Discovery
    if method == "GET" and path in ("/", "/v1", "/v1/"):
        return _ok({
            "service":  "RelayShield B2A API",
            "version":  "1.0",
            "subscription_endpoints": list(ROUTES.keys()) + ["GET /v1/result/{analysis_id}"],
            "payg_endpoints": list(PAYG_PRICE_UNITS.keys()) + ["GET /v1/payg/result/{analysis_id}"],
            "payg_note": "x402 payment required — USDC on Base. No API key needed.",
        })

    # PAYG routes (x402 payment verified inside Lambda)
    if path.startswith("/v1/payg/"):
        return handle_payg_request(path, method, event)

    # Subscription: GET /v1/result/{analysis_id}
    if method == "GET" and path.startswith("/v1/result/"):
        analysis_id = path[len("/v1/result/"):]
        return handle_result(analysis_id)

    # Subscription routes (API key enforced by API Gateway)
    handler = ROUTES.get(path)
    if not handler:
        return _err(f"unknown endpoint: {path}", 404)

    if method != "POST":
        return _err(f"{path} only accepts POST requests", 405)

    params = _body(event)
    try:
        return handler(params)
    except Exception as exc:
        logger.exception("Unhandled error in %s: %s", path, exc)
        return _err("internal server error", 500)
