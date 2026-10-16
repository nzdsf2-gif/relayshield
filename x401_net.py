"""x401_net -- the one place the x401 relying party makes an outbound request.

Two things fetch: a credential's Token Status List and a Result Artifact's
`credential_result_uri`. Both URLs arrive from an untrusted party, so the caller first
checks them against an allowlist of prefixes registered by US (x401_rp enforces that), and
this module adds the rest of what a fetch from inside a Lambda needs:

  * https only, no credentials in the URL, no redirects (a redirect is how an allowlisted
    host becomes an internal address);
  * every address the host resolves to must be a public one, so a name that points at
    169.254.169.254 or 10.x is refused;
  * a hard size cap and a short timeout, so a hostile server cannot hold the invocation.

Every failure returns None. The caller turns None into an error object, never into "valid".

KNOWN LIMIT: the address is checked and then urllib resolves again to connect, so a DNS
answer that changes between the two could slip past. The allowlist is the primary control
and this is the second; closing the gap fully means connecting to the checked address
directly, which urllib does not offer.
"""

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 256 * 1024
TIMEOUT = 5


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _public_host(host: str, resolver=socket.getaddrinfo) -> bool:
    try:
        infos = resolver(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    addrs = {i[4][0] for i in infos}
    return bool(addrs) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs)


def safe_fetch(url, accept="application/json", max_bytes=MAX_BYTES, timeout=TIMEOUT,
               resolver=socket.getaddrinfo, opener=None):
    """GET `url` -> bytes, or None on ANY problem."""
    try:
        u = urllib.parse.urlsplit(url)
        if u.scheme != "https" or not u.hostname or u.username or u.password or u.fragment:
            return None
        try:
            ipaddress.ip_address(u.hostname)
            return None                                   # a literal address is never needed here
        except ValueError:
            pass
        if not _public_host(u.hostname, resolver):
            return None
        op = opener or urllib.request.build_opener(_NoRedirect)
        req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "RelayShield-x401/1.0"})
        with op.open(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            data = resp.read(max_bytes + 1)
        return data if len(data) <= max_bytes else None
    except Exception:
        return None
