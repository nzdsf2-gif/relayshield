#!/usr/bin/env python3
"""Did any OSINT-sweep keyword actually produce a channel?  READ-ONLY.

WHY THIS EXISTS
---------------
Sweeps 001, 001b, 002 and 003 each added keywords to SEARCH_KEYWORDS in
relayshield_intel_discovery.py. Nobody has measured whether any of them found a
channel, because the table lives in AWS and the scheduled sessions have no
credentials. This answers it by reading the table directly.

TWO THINGS IT REPORTS, AND THE SECOND ONE MATTERS MORE
------------------------------------------------------
1. YIELD. For every keyword, the rows in relayshield_intel_channels whose
   `keyword_match` equals it.
2. WAS IT EVER LIVE. relayshield_intel_discovery.py is NOT in the LAMBDA_MAP of
   deploy_lambdas.yml, so merging a keyword to main does not deploy it. The weekly
   workflow only INVOKES the Lambda that is already there. A keyword that is in
   the repo but not in the deployed code cannot have produced anything, and
   "zero rows" for it says nothing about the keyword. So this also downloads the
   deployed code and marks each keyword live or NOT DEPLOYED.

HOW TO READ A ZERO
------------------
`keyword_match` is written only when a keyword's search turns up a channel that is
NOT already an active row. A channel an earlier keyword (or the cross-promotion
crawl, or the seeded list) already holds is only re-verified and is credited to
nobody. So zero rows for a deployed keyword means "nothing NEW", not "nothing
found". It is a lower bound on what the keyword reached.

USAGE (on the founder's Mac)

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/keyword_yield.py
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/keyword_yield.py --no-deployed

Needs boto3 (python3 -m venv ~/.rsvenv && ~/.rsvenv/bin/pip install boto3).
Needs dynamodb:Scan on the table and, for the deployed check, lambda:GetFunction.
The deployed check fails soft: without that permission the yield report still prints.
"""

import argparse
import io
import re
import sys
import urllib.request
import zipfile
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DISCOVERY_FILE = REPO_ROOT / "relayshield_intel_discovery.py"

TABLE = "relayshield_intel_channels"
FUNCTION = "relayshield-intel-discovery"
REGION = "us-east-1"
EXPECTED_ACCOUNT = "239677749008"

_TUPLE_RE = re.compile(r'^\s*\(\s*"([^"]+)"\s*,\s*"([a-z_]+)"\s*\)')
_SWEEP_MARKER_RE = re.compile(r"^\s*#\s*---\s*OSINT sweep (\w+)", re.I)
# This comment block belongs to sweep 001 even though a blank line precedes it.
_STILL_SWEEP_001_RE = re.compile(r"card-shop keywords added 2026-08-21", re.I)

SWEEP_ORDER = ["001", "001b", "002", "003"]


def parse_keywords(source):
    """Return [(keyword, category, label)] from a discovery source file's text.

    label is "sweep 001" / "sweep 001b" / ... or "baseline" for keywords outside a
    sweep block. A sweep block starts at its `# --- OSINT sweep NNN` marker and ends
    at the first blank line that is followed by an ordinary comment.
    """
    start = source.find("SEARCH_KEYWORDS = [")
    if start < 0:
        raise ValueError("SEARCH_KEYWORDS not found")
    end = source.find("\n]\n", start)
    block = source[start:end if end > 0 else len(source)]

    out, label, after_blank = [], "baseline", False
    for line in block.splitlines():
        stripped = line.strip()
        marker = _SWEEP_MARKER_RE.match(line)
        if marker:
            label, after_blank = f"sweep {marker.group(1)}", False
        elif not stripped:
            after_blank = True
        elif stripped.startswith("#"):
            if after_blank and not _STILL_SWEEP_001_RE.search(stripped):
                label = "baseline"
            after_blank = False
        else:
            after_blank = False
            tup = _TUPLE_RE.match(line)
            if tup:
                out.append((tup.group(1), tup.group(2), label))
    return out


def summarize(keywords, rows, deployed=None):
    """Pure function: keywords + table rows (+ deployed keyword set) -> report text."""
    by_kw = {}
    for r in rows:
        kw = r.get("keyword_match")
        if kw:
            by_kw.setdefault(kw, []).append(r)

    repo_names = {k for k, _, _ in keywords}
    lines = []
    firsts = sorted(str(r.get("first_seen")) for r in rows if r.get("keyword_match") and r.get("first_seen"))
    lines.append(f"Rows with a keyword_match : {sum(len(v) for v in by_kw.values())}")
    if firsts:
        lines.append(f"Newest keyword-matched row: first_seen {firsts[-1][:10]} (oldest {firsts[0][:10]})")
    lines.append("")

    sweeps = OrderedDict((f"sweep {s}", []) for s in SWEEP_ORDER)
    for k, c, lab in keywords:
        if lab in sweeps:
            sweeps[lab].append((k, c))

    for lab, items in sweeps.items():
        if not items:
            continue
        hit = [k for k, _ in items if by_kw.get(k)]
        n_rows = sum(len(by_kw.get(k, [])) for k, _ in items)
        n_active = sum(1 for k, _ in items for r in by_kw.get(k, []) if r.get("active") is True)
        head = f"{lab.upper()}: {len(items)} keywords, {len(hit)} produced rows, {n_rows} rows ({n_active} active)"
        if deployed is not None:
            live = sum(1 for k, _ in items if k in deployed)
            head += f", {live}/{len(items)} present in the DEPLOYED Lambda"
        lines.append(head)
        for k, c in items:
            rs = by_kw.get(k, [])
            tag = ""
            if deployed is not None:
                tag = "  [live]" if k in deployed else "  [NOT DEPLOYED]"
            if rs:
                who = ", ".join(
                    f"@{r.get('username')}({int(r.get('member_count') or 0)})" for r in rs[:4]
                ) + (f" +{len(rs) - 4} more" if len(rs) > 4 else "")
                lines.append(f"  {k!r:34} {c:16} {len(rs):3} rows  {who}{tag}")
            else:
                lines.append(f"  {k!r:34} {c:16}   0 rows{tag}")
        lines.append("")

    orphan = sorted(k for k in by_kw if k not in repo_names)
    if orphan:
        lines.append(
            f"keyword_match values NOT in the repo's SEARCH_KEYWORDS: {len(orphan)} "
            f"({sum(len(by_kw[k]) for k in orphan)} rows). Keywords since removed or edited: "
            + ", ".join(repr(k) for k in orphan[:12]) + (" ..." if len(orphan) > 12 else "")
        )
    if deployed is not None:
        missing = sorted(repo_names - deployed)
        lines.append(
            f"Repo keywords absent from the deployed Lambda: {len(missing)} of {len(repo_names)}"
        )
    lines.append("")
    if deployed is not None:
        lines.append(
            "Zero rows for a [live] keyword means nothing NEW (its hits were already tracked), "
            "not that it found nothing. Zero rows for a [NOT DEPLOYED] keyword says nothing at all."
        )
    else:
        lines.append(
            "Deployed-code check not run, so zero rows is ambiguous: it may mean nothing NEW, "
            "or that the keyword was never in the deployed Lambda."
        )
    return "\n".join(lines)


def scan_all(table, **kwargs):
    items, resp = [], table.scan(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def deployed_keywords(session):
    """Download the deployed discovery Lambda and parse its keyword list.

    Returns (set_of_keywords, last_modified) or raises."""
    client = session.client("lambda", region_name=REGION)
    fn = client.get_function(FunctionName=FUNCTION)
    url = fn["Code"]["Location"]
    with urllib.request.urlopen(url, timeout=60) as resp:  # presigned S3 URL
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if n.endswith("relayshield_intel_discovery.py")]
        if not names:
            raise RuntimeError("no relayshield_intel_discovery.py inside the deployed package")
        src = zf.read(names[0]).decode("utf-8", "replace")
    return {k for k, _, _ in parse_keywords(src)}, fn["Configuration"].get("LastModified")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-deployed", action="store_true", help="skip the deployed-code check")
    args = ap.parse_args(argv)

    import boto3
    from boto3.dynamodb.conditions import Attr

    session = boto3.Session()
    account = session.client("sts").get_caller_identity()["Account"]
    if account != EXPECTED_ACCOUNT:
        sys.exit(
            f"Refusing to run: credentials resolve to account {account}, not {EXPECTED_ACCOUNT}. "
            "Prefix the command with AWS_PROFILE=relayshield."
        )

    keywords = parse_keywords(DISCOVERY_FILE.read_text(encoding="utf-8"))
    table = session.resource("dynamodb", region_name=REGION).Table(TABLE)
    rows = scan_all(table, FilterExpression=Attr("keyword_match").exists())

    deployed, note = None, ""
    if not args.no_deployed:
        try:
            deployed, modified = deployed_keywords(session)
            note = f"Deployed Lambda {FUNCTION} last modified {modified}\n"
        except Exception as exc:  # fail soft: the yield report is still useful
            note = f"Deployed-code check skipped: {type(exc).__name__}: {exc}\n"

    print(note + summarize(keywords, rows, deployed))


if __name__ == "__main__":
    main()
