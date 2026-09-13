#!/usr/bin/env python3
"""Put the resolved address INTO each draft, so the file is send-ready.

WHY THIS EXISTS, IN THE FOUNDER'S WORDS (2026-09-13): "You identified the second
batch of prospects but you failed to provide email contact addresses which I
require. In the first batch we learned that websites are generally unuseful as
they don't often provide email contacts."

He is right, and the gap was a MISSING JOIN rather than missing work.
tools/resolve_prospect_emails.py finds the addresses and writes JSONL.
outreach_bot_prospects_batch2.md holds the copy. Nothing put them together, so
the deliverable was a document naming its channel as a question plus a data file
somewhere else, and merging fifteen of those by hand is exactly the friction that
turned batch 1's candidates into a 50% send rate.

WHAT IT DOES, AND THE ONE RULE THAT MATTERS:

  * A prospect WITH an address gets a `**To:** addr` line under its heading and
    stays in the send list.
  * A prospect WITHOUT one is MOVED to a section at the end headed "no address,
    do not chase". It is not deleted and it is not quietly left in place looking
    sendable.

THE SECOND IS THE POINT. A draft with no To: line sitting among fifteen that have
one is an invitation to go hunting for a website, and the founder's own
measurement says a website is not a contact. Separating them makes the send list
exactly the reachable rows, which is the number worth tracking.

    python3 tools/merge_prospect_emails.py \
        --drafts outreach_bot_prospects_batch2.md \
        --resolved prospects_batch2.jsonl

Writes <drafts>.sendready.md beside it. The source file is never modified: the
drafts are the durable artefact and the addresses go stale.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    from contact_hygiene import usable_email as is_usable_email   # type: ignore
except Exception:                                        # pragma: no cover
    def is_usable_email(addr: str) -> bool:
        return bool(addr) and "@" in addr


# "## 13. owner/repo (15 stars)" -- the number and the repo both matter, because
# the repo is the join key and the number is what the founder refers to.
HEADING = re.compile(r"^##\s+(\d+)\.\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")


def load_resolved(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        repo = (row.get("repository") or "").strip()
        email = (row.get("email") or "").strip()
        if not repo:
            continue
        # Re-screen here rather than trusting the upstream file. A resolved
        # JSONL can be weeks old and hygiene is cheap; this is the last thing
        # standing before a message goes out, which is where the 2026-09-03
        # extractor defect was finally caught.
        if email and not is_usable_email(email):
            email = ""
        out[repo.lower()] = {"email": email,
                             "source": row.get("email_source") or "",
                             "owner_name": row.get("owner_name") or ""}
    return out


def split_sections(lines):
    """(preamble, [(number, repo, [lines]), ...]). Everything before the first
    numbered heading is preamble and is carried through untouched."""
    preamble, sections, cur = [], [], None
    for ln in lines:
        m = HEADING.match(ln)
        if m:
            if cur:
                sections.append(cur)
            cur = [int(m.group(1)), m.group(2), [ln]]
            continue
        (cur[2] if cur else preamble).append(ln)
    if cur:
        sections.append(cur)
    return preamble, sections


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", required=True, type=Path)
    ap.add_argument("--resolved", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    for p in (args.drafts, args.resolved):
        if not p.exists():
            raise SystemExit(f"ERROR: {p} does not exist.")

    resolved = load_resolved(args.resolved)
    if not resolved:
        # A floor, for the reason tools/source_arrivals.py carries one: an empty
        # parse looks exactly like "nobody is reachable" and gets acted on.
        raise SystemExit(f"ERROR: {args.resolved} parsed but holds no rows. "
                         "Reporting every prospect as unreachable on that would "
                         "be a false absence.")

    preamble, sections = split_sections(args.drafts.read_text().splitlines())
    if not sections:
        raise SystemExit(f"ERROR: no '## <n>. owner/repo' headings in {args.drafts}.")

    send, drop, unresolved = [], [], []
    for number, repo, body in sections:
        hit = resolved.get(repo.lower())
        if hit is None:
            unresolved.append(repo)
            drop.append((number, repo, body, "not in the resolved file"))
        elif hit["email"]:
            body = [body[0], "", f"**To:** {hit['email']}"
                    + (f"  ({hit['source']})" if hit["source"] else "")] + body[1:]
            send.append((number, repo, body))
        else:
            drop.append((number, repo, body, "no deliverable address found"))

    out_path = args.out or args.drafts.with_suffix(".sendready.md")
    with out_path.open("w") as fh:
        fh.write("\n".join(preamble).rstrip() + "\n")
        fh.write(f"\n---\n\n# SEND LIST: {len(send)} of {len(sections)} reachable\n\n")
        fh.write("Every draft below carries a real address. A few a day, by hand.\n"
                 "The number worth tracking is candidates that became a SENT\n"
                 "message, not candidates found.\n\n")
        for _n, _r, body in send:
            fh.write("\n".join(body).rstrip() + "\n\n")
        fh.write(f"\n---\n\n# NO ADDRESS, DO NOT CHASE: {len(drop)}\n\n")
        fh.write("A website is not a contact. Chasing these through a contact\n"
                 "form is what turned batch 1's candidates into a 50% send rate,\n"
                 "so they are parked here rather than left looking sendable.\n\n")
        for n, r, _body, why in drop:
            fh.write(f"- **{n}. {r}** -- {why}\n")
        fh.write("\n")

    print(f"send list  {len(send)}")
    print(f"no address {len(drop)}")
    if unresolved:
        print("\nNOT IN THE RESOLVED FILE, so they were never looked up:")
        for r in unresolved:
            print(f"  {r}")
        print("Add them to the --in list and re-run resolve_prospect_emails.py.")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
