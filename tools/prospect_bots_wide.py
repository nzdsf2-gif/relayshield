#!/usr/bin/env python3
"""Wide prospecting sweep for Telegram bot and Mini App developers.

Companion to tools/prospect_github_bots.py, not a replacement. That tool proved
the shape of the pipeline and returned 93 prospects. This one is built to return
thousands, and it exists because of the two reasons the first sweep could not.

WHY THE FIRST SWEEP CAPPED OUT AT 93
------------------------------------
1. **GitHub caps every search at 1000 results.** Not 1000 per page -- 1000 per
   QUERY, total, no matter how you paginate. Eight framework queries against a
   population of hundreds of thousands of repositories therefore has a hard
   ceiling of 8000 and a practical one far lower, because each query returns the
   same high-star repos first. Adding more keywords does not help; the ceiling is
   per-query, so the fix is to SHARD each query into slices that are individually
   under 1000. This tool shards on stars and on creation date, which are the two
   axes GitHub lets you range-filter.

2. **The scorer rewarded breadth over depth.** capability_fit was
   min(len(tags),3) * 16, so any README mentioning three of six keywords scored
   48 of 50 and everything above that was noise. That is why the first run's top
   eight were Telegram channel DIRECTORIES (AZeC4/TelegramGroup,
   itgoyo/TelegramGroup), proxy lists and a desktop LLM client -- a directory
   mentions every capability by construction, and its README is wall-to-wall
   t.me/ links, so it sailed through the bot-evidence gate too.

   Depth is what matters: one bot that accepts user-submitted URLs is worth ten
   that merely say the word "wallet". So capability now scores the STRENGTH of
   the best signal, and a link-density check demotes catalogues.

WHAT THIS DOES NOT DO
---------------------
It does not touch Telegram. No Telethon, no session, no resolve calls. That is
deliberate and it is the highest-priority constraint in
telegram_miniapp_and_app_inventory_scope.md: the intel monitor and the
prospecting account share nothing, and a prospecting sweep must never be able to
flood-limit the session 99 channels of collection depend on. GitHub needs no
Telegram session at all, which is exactly why the scope doc says start here.

It also asserts nothing about anyone's security. Tags are what a project says it
does, in its own README. The offer is what we can add to that, never a verdict on
what they lack -- claiming an unverified gap in someone else's product is both
outside our measurement doctrine and one word away from the shape of an
extortion email.

USAGE (on the Mac -- this needs a GitHub token and outbound HTTPS)

    cd ~/"Side SaaS Hustle"
    python3 tools/prospect_bots_wide.py --limit 3000

Writes prospects_wide.jsonl. Compare with --min-score to tighten.
"""

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
STALE_DAYS = 90

# ---------------------------------------------------------------------------
# Query axes
# ---------------------------------------------------------------------------

# Topics are high precision: a maintainer applied them deliberately. These carry
# far less noise than a free-text README match and should be swept first.
TOPIC_QUERIES = [
    "topic:telegram-bot",
    "topic:telegram-mini-app",
    "topic:telegram-web-app",
    "topic:tma",
    "topic:telegram-bot-api",
    "topic:aiogram",
    "topic:telegraf",
    "topic:grammyjs",
    "topic:pyrogram",
    "topic:telethon",
    "topic:ton-connect",
]

# Framework dependencies. Lower precision, higher volume.
FRAMEWORK_QUERIES = [
    "python-telegram-bot in:readme,description",
    "aiogram in:readme,description",
    "pyTelegramBotAPI in:readme,description",
    "telegraf in:readme,description",
    "grammy telegram in:readme,description",
    "telethon bot in:readme,description",
    "node-telegram-bot-api in:readme,description",
    "telegram mini app in:readme,description",
    "telegram webapp in:readme,description",
    "tonconnect in:readme,description",
]

# Star buckets. Each shard is a separate 1000-result budget, and together they
# partition the population with no overlap and no gap. Open-ended at the top
# because there are few enough huge repos to fit under the cap.
STAR_SHARDS = [
    "stars:0..1", "stars:2..4", "stars:5..9", "stars:10..24",
    "stars:25..59", "stars:60..149", "stars:150..399",
    "stars:400..999", "stars:>=1000",
]

# Only repos pushed since this date are worth contacting at all, and it doubles
# as a second sharding axis when a star bucket still overflows.
PUSHED_FLOOR = "pushed:>=2026-03-01"

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Weighted by how directly the capability maps to something we sell. A bot that
# takes a user-submitted URL is a scan customer today; one that merely mentions
# "wallet" may be a wallet display with nothing to screen.
CAPABILITY_PATTERNS = {
    "links":    (r"\b(shorten|url|link)s?\b.{0,40}\b(submit|paste|send|share|user)|"
                 r"\b(user|member)s?\b.{0,40}\b(send|post|share)\b.{0,20}\blink", 22),
    "files":    (r"\b(upload|attachment|document|file)s?\b.{0,40}\b(user|send|share|receive)", 18),
    "wallets":  (r"\b(wallet|address|0x[0-9a-f]{6}|ton connect|tonconnect|seed phrase)\b", 20),
    "payments": (r"\b(payment|invoice|checkout|stars|crypto pay|subscription|paywall)\b", 16),
    "identity": (r"\b(login|sign ?up|register|auth|kyc|verify|account)\b", 10),
    "ugc":      (r"\b(user-generated|forum|marketplace|classified|listing|chat with|group chat)\b", 12),
}

# A repo whose README is mostly links is a catalogue, not a product. This is the
# single filter that removes the first sweep's entire polluted top eight.
_LINK_DENSITY_MAX = 20

_NOT_A_PRODUCT = re.compile(
    r"^(awesome[-_]|.*[-_]awesome$|dotfiles$|nix-config$|.*[-_]?list$|"
    r".*collection$|.*navigation$|.*directory$|.*导航$)", re.I)

# Evidence this is a DEPLOYED bot: a t.me link or an @…bot handle.
_BOT_EVIDENCE = re.compile(r"t\.me/[A-Za-z0-9_]{4,}|@[A-Za-z0-9_]{4,32}[Bb]ot\b")
_HANDLE = re.compile(r"(?:t\.me/|@)([A-Za-z0-9_]{4,32}[Bb]ot)\b")
_TME = re.compile(r"t\.me/")
_URL = re.compile(r"https?://")


def classify(text):
    """Return [(tag, weight), ...] for every capability the text asserts."""
    low = text.lower()
    return [(tag, weight) for tag, (pat, weight) in CAPABILITY_PATTERNS.items()
            if re.search(pat, low)]


def looks_like_catalogue(repo, body):
    """A directory, awesome-list or link dump. Cheap checks first."""
    name = (repo.get("name") or "")
    if _NOT_A_PRODUCT.match(name):
        return True
    # Wall-to-wall t.me links is the signature of a channel directory. The first
    # sweep's top two results were exactly this and passed every other check.
    if len(_TME.findall(body)) > _LINK_DENSITY_MAX:
        return True
    lines = [l for l in body.splitlines() if l.strip()]
    if lines and sum(1 for l in lines if _URL.search(l)) / len(lines) > 0.5:
        return True
    return False


def score(repo, tags, handle, contact_count):
    """capability (0-50) + reach (0-20) + contactability (0-20) + freshness (0-10).

    Capability is the STRENGTH of the best two signals rather than a count of
    weak ones. Under the old count-based formula a repo saying "login" three
    different ways outscored one that actually accepts user-submitted URLs.
    """
    # The TOP signal is weighted 1.5x and the second only 0.5x. A flat sum still
    # lets breadth win: "login" + "forum" (10 + 12) tied exactly with a bot that
    # genuinely accepts user-submitted URLs (22), which is the same defect as the
    # old count-based formula wearing a smaller number. Weighted, the real one
    # scores 33 against 23, and no amount of weak tags can overtake one strong.
    weights = sorted((w for _, w in tags), reverse=True)
    top = weights[0] if weights else 0
    second = weights[1] if len(weights) > 1 else 0
    capability = min(50, int(top * 1.5 + second * 0.5))

    stars = repo.get("stargazers_count", 0)
    reach = min(20, int(math.log10(stars + 1) * 8))
    contactability = min(20, contact_count * 7 + (5 if handle else 0))

    freshness = 0
    pushed = repo.get("pushed_at") or ""
    if pushed:
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
            freshness = 10 if age <= STALE_DAYS else max(0, 10 - (age - STALE_DAYS) // 30)
        except ValueError:
            pass
    return capability + reach + contactability + freshness


# ---------------------------------------------------------------------------
# GitHub plumbing
# ---------------------------------------------------------------------------

def gh(path, token, params=None):
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "relayshield-prospector",
    })
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                remaining = resp.headers.get("X-RateLimit-Remaining")
                # The search API allows 30 requests/minute authenticated. Sleeping
                # on the documented budget is cheaper than being 403'd mid-sweep
                # and losing the whole run's state.
                if remaining is not None and int(remaining) < 3:
                    reset = int(resp.headers.get("X-RateLimit-Reset", 0))
                    wait = max(0, reset - int(time.time())) + 2
                    print(f"  rate limit low, sleeping {wait}s", file=sys.stderr)
                    time.sleep(wait)
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                wait = 2 ** attempt * 15
                print(f"  {exc.code}, backing off {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if exc.code == 422:
                # Search refused the query, usually "only the first 1000 results
                # are available". Treat as an exhausted shard, not a failure.
                return None
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt * 5)
    return None


def readme_text(full_name, token):
    data = gh(f"/repos/{full_name}/readme", token)
    if not data:
        return ""
    import base64
    try:
        return base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
    except Exception:
        return ""


def contacts_from(repo, body):
    """Non-Telegram channels we can actually reach. A GitHub issue is the floor;
    a website or an email is what makes a prospect worth ranking."""
    found = {}
    if repo.get("homepage"):
        found["contact_site"] = repo["homepage"]
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]{2,}", body)
    if m and "example.com" not in m.group(0):
        found["contact_email"] = m.group(0)
    found["contact_github"] = repo.get("html_url", "")
    return found


def sweep(token, limit, per_page=100):
    """Shard every query across star buckets so each slice is under the 1000 cap."""
    seen, rows = set(), []
    queries = [(q, "topic") for q in TOPIC_QUERIES] + \
              [(q, "framework") for q in FRAMEWORK_QUERIES]

    for base_q, source in queries:
        for shard in STAR_SHARDS:
            if len(rows) >= limit:
                return rows
            q = f"{base_q} {shard} {PUSHED_FLOOR}"
            print(f"searching: {q}", file=sys.stderr)
            page = 1
            while page <= 10:            # 10 pages x 100 = the 1000 cap
                if len(rows) >= limit:
                    return rows
                data = gh("/search/repositories", token, {
                    "q": q, "per_page": per_page, "page": page,
                    "sort": "updated", "order": "desc",
                })
                if not data or not data.get("items"):
                    break
                for repo in data["items"]:
                    full = repo["full_name"]
                    if full in seen:
                        continue
                    seen.add(full)

                    body = (repo.get("description") or "") + "\n" + \
                           readme_text(full, token)
                    if not _BOT_EVIDENCE.search(body):
                        continue
                    if looks_like_catalogue(repo, body):
                        continue
                    tags = classify(body)
                    if not tags:
                        continue

                    handle_m = _HANDLE.search(body)
                    handle = handle_m.group(1) if handle_m else ""
                    contacts = contacts_from(repo, body)
                    non_tg = sum(1 for k in ("contact_site", "contact_email")
                                 if contacts.get(k))

                    rows.append({
                        "repo": full,
                        "url": repo.get("html_url", ""),
                        "stars": repo.get("stargazers_count", 0),
                        "pushed_at": repo.get("pushed_at"),
                        "handle": handle,
                        "capability_tags": [t for t, _ in tags],
                        "source_query": source,
                        "opportunity_score": score(repo, tags, handle, non_tg),
                        "score_note": "reach is a stars proxy, not Telegram members",
                        "status": "scored",
                        **contacts,
                    })
                page += 1
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=3000,
                    help="stop after this many scored prospects (default 3000)")
    ap.add_argument("--min-score", type=int, default=0)
    ap.add_argument("--out", default="prospects_wide.jsonl")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        try:
            import getpass
            token = getpass.getpass("Paste the GitHub token, then press Enter: ")
        except (EOFError, KeyboardInterrupt):
            return 1
    if not token:
        print("A token is required: the search API is 10 requests/minute "
              "unauthenticated, which cannot finish a sweep.", file=sys.stderr)
        return 1

    rows = [r for r in sweep(token, args.limit)
            if r["opportunity_score"] >= args.min_score]
    rows.sort(key=lambda r: r["opportunity_score"], reverse=True)

    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    print(f"\nwrote {args.out} ({len(rows)} prospects)\n")
    print("%-5s %-40s %-30s %s" % ("SCORE", "REPO", "TAGS", "CONTACT"))
    for r in rows[:args.top]:
        print("%-5d %-40s %-30s %s" % (
            r["opportunity_score"], r["repo"][:40],
            ",".join(r["capability_tags"])[:30],
            r.get("contact_site") or r.get("contact_email") or r.get("contact_github", ""),
        ))

    reachable = sum(1 for r in rows if r.get("contact_site") or r.get("contact_email"))
    print(f"\n{reachable} of {len(rows)} have a website or an email, which are the "
          "only contact channels that beat a GitHub issue.")
    print("\nNothing here asserts anything about anyone's security. The tags are\n"
          "what each project says it does; the offer is what we can add to that.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
