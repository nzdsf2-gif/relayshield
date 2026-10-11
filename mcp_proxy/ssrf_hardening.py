"""SSRF hardening: redirect-chain validation and DNS rebinding guard.

These close the gaps demonstrated by the zotero-mcp SSRF (versions
0.10.0-0.14.1, zotero_add_by_url): the fetcher validated no
destinations, so an agent could reach internal hosts directly OR
through redirects, and DNS rebinding could bypass point-in-time
checks.

Designed to be merged into mcp_proxy/screener.py.
"""

import logging
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

# Import from screener (when merged, these are module-local).
# from .screener import _is_internal_url, _url_host, _resolve_host_ips


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Capture redirect location without following."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch_redirect_chain(url: str, max_redirects: int = 5,
                          timeout: float = 5.0) -> list:
    """Follow redirect chain, returning list of URLs visited.

    Uses HEAD requests to avoid downloading bodies. Returns the
    chain including the original URL. Stops at max_redirects or on
    any non-redirect response / error.

    Note: This performs network I/O. Callers should use it only
    when redirect validation is explicitly enabled, as it adds
    latency to screening.
    """
    chain = [url]
    current = url
    opener = urllib.request.build_opener(_NoRedirect)
    # Don't send a distinctive UA.
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]

    for _ in range(max_redirects):
        try:
            req = urllib.request.Request(current, method="HEAD")
            try:
                opener.open(req, timeout=timeout)
                # No redirect (2xx) - chain ends.
                break
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 303, 307, 308):
                    location = e.headers.get("Location")
                    if not location:
                        break
                    # Resolve relative redirects.
                    current = urllib.parse.urljoin(current, location)
                    chain.append(current)
                    continue
                # Non-redirect HTTP error - chain ends.
                break
        except Exception as exc:
            log.debug("redirect chain fetch failed for %s: %s", current, exc)
            break
    return chain


def _check_dns_rebinding(host: str, resolve_fn) -> bool:
    """True if DNS rebinding is detected (two resolutions differ).

    Resolves the hostname twice with a short delay. If the IP sets
    differ, an attacker may be using DNS TTL tricks to bypass
    point-in-time validation.

    Args:
        host: Hostname to check.
        resolve_fn: Function(host) -> list of IP strings.

    Returns:
        True if rebinding detected, False otherwise (or on error).
    """
    import time
    try:
        first = set(resolve_fn(host))
        if not first:
            return False
        time.sleep(0.5)
        second = set(resolve_fn(host))
        if not second:
            return False
        return first != second
    except Exception as exc:
        log.debug("dns rebinding check failed for %s: %s", host, exc)
        return False


def check_url_with_hardening(url: str, is_internal_fn, url_host_fn,
                             resolve_fn, max_redirects: int = 5,
                             check_redirects: bool = True,
                             check_rebinding: bool = True) -> dict:
    """Full SSRF check with redirect and rebinding hardening.

    Args:
        url: The URL to check.
        is_internal_fn: Function(url, resolve=True) -> bool.
        url_host_fn: Function(url) -> host string.
        resolve_fn: Function(host) -> list of IP strings.
        max_redirects: Max redirect hops to follow.
        check_redirects: Whether to validate redirect chains.
        check_rebinding: Whether to check for DNS rebinding.

    Returns:
        Dict with keys: blocked (bool), reasons (list), chain (list).
    """
    reasons = []

    # 1. Direct check.
    if is_internal_fn(url):
        return {
            "blocked": True,
            "reasons": [f"direct: URL targets internal infrastructure"],
            "chain": [url],
        }

    chain = [url]

    # 2. Redirect chain.
    if check_redirects:
        chain = _fetch_redirect_chain(url, max_redirects=max_redirects)
        for hop in chain[1:]:  # skip original (already checked)
            if is_internal_fn(hop):
                reasons.append(
                    f"redirect: hop targets internal infrastructure: {hop[:80]}"
                )
                return {
                    "blocked": True,
                    "reasons": reasons,
                    "chain": chain,
                }

    # 3. DNS rebinding (check the final URL's host).
    if check_rebinding:
        final_host = url_host_fn(chain[-1])
        if final_host and _check_dns_rebinding(final_host, resolve_fn):
            reasons.append(
                f"rebinding: DNS for {final_host} changed between resolutions"
            )
            return {
                "blocked": True,
                "reasons": reasons,
                "chain": chain,
            }

    return {"blocked": False, "reasons": reasons, "chain": chain}
