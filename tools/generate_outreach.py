#!/usr/bin/env python3
"""Turn prospects_wide.jsonl into a review-and-send outreach file.

    python3 tools/generate_outreach.py                    # top 40 by score
    python3 tools/generate_outreach.py --limit 100 --min-score 45
    python3 tools/generate_outreach.py --tag wallets      # one capability only

Writes outreach_bot_prospects.md: one section per prospect, each with the
contact channel, the evidence the draft is built on, and a message ready to
review and send.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It never asserts anything about a prospect's security. The external study
proposed generating reports saying an app has "no URL reputation layer" and
calling those "security opportunities detected". Two things are wrong with
that, and both are fatal:

  * It is INFERRED. We can see a README. We cannot see their backend, and
    claiming a gap we have not measured is what our own measurement doctrine
    forbids. It is worse here because it is an assertion about someone else's
    product.
  * It READS AS A THREAT. An unsolicited "we analysed your app and found
    exposures" from an unknown vendor is one word away from an extortion email,
    and a security company sending it has more to lose than most.

So every draft is a CAPABILITY OFFER keyed on what the repo SAYS IT DOES, in
its own README, and the evidence line quotes that back so the founder can
check it before sending. Nothing here is mass mail: the score exists to make
the top few findable, and the founder sends them by hand.
"""

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contact_hygiene as hygiene  # noqa: E402

IN_DEFAULT = "prospects_wide.jsonl"
OUT_DEFAULT = "outreach_bot_prospects.md"

# The one-line integration, per language. Kept identical to widget/README.md.
SNIPPET_PY = "v = check(message.text)   # returns a verdict and a ready-to-send reply"
SNIPPET_JS = "const v = await check(ctx.message.text);"

# Message bodies by DOMINANT capability tag. Each opens with something checkable
# from their own README, offers a capability, and never diagnoses them.
#
# Length is a decision, not an accident: a maintainer reads about five lines of
# an unsolicited message. Everything that is not the offer is cut.
BODIES = {
    "links": """Your bot takes links from users. We publish a check for exactly that
case: one function call, and you get back a verdict plus a ready-to-send reply for
a link that is in a criminal IOC corpus, on Google Safe Browsing, or on a domain
registered days ago.

    {snippet}

No signup, no key and no card for the first calls. It never throws, and it never
tells your users something is safe, only that nothing is known against it.

{link}""",
    "wallets": """Your bot handles wallet addresses. We publish an address check that
covers EVM, Solana, TON and Bitcoin in one call, and returns a verdict plus a
ready-to-send reply.

    {snippet}

No signup, no key and no card for the first calls. It never throws, and a failed
check reports as unchecked rather than as safe.

{link}""",
    "payments": """Your bot moves money for people. The check we publish screens the two
things a user pastes right before they lose some: a link, or a wallet address.
One call, a verdict, and a reply you can send as is.

    {snippet}

No signup, no key and no card for the first calls, so it costs a few minutes to
find out whether it is useful to you.

{link}""",
    "ugc": """Your bot carries links posted by other users, which is the case our link
check exists for. One call returns a verdict and a ready-to-send reply for a
domain that is in a criminal IOC corpus, on Safe Browsing, or newly registered.

    {snippet}

No signup, no key and no card for the first calls.

{link}""",
    "identity": """Your bot signs users up. Alongside that, our free tier covers checking
whether an address given at signup is already in a breach corpus or in stealer
malware logs, which is a different question from whether the address is valid.

The link and address checks need no key at all:

    {snippet}

100 free calls, no card, for the rest.

{link}""",
    "files": """Your bot takes files and links from users. The link half of our check is
open: one call, a verdict, and a ready-to-send reply.

    {snippet}

File scanning is a separate endpoint and does need a key, with 100 free calls and
no card. The link and address checks need no key at all.

{link}""",
}

CLOSER_PR = ("If it looks useful and you would rather see it than wire it up, say so and "
             "I will open a PR against {repo} with the handler wired in, and you can close "
             "it if you hate it.")

LINK = "https://github.com/nzdsf2-gif/relayshield/tree/main/widget"


def draft(row):
    tags = row.get("capability_tags") or []
    tag = next((t for t in ("links", "wallets", "payments", "ugc", "files", "identity")
                if t in tags), "links")
    body = BODIES[tag]
    snippet = SNIPPET_JS if _is_js(row) else SNIPPET_PY
    return tag, body.format(snippet=snippet, link=LINK)


def _is_js(row):
    """Best-effort language guess from the search query that found the repo.

    Wrong only costs a snippet in the other language, which the founder can see
    at a glance, so a guess is better than omitting the line entirely.
    """
    q = (row.get("source_query") or "").lower()
    return any(k in q for k in ("grammy", "telegraf", "node-telegram", "javascript", "typescript"))


def channel(row):
    """Best contact channel, and why. Email beats a website form beats a GitHub
    issue, and a GitHub issue is last on purpose: an unsolicited issue on a
    stranger's repo is public, permanent and read as noise by everyone watching
    the repo, not just the maintainer.

    Screened again here even though prospect_bots_wide.py screens at extraction
    time, because a prospects_wide.jsonl generated before that fix still holds
    root@203.0.113.4 and t.me links, and this is the last thing standing before
    a message is sent. A stale input file must not be able to produce a draft
    addressed to a documentation example.
    """
    email = row.get("contact_email") or ""
    if email and hygiene.usable_email(email):
        return "email", email
    site = row.get("contact_site") or ""
    if site and hygiene.usable_site(site):
        return "website", site
    if row.get("contact_github"):
        return "github (last resort)", row["contact_github"]
    return "none", ""


def rejected(row):
    """Contacts this row carried that were not usable, and why. Reported so a
    dropped prospect is visible rather than silently absent."""
    out = []
    for field, kind in (("contact_email", "email"), ("contact_site", "site")):
        value = row.get(field) or ""
        if value:
            why = hygiene.reject_reason(value, kind)
            if why:
                out.append(f"{value} ({why})")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=IN_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--min-score", type=int, default=40)
    ap.add_argument("--tag", default="", help="only prospects carrying this capability tag")
    ap.add_argument("--include-github-only", action="store_true",
                    help="include prospects reachable only by opening a GitHub issue")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        sys.exit(f"{args.src} not found. Generate it first:\n"
                 f"  python3 tools/prospect_bots_wide.py --limit 200")

    rows = []
    with open(args.src) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    kept = []
    for row in rows:
        if row.get("opportunity_score", 0) < args.min_score:
            continue
        if args.tag and args.tag not in (row.get("capability_tags") or []):
            continue
        kind, _ = channel(row)
        if kind == "none":
            continue
        if kind.startswith("github") and not args.include_github_only:
            continue
        kept.append(row)

    kept.sort(key=lambda r: r.get("opportunity_score", 0), reverse=True)
    kept = kept[:args.limit]

    screened = [(r["repo"], why) for r in rows for why in rejected(r)]

    tally = Counter(channel(r)[0] for r in kept)
    tags = Counter(t for r in kept for t in (r.get("capability_tags") or []))

    out = [
        "# Bot and Mini App outreach drafts",
        "",
        f"*Generated by `tools/generate_outreach.py` from `{args.src}`. "
        f"{len(kept)} of {len(rows)} prospects, score >= {args.min_score}.*",
        "",
        "## How to use this",
        "",
        "**Every draft is a capability offer, never a claim about their security.** We can read "
        "a README. We cannot see anyone's backend, and telling a maintainer we found a gap in "
        "their product is both unverified and one word away from the shape of an extortion "
        "email. If you edit a draft, keep that line intact.",
        "",
        "Read the evidence line before sending. It is the tag the classifier matched from their "
        "own README, and it is the only claim the message rests on. If it looks wrong for that "
        "repo, drop the prospect rather than softening the message.",
        "",
        "Send by hand, a few a day. Volume is not the lever here and a burst of near-identical "
        "mail is how a domain gets blocked.",
        "",
        f"**Channels:** " + ", ".join(f"{k} {v}" for k, v in tally.most_common()) + ".",
        f"**Capabilities:** " + ", ".join(f"{k} {v}" for k, v in tags.most_common()) + ".",
        "",
        "## Tracking",
        "",
        "Fill this in as you send. The number that decides whether this channel works is "
        "replies per 100 contacted, by source, not the number sent.",
        "",
        "| Repo | Channel | Sent | Reply | Integrated |",
        "|---|---|---|---|---|",
    ]
    for row in kept:
        out.append(f"| {row['repo']} | {channel(row)[0]} | | | |")
    out.append("")
    out.append("---")
    out.append("")

    for i, row in enumerate(kept, 1):
        kind, where = channel(row)
        tag, body = draft(row)
        handle = row.get("handle") or ""
        out += [
            f"## {i}. {row['repo']}",
            "",
            f"- **Score** {row.get('opportunity_score')} · **Stars** {row.get('stars')} · "
            f"**Last push** {(row.get('pushed_at') or '')[:10]}",
            f"- **Contact** {kind}: {where}",
            f"- **Repo** {row.get('url')}" + (f" · **Bot** @{handle}" if handle else ""),
            f"- **Evidence the draft rests on**: their README asserts "
            f"`{', '.join(row.get('capability_tags') or [])}`; the draft is written to "
            f"`{tag}`.",
            "",
            "```text",
            f"Subject: A link and address check for {row['repo'].split('/')[-1]}",
            "",
            "Hi,",
            "",
            body.strip(),
            "",
            CLOSER_PR.format(repo=row["repo"]),
            "",
            "Andrew",
            "RelayShield",
            "```",
            "",
        ]

    with open(args.out, "w") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"wrote {args.out}: {len(kept)} drafts from {len(rows)} prospects")
    if screened:
        print(f"screened out {len(screened)} unusable contact(s), first few:")
        for repo, why in screened[:5]:
            print(f"  {repo}: {why}")
        print("  (README examples and links to the product itself. See "
              "tools/contact_hygiene.py.)")
    if tally.get("github (last resort)"):
        print("note: GitHub-only prospects were skipped. --include-github-only adds them, "
              "but an unsolicited issue on a stranger's repo is public and permanent.")


if __name__ == "__main__":
    main()
