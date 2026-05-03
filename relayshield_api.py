"""
RelayShield B2A API Lambda

Exposes RelayShield security intelligence as REST endpoints for
Business-to-Agent (B2A) and third-party developer consumption.

Endpoints (all POST, JSON body, Lambda proxy integration):
  POST /v1/breach       — HIBP email breach check
  POST /v1/scan-url     — VirusTotal URL malware analysis
  POST /v1/scan-file    — VirusTotal binary/file analysis (download from URL + submit)
  POST /v1/sim-swap     — Twilio Lookup v2 SIM/eSIM swap detection
  POST /v1/domain       — Typosquat/lookalike domain scan (DNS + CT + GSB)

Authentication: API key via x-api-key header — enforced by API Gateway usage plan,
NOT inside this Lambda. Lambda trusts all requests that reach it.

Request/Response format:
  All requests: Content-Type: application/json
  All responses: { "ok": bool, "data": {...}, "error": "..." }
  HTTP status: 200 (success), 400 (bad request), 500 (backend failure)

Deployment:
  Lambda name:   relayshield-api
  Handler:       relayshield_api.lambda_handler
  Runtime:       Python 3.12
  Timeout:       60 seconds (VT polling can take up to 45s)
  Memory:        256 MB
  Trigger:       API Gateway REST API (Lambda proxy integration)
  IAM requires:
    Secrets Manager GetSecretValue for all relayshield/* secrets
    No DynamoDB access required — this Lambda is stateless

Secrets used (all already exist in Secrets Manager):
  relayshield/hibp_api_key              — HIBP v3 API key
  relayshield/virustotal_api_key        — VirusTotal API key
  relayshield/twilio_account_sid        — Twilio Account SID
  relayshield/twilio_auth_token         — Twilio Auth Token
  relayshield/google_safe_browsing      — Google Safe Browsing API key
"""

import base64
import concurrent.futures
import json
import logging
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
# Router / Lambda handler
# ---------------------------------------------------------------------------

ROUTES = {
    "/v1/breach":    handle_breach,
    "/v1/scan-url":  handle_scan_url,
    "/v1/scan-file": handle_scan_file,
    "/v1/sim-swap":  handle_sim_swap,
    "/v1/domain":    handle_domain,
}


def lambda_handler(event: dict, context) -> dict:
    path   = event.get("path", "")
    method = event.get("httpMethod", "")

    logger.info("API request — method=%s path=%s", method, path)

    if method == "GET" and path in ("/", "/v1", "/v1/"):
        return _ok({
            "service":   "RelayShield B2A API",
            "version":   "1.0",
            "endpoints": list(ROUTES.keys()) + ["GET /v1/result/{analysis_id}"],
        })

    # GET /v1/result/{analysis_id}
    if method == "GET" and path.startswith("/v1/result/"):
        analysis_id = path[len("/v1/result/"):]
        return handle_result(analysis_id)

    handler = ROUTES.get(path)
    if not handler:
        return _err(f"unknown endpoint: {path} — valid endpoints: {list(ROUTES.keys())}", 404)

    if method != "POST":
        return _err(f"{path} only accepts POST requests", 405)

    params = _body(event)
    try:
        return handler(params)
    except Exception as exc:
        logger.exception("Unhandled error in %s: %s", path, exc)
        return _err("internal server error", 500)
