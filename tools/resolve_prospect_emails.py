#!/usr/bin/env python3
"""Turn a list of GitHub repos into prospects with a REAL email, or drop them.

WHY THIS EXISTS, IN THE FOUNDER'S WORDS (2026-09-08): "Less than 50% of the
initial candidates resulted in actual outreach messages (I sent roughly 10
emails). In general, without actual email contacts, links to websites rarely
produced actual contacts to message."

That is the measurement that should change the pipeline, and it does. The old
scoring treated "has a website" as contactability worth points, so half the list
was unreachable by the only channel that gets used. **A website is not a contact.**
This resolves an actual address or drops the row.

THREE SOURCES, IN DESCENDING ORDER OF HOW WELL THEY WORK:

  1. The owner's PUBLIC PROFILE EMAIL. Explicitly published; the strongest signal
     that mail is welcome. Perhaps a fifth of accounts set it.
  2. The AUTHOR EMAIL ON A RECENT COMMIT. Real and current, and the address the
     maintainer actually commits with. GitHub's privacy default replaces it with
     `<id>+<login>@users.noreply.github.com`, which is NOT deliverable and is
     rejected here rather than counted.
  3. An address in the README or a funding/support file. Weakest, and the one
     that produced `root@203.0.113.4` and `trial@telegram.bot` in the 2026-09-02
     sweep, so tools/contact_hygiene.py screens it exactly as before.

NEEDS A GITHUB TOKEN, so it runs on the Mac. api.github.com is scoped away from
this container: an unauthenticated call returns 403 and a repo call returns "not
enabled for this session", which looks like a missing repo and is not.

    export GITHUB_TOKEN=...        # or gh auth token
    python3 tools/resolve_prospect_emails.py --in candidates.txt --out prospects_emailed.jsonl

`--in` is one `owner/repo` per line, `#` comments allowed.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
NOREPLY = "users.noreply.github.com"

sys.path.insert(0, str(ROOT / "tools"))
try:
    from contact_hygiene import usable_email as is_usable_email   # type: ignore
except Exception:                                        # pragma: no cover
    def is_usable_email(addr: str) -> bool:
        return bool(addr) and "@" in addr and not addr.endswith(NOREPLY)


def _get(path: str, token: str):
    req = urllib.request.Request(API + path)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "relayshield-prospector")
    try:
        with urllib.request.urlopen(req, timeout=30) as fh:
            return json.loads(fh.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 403 and "rate limit" in e.read().decode(errors="replace").lower():
            print("  rate limited, sleeping 60s", file=sys.stderr)
            time.sleep(60)
            return _get(path, token)
        return None
    except urllib.error.URLError:
        return None


def resolve(full_name: str, token: str) -> dict:
    owner, _, name = full_name.partition("/")
    row = {"repository": full_name, "email": "", "email_source": "", "owner": owner}

    profile = _get(f"/users/{owner}", token) or {}
    row["owner_type"] = profile.get("type", "")
    row["owner_name"] = profile.get("name") or ""

    email = (profile.get("email") or "").strip()
    if email and is_usable_email(email) and not email.endswith(NOREPLY):
        row["email"], row["email_source"] = email, "profile"
        return row

    commits = _get(f"/repos/{full_name}/commits?per_page=20", token) or []
    for c in commits:
        commit = (c.get("commit") or {}).get("author") or {}
        addr = (commit.get("email") or "").strip()
        author = c.get("author") or {}
        # Only the OWNER's own commits. A contributor's address is not a contact
        # for this project and mailing it is how a maintainer list becomes spam.
        if author.get("login", "").lower() != owner.lower():
            continue
        if addr and is_usable_email(addr) and not addr.endswith(NOREPLY):
            row["email"], row["email_source"] = addr, "commit"
            return row

    row["email_source"] = "none"
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True, type=Path)
    ap.add_argument("--out", dest="out", required=True, type=Path)
    args = ap.parse_args()

    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "ERROR: GITHUB_TOKEN is not set.\n"
            "       export GITHUB_TOKEN=$(gh auth token)\n"
            "       Never pass a token as an argument: it lands in shell history.")

    names = [l.strip() for l in args.src.read_text().splitlines()
             if l.strip() and not l.startswith("#")]
    rows = []
    for i, n in enumerate(names, 1):
        row = resolve(n, token)
        rows.append(row)
        mark = "OK " if row["email"] else "-- "
        print(f"{mark}{i:3d}/{len(names)}  {n:52s} {row['email_source']:8s} {row['email']}")

    with args.out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    reachable = [r for r in rows if r["email"]]
    print(f"\n{len(reachable)} of {len(rows)} have a real email "
          f"({100.0*len(reachable)/max(len(rows),1):.0f}%)")
    print(f"wrote {args.out}")
    print("\nMail ONLY the rows with an email. A row without one is not a prospect\n"
          "for this channel, and chasing it through a website is what produced a\n"
          "50% conversion from candidate to sent message.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
