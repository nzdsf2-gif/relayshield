#!/usr/bin/env python3
"""Telegram-side prospecting sweep: find BOTS and MINI APPS, not channels.

Item 16's Telegram half. The GitHub half is tools/prospect_bots_wide.py, and
that one runs first because it needs no Telegram session at all and yields the
better contact (a repo, an author, often a website). This tool reaches the far
larger population that has no GitHub presence.

    tools/prospect_github_bots.py   first pass, proved the pipeline, 93 rows
    tools/prospect_bots_wide.py     GitHub at scale, sharded past the 1000 cap
    tools/prospect_telegram_apps.py THIS FILE -- Telegram itself


THE SESSION RULE, WHICH IS THE MOST IMPORTANT THING IN THIS FILE
---------------------------------------------------------------
This runs on `relayshield/telethon_session_prospecting` and it is not merely a
default -- COLLECTION_SECRET is listed below and refused explicitly, because
the failure mode is silent and expensive.

relayshield_intel_monitor.py and relayshield_intel_discovery.py share ONE
session, and that session's own comments record how tight the limits already
are: ResolveUsernameRequest has a per-session flood limit that "a 122-channel
resolve burst trips almost immediately". A prospecting sweep is the same call
at far higher volume. Running it on the collection session would flood-wait or
ban the account 99 channels of intel collection depend on, and
regenerate_telethon_session.py exists because that has had to be rebuilt before.

So: separate account, separate secret, separate rate budget, no shared code
path. If the prospecting session gets limited, collection is unaffected. That
is the whole reason the second account was created.

This is also why the tool is NOT a Lambda. A Lambda acquires a schedule, an
EventBridge rule and a deploy-map entry, and three sessions from now somebody
adds it to a map next to the intel monitor. A script that a human runs cannot
drift into the collection fleet by accident.


WHAT IT COLLECTS, AND WHAT IT REFUSES TO INFER
----------------------------------------------
For each bot: username, title, its own `about` text, its own declared command
list, and the Mini App URL when the bot exposes one. Capability tags come from
what the bot SAYS IT DOES, in its own words.

It never infers what a bot lacks. "We analysed your app and found exposures" is
an unverifiable claim about someone else's product and reads one word away from
an extortion email -- a security vendor sending that has more to lose than most.
The offer is additive: "your bot accepts user-submitted links; here is a call
that screens them, and a free key."

USAGE (Mac only -- needs telethon, boto3 and the prospecting session)

    ~/.rsvenv/bin/pip install telethon
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/prospect_telegram_apps.py --limit 400

Writes prospects_telegram.jsonl. Add --write-dynamo to also upsert
relayshield_tg_apps. Start SMALL: --limit 100 on the first run, and read the
flood-wait line in the summary before raising it.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

PROSPECTING_SECRET = "relayshield/telethon_session_prospecting"

# Named so the guard below can refuse it by value rather than by convention.
# A comment saying "do not use the collection session" is not a control.
COLLECTION_SECRET = "relayshield/telethon_session"

APPS_TABLE = "relayshield_tg_apps"

# Deliberately conservative. The collection session's own notes say a burst of
# ~122 resolves trips the flood limit almost immediately, so this sweep spaces
# every call and sleeps hard between keywords. A slow sweep that keeps the
# account is worth more than a fast one that loses it.
SLEEP_BETWEEN_CALLS = 1.5
SLEEP_BETWEEN_KEYWORDS = 6.0
MAX_PER_KEYWORD = 50

# Search terms aimed at bots whose own description implies a surface we can
# screen. Not "telegram bot" -- that returns the whole platform.
SEARCH_KEYWORDS = [
    "link checker bot", "url shortener bot", "file share bot",
    "wallet bot", "ton wallet bot", "crypto payment bot",
    "airdrop bot", "nft bot", "trading signals bot",
    "marketplace bot", "classifieds bot", "escrow bot",
    "download bot", "upload bot", "storage bot",
    "login bot", "verification bot", "captcha bot",
    "mini app", "tma app", "web app bot",
    "shop bot", "store bot", "invoice bot",
]

# Same weights as the GitHub sweep so a prospect scored on Telegram and one
# scored on GitHub are comparable. Depth over breadth: a bot that accepts
# user-submitted URLs is a customer today; one that merely says "wallet" may
# be a balance display with nothing to screen.
CAPABILITY_PATTERNS = {
    "links":    (r"\b(shorten|url|link)s?\b|\bcheck(er)?\b.{0,20}\blink", 22),
    "wallets":  (r"\b(wallet|ton connect|tonconnect|address|seed phrase)\b", 20),
    "files":    (r"\b(upload|download|file|document|storage|attachment)s?\b", 18),
    "payments": (r"\b(payment|invoice|checkout|stars|escrow|subscription|pay)\b", 16),
    "ugc":      (r"\b(marketplace|classified|forum|listing|group|community|share)\b", 12),
    "identity": (r"\b(login|sign ?up|register|verify|captcha|auth|kyc)\b", 10),
}

_RE_URL = re.compile(r"https?://[^\s)]+")


def classify(text):
    low = (text or "").lower()
    return [(tag, w) for tag, (pat, w) in CAPABILITY_PATTERNS.items()
            if re.search(pat, low)]


def score(tags, members, has_miniapp, contact_count):
    """Same shape as the GitHub sweep: capability + reach + contactability +
    a Mini App bonus. Top signal weighted 1.5x, second 0.5x, so no quantity of
    weak tags can overtake one strong one."""
    import math
    weights = sorted((w for _, w in tags), reverse=True)
    top = weights[0] if weights else 0
    second = weights[1] if len(weights) > 1 else 0
    capability = min(50, int(top * 1.5 + second * 0.5))
    reach = min(20, int(math.log10((members or 0) + 1) * 6))
    contactability = min(20, contact_count * 8)
    # A Mini App is a richer integration surface than a chat bot and is the
    # population the founder actually asked about, so it earns a real bonus
    # rather than a tie-break.
    return capability + reach + contactability + (10 if has_miniapp else 0)


async def _sweep(session_data, limit, keywords):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.contacts import SearchRequest
    from telethon.errors import FloodWaitError

    client = TelegramClient(
        StringSession(session_data["session_string"]),
        int(session_data["api_id"]), session_data["api_hash"],
    )
    await client.connect()

    me = await client.get_me()
    print(f"prospecting as: @{getattr(me, 'username', None)} (id {me.id})",
          file=sys.stderr)

    seen, rows, flood_waits = set(), [], []

    for keyword in keywords:
        if len(rows) >= limit:
            break
        print(f"searching: {keyword}", file=sys.stderr)
        try:
            result = await client(SearchRequest(q=keyword, limit=MAX_PER_KEYWORD))
        except FloodWaitError as exc:
            # Recorded and surfaced, never silently absorbed. A sweep that hides
            # its own rate pain is a sweep that eventually loses the account.
            flood_waits.append((keyword, exc.seconds))
            print(f"  FLOOD WAIT {exc.seconds}s on '{keyword}' — sleeping",
                  file=sys.stderr)
            await asyncio.sleep(min(exc.seconds + 5, 300))
            continue
        except Exception as exc:
            print(f"  search failed '{keyword}': {exc}", file=sys.stderr)
            await asyncio.sleep(SLEEP_BETWEEN_CALLS)
            continue

        # A bot resolves to a User with bot=True, NOT a Chat/Channel. That is
        # the single structural difference from relayshield_intel_discovery,
        # which reads result.chats and would see none of these.
        for user in getattr(result, "users", []):
            if len(rows) >= limit:
                break
            if not getattr(user, "bot", False):
                continue
            username = (getattr(user, "username", None) or "").lower()
            if not username or username in seen:
                continue
            seen.add(username)

            about, commands, miniapp_url, members = "", [], "", 0
            try:
                full = await client(
                    __import__("telethon.tl.functions.users", fromlist=["GetFullUserRequest"])
                    .GetFullUserRequest(user)
                )
                fu = getattr(full, "full_user", None)
                about = getattr(fu, "about", "") or ""
                bot_info = getattr(fu, "bot_info", None)
                if bot_info:
                    commands = [getattr(c, "command", "") for c in
                                (getattr(bot_info, "commands", None) or [])]
                    about = about or (getattr(bot_info, "description", "") or "")
                    menu = getattr(bot_info, "menu_button", None)
                    miniapp_url = getattr(menu, "url", "") or ""
            except FloodWaitError as exc:
                flood_waits.append((username, exc.seconds))
                print(f"  FLOOD WAIT {exc.seconds}s resolving @{username}",
                      file=sys.stderr)
                await asyncio.sleep(min(exc.seconds + 5, 300))
                continue
            except Exception:
                pass

            await asyncio.sleep(SLEEP_BETWEEN_CALLS)

            title = " ".join(x for x in (getattr(user, "first_name", ""),
                                         getattr(user, "last_name", "")) if x)
            body = " ".join([title, about, " ".join(commands)])
            tags = classify(body)
            if not tags:
                continue

            site = ""
            m = _RE_URL.search(about)
            if m:
                site = m.group(0)
            contact_count = sum(1 for x in (site, miniapp_url) if x)

            rows.append({
                "handle": username,
                "kind": "miniapp" if miniapp_url else "bot",
                "title": title,
                "about": about[:500],
                "commands": commands,
                "miniapp_url": miniapp_url,
                "members": members,
                "capability_tags": [t for t, _ in tags],
                "contact_site": site,
                "opportunity_score": score(tags, members, bool(miniapp_url), contact_count),
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "found_via": keyword,
                "discovery_method": "telethon_search_prospecting",
                "status": "scored",
            })

        await asyncio.sleep(SLEEP_BETWEEN_KEYWORDS)

    await client.disconnect()
    return rows, flood_waits


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--min-score", type=int, default=0)
    ap.add_argument("--out", default="prospects_telegram.jsonl")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--write-dynamo", action="store_true",
                    help=f"also upsert {APPS_TABLE}")
    ap.add_argument("--secret", default=PROSPECTING_SECRET)
    args = ap.parse_args()

    # THE GUARD. Refusing by value, before any network call, because the cost of
    # getting this wrong is the collection account and the failure is silent
    # until 99 channels stop reporting.
    if args.secret == COLLECTION_SECRET:
        print(f"REFUSED: {COLLECTION_SECRET} is the COLLECTION session.\n"
              "Prospecting must never share it — a resolve burst trips its flood\n"
              "limit and takes intel collection down with it. Use\n"
              f"  {PROSPECTING_SECRET}", file=sys.stderr)
        return 2

    import boto3
    sm = boto3.client("secretsmanager")
    try:
        session_data = json.loads(
            sm.get_secret_value(SecretId=args.secret)["SecretString"])
    except Exception as exc:
        print(f"Could not read {args.secret}: {exc}\n"
              "Create it with:  python3 intel_setup_telethon.py --secret "
              f"{PROSPECTING_SECRET}", file=sys.stderr)
        return 1

    rows, flood_waits = asyncio.get_event_loop().run_until_complete(
        _sweep(session_data, args.limit, SEARCH_KEYWORDS))

    rows = [r for r in rows if r["opportunity_score"] >= args.min_score]
    rows.sort(key=lambda r: r["opportunity_score"], reverse=True)

    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    print(f"\nwrote {args.out} ({len(rows)} prospects)\n")
    print("%-5s %-28s %-9s %-26s %s" % ("SCORE", "HANDLE", "KIND", "TAGS", "MINI APP"))
    for r in rows[:args.top]:
        print("%-5d %-28s %-9s %-26s %s" % (
            r["opportunity_score"], ("@" + r["handle"])[:28], r["kind"],
            ",".join(r["capability_tags"])[:26], r["miniapp_url"][:40]))

    miniapps = sum(1 for r in rows if r["kind"] == "miniapp")
    print(f"\n{miniapps} of {len(rows)} expose a Mini App URL.")
    if flood_waits:
        total = sum(s for _, s in flood_waits)
        print(f"\n{len(flood_waits)} FLOOD WAITS, {total}s total. Lower --limit or "
              "raise SLEEP_BETWEEN_CALLS before the next run.")
    else:
        print("\nNo flood waits. The rate budget held.")

    if args.write_dynamo and rows:
        table = boto3.resource("dynamodb").Table(APPS_TABLE)
        written = 0
        for r in rows:
            try:
                table.put_item(Item={k: v for k, v in r.items() if v not in ("", [], None)})
                written += 1
            except Exception as exc:
                print(f"  write failed @{r['handle']}: {exc}", file=sys.stderr)
        print(f"wrote {written} rows to {APPS_TABLE}")

    print("\nNothing here asserts anything about anyone's security. Tags are what\n"
          "each bot says it does, in its own words; the offer is what we can add.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
