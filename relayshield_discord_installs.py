#!/usr/bin/env python3
"""Track which Discord servers the RelayShield bot is installed in.

WHY THIS EXISTS
---------------
Until now we could not answer "how many servers is the bot in", which meant we
could not answer any of the questions that depend on it: how far off the
75-server Discord App Directory threshold we are, whether a post to a big server
produced installs, whether anyone is removing the bot, or who to name when the
next admin asks "who else runs this?".

`discord_midsize_pipeline_2026-08-13.md` established that
`relayshield_intel_discord_channels` cannot answer this: it harvests servers
advertised inside CRIMINAL Telegram channels, so by construction it finds
competitors and scam servers, not our installs. This is the replacement for that
half of the job.

WHAT IT READS
-------------
`GET /users/@me/guilds?with_counts=true`, which returns every guild the bot is a
member of, with name and approximate member count. One call, no per-guild fan
out, and it needs only the bot token.

**This does not weaken the bot's privacy claim.** "We do not request the Message
Content Intent, so we are structurally unable to read your channels" is about an
intent we do not hold. This endpoint returns guild metadata only: no messages, no
channels, no members. The claim is unchanged and still true.

PRIVACY LINE, NOT NEGOTIABLE
----------------------------
Guild-level only. No user ids, no usernames, no command arguments, ever. A table
of who ran `/exposure` on which address would make a liar of the entire pitch,
and internal fields have a way of ending up in support conversations.

Run it:
    python3 relayshield_discord_installs.py            # sync and print
    python3 relayshield_discord_installs.py --dry-run  # print, write nothing
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
_secrets = boto3.client("secretsmanager", region_name="us-east-1")

INSTALLS_TABLE = "relayshield_discord_installs"
TOKEN_SECRET = "relayshield/discord_bot_token"
TOKEN_JSON_KEY = "bot_token"

DISCORD_API = "https://discord.com/api/v10"
USER_AGENT = "RelayShield-Installs (https://relayshield.net, 1.0)"

# Discord pages this endpoint. 200 is the maximum it accepts.
PAGE_SIZE = 200

# The Discord App Directory unlocks at 75 servers. Tracked here so the number
# has one home rather than living in a doc nobody re-reads.
APP_DIRECTORY_THRESHOLD = 75

_token_cache: str | None = None


def _bot_token() -> str | None:
    """Read the bot token from Secrets Manager. Cached for the container's life."""
    global _token_cache
    if _token_cache is None:
        try:
            raw = _secrets.get_secret_value(SecretId=TOKEN_SECRET)["SecretString"]
        except Exception as exc:
            logger.error("could not read %s: %s", TOKEN_SECRET, exc)
            return None
        try:
            _token_cache = json.loads(raw)[TOKEN_JSON_KEY]
        except Exception:
            # Tolerate a bare string, since that is how a hurried rotation often
            # lands, but the documented shape is {"bot_token": "..."}.
            _token_cache = raw.strip()
    return _token_cache or None


def fetch_guilds(token: str) -> tuple[list[dict], str | None]:
    """Return (guilds, error). Never raises.

    An error is returned rather than an empty list because "we could not ask"
    and "the bot is in no servers" must never collapse into the same answer.
    That distinction is load bearing: see the caller, where an empty list would
    otherwise mark every install as churned.
    """
    guilds: list[dict] = []
    after = ""
    while True:
        url = f"{DISCORD_API}/users/@me/guilds?with_counts=true&limit={PAGE_SIZE}"
        if after:
            url += f"&after={after}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bot {token}",
            "User-Agent": USER_AGENT,
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                page = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return [], "unauthorized: the stored bot token is invalid or was reset"
            if exc.code == 429:
                return [], "rate limited by Discord"
            return [], f"discord_http_{exc.code}"
        except Exception as exc:
            return [], f"unreachable: {type(exc).__name__}"

        if not isinstance(page, list):
            return [], "unexpected response shape"
        guilds.extend(page)
        if len(page) < PAGE_SIZE:
            return guilds, None
        after = page[-1]["id"]


def sync(dry_run: bool = False) -> dict:
    """Reconcile the live guild list into the installs table.

    Returns a stats dict. Writes nothing when `dry_run`.
    """
    token = _bot_token()
    if not token:
        return {"error": "no bot token available"}

    guilds, err = fetch_guilds(token)
    if err:
        # HARD STOP. Do not touch the table on a failed fetch.
        #
        # If this returned early with an empty list and the caller carried on,
        # every previously known guild would be marked as having removed the
        # bot, and the churn signal would report a total collapse that never
        # happened. An outage is not an exodus. This codebase has shipped that
        # class of bug three times; it is not shipping a fourth.
        logger.error("guild fetch failed (%s), leaving the table untouched", err)
        return {"error": err}

    now = datetime.now(timezone.utc).isoformat()
    table = _dynamodb.Table(INSTALLS_TABLE)

    live_ids = set()
    new_count = 0
    for g in guilds:
        gid = str(g.get("id") or "")
        if not gid:
            continue
        live_ids.add(gid)
        if dry_run:
            continue
        try:
            resp = table.update_item(
                Key={"guild_id": gid},
                UpdateExpression=(
                    "SET guild_name = :n, member_count = :m, last_seen = :t, "
                    "active = :true, first_seen = if_not_exists(first_seen, :t) "
                    "REMOVE left_at"
                ),
                ExpressionAttributeValues={
                    ":n": g.get("name") or "",
                    ":m": int(g.get("approximate_member_count") or 0),
                    ":t": now,
                    ":true": True,
                },
                ReturnValues="UPDATED_OLD",
            )
            # No previous attributes means this row did not exist: a new install.
            if not resp.get("Attributes"):
                new_count += 1
                logger.info("new install: %s (%s)", g.get("name"), gid)
        except Exception as exc:
            logger.warning("could not write guild %s: %s", gid, exc)

    # Departures: rows we hold that the live list no longer contains.
    departed = []
    try:
        scanned = table.scan(ProjectionExpression="guild_id, guild_name, active").get("Items", [])
    except Exception as exc:
        logger.warning("could not scan for departures: %s", exc)
        scanned = []
    for item in scanned:
        gid = item.get("guild_id")
        if gid and gid not in live_ids and item.get("active"):
            departed.append({"guild_id": gid, "guild_name": item.get("guild_name", "")})
            if not dry_run:
                try:
                    table.update_item(
                        Key={"guild_id": gid},
                        UpdateExpression="SET active = :false, left_at = :t",
                        ExpressionAttributeValues={":false": False, ":t": now},
                    )
                    logger.info("bot removed from: %s (%s)", item.get("guild_name"), gid)
                except Exception as exc:
                    logger.warning("could not mark %s departed: %s", gid, exc)

    members = sum(int(g.get("approximate_member_count") or 0) for g in guilds)
    return {
        "servers": len(guilds),
        "new_installs": new_count,
        "departures": departed,
        "total_reach": members,
        "to_app_directory": max(0, APP_DIRECTORY_THRESHOLD - len(guilds)),
        "dry_run": dry_run,
    }


def lambda_handler(event, context):
    """Scheduled entry point. Safe to run as often as hourly."""
    stats = sync(dry_run=False)
    logger.info("install sync: %s", json.dumps(stats, default=str))
    return {"statusCode": 200, "body": json.dumps(stats, default=str)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sync the Discord install list.")
    ap.add_argument("--dry-run", action="store_true", help="Print without writing.")
    args = ap.parse_args(argv)

    stats = sync(dry_run=args.dry_run)
    if stats.get("error"):
        print(f"FAILED: {stats['error']}", file=sys.stderr)
        print("Nothing was written. An outage is not an exodus.", file=sys.stderr)
        return 1

    print()
    print(f"  Servers with the bot installed : {stats['servers']}")
    print(f"  New since last sync            : {stats['new_installs']}")
    print(f"  Combined member reach          : {stats['total_reach']:,}")
    print(f"  Servers still needed for the App Directory : {stats['to_app_directory']}")
    if stats["departures"]:
        print(f"\n  REMOVED the bot since last sync ({len(stats['departures'])}):")
        for d in stats["departures"]:
            print(f"    {d['guild_name'] or d['guild_id']}")
    if stats["dry_run"]:
        print("\n  (dry run, nothing written)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
