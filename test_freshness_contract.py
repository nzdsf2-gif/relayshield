"""Behavioural checks for the freshness contract extension.

Exercises the real handlers with the upstreams forced to fail, which is the
case the whole contract exists for. Static greps cannot tell you whether
degraded actually propagates.
"""
import importlib.util
import json
import os
import sys
import types
import urllib.error

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

_b = types.ModuleType("boto3")


class _Stub:
    def __getattr__(self, n):
        return lambda *a, **k: {}


_b.client = lambda *a, **k: _Stub()
_b.resource = lambda *a, **k: _Stub()
sys.modules["boto3"] = _b
_bc = types.ModuleType("botocore")
_exc = types.ModuleType("botocore.exceptions")


class ClientError(Exception):
    pass


_exc.ClientError = ClientError
_bc.exceptions = _exc
sys.modules["botocore"] = _bc
sys.modules["botocore.exceptions"] = _exc

sys.path.insert(0, os.getcwd())  # relayshield_api imports its sibling spec module
spec = importlib.util.spec_from_file_location("rsapi", "relayshield_api.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

FAILS = 0


def check(label, got, want):
    global FAILS
    ok = got == want
    if not ok:
        FAILS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: got={got!r} want={want!r}")


def body(resp):
    """Handlers wrap payloads as {"ok": true, "data": {...}}."""
    assert resp["statusCode"] == 200, f"expected 200, got {resp['statusCode']}: {resp['body'][:200]}"
    return json.loads(resp["body"])["data"]


print("== crypto-intel: GoPlus upstream DOWN must not read as clean ==")
m.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("boom"))
r = body(m.handle_crypto_intel({"address": "0x" + "a" * 40}))
check("degraded", r["degraded"], True)
check("ttl is the degraded ttl", r["valid_for_seconds"], 300)
check("advisory warns rather than clearing", r["correlation_advisories"][0].startswith("DEGRADED"), True)
check("no 'No risk signals detected' claim",
      any("No risk signals detected" in a for a in r["correlation_advisories"]), False)

print("== crypto-intel: healthy upstream, genuinely clean ==")


class _Resp:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode()

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


m.urllib.request.urlopen = lambda *a, **k: _Resp({"result": {"0x" + "a" * 40: {}}})
r = body(m.handle_crypto_intel({"address": "0x" + "a" * 40}))
check("degraded", r["degraded"], False)
check("ttl is the clean ttl", r["valid_for_seconds"], 3600)

print("== domain: a truncated DNS sweep must surface as degraded ==")
real_find = m._find_active_lookalikes
m._find_active_lookalikes = lambda cands, **k: ([], 17)
m._enrich_lookalikes = lambda doms, key, **k: ([], 0)
m._gsb_api_key = lambda: ""
r = body(m.handle_domain({"domain": "acme.com"}))
check("degraded on truncation", r["degraded"], True)
check("ttl is the degraded ttl", r["valid_for_seconds"], 300)
check("unchecked count surfaced", r["candidates_unchecked"], 17)
check("lookalikes_found still 0", r["lookalikes_found"], 0)

print("== domain: complete sweep, no lookalikes, is a real clean ==")
m._find_active_lookalikes = lambda cands, **k: ([], 0)
r = body(m.handle_domain({"domain": "acme.com"}))
check("degraded", r["degraded"], False)
check("ttl is the clean ttl", r["valid_for_seconds"], 3600)
m._find_active_lookalikes = real_find

print("== _find_active_lookalikes reports its own truncation ==")
m._dns_resolves = lambda d: False
active, unchecked = m._find_active_lookalikes(["a.com", "b.com"], overall_timeout=5.0)
check("nothing unchecked when fast", unchecked, 0)


def _hang(d):
    import time
    time.sleep(30)
    return False


m._dns_resolves = _hang
active, unchecked = m._find_active_lookalikes(["a.com", "b.com"], overall_timeout=0.4)
check("truncation counted", unchecked, 2)
check("active empty", active, [])

print("== asymmetry invariant across every profile ==")
for path in m._FRESHNESS_PROFILES:
    fl = m._freshness_for(path, True)["valid_for_seconds"]
    cl = m._freshness_for(path, False)["valid_for_seconds"]
    dg = m._freshness_for(path, False, True)["valid_for_seconds"]
    check(f"{path} clean<flagged and degraded shortest", (cl < fl and dg <= cl), True)

print()
print("FAILURES:", FAILS)
sys.exit(1 if FAILS else 0)
