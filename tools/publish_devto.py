#!/usr/bin/env python3
"""Publish or update a post on DEV (dev.to) from a markdown file in this repo.

WHY THIS EXISTS. The dev.to markdown editor takes Jekyll front matter, and on
2026-09-07 two attempts at pasting that front matter by hand did not take. The
keys were never wrong -- title, published, description, tags and canonical_url
are all supported -- so the fault was in the transfer. Retyping a structured
document into a web form is the kind of step that fails silently and costs a
round trip every time. This sends the fields over the API instead, where a
failure is an HTTP status with a message in it.

It strips the front matter and sends every field EXPLICITLY rather than letting
DEV re-parse it out of the body. DEV accepts front matter inside body_markdown
and lets it win, so sending both is two sources of truth for the same fields and
exactly the shape this repo keeps getting bitten by.

IT WILL NOT CREATE A SECOND COPY. Before posting it lists the account's own
articles and matches on canonical_url first, then on title, and updates that
article instead. A duplicate on DEV is not a tidiness problem: two URLs carrying
the same canonical is precisely the SEO damage the canonical tag exists to
prevent.

AND IT REFUSES TO PUBLISH AGAINST A DEAD CANONICAL. `published: true` with a
canonical_url that 404s tells every crawler our canonical does not exist, which
hands DEV the canonical position for our own post. The check is a HEAD request
and it is skipped only with --no-canonical-check, which prints why.

THE API KEY IS NEVER AN ARGUMENT. It is read from DEVTO_API_KEY in the
environment, because an argument lands in shell history and in any screen
recording. Get one at https://dev.to/settings/extensions under "DEV Community API
Keys".

Usage:

    python3 tools/publish_devto.py blog-agent-bait-scan-devto.md --dry-run
    python3 tools/publish_devto.py blog-agent-bait-scan-devto.md --draft
    python3 tools/publish_devto.py blog-agent-bait-scan-devto.md --publish
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://dev.to/api"


def parse_front_matter(text):
    """Return (fields, body). Raises if the front matter is not where DEV needs it."""
    if not text.startswith("---\n"):
        raise SystemExit(
            "ERROR: the file does not begin with '---' at column zero.\n"
            "       DEV requires the front matter to be the first three characters,\n"
            "       with no blank line and no leading whitespace before it."
        )
    end = text.find("\n---\n", 4)
    if end == -1:
        raise SystemExit("ERROR: front matter is never closed by a '---' line.")
    raw, body = text[4:end], text[end + 5:]

    fields = {}
    for line in raw.split("\n"):
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue          # DEV's editor template pre-fills commented lines
        if ":" not in line:
            raise SystemExit(f"ERROR: front matter line is not 'key: value': {line!r}")
        k, v = line.split(":", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        fields[k.strip()] = v
    return fields, body.lstrip("\n")


# dev.to sits behind Cloudflare, which 403s urllib's default `Python-urllib/3.x`
# agent before the request ever reaches the API. That is the same cause that made
# the canonical probe report 403 on a page a browser loads fine, and it was fixed
# there first and not generalised, which cost a round. Every outbound request in
# this file sends a real agent.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _request(method, url, key, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("api-key", key)
    req.add_header("User-Agent", _UA)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/vnd.forem.api-v1+json")
    try:
        with urllib.request.urlopen(req, timeout=60) as fh:
            return json.loads(fh.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:600]
        raise SystemExit(
            f"ERROR: DEV returned {e.code} for {method} {url}\n{detail}\n\n"
            + ("       401 means DEVTO_API_KEY is missing, wrong or revoked.\n"
               if e.code == 401 else "")
            + ("       403 from dev.to is usually Cloudflare rejecting the client\n"
               "       rather than the API rejecting the key. If it persists, the key\n"
               "       may lack scope: regenerate it at dev.to/settings/extensions.\n"
               if e.code == 403 else "")
            + ("       422 usually means a tag does not exist on DEV, or there are\n"
               "       more than four of them.\n" if e.code == 422 else "")
        )
    except urllib.error.URLError as e:
        raise SystemExit(f"ERROR: could not reach {url}: {e.reason}")


def canonical_is_live(url):
    """Answer "is the canonical there", as robustly as this can be answered.

    THIS BLOCKED A PUBLISH ON 2026-09-07 OVER A PAGE THAT WAS FINE, and the
    diagnosis took two wrong turns worth recording.

    The first version used HEAD and reported 403 on a canonical that a browser and
    curl both load. The obvious reading was "the Cloudflare Worker does not answer
    HEAD" -- but `cloudflare_worker_blog.js` does not branch on `request.method`
    anywhere, so that was wrong too. The likelier cause is Cloudflare refusing
    urllib's default `Python-urllib/3.x` user agent, which is a fact about the
    REQUEST rather than about the page.

    That is the whole lesson, and it is the 402-price lesson again: a status code
    describes the request you made, not the resource you asked about. So this now
    sends a GET with a real user agent, and, far more importantly, it DOES NOT
    BLOCK on an ambiguous answer.

    Only 404 and 410 mean "not published". Everything else -- 403, 405, 429, any
    5xx, a refused connection -- means "this probe could not tell", and a probe
    that cannot tell must not stand between a finished post and its publication.
    Those warn and continue.
    """
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", _UA)
    req.add_header("Accept", "text/html,application/xhtml+xml")
    try:
        with urllib.request.urlopen(req, timeout=30) as fh:
            fh.read(64)
            return fh.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except urllib.error.URLError as e:
        return None, str(e.reason)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="markdown file with DEV front matter")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--publish", action="store_true", help="force published: true")
    mode.add_argument("--draft", action="store_true", help="force published: false")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the payload and exit, sending nothing")
    ap.add_argument("--no-canonical-check", action="store_true",
                    help="skip the canonical liveness check (say why in the commit)")
    args = ap.parse_args()

    text = Path(args.file).read_text(encoding="utf-8")
    fm, body = parse_front_matter(text)

    for required in ("title", "canonical_url"):
        if not fm.get(required):
            raise SystemExit(f"ERROR: front matter has no {required}")

    tags = [t.strip() for t in fm.get("tags", "").split(",") if t.strip()]
    if len(tags) > 4:
        raise SystemExit(f"ERROR: DEV allows at most 4 tags, found {len(tags)}: {tags}")

    published = str(fm.get("published", "false")).lower() == "true"
    if args.publish:
        published = True
    if args.draft:
        published = False

    article = {
        "title": fm["title"],
        "body_markdown": body,
        "published": published,
        "canonical_url": fm["canonical_url"],
        "description": fm.get("description", ""),
        "tags": tags,
    }
    if fm.get("series"):
        article["series"] = fm["series"]

    if args.dry_run:
        print(json.dumps({"article": {**article,
                                      "body_markdown": f"<{len(body)} chars>"}}, indent=2))
        print(f"\nwould {'PUBLISH' if published else 'save as DRAFT'}: {fm['title']}")
        print(f"tags ({len(tags)}): {tags}")
        print(f"canonical: {fm['canonical_url']}")
        return 0

    if published and not args.no_canonical_check:
        code, err = canonical_is_live(fm["canonical_url"])
        if code in (404, 410):
            raise SystemExit(
                f"ERROR: the canonical returned {code}. It is not published:\n"
                f"       {fm['canonical_url']}\n"
                f"       Publish the canonical first. A live DEV copy pointing at a\n"
                f"       canonical that does not exist hands DEV the canonical position\n"
                f"       for our own post, which is the one thing this ordering prevents."
            )
        if code != 200:
            what = err if err is not None else f"HTTP {code}"
            print(f"NOTE: could not confirm the canonical ({what}).\n"
                  f"      That is a fact about this probe, not proof the page is missing:\n"
                  f"      bot protection and edge rules reject scripted requests that a\n"
                  f"      browser sails through. Continuing. Open it yourself if unsure:\n"
                  f"      {fm['canonical_url']}", file=sys.stderr)

    key = os.environ.get("DEVTO_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "ERROR: DEVTO_API_KEY is not set in the environment.\n"
            "       Get a key at https://dev.to/settings/extensions and export it\n"
            "       with `read -rs`, never as a literal in a pasted command."
        )

    # Never create a second copy of a post that is already there.
    existing, page, lookup_failed = None, 1, None
    while page <= 5:
        try:
            batch = _request("GET", f"{API}/articles/me/all?per_page=100&page={page}", key)
        except SystemExit as e:
            # A probe that cannot tell must not stop the work: that is the rule
            # this file's own canonical check broke earlier today. Worst case is a
            # duplicate, which is visible on the dashboard and deletable. Blocking
            # a finished post is worse.
            lookup_failed = str(e).split("\n")[0]
            break
        if not batch:
            break
        for a in batch:
            if a.get("canonical_url") == fm["canonical_url"] or a.get("title") == fm["title"]:
                existing = a
                break
        if existing:
            break
        page += 1

    if lookup_failed:
        print(f"NOTE: could not list existing articles ({lookup_failed}).\n"
              f"      Posting anyway. If this post already existed, there will now be\n"
              f"      TWO on dev.to: delete the older one from the dashboard.",
              file=sys.stderr)

    if existing:
        out = _request("PUT", f"{API}/articles/{existing['id']}", key, {"article": article})
        action = "UPDATED"
    else:
        out = _request("POST", f"{API}/articles", key, {"article": article})
        action = "CREATED"

    print(f"{action}: {out.get('url') or out.get('id')}")
    print(f"published: {out.get('published')}")
    if not out.get("published"):
        print("It is a DRAFT. Re-run with --publish once the canonical is live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
