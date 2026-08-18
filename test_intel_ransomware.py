"""Behavioural checks for the INTEL-4 feed migration.

INTEL-4-SOURCE went unnoticed for 14 months because the dead feed returned
16,072 records and HTTP 200. Nothing asserted that the records were recent, and
nothing asserted that a victim domain could actually match a monitored one.
These are the two checks that would have caught it.
"""
import importlib.util
import logging
import os
import sys
import types

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

_b = types.ModuleType("boto3")


class _Stub:
    def __getattr__(self, n):
        return lambda *a, **k: {}


_b.client = lambda *a, **k: _Stub()
_b.resource = lambda *a, **k: _Stub()
sys.modules["boto3"] = _b

_spec = importlib.util.spec_from_file_location(
    "rw", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "relayshield_intel_ransomware.py"))
rw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rw)


def test_maps_ransomware_live_fields():
    """The v2 schema uses group/victim where this module expects
    group_name/post_title. A wrong mapping is silent: records normalise to
    empty strings and no alert ever fires."""
    n = rw._normalise({
        "victim": "Acme Manufacturing",
        "group": "lockbit3",
        "discovered": "2026-08-17 22:14:03.000000",
        "website": "https://www.acme-manufacturing.com",
        "description": "Files exfiltrated.",
    })
    assert n["group_name"] == "lockbit3"
    assert n["post_title"] == "Acme Manufacturing"
    assert n["discovered"].startswith("2026-08-17")


def test_falls_back_to_attackdate():
    """Not every record carries `discovered`, and the watermark orders on it."""
    assert rw._normalise({"victim": "X", "group": "g",
                          "attackdate": "2026-08-01"})["discovered"] == "2026-08-01"


def test_degrades_on_empty_record():
    assert rw._normalise({})["group_name"] == "unknown"
    assert rw._normalise({})["discovered"] == ""


def test_strips_www_so_the_user_match_can_fire():
    """_find_monitored_users compares with eq(). A victim domain of
    www.acme.com never equals the acme.com a user registered, so the CRITICAL
    alert silently does not fire."""
    assert rw._extract_victim_domain(
        {"website": "https://www.acme-manufacturing.com"}) == "acme-manufacturing.com"
    assert rw._extract_victim_domain({"website": "http://ACME.CO.UK/leak"}) == "acme.co.uk"
    assert rw._extract_victim_domain({"website": "https://acme.com"}) == "acme.com"


def test_stale_feed_is_reported_as_an_error(caplog=None):
    """The exact condition that hid INTEL-4: plenty of records, none recent."""
    logger = logging.getLogger("rw")
    records = []

    class _Capture(logging.Handler):
        def emit(self, r):
            records.append(r)

    h = _Capture()
    rw.logger.addHandler(h)
    try:
        rw._warn_if_stale([{"discovered": "2025-06-16"}])   # the archived feed
        assert any(r.levelno >= logging.ERROR for r in records), \
            "a 428-day-old feed must raise an ERROR, not pass quietly"
        records.clear()
        rw._warn_if_stale([{"discovered": "2026-08-18"}])
        assert not any(r.levelno >= logging.ERROR for r in records)
    finally:
        rw.logger.removeHandler(h)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS %s" % name)
            except AssertionError as exc:
                failures += 1
                print("FAIL %s: %s" % (name, exc))
    print("\n%d failure(s)" % failures)
    sys.exit(1 if failures else 0)
