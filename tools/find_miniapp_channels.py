#!/usr/bin/env python3
"""Find Telegram channels that announce new Mini Apps, and measure them.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/find_miniapp_channels.py
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/find_miniapp_channels.py --min-members 5000

Read-only. It searches, resolves and counts members. It writes NOTHING to
Telegram and NOTHING to DynamoDB: this is prospecting, not collection, and the
two must not touch the same tables any more than they touch the same session.

Output: miniapp_channels.md, a ranked shortlist with member counts, plus the
raw rows as miniapp_channels.json.

WHY A SCRIPT AND NOT A LIST IN A DOCUMENT
------------------------------------------
Asked on 2026-09-03: "I have seen Telegram channels that highlight new Mini
Apps, we should find a few." Any list I write from memory is unverifiable, and
this repo has been bitten three times by a document asserting something nobody
checked. Channel names change, channels die, and member counts are the only
part of the pitch a reader can check in ten seconds. So the answer is a
measurement, taken now, on the account that is allowed to take it.

THE SESSION RULE, WHICH IS NOT NEGOTIABLE
-----------------------------------------
This runs on relayshield/telethon_session_prospecting, the SECOND account.
Never the collection session. relayshield_intel_monitor and
relayshield_intel_discovery share one session whose own comments record how
tight the limits already are: a 122-channel resolve burst trips the
ResolveUsername flood limit almost immediately. Ninety-nine channels of intel
collection depend on that account staying unlimited, and a prospecting sweep is
the same call at higher volume for a much less valuable purpose.

The script asserts the secret name before it connects, so running it against
the collection session takes a deliberate edit rather than a slip.

WHAT TO DO WITH THE OUTPUT, AND WHAT NOT TO
-------------------------------------------
These are submission targets, not a mailing list. Most catalogue channels take
new apps through a submission bot or a named admin, and one polite submission
per channel is the whole play. Do not DM the members, do not post into the
channels, and do not run this often: a search sweep every few weeks is
plenty, and the account this uses is the one Item 16 depends on next.
"""

import argparse
import asyncio
import json
import sys

PROSPECTING_SECRET = "relayshield/telethon_session_prospecting"
COLLECTION_SECRET = "relayshield/telethon_session"

# Deliberately narrow. Each term costs a search call and every extra term is
# another slice of a rate budget that belongs to Item 16.
KEYWORDS = [
    "mini apps",
    "telegram mini apps",
    "miniapps",
    "tapps",
    "telegram apps catalog",
    "new mini app",
    "ton apps",
    "web apps telegram",
]

MAX_PER_KEYWORD = 40


def _secret(name):
    import boto3
    sm = boto3.client("secretsmanager", region_name="us-east-1")
    return json.loads(sm.get_secret_value(SecretId=name)["SecretString"])


async def _sweep(session_data, min_members, pause):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.contacts import SearchRequest
    from telethon.tl.functions.channels import GetFullChannelRequest

    client = TelegramClient(StringSession(session_data["session_string"]),
                            int(session_data["api_id"]), session_data["api_hash"])
    await client.connect()
    me = await client.get_me()
    print(f"connected as @{getattr(me, 'username', None) or me.id} "
          f"(prospecting account)\n")

    seen, rows = set(), []
    for keyword in KEYWORDS:
        print(f"searching: {keyword}")
        try:
            result = await client(SearchRequest(q=keyword, limit=MAX_PER_KEYWORD))
        except Exception as exc:
            print(f"  search failed: {exc}")
            await asyncio.sleep(pause * 2)
            continue

        for chat in getattr(result, "chats", []):
            username = (getattr(chat, "username", None) or "").lower()
            if not username or username in seen:
                continue
            seen.add(username)
            try:
                entity = await client.get_entity(username)
                full = await client(GetFullChannelRequest(entity))
                members = getattr(full.full_chat, "participants_count", 0) or 0
                about = (getattr(full.full_chat, "about", "") or "").replace("\n", " ")
            except Exception as exc:
                print(f"  @{username}: unreadable ({type(exc).__name__})")
                await asyncio.sleep(pause)
                continue

            if members >= min_members:
                rows.append({
                    "username": username,
                    "title": getattr(chat, "title", username),
                    "members": members,
                    "about": about[:300],
                    "found_via": keyword,
                    "url": f"https://t.me/{username}",
                })
                print(f"  @{username}  {members:,}  {getattr(chat, 'title', '')[:50]}")
            await asyncio.sleep(pause)
        await asyncio.sleep(pause)

    await client.disconnect()
    rows.sort(key=lambda r: r["members"], reverse=True)
    return rows


def write_report(rows, path, min_members):
    lines = [
        "# Telegram channels that announce Mini Apps",
        "",
        f"*Measured by `tools/find_miniapp_channels.py` on the prospecting account. "
        f"{len(rows)} channels at or above {min_members:,} members.*",
        "",
        "**These are submission targets, not a mailing list.** One polite submission per "
        "channel, through whatever route that channel actually publishes. Do not DM the "
        "members and do not post into the channels.",
        "",
        "**Member count is the only measured number here.** It is not engagement, and a large "
        "channel full of bots is worth less than a small one people read. Check the recent posts "
        "before submitting: a channel that has not posted in months is dead whatever its count "
        "says.",
        "",
        "| Channel | Members | Found via | Title |",
        "|---|---:|---|---|",
    ]
    for r in rows:
        lines.append(f"| [@{r['username']}]({r['url']}) | {r['members']:,} | "
                     f"{r['found_via']} | {r['title'][:60]} |")
    lines += ["", "## What each one says about itself", ""]
    for r in rows:
        lines += [f"### @{r['username']} ({r['members']:,})", "",
                  f"{r['about'] or '_no description_'}", ""]
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-members", type=int, default=1000,
                    help="ignore channels smaller than this (default 1000)")
    ap.add_argument("--pause", type=float, default=1.5,
                    help="seconds between Telegram calls. Lower is a flood-wait risk "
                         "on an account Item 16 depends on.")
    ap.add_argument("--out", default="miniapp_channels.md")
    ap.add_argument("--secret", default=PROSPECTING_SECRET)
    args = ap.parse_args()

    if args.secret == COLLECTION_SECRET:
        sys.exit("STOP: that is the COLLECTION session. Ninety-nine channels of intel "
                 "collection depend on it and a prospecting sweep is how it gets "
                 "flood-limited. Use the prospecting account.")

    try:
        session_data = _secret(args.secret)
    except Exception as exc:
        sys.exit(f"could not read {args.secret}: {exc}\n"
                 f"Set it up first:  python3 intel_setup_telethon.py --secret {args.secret}")

    rows = asyncio.get_event_loop().run_until_complete(
        _sweep(session_data, args.min_members, args.pause))

    write_report(rows, args.out, args.min_members)
    with open(args.out.replace(".md", ".json"), "w") as fh:
        json.dump(rows, fh, indent=2)
    print(f"\nwrote {args.out} ({len(rows)} channels) and its .json")
    print("Member counts are measured. Engagement is not: read the recent posts "
          "before submitting to any of them.")


if __name__ == "__main__":
    main()
