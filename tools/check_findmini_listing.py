#!/usr/bin/env python3
"""Has findmini.app published the RelayShield IDCheck listing yet?

    python3 tools/check_findmini_listing.py

WHY THIS EXISTS
---------------
The app was submitted to findmini.app/submit/ on 2026-09-14 and their stated
turnaround is "usually within 24 hours or less". Nothing tells us when it goes
live. The alternative to this file is somebody remembering to look, which is
the same gate-nobody-re-checks problem tools/check_xsoar_pack.sh was written
for -- and here it is worse than a delay, because the ORDERING depends on it:
the --snapshot before-findminiweb baseline has to be taken BEFORE the listing
starts returning arrivals, and a baseline taken after is a comparison of a
number with itself.

THREE THINGS IT DELIBERATELY DOES
---------------------------------
1. A 200 IS NOT PROOF. A catalogue can serve a soft 404, a placeholder or a
   search page at 200, so a status code alone would flip this watcher to LISTED
   on a page that says "app not found". The page has to NAME us -- the bot link
   or the app name -- before this reports listed. Same rule as the 402 that came
   back at the wrong price: when two outcomes produce the same SHAPE, verify the
   field that differs.

2. NOT LISTED AND CANNOT TELL ARE DIFFERENT ANSWERS. 404 on every candidate is
   the normal state for as long as moderation is running, and it must not go
   red: a daily red run is an alarm nobody reads. A refused connection, a 403,
   a 429 or any 5xx means this probe could not ask the question, which is the
   one case that IS worth a red run, because otherwise it reads as "not listed
   yet" forever.

3. THE URL SCHEME IS A GUESS AND IT SAYS SO. Their own app pages observed in
   search results are findmini.app/<bot_username>/, e.g. /tapps_bot/ and
   /findminiappbot/, so /relayshield_bot/ is the likely shape -- but the app is
   registered as relayshield_bot/idcheck, and a catalogue may slug a Mini App
   differently from a bot. So it probes several candidates and PRINTS EVERY ONE
   IT TRIED with what came back. A watcher that guesses one URL and reports a
   false negative forever is the quiet alarm this repo keeps paying for.

Browser User-Agent throughout: a scripted default agent is what dev.to's
Cloudflare 403'd, and a 403 here would be read as "cannot tell" and redden the
run for a reason that has nothing to do with findmini.app.
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

CANDIDATES = [
    "https://www.findmini.app/relayshield_bot/",
    "https://www.findmini.app/relayshield_bot/idcheck/",
    "https://findmini.app/relayshield_bot/",
]

# Any ONE of these appearing in the page body is proof the page is about us.
# The bot link first: it is the string a catalogue cannot render by accident.
PROOF = [
    "t.me/relayshield_bot",
    "relayshield_bot/idcheck",
    "RelayShield IDCheck",
]

# Statuses that mean "the listing is not there", as opposed to "no answer".
ABSENT_CODES = {404, 410}


def fetch(url: str) -> tuple[int | None, str, str]:
    """Return (status, body, note). status None means no answer at all."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "text/html,application/xhtml+xml")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        return exc.code, body, ""
    except Exception as exc:
        return None, "", f"{type(exc).__name__}: {exc}"


def names_us(body: str) -> str | None:
    """Which proof string the page carries, if any."""
    low = body.lower()
    for needle in PROOF:
        if needle.lower() in low:
            return needle
    return None


def main() -> int:
    verdict = "not_listed"
    unreachable = 0
    found_at = ""

    for url in CANDIDATES:
        status, body, note = fetch(url)
        if status is None:
            unreachable += 1
            print(f"  {url}\n      NO ANSWER  {note}")
            continue

        proof = names_us(body) if status == 200 else None
        if status == 200 and proof:
            verdict = "listed"
            found_at = url
            print(f"  {url}\n      200  and the page names us: {proof!r}")
        elif status == 200:
            # The dangerous case: a soft 404 or a placeholder served at 200.
            snippet = " ".join(body.split())[:160]
            print(f"  {url}\n      200  but NO proof string. Body starts: {snippet!r}")
        elif status in ABSENT_CODES:
            print(f"  {url}\n      {status}  not published yet (the normal state)")
        else:
            unreachable += 1
            snippet = " ".join(body.split())[:160]
            print(f"  {url}\n      {status}  cannot tell from this. Body: {snippet!r}")

    # Every candidate failed to answer -> this run is not evidence either way.
    if verdict != "listed" and unreachable == len(CANDIDATES):
        verdict = "undetermined"

    print()
    if verdict == "listed":
        print(f"LISTED at {found_at}")
        print("Take the before-findminiweb baseline NOW if it has not been taken.")
    elif verdict == "not_listed":
        print("Not published yet. This is the normal state and is not an error.")
    else:
        print("COULD NOT TELL. Every candidate failed to answer, so this run")
        print("says nothing about whether the listing is live.")

    print(f"FINDMINI_LISTING_STATUS={verdict}", file=sys.stderr)
    print(f"FINDMINI_LISTING_STATUS={verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
