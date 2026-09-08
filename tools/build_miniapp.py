#!/usr/bin/env python3
"""Inline widget/relayshield-widget.js into the Mini App Worker.

WHY A BUILD STEP RATHER THAN A COPY. The Mini App and the Telegram bot widget do
the same job: detect what a string is, call the keyless endpoint for it, shape a
verdict. This repo already carries four copies of one pattern table that must
agree with nothing checking that they do, and that is a documented, recurring
cost. So there is ONE implementation, in widget/, pinned by
widget/relayshield-widget.test.mjs, and the Worker serves it rather than
restating it.

A Cloudflare Worker is a single module with no bundler in this repo's toolchain,
so "serve the file" means embedding it at build time. That is what this does, and
--check is what stops the embedded copy drifting from the source: it runs in CI
and fails if they differ, which turns a silent copy into a loud one.

    python3 tools/build_miniapp.py            # write
    python3 tools/build_miniapp.py --check    # fail if stale
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "widget" / "relayshield-widget.js"
WORKER = ROOT / "cloudflare_worker_miniapp.js"
MARK = re.compile(r'^const WIDGET_JS = (".*"|"__WIDGET_JS__");\s*$', re.M)


def build(check_only: bool) -> int:
    widget = SRC.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")

    if not MARK.search(worker):
        print("ERROR: the WIDGET_JS marker line is missing from the Worker.",
              file=sys.stderr)
        return 1

    # json.dumps produces a correctly escaped JS string literal, including for
    # backslashes and the newlines in the source. Hand-rolling that escaping is
    # how a regex in the widget would silently arrive mangled.
    literal = json.dumps(widget)
    # A FUNCTION replacement, not a string. re.sub parses backslash escapes in a
    # string replacement, and the widget is full of regexes: the first build
    # died on `\u` inside its own source with "bad escape \u". A lambda is
    # substituted verbatim and cannot be reinterpreted.
    updated = MARK.sub(lambda _m: f"const WIDGET_JS = {literal};", worker, count=1)

    if check_only:
        if updated != worker:
            print("STALE: cloudflare_worker_miniapp.js does not carry the current\n"
                  "       widget/relayshield-widget.js. Run:\n"
                  "         python3 tools/build_miniapp.py\n"
                  "       and commit the result.", file=sys.stderr)
            return 1
        print(f"IN SYNC: embedded widget matches {SRC.relative_to(ROOT)} "
              f"({len(widget)} chars)")
        return 0

    WORKER.write_text(updated, encoding="utf-8")
    print(f"embedded {len(widget)} chars of {SRC.relative_to(ROOT)} "
          f"into {WORKER.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build("--check" in sys.argv))
