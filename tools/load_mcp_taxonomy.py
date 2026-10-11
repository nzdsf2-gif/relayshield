#!/usr/bin/env python3
"""Load the approved MCP attack-pattern taxonomy entries into DynamoDB.

    AWS_PROFILE=relayshield python3 tools/load_mcp_taxonomy.py
    AWS_PROFILE=relayshield python3 tools/load_mcp_taxonomy.py --apply

Read-only without --apply: it prints, per entry, whether it would be CREATED,
UPDATED or is UNCHANGED, and writes nothing.

Source file: intel_taxonomy/mcp_attack_patterns_2026-10-10.json (override with
--file). Destination: relayshield_mcp_taxonomy, created by
tools/setup_mcp_taxonomy_table.sh. Run that first.

WHAT IS LOADED: STRONG and MODERATE fits only. THIN and UNKNOWN fits are listed
under "excluded_thin_fits" in the source and are never written.

IDEMPOTENT. Each entry is keyed on its id and carries a content_hash. Re-running
writes nothing unless an entry changed, and a changed entry keeps its original
first_loaded_at.

THE FILE ARRIVED AS AN UPLOAD, SO IT IS VALIDATED, NOT TRUSTED. Unknown fit,
unknown poison_category, a missing field, a duplicate id or an unapproved file
each stop the run before anything is written. boto3 is imported only after the
file has passed.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_FILE = REPO / "intel_taxonomy" / "mcp_attack_patterns_2026-10-10.json"
TABLE = "relayshield_mcp_taxonomy"
ACCOUNT = "239677749008"
TAXONOMY = "mcp_attack_patterns"

LOADABLE_FITS = frozenset({"STRONG", "MODERATE"})
# The five core categories the proposal maps against. Pinned against
# mcp_proxy/screener.py by test_mcp_taxonomy_loader.py.
CATEGORIES = frozenset({
    "prompt_injection", "malicious_url", "unknown_synthetic",
    "kit_match", "pii_leak",
})
REQUIRED = ("id", "fit", "poison_category", "disclosure", "attack_pattern",
            "description", "indicators", "mitigation")


def validate(doc: dict) -> list:
    """Return the entries to load. Raises ValueError on anything off-spec."""
    if doc.get("taxonomy") != TAXONOMY:
        raise ValueError(f"taxonomy is {doc.get('taxonomy')!r}, expected {TAXONOMY!r}")
    if not doc.get("approved_by") or not doc.get("approved_date"):
        raise ValueError("file carries no approved_by / approved_date: refusing to load")
    entries = doc.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("no entries")
    seen = set()
    for e in entries:
        missing = [k for k in REQUIRED if k not in e]
        if missing:
            raise ValueError(f"{e.get('id', '?')}: missing {missing}")
        if e["id"] in seen:
            raise ValueError(f"duplicate id {e['id']}")
        seen.add(e["id"])
        if e["fit"] not in LOADABLE_FITS:
            raise ValueError(f"{e['id']}: fit {e['fit']!r} is not loadable "
                             f"(only {sorted(LOADABLE_FITS)})")
        if e["poison_category"] not in CATEGORIES:
            raise ValueError(f"{e['id']}: unknown poison_category {e['poison_category']!r}")
        if not isinstance(e["indicators"], list) or not e["indicators"]:
            raise ValueError(f"{e['id']}: indicators must be a non-empty list")
    return entries


def content_hash(e: dict) -> str:
    return hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--file", default=str(DEFAULT_FILE))
    args = ap.parse_args()

    doc = json.loads(Path(args.file).read_text())
    try:
        entries = validate(doc)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(f"file: {args.file}")
    print(f"validated {len(entries)} entries "
          f"(approved by {doc['approved_by']} on {doc['approved_date']}, "
          f"taxonomy version {doc.get('version')})")

    import boto3
    from botocore.exceptions import ClientError

    got = boto3.client("sts").get_caller_identity()["Account"]
    if got != ACCOUNT:
        print(f"STOP: credentials resolve to account {got}, not {ACCOUNT}. "
              f"Nothing was read or written.", file=sys.stderr)
        return 1

    table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    try:
        table.load()
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"STOP: table {TABLE} does not exist. "
                  f"Run: sh tools/setup_mcp_taxonomy_table.sh", file=sys.stderr)
            return 1
        raise

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts = {"CREATED": 0, "UPDATED": 0, "UNCHANGED": 0}
    for e in entries:
        h = content_hash(e)
        existing = table.get_item(Key={"entry_id": e["id"]}).get("Item")
        if existing is None:
            verdict = "CREATED"
        elif existing.get("content_hash") == h:
            verdict = "UNCHANGED"
        else:
            verdict = "UPDATED"
        counts[verdict] += 1
        print(f"  {verdict:9} {e['fit']:8} {e['poison_category']:18} {e['id']}")
        if verdict == "UNCHANGED" or not args.apply:
            continue
        item = {
            "entry_id": e["id"],
            "taxonomy": TAXONOMY,
            "taxonomy_version": doc.get("version", ""),
            "disclosure": e["disclosure"],
            "fit": e["fit"],
            "poison_category": e["poison_category"],
            "attack_pattern": e["attack_pattern"],
            "description": e["description"],
            "indicators": e["indicators"],
            "mitigation": e["mitigation"],
            "approved_by": doc["approved_by"],
            "approved_date": doc["approved_date"],
            "content_hash": h,
            "first_loaded_at": existing["first_loaded_at"] if existing else now,
            "updated_at": now,
        }
        table.put_item(Item=item)

    print()
    print("  ".join(f"{k}={v}" for k, v in counts.items()))
    if not args.apply:
        print("DRY RUN: nothing written. Re-run with --apply to write.")
    else:
        print(f"wrote {counts['CREATED'] + counts['UPDATED']} item(s) to {TABLE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
