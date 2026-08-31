#!/usr/bin/env python3
"""
Item 16, GitHub half: find Telegram bot developers we can actually reach.

Why GitHub first, and not Telegram
----------------------------------
telegram_miniapp_and_app_inventory_scope.md ranks the sources and GitHub wins on
the only axis that matters for outreach: it reliably yields a developer on a
professional channel. It also needs no Telegram session, so it cannot endanger
the one 99 channels of intel collection depend on. And if the first 200 scored
prospects produce nothing, that is a cheap early answer rather than a burned
account.

The rule this tool obeys
------------------------
Classify from what a project SAYS IT DOES, never from what we guess it lacks.
The scope document is explicit that "we analysed your app and found exposures"
is both unverifiable and one word from an extortion email. So capability tags
come from the repo's own description, topics and README, and the output is a
list of things a bot already does that our checks map onto. Nothing here
produces a claim about anybody's security.

Runs with no AWS. Needs a GitHub token for the search API.

    export GITHUB_TOKEN=...            # any classic or fine-grained read token
    python3 tools/prospect_github_bots.py --limit 200
    python3 tools/prospect_github_bots.py --limit 200 --out iam/../prospects.jsonl

Writes JSONL plus a ranked shortlist on stdout. Loading into
relayshield_tg_apps is a separate step, deliberately: score first, look at the
top of the list, and only persist once the scoring looks sane.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"

# Frameworks a Telegram bot is actually built with. Searching these finds bots
# by construction rather than by the word "telegram" appearing somewhere.
FRAMEWORK_QUERIES = [
    "python-telegram-bot",
    "aiogram",
    "pyTelegramBotAPI",
    "telegraf",
    "grammy telegram",
    "telethon bot",
    "telegram-bot-api",
    "telegram mini app",
]

# Capability tags, matched against the project's OWN words. Each maps to checks
# we already sell, which is what makes the outreach a capability offer rather
# than a verdict.
CAPABILITY_PATTERNS = {
    "links":     r"\b(url|link|shorten|redirect|website|phish)",
    "wallets":   r"\b(wallet|erc-?20|evm|solana|ethereum|token|airdrop|defi|web3)",
    "payments":  r"\b(payment|invoice|checkout|stripe|crypto pay|subscription|billing)",
    "files":     r"\b(file|upload|attachment|document|pdf|image|download)",
    "identity":  r"\b(login|auth|verify|kyc|identity|account|register|otp)",
    "ugc":       r"\b(group|community|moderat|spam|member|chat|forward|user-submitted)",
}

# What we can offer against each tag. Their words on the left, our endpoint on
# the right. Nothing is asserted about what they currently do.
CAPABILITY_OFFER = {
    "links":    "scan-url, domain lookalike",
    "wallets":  "scan-wallet, token-security",
    "payments": "wallet-risk before settlement",
    "files":    "scan-file",
    "identity": "breach, infostealer, session-risk",
    "ugc":      "scan-url on posted links",
}

STALE_DAYS = 90


def gh(path, token, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "relayshield-prospector")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read()), resp.headers
        except urllib.error.HTTPError as exc:
            # Search is rate limited far more tightly than the core API (30/min
            # authenticated). Backing off is normal operation here, not an error.
            if exc.code in (403, 429):
                wait = int(exc.headers.get("Retry-After") or (5 * (attempt + 1)))
                print("  rate limited, waiting %ds" % wait, file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise SystemExit("gave up after repeated rate limiting on %s" % path)


def readme_text(full_name, token):
    """The README in the project's own words. Empty on any failure: a missing
    README must never look like an absence of capability."""
    try:
        data, _ = gh("/repos/%s/readme" % full_name, token)
    except urllib.error.HTTPError:
        return ""
    import base64
    if data.get("encoding") != "base64":
        return ""
    try:
        return base64.b64decode(data["content"]).decode("utf-8", "replace")[:20000]
    except Exception:
        return ""


_HANDLE = re.compile(r"(?:t\.me/|@)([A-Za-z0-9_]{4,32}[Bb]ot)\b")


def classify(text):
    low = text.lower()
    return sorted(t for t, pat in CAPABILITY_PATTERNS.items() if re.search(pat, low))


def score(repo, tags, handle, contact_count):
    """The formula from telegram_miniapp_and_app_inventory_scope.md.

    One honest substitution: the scope's "reach" is Telegram member count, which
    GitHub cannot see. Stars stand in for it. Stars measure developer attention,
    not bot users, so this is a proxy and is labelled as one in the output rather
    than being passed off as reach.
    """
    import math
    capability_fit = min(50, len(tags) * 12)
    stars = repo.get("stargazers_count", 0)
    reach = min(20, int(math.log10(stars + 1) * 8))
    contactability = min(20, contact_count * 7 + (5 if handle else 0))

    pushed = repo.get("pushed_at") or ""
    freshness = 0
    if pushed:
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
            freshness = 10 if age <= STALE_DAYS else max(0, 10 - (age - STALE_DAYS) // 30)
        except ValueError:
            pass
    return capability_fit + reach + contactability + freshness


def harvest(token, limit, per_query):
    seen, rows = set(), []
    for q in FRAMEWORK_QUERIES:
        if len(rows) >= limit:
            break
        print("searching: %s" % q, file=sys.stderr)
        data, _ = gh("/search/repositories", token, {
            "q": "%s in:name,description,readme" % q,
            "sort": "updated", "order": "desc",
            "per_page": min(per_query, 100),
        })
        for repo in data.get("items", []):
            if len(rows) >= limit:
                break
            full = repo["full_name"]
            if full in seen:
                continue
            seen.add(full)

            body = " ".join(filter(None, [
                repo.get("description") or "",
                " ".join(repo.get("topics") or []),
                readme_text(full, token),
            ]))
            tags = classify(body)
            if not tags:
                continue  # nothing of ours maps onto what they say they do

            m = _HANDLE.search(body)
            handle = ("@" + m.group(1)) if m else ""

            contacts = {
                "github": repo["html_url"],
                "site": repo.get("homepage") or "",
                "owner": (repo.get("owner") or {}).get("html_url", ""),
            }
            contact_count = sum(1 for v in contacts.values() if v)

            rows.append({
                "repo": full,
                "handle": handle,
                "kind": "bot",
                "title": repo.get("name"),
                "description": (repo.get("description") or "")[:300],
                "stars": repo.get("stargazers_count", 0),
                "pushed_at": repo.get("pushed_at"),
                "language": repo.get("language"),
                "license": ((repo.get("license") or {}) or {}).get("spdx_id"),
                "capability_tags": tags,
                "offer": sorted({CAPABILITY_OFFER[t] for t in tags}),
                "contact_github": contacts["github"],
                "contact_site": contacts["site"],
                "contact_owner": contacts["owner"],
                "opportunity_score": score(repo, tags, handle, contact_count),
                "score_note": "reach is a stars proxy, not Telegram members",
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "status": "scored",
            })
    rows.sort(key=lambda r: r["opportunity_score"], reverse=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200,
                    help="stop after this many scored prospects (default 200, "
                         "the number the scope doc calls a cheap early answer)")
    ap.add_argument("--per-query", type=int, default=50)
    ap.add_argument("--out", default="prospects_github.jsonl")
    ap.add_argument("--top", type=int, default=20, help="how many to print")
    ap.add_argument("--min-score", type=int, default=0,
                    help="drop anything below this before writing")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("Set GITHUB_TOKEN. The unauthenticated search API is 10 requests "
                 "per minute and will not get through one run.")

    rows = [r for r in harvest(token, args.limit, args.per_query)
            if r["opportunity_score"] >= args.min_score]

    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("\nwrote %s (%d prospects)\n" % (args.out, len(rows)))
    print("%-5s %-38s %-26s %s" % ("SCORE", "REPO", "TAGS", "CONTACT"))
    for r in rows[:args.top]:
        print("%-5d %-38s %-26s %s" % (
            r["opportunity_score"], r["repo"][:38],
            ",".join(r["capability_tags"])[:26],
            r["contact_site"] or r["contact_owner"]))

    if rows:
        reachable = sum(1 for r in rows if r["contact_site"])
        print("\n%d of %d have a website, which is the only contact channel that "
              "beats a GitHub issue." % (reachable, len(rows)))
    print("\nNothing here asserts anything about anyone's security. The tags are "
          "\nwhat each project says it does; the offer is what we can add to that.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
