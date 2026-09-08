#!/usr/bin/env python3
"""FD-13: insert our catalog entry into a fork of xai-org/plugin-marketplace,
adding lines and changing nothing else.

WHY NOT json.load / json.dump. Their catalog keeps `keywords` and `domains` on a
single line per entry, and Python's json.dump expands every array it touches. A
round trip therefore reformats all 22 other vendors' entries, turning a one-entry
addition into a 264-line diff across code nobody asked us to touch. Their own
"common reasons a PR gets sent back" list names a botched merge that breaks the
catalog, and their checklist says ONE entry added. A reviewer seeing every other
plugin rewritten is entitled to close it.

So this edits the file as TEXT, appending one object before the closing bracket of
the `plugins` array, in their exact style. Then it parses the result to prove the
JSON is still valid, and reports the diff shape so the change can be seen to be
additive before anything is committed.

Run it from inside the fork:

    python3 ~/dev/relayshield/tools/fd13_grok_pr.py --catalog .grok-plugin/marketplace.json
    python3 ~/dev/relayshield/tools/fd13_grok_pr.py --catalog .grok-plugin/marketplace.json --write
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ORG_URL = "https://github.com/RelayShield/relayshield-plugin.git"

DESCRIPTION = (
    "Counterparty screening for agents. Scans the instruction files a repository "
    "gives an agent (README, AGENTS.md, CLAUDE.md, .cursorrules, MCP manifests) for "
    "text that would make it fetch and execute remote code, ignore prior "
    "instructions, or open credential files, then checks every domain those "
    "instructions reference against indicators collected from criminal channels. "
    "Also screens MCP servers for typosquat distance and registration age."
)
KEYWORDS = ["relayshield", "agent bait scan", "mcp registry risk", "relayshield scan"]
DOMAINS = ["relayshield.net", "api.relayshield.net"]


def org_head_sha() -> str:
    try:
        out = subprocess.check_output(["git", "ls-remote", ORG_URL, "HEAD"],
                                      text=True, timeout=90,
                                      stderr=subprocess.DEVNULL).split()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        raise SystemExit(f"ERROR: cannot read HEAD of {ORG_URL}")
    if not out:
        raise SystemExit(f"ERROR: {ORG_URL} has no HEAD")
    return out[0]


def entry_text(sha: str) -> str:
    j = json.dumps
    inline = lambda xs: "[" + ", ".join(j(x) for x in xs) + "]"
    return (
        '    {\n'
        f'      "name": "relayshield",\n'
        f'      "description": {j(DESCRIPTION)},\n'
        f'      "category": "security",\n'
        f'      "source": {{\n'
        f'        "source": "url",\n'
        f'        "url": {j(ORG_URL)},\n'
        f'        "sha": {j(sha)}\n'
        f'      }},\n'
        f'      "homepage": "https://relayshield.net",\n'
        f'      "keywords": {inline(KEYWORDS)},\n'
        f'      "domains": {inline(DOMAINS)}\n'
        '    }\n'
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=".grok-plugin/marketplace.json")
    ap.add_argument("--write", action="store_true",
                    help="apply the edit (default: show what it would do)")
    args = ap.parse_args()

    path = Path(args.catalog)
    if not path.is_file():
        raise SystemExit(f"ERROR: {path} not found. Run this from inside your fork "
                         f"of xai-org/plugin-marketplace.")

    original = path.read_text(encoding="utf-8")
    data = json.loads(original)
    if any(p.get("name") == "relayshield" for p in data.get("plugins", [])):
        print("Already present in the catalog. To update a live plugin, bump the sha "
              "on the EXISTING entry rather than adding a parallel one.")
        return 0

    sha = org_head_sha()

    # Close of the last plugin object, then the array, then the document. Anchored
    # on the end of the file so a stray '  ]' inside a description cannot match.
    tail = "\n    }\n  ]\n}"
    if not original.rstrip("\n").endswith(tail.rstrip("\n")):
        raise SystemExit(
            "ERROR: the catalog does not end in the expected shape.\n"
            "       Their format may have changed; do not force an edit, read the file."
        )
    cut = original.rstrip("\n").rfind(tail)
    new = (original.rstrip("\n")[:cut]
           + "\n    },\n"
           + entry_text(sha)
           + "  ]\n}\n")

    # Prove it is still valid and that we added exactly one plugin.
    after = json.loads(new)
    if len(after["plugins"]) != len(data["plugins"]) + 1:
        raise SystemExit("ERROR: the edit did not add exactly one plugin.")
    if after["plugins"][:-1] != data["plugins"]:
        raise SystemExit("ERROR: the edit changed an existing entry. Refusing.")

    added = len(new.split("\n")) - len(original.split("\n"))
    print(f"pinning {sha}")
    print(f"adds {added} lines, changes 1 (the comma after the previous entry)")
    print(f"plugins: {len(data['plugins'])} -> {len(after['plugins'])}")

    if not args.write:
        print("\n--- the entry that would be inserted ---")
        print(entry_text(sha), end="")
        print("\nRe-run with --write to apply.")
        return 0

    path.write_text(new, encoding="utf-8")
    print(f"\nWROTE {path}")
    print("Next, in this fork:\n"
          "  python3 scripts/generate-plugin-index.py\n"
          "  python3 scripts/validate-catalog.py\n"
          "  python3 scripts/generate-plugin-index.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
