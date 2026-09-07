#!/usr/bin/env python3
"""FD-13: mirror plugins/relayshield/ into RelayShield/relayshield-plugin, and
prove the two copies have not diverged.

WHY THE PLUGIN NEEDS A SECOND HOME AT ALL. xAI's marketplace guide is explicit:
"Source from your official org, not a personal account. A branded plugin sourced
from some-personal-account/acme-thing reads as a possible impersonation and WILL
be questioned." Our marketplace is nzdsf2-gif/relayshield, which is exactly that
shape. The org is already authoritative for the MCP registry record and rsscan,
so the plugin belongs there too.

WHY THIS IS A SYNC AND NOT A MOVE, which is the part worth reading. The published
agent-bait post tells readers, on a live page:

    claude plugin marketplace add nzdsf2-gif/relayshield
    claude plugin install relayshield@relayshield

Moving the plugin out of the monorepo breaks that command and makes a published
instruction false. So the monorepo stays a working marketplace and keeps its copy,
and the org repo becomes the canonical source that FD-13's catalog entry points
at. Nothing that already works stops working.

AND WHY THERE IS A --check MODE. This repo has been bitten by exactly this shape
before: rsscan/ in the monorepo is a stale snapshot of RelayShield/rsscan, and
FD-1's own entry has to warn that editing the pin here changes nothing anyone can
install. A second copy with nothing comparing them drifts silently, and drift you
cannot see is the most expensive kind. So the copies are byte-identical by
construction, `--check` is the alarm, and plugin.json's `repository` field was
repointed at the org repo so that identity is actually achievable.

Neither mode needs the org repo to be writable from a container: this script runs
on the Mac, where the push credential lives.

    python3 tools/sync_plugin_repo.py --clone-dir ~/dev/relayshield-plugin --check
    python3 tools/sync_plugin_repo.py --clone-dir ~/dev/relayshield-plugin --write
"""

import argparse
import filecmp
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "plugins" / "relayshield"

# Everything the plugin is. A file here and not in the org repo is a sync that
# never ran; a file there and not here is something added out of band.
TRACKED = [
    ".claude-plugin/plugin.json",
    ".mcp.json",
    "skills/relayshield-agent-bait/SKILL.md",
    "README.md",
    "LICENSE",
]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clone-dir", required=True,
                    help="local clone of RelayShield/relayshield-plugin")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="compare only, exit 1 on any difference")
    mode.add_argument("--write", action="store_true",
                      help="copy this repo's plugin over the clone")
    args = ap.parse_args()

    dest = Path(args.clone_dir).expanduser().resolve()
    if not dest.is_dir():
        print(f"ERROR: {dest} is not a directory. Clone the org repo there first.",
              file=sys.stderr)
        return 1
    if args.check and not (dest / ".git").exists():
        print(f"NOTE: {dest} is not a git clone. Comparing anyway.", file=sys.stderr)

    missing_src = [rel for rel in TRACKED if not (SRC / rel).is_file()]
    if missing_src:
        print("ERROR: the source plugin is incomplete:\n  " + "\n  ".join(missing_src),
              file=sys.stderr)
        return 1

    differences = []
    for rel in TRACKED:
        s, d = SRC / rel, dest / rel
        if not d.is_file():
            differences.append((rel, "missing in the org repo"))
        elif not filecmp.cmp(s, d, shallow=False):
            differences.append((rel, f"differs  ({_digest(s)} here, {_digest(d)} there)"))

    # A file in the org repo that this repo does not know about is drift too, and
    # it is the direction that produced the rsscan problem: work done in the other
    # copy, invisible from here.
    extras = []
    for path in sorted(dest.rglob("*")):
        if path.is_dir() or ".git/" in str(path.relative_to(dest)):
            continue
        rel = str(path.relative_to(dest))
        if rel.startswith(".git"):
            continue
        if rel not in TRACKED:
            extras.append(rel)

    if args.check:
        if not differences and not extras:
            print(f"IN SYNC: {len(TRACKED)} files identical in {dest}")
            return 0
        for rel, why in differences:
            print(f"  DRIFT   {rel}: {why}")
        for rel in extras:
            print(f"  EXTRA   {rel}: present in the org repo, not tracked here")
        print("\nOut of sync. Run with --write, read the diff, then commit in the "
              "org repo.\nIf an EXTRA file is real work done there, bring it back "
              "here FIRST -- a --write would delete it.")
        return 1

    if extras:
        print("REFUSING TO WRITE. The org repo carries files this repo does not:\n  "
              + "\n  ".join(extras)
              + "\n\nThat is the 2026-08-17 hand-deploy shape in a second repo: a copy\n"
                "holding work no commit here has ever held. Recover them into\n"
                "plugins/relayshield/ first, then sync.", file=sys.stderr)
        return 1

    for rel in TRACKED:
        s, d = SRC / rel, dest / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    print(f"WROTE {len(TRACKED)} files into {dest}")
    print("Now, in that directory: git add -A && git commit && git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
