#!/usr/bin/env python3
"""Regenerate (or verify) rsscan's local pattern mirror from relayshield_api.py.

rsscan matches on the developer's machine, so it carries its own copy of
NHI_PATTERNS. A copy is a liability: every silent false negative fixed
server-side (the OpenAI `sk-proj-` rebuild, the Anthropic underscore) would go
stale in the client and quietly stop catching real keys.

    python3 tools/sync_patterns.py            # regenerate
    python3 tools/sync_patterns.py --check    # exit 1 if drifted (CI / pre-release)

Run --check before publishing rsscan. Never hand-edit rsscan/rsscan/patterns.py.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER = ROOT / "relayshield_api.py"
TARGET = ROOT / "rsscan" / "rsscan" / "patterns.py"


def extract() -> tuple[str, str, str]:
    src = SERVER.read_text().split("\n")
    cs = next(i for i, l in enumerate(src) if l.startswith("def _ctx_key"))
    ce = next(i for i in range(cs, len(src)) if src[i].startswith("NHI_PATTERNS"))
    ctx_src = "\n".join(src[cs:ce]).rstrip()

    ns = next(i for i, l in enumerate(src) if l.startswith("NHI_PATTERNS"))
    ne = next(i for i in range(ns, len(src)) if src[i].rstrip() == "]")
    pat_src = "\n".join(src[ns:ne + 1]).replace(
        "NHI_PATTERNS: list[tuple[str, str, str, str, str | None]]", "NHI_PATTERNS"
    )
    digest = hashlib.sha256((ctx_src + pat_src).encode()).hexdigest()[:16]
    return ctx_src, pat_src, digest


def render(ctx_src: str, pat_src: str, digest: str) -> str:
    header = f'''"""Credential patterns — a byte-faithful mirror of the server's NHI_PATTERNS.

rsscan matches entirely on the developer's machine. No source code, no diff and
no matched value ever leaves the host, which is what makes the free tier free
(zero API cost) and removes the "why does this hook POST our source to a third
party" objection outright.

DO NOT hand-edit. Regenerate with:

    python3 tools/sync_patterns.py

Sync digest: {digest}
`tools/sync_patterns.py --check` fails if this drifts from relayshield_api.py,
so a pattern fixed server-side cannot silently go stale in the client.
"""

from __future__ import annotations

import hashlib
import re as _re


'''
    footer = '''


_COMPILED = [
    (name, _re.compile(pat), sev, desc, provider)
    for name, pat, sev, desc, provider in NHI_PATTERNS
]

PATTERN_COUNT = len(_COMPILED)


def fingerprint(value: str) -> str:
    """Stable, non-reversible id — identical scheme to the server's.

    Must stay byte-identical or an allowlist written against a server-side scan
    would stop matching a local one.
    """
    return "sha256:" + hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:16]
'''
    return header + ctx_src + "\n\n\n" + pat_src + footer + "\n"


def main() -> int:
    ctx_src, pat_src, digest = extract()
    rendered = render(ctx_src, pat_src, digest)

    if "--check" in sys.argv:
        if not TARGET.exists():
            print(f"DRIFT: {TARGET} does not exist", file=sys.stderr)
            return 1
        if TARGET.read_text() != rendered:
            print(
                "DRIFT: rsscan/rsscan/patterns.py no longer matches relayshield_api.py.\n"
                "       Run: python3 tools/sync_patterns.py",
                file=sys.stderr,
            )
            return 1
        print(f"in sync ({digest})")
        return 0

    TARGET.write_text(rendered)
    print(f"regenerated {TARGET.relative_to(ROOT)} ({digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
