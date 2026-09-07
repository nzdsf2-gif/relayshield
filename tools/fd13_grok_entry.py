#!/usr/bin/env python3
"""FD-13: emit our catalog entry for xai-org/plugin-marketplace, correctly pinned.

Why a script rather than a JSON block in a doc. Their validator rejects a SHA that
is not exactly 40 lowercase hex characters, and rejects a branch name or a tag,
because a moving ref would let a later force-push ship new code to every user
silently. A SHA pasted from a doc is stale the moment main moves, and the failure
arrives as a red CI run on somebody else's repo. So the SHA is READ, never typed.

Two schema details that are easy to get wrong and were taken from their repo
rather than guessed, verified 2026-09-07:

  * The inner key is "source", NOT "type".  {"source": "url", "url": ..., "sha": ...}
    `"type": "remote"` is what the shape looks like it should be and it is wrong.
  * A url source takes an optional relative "path", which is what makes this work
    at all: our plugin lives at plugins/relayshield inside a monorepo, not at a
    repo root, and without `path` their loader would look for a plugin manifest
    beside our marketplace manifest and find the wrong thing.

Usage, from the repo root:

    python3 tools/fd13_grok_entry.py                  # pin origin/main
    python3 tools/fd13_grok_entry.py --rev <ref>      # pin something else

It refuses to emit an entry for a commit that is not on the remote, because a
local-only SHA passes our own eye and fails their CI when it cannot be fetched.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The ORG repo is the source we submit, and that is the whole point of FD-13's
# org move: xAI's guide says a branded plugin sourced from a personal account
# "will be questioned". There the plugin's files are at the repo ROOT, so no
# `path` is needed at all.
ORG_URL = "https://github.com/RelayShield/relayshield-plugin.git"
# The monorepo remains a fallback, and stays valid: .claude-plugin/marketplace.json
# still sources ./plugins/relayshield, so `claude plugin marketplace add
# nzdsf2-gif/relayshield` keeps working and the published blog post stays true.
PLUGIN_SUBDIR = "plugins/relayshield"
REMOTE_URL = "https://github.com/nzdsf2-gif/relayshield.git"


def _git(*args: str) -> str:
    return subprocess.check_output(("git",) + args, cwd=ROOT, text=True).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="origin/main",
                    help="revision to pin (default: origin/main)")
    ap.add_argument("--from-monorepo", action="store_true",
                    help="pin nzdsf2-gif/relayshield at plugins/relayshield instead of "
                         "the org repo. Only for a submission made before the org "
                         "move lands; it is the shape xAI's guide questions.")
    args = ap.parse_args()

    if not args.from_monorepo:
        # Read the org repo's own HEAD. Nothing local can vouch for it, so it is
        # resolved against the remote rather than assumed.
        try:
            out = subprocess.check_output(
                ["git", "ls-remote", ORG_URL, "HEAD"], text=True, timeout=90,
                stderr=subprocess.DEVNULL).split()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            print("ERROR: cannot read HEAD of\n"
                  f"       {ORG_URL}\n"
                  "       Create the org repo and push the plugin first (see FD-13 in\n"
                  "       FRONT_DOORS.md), or pass --from-monorepo to pin the monorepo.",
                  file=sys.stderr)
            return 1
        if not out:
            print(f"ERROR: {ORG_URL} has no HEAD. Push the first commit.", file=sys.stderr)
            return 1
        sha = out[0]
        entry = _entry(ORG_URL, sha, path=None)
        print(json.dumps(entry, indent=2))
        return 0

    try:
        sha = _git("rev-parse", args.rev)
    except subprocess.CalledProcessError:
        print(f"ERROR: cannot resolve {args.rev!r}", file=sys.stderr)
        return 1

    if len(sha) != 40 or sha != sha.lower() or not all(c in "0123456789abcdef" for c in sha):
        print(f"ERROR: {sha!r} is not a 40-character lowercase hex SHA", file=sys.stderr)
        return 1

    # The commit must be REACHABLE on the remote. Their index generator clones and
    # runs `git rev-parse HEAD == sha`, so an unpushed commit fails their CI with an
    # error that reads like a broken catalog rather than an unpushed branch.
    remote_heads = _git("ls-remote", "--heads", "origin")
    if sha not in remote_heads:
        try:
            _git("merge-base", "--is-ancestor", sha, "origin/main")
        except subprocess.CalledProcessError:
            print(f"ERROR: {sha} is not an ancestor of origin/main.\n"
                  f"       Push it before pinning it, or their CI cannot fetch it.",
                  file=sys.stderr)
            return 1

    # The plugin must actually exist at that commit, at that path.
    try:
        listing = _git("ls-tree", "-r", "--name-only", sha, "--", PLUGIN_SUBDIR)
    except subprocess.CalledProcessError:
        listing = ""
    required = [f"{PLUGIN_SUBDIR}/.claude-plugin/plugin.json",
                f"{PLUGIN_SUBDIR}/.mcp.json"]
    missing = [r for r in required if r not in listing]
    if missing:
        print("ERROR: the pinned commit does not carry the plugin:\n  "
              + "\n  ".join(missing), file=sys.stderr)
        return 1

    entry = _entry(REMOTE_URL, sha, path=PLUGIN_SUBDIR)
    print(json.dumps(entry, indent=2))
    return 0


def _entry(url, sha, path):
    source = {"source": "url", "url": url, "sha": sha}
    if path:
        source["path"] = path
    return {
        "name": "relayshield",
        "description": (
            "Counterparty screening for agents. Scans the instruction files a repository "
            "gives an agent (README, AGENTS.md, CLAUDE.md, .cursorrules, MCP manifests) for "
            "text that would make it fetch and execute remote code, ignore prior "
            "instructions, or open credential files, then checks every domain those "
            "instructions reference against indicators collected from criminal channels. "
            "Also screens MCP servers for typosquat distance and registration age."
        ),
        "category": "security",
        "source": source,
        "homepage": "https://relayshield.net",
        # Brand-scoped on purpose. Their guide pushes back on generic terms like
        # "api", "cli" and "security" because keywords power Grok Build's proactive
        # plugin CTA, and a generic term mis-fires it on unrelated requests.
        "keywords": ["relayshield", "agent bait scan", "mcp registry risk", "relayshield scan"],
        "domains": ["relayshield.net", "api.relayshield.net"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
