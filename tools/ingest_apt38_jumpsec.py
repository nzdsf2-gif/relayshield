#!/usr/bin/env python3
"""
Ingest the APT38 / BlueNoroff ClickFix campaign indicators published by JUMPSEC
into `relayshield_intel_iocs`.

WHY THIS SCRIPT EXISTS, AND WHAT IT DELIBERATELY DOES NOT DO
------------------------------------------------------------
The corpus had zero indicators tagged to APT38, BlueNoroff, UNC1069, Lazarus or
NukeSped. The fix for that is to ingest indicators a named researcher has
actually attributed to the actor, with the citation stored alongside each row.

It is NOT to tag existing untagged indicators as APT38. Attribution that is not
evidenced is a fabricated detection: a customer who queries this corpus is
making a containment decision on the answer, and a fabricated hit produces a
real incident response against an innocent asset. Every row written here comes
from one published source and carries `reference` pointing back to it.

SOURCE
    JUMPSEC, "Inside a DPRK BlueNoroff ClickFix Kit", July 2026
    https://www.jumpsec.com/guides/inside-a-dprk-bluenoroff-clickfix-kit/

    JUMPSEC separates high-confidence from medium-confidence infrastructure and
    that separation is preserved in the `confidence` attribute rather than
    flattened. Consumers can filter.

ATTRIBUTION CHAIN, so the claim is auditable
    JUMPSEC and Mandiant attribute the campaign to UNC1069, which Mandiant
    describes as overlapping with BlueNoroff. The US Treasury designated
    BlueNoroff / APT38 as a DPRK state entity under the Reconnaissance General
    Bureau. MITRE ATT&CK G0082 carries APT38 with "Bluenoroff" among its
    aliases. That chain is why these rows are tagged `apt38`.

SCHEMA NOTES
    Table key is (ioc_value HASH, seen_ts RANGE).
    `malware` is the malware-index GSI hash key and MUST be lowercase to match
    the bulk-ingestion convention ("mirai", "qakbot"). Note the pre-existing
    `ClickFix` rows are capitalised and therefore invisible to a lowercase
    query; that inconsistency predates this script and is logged as its own
    item rather than silently rewritten here.

NOT INGESTED ON PURPOSE
    The attacker's Telegram bot tokens. They are live third-party credentials,
    they are not an indicator anyone can sweep their own assets against, and
    this repo is public.

Usage:
    AWS_PROFILE=relayshield python3 tools/ingest_apt38_jumpsec.py --dry-run
    AWS_PROFILE=relayshield python3 tools/ingest_apt38_jumpsec.py --commit
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import boto3

TABLE   = "relayshield_intel_iocs"
REGION  = "us-east-1"
TTL_DAYS = 365   # campaign infrastructure, longer-lived than a daily feed row

MALWARE_TAG = "apt38"
ACTOR       = "APT38"
ALIASES     = ["APT38", "BlueNoroff", "UNC1069", "NICKEL GLADSTONE", "BeagleBoyz",
               "Stardust Chollima", "Sapphire Sleet", "COPERNICIUM"]
CAMPAIGN    = "BlueNoroff ClickFix fake-meeting kit"
REFERENCE   = "https://www.jumpsec.com/guides/inside-a-dprk-bluenoroff-clickfix-kit/"
CHANNEL     = "jumpsec"
CATEGORY    = "threat_report"

# Guard against the failure mode already present in the corpus, where
# `sites.google.com` and `raw.githubusercontent.com` are tagged as ClickFix
# domain IOCs. Those are hosting platforms, not threats, and a customer sweep
# matching them produces a false positive with real operational cost. Nothing
# in the list below currently trips this, which is the point: it stays as a
# standing guard for the next ingestion.
NEVER_INGEST = {
    "sites.google.com", "google.com", "drive.google.com", "docs.google.com",
    "raw.githubusercontent.com", "github.com", "gist.github.com",
    "githubusercontent.com", "gitlab.com", "bitbucket.org",
    "pastebin.com", "t.me", "telegram.org", "api.telegram.org",
    "discord.com", "cdn.discordapp.com", "dropbox.com", "onedrive.live.com",
    "amazonaws.com", "s3.amazonaws.com", "cloudflare.com", "azurewebsites.net",
    "zoom.us", "teams.microsoft.com", "microsoft.com", "office.com",
}

DOMAINS_HIGH = [
    "callsdk.online", "web02eu.live", "team.business.in", "webcamsdk-update.online",
    "meetsdk.online", "us05.zoom.web05.uk", "us.zoom.06webin.us", "meet.teamicro.live",
    "web.zoomapp.05meet.am.in", "zoom.05ukweb.uk", "zoom.us05-web.us",
    "webapp.zoom.05live.co", "teamapp.live", "lives.teamicrosoft.sbs", "teamlive.vip",
    "mwmelke.com", "microteam.live", "onteam.business.in", "cloud.inteam.live",
    "microsoft-workspace.live", "weekly-up.online",
]

DOMAINS_MEDIUM = [
    "edensun.xyz", "xmpp.edensun.xyz", "muc.edensun.xyz", "turn.edensun.xyz",
    "proxy.edensun.xyz", "uploads.edensun.xyz", "softwareupdate.online",
    "support-mac.online", "teams-supports.online", "zoom-support.online",
    "teams07.lives07.com", "us.zoom.06web.us", "usweb06.zoom.meet06.us",
    "web02us.zoom.02io.us", "webus.zoom.05live.us", "02webus.zoom.02us.sbs",
    "02webus.zoom.web02.sbs", "05us.zoom.web05.sbs", "06usweb.zoom.us06.sbs",
    "live.teamsbrowser.com", "livemicrosft.com", "lives.ms.teams02.co",
    "lives.teams-app.pro", "lives.teams03.com", "lives.teamstunnel.com",
    "macro.teams.live02.co", "teams.lives02.com", "teams.microsoft.lives02.run",
    "teams.premuims.live", "teams.web.lives06.com", "teams02.lives05.com",
    "teams05web.lives07.com", "teamsupport.live", "web08.teams08.run",
    "webus.zoom.02web.sbs", "teamicro.live", "teams.live.miclesoft.com",
    "teamms.live.miclesoft.com", "secure.inteam.live",
]

# All on AS14956 (RouterHosting LLC / Cloudzy) per JUMPSEC.
IPS = [
    "144.172.110.53", "144.172.115.16", "144.172.117.143",
    "172.86.89.213", "172.86.91.195",
    "45.61.163.100", "45.61.163.113", "45.61.163.43", "45.61.129.29",
    "153.75.91.159",
]

HASHES_SHA256 = [
    "7a0b96f1063593a2e76f2f92ddfe091776a2ba63bc4f87f83dc5ebb675309d8d",
    "180f797723bd65e82189eb1f737d39ce522614a182e2b46b51faeb49953a412f",
    "8889f1b67aea6896945506dae192326149f6c5db87e9b04fa08ac9a142a87775",
    "a86659dff126be72aff1d5e546baff735dcb7ed6ddd521737e7e3be8910c05f2",
    "26bdad9189f6b28a90165c09ceed4386eff2fb352bea7fb78ebb164f28ebed28",
    "163e4a72cbe392c073eddc60aee69dc1cf87ce492c375af74e923d75d8084683",
    "b149e207a3aad68605785710c58e8439aef61f48776c136d5a0ec6682d7dd2c0",
    "0517ca4649e33faefa3a6bfcd2707a8376a981be4b42b9d19146ebb93e7f8a35",
    "203bd56fbb75c9176fcbc77be6ff0792c9f55cb0ea3a255766130fadaa0c05de",
    "eb78f46fd7cf28aacfbb4db1fdbaee8022e7874db6af588fe1c56b964c7c6833",
    "9d8b9090972ec013f3ad0236f5210bd70fe4ba87402fdefeac399cf11dba2efe",
    "9e9ad85212b681f8aef6d0b15f23b9d8b78b8d61ec56d4f71e22d4a1c46a6c17",
    "159046fd26701315cfd79bd392a8fa05d4bcae47cfa2409f03628b823cb477c4",
]


def build_rows(now_iso: str, ttl: int) -> list[dict]:
    rows, skipped = [], []
    groups = [
        (DOMAINS_HIGH,   "domain", "high"),
        (DOMAINS_MEDIUM, "domain", "medium"),
        (IPS,            "ip",     "high"),
        (HASHES_SHA256,  "sha256", "high"),
    ]
    for values, ioc_type, confidence in groups:
        for raw in values:
            value = raw.strip().lower()
            if not value:
                continue
            if value in NEVER_INGEST:
                skipped.append(value)
                continue
            rows.append({
                "ioc_value":     value,
                "seen_ts":       now_iso,
                "ioc_type":      ioc_type,
                "channel":       CHANNEL,
                "category":      CATEGORY,
                "malware":       MALWARE_TAG,
                "threat_actor":  ACTOR,
                "actor_aliases": ALIASES,
                "campaign":      CAMPAIGN,
                "confidence":    confidence,
                "reference":     REFERENCE,
                "ttl":           ttl,
            })
    if skipped:
        print(f"SKIPPED by NEVER_INGEST guard ({len(skipped)}): {skipped}", file=sys.stderr)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    now_iso = datetime.now(timezone.utc).isoformat()
    ttl     = int(time.time()) + TTL_DAYS * 86400
    rows    = build_rows(now_iso, ttl)

    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r["ioc_type"]] = by_type.get(r["ioc_type"], 0) + 1
    print(f"{len(rows)} rows to write: {by_type}")
    print(f"malware tag: {MALWARE_TAG!r}  actor: {ACTOR}  reference: {REFERENCE}")

    if args.dry_run:
        for r in rows[:5]:
            print("  sample:", {k: r[k] for k in ("ioc_value", "ioc_type", "malware", "confidence")})
        print("DRY RUN, nothing written.")
        return 0

    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    written = 0
    with table.batch_writer() as batch:
        for r in rows:
            batch.put_item(Item=r)
            written += 1
    print(f"WROTE {written} rows to {TABLE}")

    # Verify by reading back through the GSI the API actually queries, not by
    # trusting the write. A batch_writer that silently dropped items would look
    # identical to success up to this line.
    resp = table.query(
        IndexName="malware-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("malware").eq(MALWARE_TAG),
        Select="COUNT",
    )
    print(f"VERIFY malware-index malware={MALWARE_TAG!r} -> Count={resp['Count']}")
    if resp["Count"] < written:
        print("VERIFY FAILED: GSI count is lower than rows written.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
