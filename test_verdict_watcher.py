"""Behavioural checks for the Verdict Watch licence.

The two rules that matter are negative ones: a degraded result must never page,
and a baseline must never page. Both are the kind of thing that looks fine in
review and only shows up as a 3am false alert, so they are tested directly.

Also asserts the fingerprint duplicated across relayshield_api.py and
relayshield_verdict_watcher.py has not drifted. That duplication is deliberate
(single-file Lambda deploys) but on 2026-08-08 the sim-swap fix landed in one of
two copies of the same logic and left a live false-clean in the paid API for a
day. This test is the tripwire for a repeat.
"""
import importlib.util
import os
import re
import sys
import types
from datetime import datetime, timezone

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ["RELAYSHIELD_INTERNAL_API_KEY"] = "test-internal-key"
sys.path.insert(0, os.getcwd())

WRITES = []


class _Table:
    def __init__(self, name):
        self.name = name

    def scan(self, **kw):
        return {"Items": list(SCAN_ITEMS)}

    def update_item(self, **kw):
        WRITES.append(kw)
        return {}

    def get_item(self, **kw):
        return {"Item": KEY_RECORD}

    def put_item(self, **kw):
        WRITES.append(kw)
        return {}

    def query(self, **kw):
        return {"Items": [], "Count": 0}


_b = types.ModuleType("boto3")
_b.resource = lambda *a, **k: types.SimpleNamespace(Table=_Table)
_b.client = lambda *a, **k: types.SimpleNamespace()
_dyn = types.ModuleType("boto3.dynamodb")
_cond = types.ModuleType("boto3.dynamodb.conditions")


class _Cmp:
    def __init__(self, n):
        self.n = n

    def lte(self, v):
        return ("lte", self.n, v)

    def eq(self, v):
        return ("eq", self.n, v)


_cond.Attr = _Cmp
_cond.Key = _Cmp
_dyn.conditions = _cond
_b.dynamodb = _dyn
sys.modules["boto3"] = _b
sys.modules["boto3.dynamodb"] = _dyn
sys.modules["boto3.dynamodb.conditions"] = _cond

spec = importlib.util.spec_from_file_location("watcher", "relayshield_verdict_watcher.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

FAILS = 0
NOTIFIED = []
SCAN_ITEMS = []
KEY_RECORD = {"watch_access": True, "webhook_url": "https://example.invalid/hook"}


def check(label, got, want):
    global FAILS
    ok = got == want
    if not ok:
        FAILS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: got={got!r} want={want!r}")


def run(screen_result):
    global NOTIFIED
    NOTIFIED = []
    WRITES.clear()
    w._screen = lambda t, v: screen_result
    w._notify = lambda k, watch, b, a, d: NOTIFIED.append((b, a)) or True
    return w.lambda_handler({}, None)


BASE = {"api_key": "k1", "watch_id": "w1", "subject_type": "address",
        "subject_value": "0x" + "a" * 40, "next_check_at": "2020-01-01T00:00:00+00:00"}

print("== rule 1: a degraded result must never page ==")
SCAN_ITEMS = [dict(BASE, last_fingerprint="clean")]
r = run({"degraded": True, "address_flags": [], "valid_for_seconds": 300})
check("no notification", NOTIFIED, [])
check("counted as degraded", r["degraded"], 1)
check("no flip recorded", r["flips"], 0)

print("== rule 1b: total upstream failure must never page ==")
SCAN_ITEMS = [dict(BASE, last_fingerprint="clean")]
r = run(None)
check("no notification", NOTIFIED, [])
check("counted as degraded", r["degraded"], 1)

print("== rule 2: the baseline check must never page ==")
SCAN_ITEMS = [dict(BASE, last_fingerprint=None)]
r = run({"degraded": False, "address_flags": ["honeypot_related"], "valid_for_seconds": 86400})
check("no notification on first sighting", NOTIFIED, [])
check("counted as baseline", r["baselines"], 1)
check("no flip", r["flips"], 0)

print("== a real flip DOES page ==")
SCAN_ITEMS = [dict(BASE, last_fingerprint="clean")]
r = run({"degraded": False, "address_flags": ["honeypot_related"], "valid_for_seconds": 86400})
check("notified once", len(NOTIFIED), 1)
check("carries before and after", NOTIFIED[0], ("clean", "honeypot_related"))
check("counted", r["flips"], 1)

print("== an unchanged verdict does NOT page ==")
SCAN_ITEMS = [dict(BASE, last_fingerprint="honeypot_related")]
r = run({"degraded": False, "address_flags": ["honeypot_related"], "valid_for_seconds": 86400})
check("no notification", NOTIFIED, [])
check("no flip", r["flips"], 0)

print("== cadence follows the freshness TTL the API returned ==")
SCAN_ITEMS = [dict(BASE, last_fingerprint="clean")]
run({"degraded": False, "address_flags": [], "valid_for_seconds": 3600})
nxt = [x for x in WRITES if ":n" in x.get("ExpressionAttributeValues", {})][-1]
delta = (datetime.fromisoformat(nxt["ExpressionAttributeValues"][":n"])
         - datetime.now(timezone.utc)).total_seconds()
check("clean re-checks in about an hour", 3400 < delta < 3700, True)

SCAN_ITEMS = [dict(BASE, last_fingerprint="honeypot_related")]
run({"degraded": False, "address_flags": ["honeypot_related"], "valid_for_seconds": 86400})
nxt = [x for x in WRITES if ":n" in x.get("ExpressionAttributeValues", {})][-1]
delta = (datetime.fromisoformat(nxt["ExpressionAttributeValues"][":n"])
         - datetime.now(timezone.utc)).total_seconds()
check("flagged re-checks in about a day", 86000 < delta < 86500, True)

print("== a lapsed licence stops delivery ==")
KEY_RECORD = {"watch_access": False, "webhook_url": "https://example.invalid/hook"}
check("no webhook url returned", w._webhook_url_for("k1"), "")
KEY_RECORD = {"watch_access": True, "webhook_url": "https://example.invalid/hook"}

print("== fingerprint has not drifted between the two files ==")


def logic(path):
    s = open(path, encoding="utf-8").read()
    m = re.search(r"def _verdict_fingerprint\(.*?\n(?=\n\ndef |\n\n[A-Z_]|\nclass )", s, re.S)
    return [ln.strip() for ln in m.group(0).splitlines() if ln.strip().startswith(("if ", "return "))]


check("api and watcher agree", logic("relayshield_api.py") == logic("relayshield_verdict_watcher.py"), True)

print()
print("FAILURES:", FAILS)
sys.exit(1 if FAILS else 0)
