"""Control tests for _verify_github_fragment (BB-1).

Loads NHI_PATTERNS straight out of relayshield_api.py so the tests run against
the real shipped patterns, not a copy that can drift.
"""
import re as _re

from pathlib import Path

# Derived from this file's own location rather than hardcoded: rsscan/ sits
# inside the clone, so the source is one directory up whatever the clone is
# called or wherever it lives.
SRC = str(Path(__file__).resolve().parent.parent / "relayshield_api.py")
src = open(SRC).read().split("\n")


def _ctx_key(vendors: str, key_re: str) -> str:
    return (
        rf"(?i)(?:{vendors})[\w.\-]{{0,20}}[\s'\"]{{0,3}}"
        rf"(?:=|:|=>|:=|\|\|)[\s'\"`]{{0,5}}({key_re})"
    )


s = next(i for i, l in enumerate(src) if l.startswith("NHI_PATTERNS"))
e = next(i for i in range(s, len(src)) if src[i].rstrip() == "]")
ns = {"_ctx_key": _ctx_key}
exec(
    "\n".join(src[s:e + 1]).replace(
        "NHI_PATTERNS: list[tuple[str, str, str, str, str | None]]", "NHI_PATTERNS"
    ),
    ns,
)
_NHI_COMPILED = [(n, _re.compile(p), sev, d, pr) for n, p, sev, d, pr in ns["NHI_PATTERNS"]]


def verify(pattern_name, item):
    """Mirror of _verify_github_fragment in relayshield_api.py."""
    fragments = [
        m.get("fragment", "") for m in (item.get("text_matches") or []) if m.get("fragment")
    ]
    if not fragments:
        return True
    blob = "\n".join(fragments)
    for name, pattern, _s, _d, _p in _NHI_COMPILED:
        if name == pattern_name and pattern.search(blob):
            return True
    return any(p.search(blob) for _n, p, _s, _d, _pr in _NHI_COMPILED)


def item(fragment):
    return {"text_matches": [{"fragment": fragment}]}


TESTS = [
    # (label, pattern queried, item, expected_kept)
    ("REAL leaked AWS key",            "aws_access_key", item("AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF"), True),
    ("placeholder AKIA....",           "aws_access_key", item("aws_access_key_id=AKIA...."), False),
    ("docs table mention only",        "aws_access_key", item("| `openai` | `OPENAI_API_KEY` |"), False),
    ("domain allowlist entry",         "aws_access_key", item('- "*.openai.com"'), False),
    ("blocklist w/ both strings",      "aws_access_key", item("openai.com\nAKIA\nexample.org"), False),
    ("cross-type: ghp_ under AKIA q",  "aws_access_key", item("token: ghp_" + "a" * 36), True),
    ("no fragments -> degrade open",   "aws_access_key", {"text_matches": []}, True),
    ("missing key -> degrade open",    "aws_access_key", {}, True),
    ("real stripe key",                "stripe_secret",  item("STRIPE_KEY=sk_live_" + "a" * 24), True),
    ("real anthropic key",             "anthropic_key",  item("sk-ant-" + "a" * 95), True),
    ("real private key header",        "private_key",    item("-----BEGIN RSA PRIVATE KEY-----"), True),
    ("prose about private keys",       "private_key",    item("Never commit your private key to git."), False),
]

if __name__ == "__main__":
    ok = True
    for label, name, it, expected in TESTS:
        got = verify(name, it)
        passed = got == expected
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'}  expect={str(expected):5s} got={str(got):5s}  {label}")
    print()
    print("ALL CONTROL TESTS PASS" if ok else "*** SOME TESTS FAILED ***")
    raise SystemExit(0 if ok else 1)
