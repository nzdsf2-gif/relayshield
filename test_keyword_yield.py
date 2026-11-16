#!/usr/bin/env python3
"""tools/keyword_yield.py: parse the real SEARCH_KEYWORDS and format a report.

Runs against the actual relayshield_intel_discovery.py, not a fixture, so a change
to the comment layout that breaks the sweep attribution fails here.
boto3 is not needed; the AWS calls are checked separately (see the 2026-11-16
LOG_CURRENT entry): this suite stubs nothing and covers the pure functions only.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import keyword_yield as ky  # noqa: E402

kws = ky.parse_keywords((ROOT / "relayshield_intel_discovery.py").read_text(encoding="utf-8"))
by = {}
for k, c, lab in kws:
    by.setdefault(lab, []).append(k)

# Counts as of the 2026-11-16 recovery. A sweep adding keywords later is a sweep 004+, so these hold.
assert len(by["sweep 001"]) == 9, by["sweep 001"]
assert len(by["sweep 001b"]) == 4
assert len(by["sweep 002"]) == 13
assert len(by["sweep 003"]) == 16
assert "fullz" in by["sweep 001"], "card-shop block after a blank line must still be sweep 001"
assert "撞库" in by["baseline"], "zh/ko block after sweep 003 must NOT be attributed to sweep 003"
assert "serverkillers" in by["sweep 003"]
assert len({k for k, _, _ in kws}) == len(kws), "duplicate keyword names"

rows = [
    {"username": "a", "keyword_match": "qilin", "active": True, "member_count": 120, "first_seen": "2026-10-01T00:00:00Z"},
    {"username": "b", "keyword_match": "qilin", "active": False, "member_count": 5},
    {"username": "c", "keyword_match": "gone_keyword", "active": True},
]
out = ky.summarize(kws, rows, deployed={k for k, _, _ in kws if k != "fullz"})
assert "SWEEP 001B: 4 keywords, 1 produced rows, 2 rows (1 active)" in out, out
assert "@a(120)" in out
assert "[NOT DEPLOYED]" in out and "[live]" in out
assert "NOT in the repo's SEARCH_KEYWORDS: 1" in out
assert "SWEEP 003" in out
# without a deployed set no live/not-deployed tags are printed
assert "[live]" not in ky.summarize(kws, rows)
print("OK: test_keyword_yield")
