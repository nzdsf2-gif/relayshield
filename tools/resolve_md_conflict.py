#!/usr/bin/env python3
"""Resolve a git conflict in an APPEND-STRUCTURED markdown file by keeping BOTH sides.

WHY THIS EXISTS. CLAUDE.md conflicts on almost every merge now, and it is
arithmetic rather than bad luck: every session appends a section, so two
sessions in a day append to the same region of the same file and git cannot
know that two new sections are not a contradiction. The resolution is always
the same -- KEEP BOTH SIDES, because two appended sections are two appended
sections and never an either/or.

That rule is simple and the execution is not: it means opening a 3,000-line
file and deleting three marker lines per conflict without disturbing anything
else. On 2026-09-10 Andrew hit the conflict, stopped there, and the merge sat
unresolved for two days -- blocking `git stash` and every later `git merge`,
which then failed with "Merging is not possible because you have unmerged
files" and read like a new problem.

So the rule is carried by a script instead of by an instruction.

WHAT IT DOES NOT DO, and this is deliberate. Keeping both sides is mechanically
right and occasionally leaves something a person must judge -- most often two
copies of a heading, when one session supersedes a list another session
regenerated. That happened for real: a Top 15 heading for 2026-09-08 and one
for 2026-09-09 both survived, and the stale one had to be dropped by hand.
So this reports duplicate headings after resolving and says plainly that they
are a human's call. It does not guess which one to drop.

    python3 tools/resolve_md_conflict.py CLAUDE.md            # dry run
    python3 tools/resolve_md_conflict.py CLAUDE.md --write

It refuses a file with no conflict markers, and refuses one whose markers do
not nest correctly, rather than writing something half-resolved.
"""

import argparse
import re
import sys
from pathlib import Path

OURS = "<<<<<<< "
SEP = "======="
THEIRS = ">>>>>>> "


def resolve(lines):
    """Return (resolved_lines, n_conflicts). Keeps ours then theirs, drops markers."""
    out, n, i = [], 0, 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith(OURS):
            out.append(line)
            i += 1
            continue

        # Collect this conflict block.
        i += 1
        ours = []
        while i < len(lines) and not lines[i].startswith(SEP):
            if lines[i].startswith(OURS):
                raise SystemExit(f"ERROR: nested '{OURS}' near line {i + 1}. Not resolving.")
            ours.append(lines[i])
            i += 1
        if i >= len(lines):
            raise SystemExit(f"ERROR: '{OURS}' with no '{SEP}'. Not resolving.")

        i += 1  # skip the =======
        theirs = []
        while i < len(lines) and not lines[i].startswith(THEIRS):
            theirs.append(lines[i])
            i += 1
        if i >= len(lines):
            raise SystemExit(f"ERROR: '{SEP}' with no '{THEIRS}'. Not resolving.")
        i += 1  # skip the >>>>>>>

        # BOTH sides, ours first, with exactly one blank line between them so a
        # heading never ends up welded to the previous section's last line.
        out.extend(ours)
        if ours and ours[-1].strip() != "" and theirs and theirs[0].strip() != "":
            out.append("\n")
        out.extend(theirs)
        n += 1
    return out, n


# A heading stripped of trailing dates and digits. "THE TOP 15, REGENERATED
# 2026-09-08" and "... 2026-09-09" are the case that actually occurs, and they
# are NOT equal strings -- an exact-match check sails straight past the one
# collision this repo has really had. Tested against that pair rather than
# against a fixture written to match the assumption.
_STEM = re.compile(r"[\s,._:-]*\b\d{4}-\d{2}-\d{2}\b[\s,._:-]*$|[\s,._:-]*\d+[\s,._:-]*$")


def _stem(heading):
    prev = None
    out = heading.strip()
    while out != prev:            # strip a trailing date AND a trailing number
        prev = out
        out = _STEM.sub("", out)
    return out.rstrip(" ,.:-").upper()


def duplicate_headings(lines):
    """Exact duplicates AND near-duplicates that differ only by a trailing date."""
    seen, dupes = {}, []
    for idx, line in enumerate(lines, 1):
        if re.match(r"^#{1,4} \S", line):
            text = line.strip()
            key = _stem(text)
            if not key:
                continue
            if key in seen:
                prev_idx, prev_text = seen[key]
                exact = prev_text == text
                dupes.append((prev_text, text, prev_idx, idx, exact))
            else:
                seen[key] = (idx, text)
    return dupes


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--write", action="store_true", help="apply; otherwise dry run")
    args = ap.parse_args()

    p = Path(args.path)
    if not p.is_file():
        raise SystemExit(f"ERROR: {p} is not a file.")
    lines = p.read_text().splitlines(keepends=True)

    if not any(l.startswith(OURS) for l in lines):
        print(f"{p}: no conflict markers. Nothing to do.")
        return 0

    resolved, n = resolve(lines)
    leftover = [l for l in resolved if l.startswith((OURS, THEIRS)) or l.rstrip("\n") == SEP]
    if leftover:
        raise SystemExit(f"ERROR: {len(leftover)} marker line(s) survived. Not writing.")

    print(f"{p}: {n} conflict(s), both sides kept.")
    print(f"  {len(lines)} lines in -> {len(resolved)} lines out")

    dupes = duplicate_headings(resolved)
    if dupes:
        print("\n  DUPLICATE HEADINGS after resolving. Keeping both sides is")
        print("  mechanically right and these are a judgement call -- usually one")
        print("  session superseding a list another regenerated. Read them and drop")
        print("  the stale one BY HAND; this tool deliberately does not choose:")
        for prev_text, text, first, second, exact in dupes:
            kind = "IDENTICAL" if exact else "SAME SECTION, DIFFERENT DATE"
            print(f"    {kind}")
            print(f"      line {first}: {prev_text[:74]}")
            print(f"      line {second}: {text[:74]}")

    if not args.write:
        print("\nDry run. Re-run with --write to apply.")
        return 0

    p.write_text("".join(resolved))
    print(f"\nWROTE {p}. Now: git add {p} && git commit --no-edit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
