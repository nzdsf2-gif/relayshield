#!/usr/bin/env python3
"""Review and promote MCP-proxy telemetry candidates into the IOC corpus.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/promote_mcp_candidates.py
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/promote_mcp_candidates.py --all
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/promote_mcp_candidates.py \\
        --approve <id-prefix> --reviewer NAME --evidence "what you checked" --confirm-host HOST
    ... add --apply to write. Without it, --approve is a dry run.
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/promote_mcp_candidates.py \\
        --reject <id-prefix> --reviewer NAME --reason "why"

This is the ONLY path from relayshield_mcp_proxy_telemetry (CAND# rows) into
relayshield_intel_iocs. The telemetry endpoint never writes the corpus, and the privacy
policy (section 12) promises "it is not added to our threat intelligence corpus ... unless
we have independently confirmed it". This script is where that promise is kept.

WHAT PROMOTING DOES, because it is easy to underrate: relayshield_api._assess_domain flags
ANY relayshield_intel_iocs row of type domain/url as "this domain appears in RelayShield's
criminal IOC corpus". It reads no confidence or source field. So a promoted host starts
flagging for /v1/link-check, /v1/composite-check and every MCP proxy that screens through
them, immediately. A wrong promotion is a false positive served to every user. That is why
a human approves each one and why every blocker below is checked AGAIN at approval time.

WHAT A CANDIDATE'S HOST IS: the hostname of the UPSTREAM MCP SERVER that served a flagged
response. It is NOT a host found inside the content. So the rules are about when a server
can be held responsible for what it served:

  * malicious_url and kit_match are NEVER promotable. The proxy derives them from OUR
    corpus (composite-check, scamkit-match). Promoting them would feed our own verdict back
    in as "independent" evidence: a loop that can make a false positive look corroborated.
  * Only categories the proxy decides from its OWN content analysis are promotable, and
    only for attacks a server controls: prompt_injection, credential_exfiltration,
    oauth_tampering.
  * A candidate with no taxonomy id is NOT promotable. The proxy records an approved-taxonomy
    id only for DISCOVERY-time findings (tools/list, prompts/list: metadata the server
    itself authors). Tool RESULTS are recorded with no id, and a result can relay
    third-party content, such as a repository or a document containing an injection, so the
    host is not the actor. test_promote_mcp_candidates pins this coupling to proxy.py.
  * Corroboration is distinct reporting ACCOUNTS (default 2), never report volume. A free key
    is minted from an email address alone, so this is a threshold and not proof.
  * Reserved documentation names, brand domains, and shared-hosting platforms themselves
    are never promotable. A specific tenant of a hosting platform is allowed, with a note.

--evidence IS REQUIRED to approve, and is stored on the corpus row. "Independently
confirmed" has to mean someone looked. Fetch the server's tools/list yourself and see it.

A zero is the normal output of a young pipeline. Reporting is opt-in; do not read an empty
list as a fault.
"""
import argparse
import ast
import ipaddress
import json
import pathlib
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal

ACCOUNT = "239677749008"
REGION = "us-east-1"
TELEMETRY_TABLE = "relayshield_mcp_proxy_telemetry"
IOCS_TABLE = "relayshield_intel_iocs"
ROOT = pathlib.Path(__file__).resolve().parent.parent

PROMOTABLE_CATEGORIES = frozenset({"prompt_injection", "credential_exfiltration", "oauth_tampering"})
ECHO_CATEGORIES = frozenset({"malicious_url", "kit_match"})
DEFAULT_MIN_REPORTERS = 2
MIN_EVIDENCE_CHARS = 20
CORPUS_TTL_DAYS = 365
STATUS_UNREVIEWED = "unreviewed"

_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
_ZERO_HASH = "0" * 64


# --- denylists, read from the API source so there is one copy ----------------------

def _literal(tree, name):
    """The literal value assigned to a module-level `name`. Handles frozenset({...})."""
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets, value = [t for t in node.targets if isinstance(t, ast.Name)], node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target], node.value
        else:
            continue
        if any(t.id == name for t in targets) and value is not None:
            if isinstance(value, ast.Call) and getattr(value.func, "id", "") == "frozenset":
                return ast.literal_eval(value.args[0]) if value.args else set()
            return ast.literal_eval(value)
    raise KeyError(name)


def load_denylists(api_source: str) -> dict:
    """Parsed, not imported: relayshield_api needs boto3 and AWS config at import time."""
    tree = ast.parse(api_source)
    brands = set()
    for domains in _literal(tree, "_EMAIL_BRAND_DOMAINS").values():
        brands.update(d.lower() for d in domains)
    platforms = {h.lower() for h in _literal(tree, "_EMAIL_PUBLIC_PAGE_HOSTS") if "/" not in h}
    deny = {"brands": brands, "platforms": platforms,
            "reserved_names": {n.lower() for n in _literal(tree, "_RESERVED_DOCUMENTATION_NAMES")},
            "reserved_tlds": {t.lower() for t in _literal(tree, "_RESERVED_SPECIAL_TLDS")}}
    # A floor: an empty list would turn every guard below into a pass.
    if len(deny["brands"]) < 20 or len(deny["platforms"]) < 10 or not deny["reserved_names"]:
        raise RuntimeError("denylists parsed from relayshield_api.py look empty; refusing to continue")
    return deny


def _under(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _is_ip(host: str):
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


# --- eligibility -------------------------------------------------------------------

def reporters_of(cand: dict) -> set:
    return {r for r in (cand.get("reporters") or ()) if r and r != "anon"}


def evaluate(cand: dict, deny: dict, min_reporters: int, corpus_known: bool):
    """-> (blockers, notes). No blockers means eligible for review, not that it is true."""
    blockers, notes = [], []
    host = str(cand.get("host", "")).strip().lower()
    category = cand.get("category", "")
    status = cand.get("status", STATUS_UNREVIEWED)

    if status != STATUS_UNREVIEWED:
        blockers.append(f"already decided (status={status})")
    if category in ECHO_CATEGORIES:
        blockers.append(f"{category} is derived from our own corpus, so it cannot corroborate it (echo)")
    elif category not in PROMOTABLE_CATEGORIES:
        blockers.append(f"{category or 'no category'} is not an attack a server controls; counts only")
    if not cand.get("taxonomy_id"):
        blockers.append("no taxonomy id: a tool-result finding, and a result can relay third-party "
                        "content, so the host is not shown to be the actor")
    n = len(reporters_of(cand))
    if n < min_reporters:
        blockers.append(f"{n} distinct reporting account(s), need {min_reporters}")
    if cand.get("payload_hash") == _ZERO_HASH:
        blockers.append("all-zero payload hash: a test fixture")

    ip = _is_ip(host)
    if ip is not None:
        if not ip.is_global:
            blockers.append("not a global address")
    elif not (host and "." in host and _HOST_RE.match(host)):
        blockers.append("not a valid public hostname")
    else:
        tld = host.rsplit(".", 1)[-1]
        if tld in deny["reserved_tlds"] or any(_under(host, r) for r in deny["reserved_names"]):
            blockers.append("reserved documentation or special-use name")
        for b in sorted(deny["brands"]):
            if _under(host, b):
                blockers.append(f"{b} is a brand's official domain")
                break
        for p in sorted(deny["platforms"]):
            if host == p:
                blockers.append(f"{p} is a shared hosting platform, not a tenant")
                break
            if host.endswith("." + p):
                notes.append(f"a tenant of {p}: confirm THIS tenant served the response, never the platform")
                break
    if corpus_known:
        blockers.append("already in the corpus")
    return blockers, notes


def corpus_row(cand: dict, reviewer: str, evidence: str, now_iso: str) -> dict:
    host = str(cand["host"]).strip().lower()
    return {
        "ioc_value": host, "seen_ts": now_iso,
        "ioc_type": "ip" if _is_ip(host) else "domain",
        "channel": "mcp_proxy_telemetry", "category": "mcp_proxy",
        "source": "mcp_proxy_telemetry",
        # A label, not a gate: relayshield_api reads no confidence field, so this row flags.
        "confidence": "unverified",
        "proxy_category": cand["category"], "taxonomy_id": cand.get("taxonomy_id", ""),
        "corroboration": {"distinct_reporters": len(reporters_of(cand)),
                          "report_count": int(cand.get("report_count", 0))},
        "candidate_id": cand["pk"][len("CAND#"):],
        "reviewer": reviewer, "evidence": evidence,
        "ttl": Decimal(int(time.time()) + CORPUS_TTL_DAYS * 86400),
    }


# --- operations (tables injected, so the logic runs with no AWS) -------------------

class Refused(Exception):
    pass


def _resolve(items: list, prefix: str) -> dict:
    prefix = prefix.strip().lower()
    if len(prefix) < 8:
        raise Refused("id prefix must be at least 8 characters")
    hits = [c for c in items if c.get("pk", "").startswith("CAND#" + prefix)]
    if not hits:
        raise Refused(f"no candidate starts with {prefix}")
    if len(hits) > 1:
        raise Refused(f"{len(hits)} candidates start with {prefix}; use more characters")
    return hits[0]


def _status_update(table, key, new_status, expect, extra=None):
    names = {"#st": "status"}
    values = {":new": new_status, ":expect": expect}
    sets = ["#st = :new"]
    for i, (k, v) in enumerate((extra or {}).items()):
        names[f"#x{i}"] = k
        values[f":x{i}"] = v
        sets.append(f"#x{i} = :x{i}")
    table.update_item(Key=key, UpdateExpression="SET " + ", ".join(sets),
                      ConditionExpression="#st = :expect",
                      ExpressionAttributeNames=names, ExpressionAttributeValues=values)


def approve(tel_table, iocs_table, items, prefix, *, deny, min_reporters, corpus_known,
            reviewer, evidence, confirm_host, apply, now_iso):
    """-> the corpus row (written only if apply). Raises Refused with the reason."""
    if not reviewer.strip():
        raise Refused("--reviewer is required")
    if len(evidence.strip()) < MIN_EVIDENCE_CHARS:
        raise Refused(f"--evidence is required ({MIN_EVIDENCE_CHARS}+ characters): say what you "
                      "checked. The privacy policy promises independent confirmation.")
    listed = _resolve(items, prefix)
    key = {"pk": listed["pk"], "sk": "CAND"}
    cand = tel_table.get_item(Key=key).get("Item") or {}      # fresh, never the scan copy
    if not cand:
        raise Refused("candidate vanished (expired?)")
    host = str(cand.get("host", "")).strip().lower()
    if confirm_host.strip().lower() != host:
        raise Refused(f"--confirm-host must be the candidate's host exactly ({host})")
    blockers, _ = evaluate(cand, deny, min_reporters, corpus_known(host))
    if blockers:
        raise Refused("not promotable: " + "; ".join(blockers))
    row = corpus_row(cand, reviewer.strip(), evidence.strip(), now_iso)
    if not apply:
        return row
    try:
        _status_update(tel_table, key, "promoting", STATUS_UNREVIEWED, {"reviewer": reviewer.strip()})
    except Exception as exc:
        raise Refused(f"could not claim the candidate (decided concurrently?): {exc}")
    try:
        iocs_table.put_item(Item=row)
    except Exception as exc:
        released = True
        try:
            _status_update(tel_table, key, STATUS_UNREVIEWED, "promoting")
        except Exception:
            released = False
        raise Refused(f"corpus write failed ({exc}); " + (
            "candidate released, safe to retry" if released else
            "candidate LEFT at status=promoting, reset it by hand before retrying"))
    _status_update(tel_table, key, "promoted", "promoting",
                   {"promoted_at": now_iso, "evidence": evidence.strip()})
    return row


def reject(tel_table, items, prefix, *, reviewer, reason, now_iso):
    if not reviewer.strip() or len(reason.strip()) < 5:
        raise Refused("--reviewer and --reason are required")
    cand = _resolve(items, prefix)
    try:
        _status_update(tel_table, {"pk": cand["pk"], "sk": "CAND"}, "rejected", STATUS_UNREVIEWED,
                       {"reviewer": reviewer.strip(), "reject_reason": reason.strip(),
                        "rejected_at": now_iso})
    except Exception as exc:
        raise Refused(f"could not reject (already decided?): {exc}")
    return cand


# --- CLI ---------------------------------------------------------------------------

def _scan_candidates(table) -> list:
    items, kw, pages = [], {}, 0
    while True:
        r = table.scan(**kw)
        pages += 1
        items += [i for i in r.get("Items", []) if i.get("pk", "").startswith("CAND#")]
        print(f"  scanned {pages} page(s), {len(items)} candidate(s)", file=sys.stderr)
        if not r.get("LastEvaluatedKey"):
            return items
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all", action="store_true", help="also list ineligible candidates with reasons")
    ap.add_argument("--min-reporters", type=int, default=DEFAULT_MIN_REPORTERS)
    ap.add_argument("--approve", metavar="ID_PREFIX")
    ap.add_argument("--reject", metavar="ID_PREFIX")
    ap.add_argument("--reviewer", default="")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--confirm-host", default="")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    import boto3
    from boto3.dynamodb.conditions import Key
    got = boto3.client("sts").get_caller_identity()["Account"]
    if got != ACCOUNT:
        print(f"STOP: credentials resolve to {got}, not {ACCOUNT}. Use AWS_PROFILE=relayshield.",
              file=sys.stderr)
        return 1
    ddb = boto3.resource("dynamodb", region_name=REGION)
    tel, iocs = ddb.Table(TELEMETRY_TABLE), ddb.Table(IOCS_TABLE)
    deny = load_denylists((ROOT / "relayshield_api.py").read_text(encoding="utf-8"))

    def corpus_known(host: str) -> bool:
        return bool(iocs.query(KeyConditionExpression=Key("ioc_value").eq(host),
                               Limit=1, ProjectionExpression="ioc_value").get("Items"))

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    items = _scan_candidates(tel)
    try:
        if args.approve:
            row = approve(tel, iocs, items, args.approve, deny=deny, min_reporters=args.min_reporters,
                          corpus_known=corpus_known, reviewer=args.reviewer, evidence=args.evidence,
                          confirm_host=args.confirm_host, apply=args.apply, now_iso=now_iso)
            shown = {k: (int(v) if isinstance(v, Decimal) else v) for k, v in row.items()}
            print(("WROTE to " if args.apply else "DRY RUN, would write to ") + IOCS_TABLE + ":")
            print(json.dumps(shown, indent=2, default=str))
            if args.apply:
                print(f"\nThis host now flags in /v1/link-check and /v1/composite-check. "
                      f"Verify: POST {{\"url\":\"https://{row['ioc_value']}/\"}} to /v1/composite-check.")
            else:
                print("\nNothing written. Re-run with --apply to promote.")
            return 0
        if args.reject:
            c = reject(tel, items, args.reject, reviewer=args.reviewer, reason=args.reason, now_iso=now_iso)
            print(f"rejected {c['host']} ({c['pk'][5:17]}). It will not resurface: later reports keep this status.")
            return 0
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    eligible, rest = [], []
    for c in items:
        b, notes = evaluate(c, deny, args.min_reporters, corpus_known(str(c.get("host", "")).lower()))
        (rest if b else eligible).append((c, b, notes))
    print(f"\n{len(items)} candidate(s) in {TELEMETRY_TABLE}: {len(eligible)} eligible for review, "
          f"{len(rest)} not.")
    for c, _, notes in eligible:
        print(f"\n  {c['pk'][5:17]}  {c['host']}   {c['category']}   {c.get('taxonomy_id', '')}")
        print(f"    reporters={len(reporters_of(c))} reports={int(c.get('report_count', 0))} "
              f"first={c.get('first_seen', '')} last={c.get('last_seen', '')}")
        for n in notes:
            print(f"    NOTE: {n}")
    if not eligible:
        print("  none. That is the normal state of a young pipeline: reporting is opt-in.")
    if args.all:
        print("\nNOT ELIGIBLE")
        for c, b, _ in rest:
            print(f"  {c['pk'][5:17]}  {str(c.get('host', '')):<38} " + "; ".join(b))
    elif rest:
        print("  (--all lists the rest with the reason each is blocked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
