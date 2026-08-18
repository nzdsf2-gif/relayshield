#!/usr/bin/env python3
"""Resolve Discord invite codes to guild name and member counts, ranked.

The Tier 2 targeting pipeline. Uses Discord's PUBLIC invite-preview endpoint,
which needs no bot token and no auth at all: it returns the same metadata the
Discord client shows you on an invite preview before you join. Same endpoint
`_queue_discovered_discord_invites()` in relayshield_intel_monitor.py uses.

    python3 scripts/resolve_discord_invites.py solflare sanctum drift
    python3 scripts/resolve_discord_invites.py --file candidates.txt

WHERE THE CODES MUST COME FROM: the project's own official website. Not a
directory, not a DM, and never guessed. Guessing is how you end up measuring a
squatted server: on 2026-08-13 the vanity code `phantom` resolved to a
77-member server called "/phantom", which is emphatically not Phantom's
community. This script will happily report that number, so it cannot be the
thing that decides whether a server is real.

Ranking is by ONLINE PERCENTAGE, not member count. A member count accumulated
during a mint three years ago is not a community; presence share is the cheapest
available proxy for whether anyone is actually in there.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

API = "https://discord.com/api/v10/invites/{code}?with_counts=true"
UA = "RelayShield-INTEL (https://relayshield.net, 1.0)"

# The qualification band from discord_server_targets.md: small enough that one
# person decides, large enough that an install is worth having.
BAND_MIN = 1_000
BAND_MAX = 50_000

# Discord rate-limits unauthenticated invite lookups. This is deliberately
# unhurried; a target list is built once and the endpoint owes us nothing.
DELAY_SECONDS = 0.4


def resolve(code: str, timeout: int = 10) -> dict:
    """Resolve one invite code. Never raises; returns an `error` key instead.

    An unreachable lookup and a server with no members must not collapse into
    the same row, so a failure carries its reason rather than a zero.
    """
    req = urllib.request.Request(API.format(code=code), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            invite = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # 404 is the interesting one: expired, revoked, or never existed. It is
        # not evidence the project has no Discord.
        return {"code": code, "error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"code": code, "error": type(exc).__name__}

    guild = invite.get("guild") or {}
    channel = invite.get("channel") or {}
    members = invite.get("approximate_member_count")
    online = invite.get("approximate_presence_count")
    return {
        "code": code,
        "guild_name": guild.get("name", ""),
        "guild_id": guild.get("id", ""),
        "channel_name": channel.get("name", ""),
        "members": members,
        "online": online,
        "online_pct": (online / members * 100) if (members and online) else None,
        "in_band": bool(members and BAND_MIN <= members <= BAND_MAX),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("codes", nargs="*", help="Invite codes (the part after discord.gg/)")
    ap.add_argument("--file", help="File of invite codes, one per line, # for comments")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    args = ap.parse_args(argv)

    codes = list(args.codes)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            codes += [ln.strip() for ln in fh
                      if ln.strip() and not ln.lstrip().startswith("#")]
    # Preserve order while de-duplicating, so a repeated code is not looked up twice.
    codes = list(dict.fromkeys(codes))
    if not codes:
        ap.error("give at least one invite code, or --file")

    rows = []
    for i, code in enumerate(codes):
        rows.append(resolve(code))
        if i < len(codes) - 1:
            time.sleep(DELAY_SECONDS)

    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        print()
        return 0

    ok = [r for r in rows if "error" not in r]
    failed = [r for r in rows if "error" in r]
    # Unranked rows sort last rather than being dropped.
    ok.sort(key=lambda r: (r["online_pct"] is None, -(r["online_pct"] or 0)))

    print(f"\n{'code':18} {'guild':32} {'members':>9} {'online':>7} {'online%':>8}  band")
    print("-" * 88)
    for r in ok:
        pct = f"{r['online_pct']:.1f}%" if r["online_pct"] is not None else "-"
        band = "IN" if r["in_band"] else ("too big" if (r["members"] or 0) > BAND_MAX else "too small")
        print(f"{r['code']:18} {r['guild_name'][:32]:32} "
              f"{(r['members'] or 0):>9,} {(r['online'] or 0):>7,} {pct:>8}  {band}")

    in_band = [r for r in ok if r["in_band"]]
    print(f"\n{len(ok)} resolved, {len(in_band)} in the {BAND_MIN:,} to {BAND_MAX:,} band.")

    # Printed explicitly. A code that could not be resolved is not a server that
    # failed to qualify, and silently omitting it would make the list look more
    # complete than it is.
    if failed:
        print(f"\n{len(failed)} could NOT be resolved (tells you nothing either way):")
        for r in failed:
            print(f"  {r['code']:18} {r['error']}")

    print("\nMember count is not qualification. Before pitching any of these: confirm the invite "
          "\nfrom the project's OWN website, read two weeks of their general channel for live "
          "\nscam-link traffic, check the member list for an existing scam bot (SecurityBot "
          "\nespecially), and identify a named human who moderates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
