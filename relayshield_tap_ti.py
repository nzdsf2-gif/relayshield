"""relayshield_tap_ti -- the threat-intelligence screen for the TAP verifier.

    verify_tap_request(request, ti_screen=relayshield_tap_ti.screen)

verify_tap_request calls `ti_screen(wallet=..., domain=...)` and expects
{"level": ..., "reasons": [...]}, where critical/high rejects and medium reviews. Until
this module existed the committed Lambda handler passed NO screen, so a verifier sold on
"screens every transaction against threat indicators" screened nothing.

WHAT IT CALLS. The same in-process functions the keyless endpoints use, never their HTTP
doors: a Lambda calling our public API would arrive from one NAT address and be throttled
by the per-IP cap against itself (the lesson in relayshield_watchlist_monitor.py).
    domain -> _assess_domain + _link_check_level   (IOC corpus, lookalike brand, domain age)
    wallet -> handle_wallet_risk                   (sanctions, scam-token and chain checks)
It does NOT ask Safe Browsing: that needs a request per domain and a key this Lambda may
not have, and the corpus is the differentiator.

THE LEVEL IT RETURNS. `high`, `medium` or `unknown`, and NEVER `low` or `clean`. Nothing
found is "no known finding", exactly as /v1/link-check words it; a verifier that says
"clean" about a counterparty it merely failed to find evidence against is making the claim
this product refuses to make anywhere else.

WHEN IT CANNOT ANSWER IT RAISES. A lookup that failed must not become a clean result, so
the caller turns the exception into `review` with the reason `ti_unavailable`, which
threat telemetry does not count as an attack.

PACKAGING. This imports relayshield_api, so the Lambda zip must carry that module and its
relayshield_* dependencies, and the function's role needs read access to the intel tables.
That is why the TAP handler only switches the screen on when VERIFIER_TI_SCREEN=1.
"""
import json

# wallet-risk speaks CRITICAL/HIGH/MEDIUM/LOW; the verifier speaks critical/high/medium.
_WALLET_LEVEL = {"CRITICAL": "high", "HIGH": "high", "MEDIUM": "medium"}
_RANK = {"unknown": 0, "medium": 1, "high": 2}


def _api():
    import relayshield_api  # lazily, so importing this module costs nothing
    return relayshield_api


def normalise_domain(value) -> str:
    """Host only: no scheme, path, port or credentials, lower-cased. '' if nothing usable."""
    if not isinstance(value, str):
        return ""
    v = value.strip().lower()
    for scheme in ("https://", "http://"):
        if v.startswith(scheme):
            v = v[len(scheme):]
    v = v.split("/", 1)[0].rsplit("@", 1)[-1]
    if v.startswith("["):          # a bracketed IPv6 literal is not a domain we can screen
        return ""
    return v.split(":", 1)[0].strip(".")


def _screen_domain(domain: str):
    api = _api()
    result = api._assess_domain(domain, False)
    level = api._link_check_level(result.get("signals") or {})
    return (level if level in _RANK else "unknown"), list(result.get("reasons") or [])


def _screen_wallet(wallet: str):
    api = _api()
    resp = api.handle_wallet_risk({"address": wallet})
    ok, data = api._unwrap(resp)
    if not ok:
        raise RuntimeError("wallet screening unavailable")
    raw = str(data.get("risk_level") or "").upper()
    reasons = [f"wallet risk flag: {f}" for f in (data.get("risk_flags") or []) if isinstance(f, str)]
    return _WALLET_LEVEL.get(raw, "unknown"), reasons


def screen(wallet=None, domain=None) -> dict:
    """The worst level across whatever was supplied. Raises if a supplied item could not
    be screened."""
    level, reasons = "unknown", []
    host = normalise_domain(domain) if domain else ""
    if host:
        lv, rs = _screen_domain(host)
        if _RANK[lv] > _RANK[level]:
            level = lv
        reasons += rs
    if isinstance(wallet, str) and wallet.strip():
        lv, rs = _screen_wallet(wallet.strip())
        if _RANK[lv] > _RANK[level]:
            level = lv
        reasons += rs
    return {"level": level, "reasons": reasons}
