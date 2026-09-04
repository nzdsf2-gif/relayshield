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
    # Added after the first run, 2026-09-03. The founder had seen a channel
    # called "Trending Apps" that the first keyword set did not reach: the
    # catalogues do not all describe themselves as "mini apps", and several
    # index by what is popular rather than what is new.
    "trending apps",
    "app of the day",
    "best mini apps",
    "tma apps",
    "telegram app store",
]

MAX_PER_KEYWORD = 40

# Channels named by a person rather than found by a keyword. Search does not
# reach everything: @trendingapps and @twa_apps were both given by the founder
# on 2026-09-03 after the second sweep missed them, and a seed is how a human
# observation gets measured instead of argued about. Resolved and reported like
# any other row, so their member counts and last-post dates are comparable.
SEED_CHANNELS = [
    "trendingapps",
    # @twa_apps resolves to the SAME channel as @trendingapps: identical title,
    # identical member count, measured 2026-09-03. Kept in the list so the next
    # person does not re-add it as a separate target; the dedup below reports it
    # rather than counting it twice.
    "twa_apps",
    # Not a channel: the submission bot @trendingapps names in its own
    # description ("We handpick and showcase top tApps submitted via
    # @tapps_bot"). Resolving it confirms it exists and is the route in;
    # it will report as a user rather than a channel and that is expected.
    "tapps_bot",
]

# Enough Cyrillic in the title or description and the channel publishes in
# Russian. Not a judgement about the channel: a submission written in English to
# a Russian-language audience converts badly and reads as spam, which is worth
# knowing BEFORE writing it rather than after. The founder flagged exactly this
# on the first run.
_CYRILLIC = set(range(0x0400, 0x0500))


def _script_hint(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "unknown"
    cyr = sum(1 for c in letters if ord(c) in _CYRILLIC)
    share = cyr / len(letters)
    if share > 0.5:
        return "cyrillic"
    if share > 0.1:
        return "mixed"
    return "latin"


def _secret(name):
    import boto3
    sm = boto3.client("secretsmanager", region_name="us-east-1")
    return json.loads(sm.get_secret_value(SecretId=name)["SecretString"])


async def _sweep(session_data, min_members, pause, latin_only):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.contacts import SearchRequest
    from telethon.tl.functions.channels import GetFullChannelRequest
    # GetFullChannelRequest is used for seeds too, hence the import order.

    client = TelegramClient(StringSession(session_data["session_string"]),
                            int(session_data["api_id"]), session_data["api_hash"])
    await client.connect()
    me = await client.get_me()
    print(f"connected as @{getattr(me, 'username', None) or me.id} "
          f"(prospecting account)\n")

    seen, rows = set(), []
    seen_ids = set()

    # Seeds first, so a channel a human named is never crowded out by the
    # per-keyword cap.
    for username in SEED_CHANNELS:
        username = username.lower()
        seen.add(username)
        try:
            entity = await client.get_entity(username)
        except Exception as exc:
            print(f"  seed @{username}: unreadable ({type(exc).__name__})")
            await asyncio.sleep(pause)
            continue
        # A bot resolves to a User, which has no .title at all, and getattr's
        # default does not help when the attribute EXISTS and is None. That
        # crashed the first seeded run on title[:40].
        title = (getattr(entity, "title", None)
                 or getattr(entity, "username", None)
                 or " ".join(x for x in (getattr(entity, "first_name", None),
                                         getattr(entity, "last_name", None)) if x)
                 or username)

        # Two usernames can be the same channel: @trendingapps and @twa_apps
        # both resolved to "Trending Apps" with an identical member count on the
        # first seeded run, which is one channel counted twice and would have
        # been two submissions to the same admin.
        entity_id = getattr(entity, "id", None)
        if entity_id is not None and entity_id in seen_ids:
            print(f"  seed @{username}: same channel as one already listed, skipping")
            await asyncio.sleep(pause)
            continue
        if entity_id is not None:
            seen_ids.add(entity_id)
        members, about = 0, ""
        try:
            full = await client(GetFullChannelRequest(entity))
            members = getattr(full.full_chat, "participants_count", 0) or 0
            about = (getattr(full.full_chat, "about", "") or "").replace("\n", " ")
        except Exception:
            # A bot resolves to a User, which has no full channel. Still worth
            # reporting: it is the submission route, not an audience.
            about = "resolves as a user or bot, not a channel: this is a submission route"
        last_post = ""
        try:
            msgs = await client.get_messages(entity, limit=1)
            if msgs:
                last_post = msgs[0].date.strftime("%Y-%m-%d")
        except Exception:
            pass
        rows.append({
            "username": username, "title": title, "members": members,
            "script": _script_hint(f"{title} {about}"), "last_post": last_post,
            "about": about[:300], "found_via": "seed (named by hand)",
            "url": f"https://t.me/{username}",
        })
        print(f"  seed @{username}  {members:,}  last post {last_post or '?'}  {title[:40]}")
        await asyncio.sleep(pause)

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
                entity_id = getattr(entity, "id", None)
                if entity_id is not None and entity_id in seen_ids:
                    continue
                if entity_id is not None:
                    seen_ids.add(entity_id)
                full = await client(GetFullChannelRequest(entity))
                members = getattr(full.full_chat, "participants_count", 0) or 0
                about = (getattr(full.full_chat, "about", "") or "").replace("\n", " ")
            except Exception as exc:
                print(f"  @{username}: unreadable ({type(exc).__name__})")
                await asyncio.sleep(pause)
                continue

            if members >= min_members:
                title = getattr(chat, "title", username)
                script = _script_hint(f"{title} {about}")
                if latin_only and script == "cyrillic":
                    print(f"  @{username}: skipped, publishes in Cyrillic")
                    await asyncio.sleep(pause)
                    continue

                # A catalogue that stopped posting is worth nothing whatever its
                # member count says, and the count alone cannot tell you.
                last_post = ""
                try:
                    msgs = await client.get_messages(entity, limit=1)
                    if msgs:
                        last_post = msgs[0].date.strftime("%Y-%m-%d")
                except Exception:
                    pass

                rows.append({
                    "username": username,
                    "title": title,
                    "members": members,
                    "script": script,
                    "last_post": last_post,
                    "about": about[:300],
                    "found_via": keyword,
                    "url": f"https://t.me/{username}",
                })
                print(f"  @{username}  {members:,}  {script:<8} last post {last_post or '?'}  "
                      f"{title[:40]}")
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
        "**Member count and last-post date are the measured numbers here. Engagement is not.** A "
        "large channel full of bots is worth less than a small one people read, and no API call "
        "tells you which this is. Read the recent posts before submitting.",
        "",
        "**Script is a routing signal, not a verdict.** A channel marked `cyrillic` publishes in "
        "Russian, and an English submission to a Russian-language audience converts badly and "
        "reads as spam. Either write the submission in the channel's language or skip it; "
        "`--latin-only` drops them for you.",
        "",
        "**Sequencing, which matters more than the list.** These channels announce MINI APPS, and "
        "we do not have one yet. Submitting before it exists wastes the only first impression "
        "each channel will give us. The list is the target for the day the Mini App ships. Some "
        "of these cover bots too, and `@relayshield_bot` could be submitted today, but that is a "
        "different pitch and a weaker one.",
        "",
        "| Channel | Members | Script | Last post | Found via | Title |",
        "|---|---:|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| [@{r['username']}]({r['url']}) | {r['members']:,} | "
                     f"{r.get('script', '?')} | {r.get('last_post') or '?'} | "
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
    ap.add_argument("--latin-only", action="store_true",
                    help="skip channels that publish in Cyrillic. An English "
                         "submission to a Russian-language audience converts "
                         "badly and reads as spam.")
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
        _sweep(session_data, args.min_members, args.pause, args.latin_only))

    write_report(rows, args.out, args.min_members)
    with open(args.out.replace(".md", ".json"), "w") as fh:
        json.dump(rows, fh, indent=2)
    print(f"\nwrote {args.out} ({len(rows)} channels) and its .json")
    print("Member counts are measured. Engagement is not: read the recent posts "
          "before submitting to any of them.")


if __name__ == "__main__":
    main()
