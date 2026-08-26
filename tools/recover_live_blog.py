#!/usr/bin/env python3
"""Recover posts that are live on blog.relayshield.net but absent from this repo.

This is the Worker equivalent of recover_live_handler.yml. A Worker deploy is
destructive: `wrangler deploy` replaces the live script with whatever the repo
builds, so any post that was hand-published and never committed disappears with
no error anywhere. That is the drift rule, and on 2026-08-26 the blog deploy
guard caught four such posts, none of which had ever existed in git history:

    rsscan-deps-who-can-publish-into-your-dependencies
    sender-recognition-is-not-authentication
    the-npm-worm-does-not-start-with-malicious-code
    your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard

Recovery is lossless because the Worker's own RSS feed serves every field the
post schema has: <link> carries the slug, <pubDate> the date, <description> the
excerpt, and <content:encoded> the exact stored html, uncut.

    python3 tools/recover_live_blog.py            # report only
    python3 tools/recover_live_blog.py --write    # write blog_content/*.json

Then run build_blog.py and commit both. Recover BEFORE deploying, never after.
"""
import argparse
import glob
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEED = "https://blog.relayshield.net/rss.xml"
CONTENT_DIR = os.path.join(HERE, "blog_content")
MARKDOWN_DIR = os.path.join(HERE, "blog_markdown")


def fetch(url):
    return subprocess.run(
        ["curl", "-fsS", "--max-time", "30", url], capture_output=True, text=True, check=True
    ).stdout


def _tag(block, name):
    m = re.search(r"<%s[^>]*>(.*?)</%s>" % (name, name), block, re.S)
    if not m:
        return ""
    # A CDATA payload is returned EXACTLY as served, unstripped. build_blog.py's
    # equivalent strips it, which silently drops the trailing newline on every
    # post body. Here that would make a recovered post differ from the live one
    # by a byte, and every later drift check noisier for no reason.
    v = m.group(1)
    cd = re.match(r"^\s*<!\[CDATA\[(.*)\]\]>\s*$", v, re.S)
    return cd.group(1) if cd else v.strip()


def _date(pub):
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(pub, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError("unparseable pubDate: %r" % pub)


def parse_feed(xml):
    """Every <item> in the feed, as a post dict matching the blog_content schema."""
    posts = []
    for block in re.findall(r"<item>.*?</item>", xml, re.S):
        link = _tag(block, "link")
        slug = link.rstrip("/").rsplit("/", 1)[-1]
        html = _tag(block, "content:encoded")
        if not slug or not html:
            continue
        posts.append(
            {
                "slug": slug,
                "title": _tag(block, "title"),
                "date": _date(_tag(block, "pubDate")),
                "excerpt": _tag(block, "description"),
                "html": html,
            }
        )
    return posts


def known_slugs():
    slugs = {os.path.splitext(os.path.basename(p))[0]
             for p in glob.glob(os.path.join(CONTENT_DIR, "*.json"))}
    for path in glob.glob(os.path.join(MARKDOWN_DIR, "*.md")):
        m = re.search(r"^slug:\s*(\S+)\s*$", io.open(path, encoding="utf-8").read(), re.M)
        slugs.add(m.group(1) if m else os.path.splitext(os.path.basename(path))[0])
    return slugs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write the recovered posts to blog_content/")
    ap.add_argument("--feed", default=FEED)
    args = ap.parse_args()

    live = parse_feed(fetch(args.feed))
    if not live:
        print("ERROR: the feed returned no items. Refusing to conclude anything.", file=sys.stderr)
        return 1

    have = known_slugs()
    missing = [p for p in live if p["slug"] not in have]
    print("live: %d posts | in repo: %d | missing from repo: %d" % (len(live), len(have), len(missing)))
    if not missing:
        print("nothing to recover")
        return 0

    for post in missing:
        print("  %s  %s  (%d bytes of html)" % (post["date"], post["slug"], len(post["html"])))
        if args.write:
            out = os.path.join(CONTENT_DIR, post["slug"] + ".json")
            with io.open(out, "w", encoding="utf-8") as fh:
                json.dump(post, fh, ensure_ascii=False, indent=1)

    if args.write:
        print("\nwrote %d posts into blog_content/. Now run build_blog.py and commit both."
              % len(missing))
    else:
        print("\nreport only. Re-run with --write to recover these into blog_content/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
