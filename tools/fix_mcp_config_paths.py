#!/usr/bin/env python3
"""Repoint MCP client configs at the moved clone. Dry-run by default.

    python3 tools/fix_mcp_config_paths.py            # show what would change
    python3 tools/fix_mcp_config_paths.py --write    # apply, after a backup

WHY THIS EXISTS
---------------
Moving the clone from `~/Side SaaS Hustle` to `~/dev/relayshield` on 2026-09-05
broke the RelayShield MCP server in Claude Desktop and Claude Code. Both configs
launch it by ABSOLUTE PATH:

    /Users/andrewgibbs/anaconda3/bin/python3 \\
      /Users/andrewgibbs/Side SaaS Hustle/relayshield_mcp_server.py

and the log said so plainly, every few minutes, for hours:

    can't open file '.../Side SaaS Hustle/relayshield_mcp_server.py':
    [Errno 2] No such file or directory

THE LESSON, WHICH IS BIGGER THAN THIS FILE
-------------------------------------------
The move was made safe INSIDE the repo by deriving paths from
`Path(__file__).resolve().parent`. That fix could never reach these configs,
because they live in application support directories that the repo does not own
and cannot see. **An absolute path to the clone can exist anywhere on the
machine**, and moving the clone breaks every one of them silently -- the client
shows "disconnected", not "the path moved".

So the move checklist has a second half: after relocating the clone, grep the
places outside it that name it. MCP client configs, launchd plists, cron, shell
aliases, IDE run configurations.

SAFETY
------
Backs up every file it touches with a timestamp suffix before writing, prints a
redacted diff (an MCP config holds RELAYSHIELD_API_KEY in plain text and this
output goes into a chat), and is idempotent: a second run finds nothing to do.
"""

import argparse
import datetime
import json
import os
import shutil
import sys

HOME = os.path.expanduser("~")
OLD = os.path.join(HOME, "Side SaaS Hustle")
NEW = os.path.join(HOME, "dev", "relayshield")

TARGETS = [
    ("Claude Desktop", f"{HOME}/Library/Application Support/Claude/claude_desktop_config.json"),
    ("Claude Code (user)", f"{HOME}/.claude.json"),
    ("Claude Code (settings)", f"{HOME}/.claude/settings.json"),
    ("Cursor", f"{HOME}/.cursor/mcp.json"),
    ("Windsurf", f"{HOME}/.codeium/windsurf/mcp_config.json"),
    ("VS Code", f"{HOME}/Library/Application Support/Code/User/mcp.json"),
]

SECRET_HINTS = ("key", "token", "secret", "password", "payment")


def redact_pair(k, v):
    if any(h in str(k).lower() for h in SECRET_HINTS):
        s = str(v)
        return f"{s[:4]}… ({len(s)} chars)" if s else "(empty)"
    return v


def rewrite(node, changes, path="$"):
    """Walks the document replacing OLD with NEW in every string, and in dict
    KEYS too -- Claude Code files its MCP servers under the project's absolute
    path, so the key itself names the old location."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            nk = k.replace(OLD, NEW) if isinstance(k, str) and OLD in k else k
            if nk != k:
                changes.append((f"{path} (key)", k, nk))
            out[nk] = rewrite(v, changes, f"{path}.{nk}")
        return out
    if isinstance(node, list):
        return [rewrite(v, changes, f"{path}[{i}]") for i, v in enumerate(node)]
    if isinstance(node, str) and OLD in node:
        new = node.replace(OLD, NEW)
        changes.append((path, node, new))
        return new
    return node


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="apply the changes")
    args = ap.parse_args()

    print(f"old clone path : {OLD}")
    print(f"new clone path : {NEW}")
    if not os.path.isdir(NEW):
        sys.exit(f"STOP: {NEW} does not exist. Nothing was changed. Has the move "
                 "actually happened?")
    if not os.path.isfile(os.path.join(NEW, "relayshield_mcp_server.py")):
        sys.exit(f"STOP: {NEW}/relayshield_mcp_server.py is missing, so repointing "
                 "the configs there would swap one broken path for another.")
    print()

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    touched = 0

    for label, path in TARGETS:
        if not os.path.exists(path):
            continue
        try:
            doc = json.load(open(path))
        except Exception as exc:
            print(f"  {label}: UNREADABLE ({exc}) -- skipped, fix by hand")
            continue

        changes = []
        new_doc = rewrite(doc, changes)
        if not changes:
            print(f"  {label}: nothing to change")
            continue

        touched += 1
        print(f"  {label}")
        print(f"    {path}")
        for where, before, after in changes:
            # `where` can name a secret field; redact by the leaf key.
            leaf = where.rsplit(".", 1)[-1]
            print(f"    {where}")
            print(f"      - {redact_pair(leaf, before)}")
            print(f"      + {redact_pair(leaf, after)}")

        if args.write:
            backup = f"{path}.bak-{stamp}"
            shutil.copy2(path, backup)
            with open(path, "w") as fh:
                json.dump(new_doc, fh, indent=2)
                fh.write("\n")
            print(f"    written. backup: {backup}")
        print()

    if not touched:
        print("\nNo config named the old path. Either this has already been run, or")
        print("the disconnect has a different cause -- re-read section 3 of")
        print("tools/mcp_inventory.sh rather than assuming.")
        return

    if not args.write:
        print("DRY RUN. Nothing was written. Re-run with --write to apply.")
    else:
        print("Done. QUIT AND REOPEN the client -- an MCP config is read at start,")
        print("so an edited file changes nothing until the app restarts.")


if __name__ == "__main__":
    main()
