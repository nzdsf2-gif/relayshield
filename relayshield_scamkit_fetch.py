#!/usr/bin/env python3
"""v1b custom TLS fetch pipeline for scam-kit fingerprinting.

Stdlib only (urllib + ssl + socket + ipaddress) — no new Lambda
dependencies, no JS rendering.

``fetch_kit_page(url, observed_telemetry=None)`` returns
``(html, observations, error)`` — never discards everything but the HTML.

Server-side telemetry this captures (the fetch pipeline no other kit API
ships):
  * Up to 5 redirect hops (url + status each) — drives the dormant
    ``evilginx-rickroll-redirect`` / ``w3ll-wikipedia-antibot-redirect``
    behavior classes via ``classify_url_pattern(url, observations)``.
  * Response headers of every hop (capped), flagging ``X-Evilginx``.
  * TLS facts for the final host, measured against the SERVER:
    negotiated version, cipher, certificate issuer / subject / SAN /
    validity window / age. Two attempts: verified first (full cert facts),
    then unverified (cipher + version only — kits often serve odd certs).
  * Up to 2 bounded secondary fetches: the Evilginx canary
    (``/s/<64hex>.js`` referenced in the page) and the page's remote
    favicon.

JA3/JA4 caveat (deliberate): those fingerprint the TLS *client*. Our
fetcher IS the client, so a locally computed JA3 would describe us, not
the kit server — this module never emits one. Callers with their own
telemetry (proxies, EDR, IdP sign-in logs) may pass
``observed_telemetry`` with any of ``ja3``, ``ja4``,
``user_agent_shifts``, ``app_ids``, ``ip_anomalies``,
``session_anomalies``; it is recorded VERBATIM, marked
``caller_supplied: True``, and never presented as server-measured.

Lambda-safe: per-request timeouts, an overall wall-clock deadline (under
API Gateway's 29s ceiling), a 2MB main-page cap, 256KB secondary caps,
an SSRF guard (no private/loopback/link-local targets), and no JS
rendering — static HTML only, documented as a limitation.
"""

import hashlib
import ipaddress
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER_AGENT = "RelayShield/1.0 (+https://relayshield.net)"

FETCH_TIMEOUT = 8                    # per-request socket timeout, seconds
FETCH_MAX_BYTES = 2 * 1024 * 1024   # main page cap
SECONDARY_MAX_BYTES = 256 * 1024    # canary / favicon cap
SECONDARY_TIMEOUT = 6
MAX_REDIRECT_FOLLOWS = 5
MAX_SECONDARY_FETCHES = 2
OVERALL_DEADLINE = 25               # hard wall-clock budget, seconds
_MAX_HEADERS = 40
_HEADER_VALUE_CAP = 300

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)

_CANARY_RE = re.compile(r"/s/[0-9a-fA-F]{64}\.js\b")
_FAVICON_LINK_RE = re.compile(
    r"""<link\b[^>]*\brel\s*=\s*["'](?:shortcut\s+)?icon["'][^>]*>""",
    re.IGNORECASE)
_HREF_ATTR_RE = re.compile(r"""\bhref\s*=\s*["']([^"']+)["']""",
                           re.IGNORECASE)

# Caller-supplied telemetry keys we accept and echo verbatim.
_TELEMETRY_KEYS = ("ja3", "ja4", "user_agent_shifts", "app_ids",
                   "ip_anomalies", "session_anomalies")


class _FetchError(Exception):
    """Any fetch failure, already human-readable."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Disable automatic redirects so we can record every hop ourselves."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_opener():
    return urllib.request.build_opener(_NoRedirect())


def _host_check(host):
    """SSRF guard: refuse non-public targets. Returns (ok, reason)."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except Exception:
        return False, "dns resolution failed"
    if not infos:
        return False, "dns resolution failed"
    for _fam, _typ, _proto, _canon, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False, "unparseable resolved address"
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return False, f"blocked non-public address {ip}"
    return True, ""


def _cap_headers(headers):
    """headers (mapping) -> capped plain dict, lowercased keys kept."""
    out = {}
    for i, (k, v) in enumerate(headers.items()):
        if i >= _MAX_HEADERS:
            break
        out[str(k)] = str(v)[:_HEADER_VALUE_CAP]
    return out


def _hget(headers, name):
    """Case-insensitive header lookup (values were capped at capture)."""
    want = name.lower()
    for k, v in headers.items():
        if k.lower() == want:
            return v
    return ""


def _fetch_one(opener, url, timeout, max_bytes):
    """Single GET. Returns {status, headers, body, url}.

    HTTPError (4xx/5xx) is converted to the same shape — an antibot 403
    page is still signal-rich HTML worth recording.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read(max_bytes + 1)
        except Exception:
            body = b""
        if len(body) > max_bytes:
            raise _FetchError("response exceeds size cap")
        return {"status": exc.code, "headers": _cap_headers(dict(exc.headers.items())),
                "body": body, "url": url}
    except Exception as exc:
        raise _FetchError(f"{type(exc).__name__}: {exc}")
    try:
        status = getattr(resp, "status", None) or resp.getcode()
        headers = _cap_headers(dict(resp.headers.items()))
        body = resp.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise _FetchError("response exceeds size cap")
        return {"status": status, "headers": headers, "body": body,
                "url": getattr(resp, "geturl", lambda: url)()}
    finally:
        try:
            resp.close()
        except Exception:
            pass


def _dn_name(seq):
    parts = {}
    for rdn in seq or ():
        for kv in rdn:
            parts.setdefault(kv[0], kv[1])
    return parts


def _cert_facts(cert):
    """Parse an ssl.getpeercert() dict into JSON-safe facts."""
    fmt = "%b %d %H:%M:%S %Y %Z"
    nb = datetime.strptime(cert["notBefore"], fmt).replace(tzinfo=timezone.utc)
    na = datetime.strptime(cert["notAfter"], fmt).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    san = [v for (k, v) in cert.get("subjectAltName", ()) if k == "DNS"]
    return {
        "issuer": _dn_name(cert.get("issuer")),
        "subject": _dn_name(cert.get("subject")),
        "san": san,
        "not_before": nb.isoformat(),
        "not_after": na.isoformat(),
        "age_days": (now - nb).days,
        "expires_in_days": (na - now).days,
    }


def _probe_tls(host, port=443, timeout=FETCH_TIMEOUT):
    """TLS facts for the SERVER. Verified attempt first (full cert facts),
    then an unverified attempt (cipher + version only)."""
    facts = {"host": host, "port": port}
    # Attempt 1: verified — full certificate facts when the chain verifies.
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as s:
                cipher = s.cipher() or (None, None, None)
                facts.update({"tls_version": s.version(),
                              "cipher": cipher[0], "cipher_bits": cipher[2],
                              "verified": True})
                cert = s.getpeercert()
                if cert:
                    facts.update(_cert_facts(cert))
                return facts
    except Exception as exc:
        facts["verify_error"] = f"{type(exc).__name__}: {exc}"
    # Attempt 2: unverified — kits often serve self-signed/mismatched certs.
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as s:
                cipher = s.cipher() or (None, None, None)
                facts.update({"tls_version": s.version(),
                              "cipher": cipher[0], "cipher_bits": cipher[2],
                              "verified": False})
                return facts
    except Exception as exc:
        facts["error"] = f"{type(exc).__name__}: {exc}"
    return facts


def _telemetry_observations(observed_telemetry):
    """Mark caller-supplied telemetry; never presented as server-measured."""
    if not isinstance(observed_telemetry, dict):
        return None
    marked = {"caller_supplied": True}
    for key in _TELEMETRY_KEYS:
        if key in observed_telemetry:
            marked[key] = observed_telemetry[key]
    return marked


def _secondary_candidates(html, final_url):
    """Up to MAX_SECONDARY_FETCHES (purpose, url): canary first, favicon."""
    cands = []
    m = _CANARY_RE.search(html or "")
    if m:
        cands.append(("evilginx-canary",
                      urllib.parse.urljoin(final_url, m.group(0))))
    for lm in _FAVICON_LINK_RE.finditer(html or ""):
        hm = _HREF_ATTR_RE.search(lm.group(0))
        if not hm:
            continue
        href = hm.group(1)
        if href.lower().startswith("data:"):
            continue
        if href.startswith("http://") or href.startswith("https://"):
            cands.append(("remote-favicon", href))
            break
    return cands[:MAX_SECONDARY_FETCHES]


def fetch_kit_page(url, observed_telemetry=None, *, timeout=FETCH_TIMEOUT,
                   max_bytes=FETCH_MAX_BYTES, opener=None,
                   tls_probe=None, host_check=None):
    """Fetch a kit URL with full server-side telemetry.

    Returns ``(html, observations, error)``. ``opener``, ``tls_probe``
    and ``host_check`` are injectable for tests; production callers omit
    them.
    """
    host_check = host_check or _host_check
    tls_probe = tls_probe or _probe_tls
    opener = opener or _default_opener()
    deadline = time.monotonic() + OVERALL_DEADLINE

    def _base_obs(**kw):
        obs = {"final_url": None, "redirect_chain": [],
               "redirect_count": 0, "response_headers": {},
               "x_evilginx": False, "tls": None, "secondary_fetches": [],
               "observed_telemetry": _telemetry_observations(observed_telemetry),
               "notes": [
                   "static HTML only — no JS rendering in the Lambda; "
                   "submit rendered HTML via the html field for JS-heavy kits",
                   "JA3/JA4 fingerprint the TLS client, not the server: "
                   "none computed locally; caller-supplied values only",
               ]}
        obs.update(kw)
        return obs

    parts = urllib.parse.urlparse(url or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "", _base_obs(), "url must be http(s) with a hostname"
    ok, reason = host_check(parts.hostname)
    if not ok:
        return "", _base_obs(), f"target blocked: {reason}"

    chain = []
    current = url
    final = None
    try:
        for _ in range(MAX_REDIRECT_FOLLOWS + 1):
            if time.monotonic() > deadline:
                raise _FetchError("fetch deadline exceeded")
            r = _fetch_one(opener, current, timeout, max_bytes)
            chain.append({"url": current, "status": r["status"]})
            location = _hget(r["headers"], "location")
            if r["status"] in _REDIRECT_STATUSES and location:
                if len(chain) - 1 >= MAX_REDIRECT_FOLLOWS:
                    raise _FetchError(
                        f"too many redirects (>{MAX_REDIRECT_FOLLOWS})")
                current = urllib.parse.urljoin(current, location)
                continue
            final = r
            break
        else:
            raise _FetchError(f"too many redirects (>{MAX_REDIRECT_FOLLOWS})")
    except _FetchError as exc:
        return "", _base_obs(redirect_chain=chain,
                             redirect_count=max(0, len(chain) - 1)), str(exc)

    headers = final["headers"]
    ctype = _hget(headers, "content-type")
    if "html" not in ctype.lower():
        return "", _base_obs(
            final_url=current, redirect_chain=chain,
            redirect_count=max(0, len(chain) - 1),
            response_headers=headers,
            x_evilginx=any(k.lower() == "x-evilginx" for k in headers),
        ), f"not_html (Content-Type: {ctype[:60]})"

    html = final["body"].decode("utf-8", "replace")
    if len(html.strip()) < 50:
        return "", _base_obs(
            final_url=current, redirect_chain=chain,
            redirect_count=max(0, len(chain) - 1),
            response_headers=headers,
            x_evilginx=any(k.lower() == "x-evilginx" for k in headers),
        ), "page body empty or trivial"

    # TLS facts for the final host (https only).
    tls_facts = None
    fparts = urllib.parse.urlparse(current)
    if fparts.scheme == "https" and fparts.hostname:
        try:
            if time.monotonic() <= deadline:
                tls_facts = tls_probe(fparts.hostname,
                                      fparts.port or 443, timeout)
        except Exception as exc:  # never fail the fingerprint on TLS probe
            tls_facts = {"host": fparts.hostname,
                         "error": f"{type(exc).__name__}: {exc}"}

    # Bounded secondary fetches: canary, then favicon.
    secondaries = []
    for purpose, surl in _secondary_candidates(html, current):
        if time.monotonic() > deadline:
            secondaries.append({"purpose": purpose, "url": surl,
                                "error": "fetch deadline exceeded"})
            continue
        try:
            sr = _fetch_one(opener, surl, SECONDARY_TIMEOUT,
                            SECONDARY_MAX_BYTES)
            secondaries.append({
                "purpose": purpose, "url": surl, "status": sr["status"],
                "bytes": len(sr["body"]),
                "sha256": hashlib.sha256(sr["body"]).hexdigest(),
            })
        except _FetchError as exc:
            secondaries.append({"purpose": purpose, "url": surl,
                                "error": str(exc)})

    observations = _base_obs(
        final_url=current,
        redirect_chain=chain,
        redirect_count=max(0, len(chain) - 1),
        response_headers=headers,
        x_evilginx=any(k.lower() == "x-evilginx" for k in headers),
        tls=tls_facts,
        secondary_fetches=secondaries,
    )
    return html, observations, ""
