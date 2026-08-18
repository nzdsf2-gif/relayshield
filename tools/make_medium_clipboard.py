#!/usr/bin/env python3
"""Load a published post onto the clipboard as HTML, ready to paste into Medium.

WHY THIS EXISTS
---------------
Medium's editor converts a *rich* (HTML-flavoured) clipboard into real headings,
lists, tables and code blocks. A plain-text clipboard makes it render raw
Markdown characters, and RTF flattens <pre> into prose. So the clipboard has to
carry the `public.html` flavour specifically.

The previous recipe was a one-liner:

    osascript -e "set the clipboard to «data HTML$(hexdump -ve '1/1 "%.2x"' post.html)»"

It is fragile for two reasons that both bit us on 2026-08-11. It depends on a
`post.html` existing in the current directory, and when that file is missing
`hexdump` emits nothing, so AppleScript receives a bare `«data HTML»` and fails
with a syntax error at column 31 that says nothing about the real cause. It also
carries guillemets, which do not survive being copied between terminals.

This script takes the slug instead, reads the HTML straight out of the generated
`blog_posts.js` so what you paste is exactly what is published, and sets both the
HTML and plain-text flavours on the pasteboard.

Usage:
    ~/anaconda3/bin/python3 tools/make_medium_clipboard.py <slug>
    ~/anaconda3/bin/python3 tools/make_medium_clipboard.py --list
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_JS = os.path.join(HERE, "blog_posts.js")
SITE = "https://blog.relayshield.net"


def load_posts():
    raw = io.open(POSTS_JS, encoding="utf-8").read()
    return json.loads(raw[raw.index("["):raw.rindex("]") + 1])


def set_clipboard_html(html: str, plain: str) -> None:
    from AppKit import NSPasteboard, NSPasteboardTypeHTML, NSPasteboardTypeString

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(html, NSPasteboardTypeHTML)
    pb.setString_forType_(plain, NSPasteboardTypeString)


def main():
    args = [a for a in sys.argv[1:] if a]
    posts = load_posts()

    if not args or args[0] == "--list":
        for p in posts:
            print("%s  %s" % (p["date"], p["slug"]))
        return 0

    slug = args[0].rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    match = [p for p in posts if p["slug"] == slug]
    if not match:
        print("no post with slug %r. run --list to see them." % slug, file=sys.stderr)
        return 1
    post = match[0]

    # Medium sets canonical from the "Import" flow only. We paste, so the
    # canonical has to be set by hand afterwards. Carrying the source line in the
    # body means the attribution survives even if that step is forgotten.
    body = post["html"]
    source_line = (
        '<p><em>Originally published at '
        '<a href="{site}/{slug}">{site}/{slug}</a>.</em></p>'
    ).format(site=SITE, slug=post["slug"])

    html = "<h1>%s</h1>\n%s\n%s" % (post["title"], body, source_line)
    plain = re.sub(r"<[^>]+>", "", html)

    set_clipboard_html(html, plain)

    print("clipboard loaded with HTML flavour")
    print("  title:      %s" % post["title"])
    print("  date:       %s" % post["date"])
    print("  html bytes: %d" % len(html.encode("utf-8")))
    print("  canonical:  %s/%s" % (SITE, post["slug"]))
    print()
    print("In Medium: Cmd+V into a new story, then set the canonical by hand at")
    print("  ... -> More settings -> Advanced Settings -> Customize Canonical Link")
    print("The button relabels to 'Edit canonical link' once it saves. That means it worked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
