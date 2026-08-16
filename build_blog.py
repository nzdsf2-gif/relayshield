#!/usr/bin/env python3
"""Generate blog_posts.js for the self-hosted RelayShield blog Worker.

Sources, in precedence order (later wins):
  1. blog_content/*.json    - the FROZEN local snapshot. This is the source of
                              truth and the reason the blog does not depend on
                              Hashnode staying up.
  2. The live Hashnode RSS  - only fills in slugs not already frozen locally.
  3. blog_source/*.md       - manually exported posts (incl. archived ones the
                              public RSS cannot reach). Front matter: title,
                              slug, date. Overrides both of the above.

Run:    python3 build_blog.py
Freeze: python3 build_blog.py --freeze   (writes blog_content/ from whatever
        sources currently resolve — do this BEFORE deleting anything upstream)
Then:   npx wrangler deploy --config wrangler.blog.toml

WHY THE FREEZE EXISTS: the original build pulled all 15 posts from Hashnode's
live RSS. Deleting those posts on Hashnode would have made the next build emit
one post and a deploy would have wiped the blog. Freeze first, then take down.
"""
import glob
import html
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RSS = "https://relayshield.hashnode.dev/rss.xml"
# Renamed from "hashnode_export" on 2026-08-11. This directory is a LOCAL input
# to this build and has never been a publishing destination, but the old name
# read like one and caused a false alarm that a post had been sent to Hashnode.
# Hashnode is retired: never publish there. See the RSS note below.
EXPORT_DIR = os.path.join(HERE, "blog_source")
CONTENT_DIR = os.path.join(HERE, "blog_content")
OUT = os.path.join(HERE, "blog_posts.js")


def from_local():
    """The frozen snapshot — independent of Hashnode being online."""
    posts = []
    for path in sorted(glob.glob(os.path.join(CONTENT_DIR, "*.json"))):
        with io.open(path, encoding="utf-8") as fh:
            post = json.load(fh)
        post["source"] = "local"
        posts.append(post)
    return posts


def freeze(posts):
    os.makedirs(CONTENT_DIR, exist_ok=True)
    for post in posts:
        out = dict(post)
        out.pop("source", None)
        with io.open(os.path.join(CONTENT_DIR, post["slug"] + ".json"), "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
    print("froze %d posts into %s" % (len(posts), CONTENT_DIR))


def _tag(block, name):
    m = re.search(r"<%s[^>]*>(.*?)</%s>" % (name, name), block, re.S)
    if not m:
        return ""
    v = m.group(1).strip()
    cd = re.match(r"^<!\[CDATA\[(.*)\]\]>$", v, re.S)
    return (cd.group(1) if cd else v).strip()


def from_rss():
    try:
        xml = subprocess.run(
            ["curl", "-s", "--max-time", "30", RSS], capture_output=True, text=True, check=True
        ).stdout
    except Exception as exc:
        print("RSS fetch failed (%s) - continuing with exports only" % exc, file=sys.stderr)
        return []

    posts = []
    for block in re.findall(r"<item>.*?</item>", xml, re.S):
        link = _tag(block, "link")
        slug = link.rstrip("/").rsplit("/", 1)[-1]
        body = _tag(block, "content:encoded")
        if not slug or not body:
            continue
        posts.append(
            {
                "slug": slug,
                "title": html.unescape(_tag(block, "title")),
                "date": _rfc822(_tag(block, "pubDate")),
                "excerpt": _excerpt(body),
                "html": body,
                "source": "rss",
            }
        )
    return posts


def _rfc822(value):
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _excerpt(body, limit=185):
    text = re.sub(r"<[^>]+>", " ", body)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit].rsplit(" ", 1)[0] + ("..." if len(text) > limit else "")


def from_exports():
    """Markdown exports, for archived posts the RSS cannot serve."""
    posts = []
    for path in sorted(glob.glob(os.path.join(EXPORT_DIR, "*.md"))):
        raw = io.open(path, encoding="utf-8").read()
        meta, body_md = {}, raw
        fm = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
        if fm:
            for line in fm.group(1).split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
            body_md = fm.group(2)

        slug = meta.get("slug") or os.path.splitext(os.path.basename(path))[0]
        title = meta.get("title") or _first_heading(body_md) or slug.replace("-", " ").title()
        # Strip the leading H1 — the Worker renders the title itself, so leaving
        # it in the body duplicates it on the page and pollutes the excerpt.
        # Anchored with \A plus \s* because front matter leaves a leading newline.
        body_md = re.sub(r"\A\s*#\s+.*\n", "", body_md, count=1)
        body_html = md_to_html(body_md)
        posts.append(
            {
                "slug": slug,
                "title": title,
                "date": meta.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "excerpt": _excerpt(body_html),
                "html": body_html,
                "source": "export",
            }
        )
    return posts


def _first_heading(md):
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else ""


_CODE_RE   = re.compile(r"`([^`]+)`")
_LINK_RE   = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_STRONG_RE = re.compile(r"\*\*([^*]+)\*\*")
_EM_RE     = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def _inline(text):
    """Render inline markdown.

    Code spans are stashed BEFORE escaping and before the emphasis passes. Doing
    it in the other order caused two real bugs that shipped to the published
    Elastic guide on 2026-07-29:
      * `<API Key Type>` was escaped to &lt;...&gt; and then escaped AGAIN inside
        the code span, rendering the literal text "&lt;API Key Type&gt;".
      * In "`logs-*` or `filebeat-*`" the emphasis regex matched across the two
        code spans, swallowing both asterisks and emitting a stray <em>, so the
        index patterns rendered as "logs-" and "filebeat-".
    """
    stash = []

    def _keep(m):
        stash.append(m.group(1))
        return "\x00C%d\x00" % (len(stash) - 1)

    text = _CODE_RE.sub(_keep, text)
    text = html.escape(text, quote=False)
    text = _LINK_RE.sub(r'<a href="\2">\1</a>', text)
    text = _STRONG_RE.sub(r"<strong>\1</strong>", text)
    text = _EM_RE.sub(r"<em>\1</em>", text)
    for i, code in enumerate(stash):
        text = text.replace("\x00C%d\x00" % i, "<code>%s</code>" % html.escape(code, quote=False))
    return text


def md_to_html(md):
    # in_list holds the open list tag ("ul" / "ol") or None. It was a bool while
    # only bullets were supported; ordered lists had NO branch at all, so "1. ..."
    # fell through to the paragraph gatherer and five numbered items rendered as
    # one run-on paragraph. Caught on the secret-scanning post 2026-08-03, where
    # the numbered list is the centrepiece.
    out, lines, i, in_list = [], md.split("\n"), 0, None
    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            if in_list:
                out.append("</%s>" % in_list)
                in_list = None
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(buf)))
            continue

        if re.match(r"^\s*\|.*\|\s*$", line):
            rows = []
            while i < len(lines) and re.match(r"^\s*\|.*\|\s*$", lines[i]):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            if len(rows) >= 2 and all(re.match(r"^:?-{2,}:?$", c) for c in rows[1]):
                head, body = rows[0], rows[2:]
                cells = "".join("<th>%s</th>" % _inline(c) for c in head)
                trs = "".join(
                    "<tr>%s</tr>" % "".join("<td>%s</td>" % _inline(c) for c in r) for r in body
                )
                out.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (cells, trs))
                continue
            for r in rows:
                out.append("<p>%s</p>" % _inline(" | ".join(r)))
            continue

        if line.startswith(">"):
            # Gather the whole quote, not one <blockquote> per source line. The
            # sources are hard-wrapped at ~100 chars, so emitting a blockquote
            # per line turned every multi-line callout into a stack of
            # separately-bordered boxes with gaps between them, and stopped
            # **bold** spanning a line break from rendering at all -- the same
            # failure the paragraph gatherer below already fixes. A bare ">"
            # separates paragraphs inside a quote; it previously fell through
            # to the paragraph branch and rendered as a literal "&gt;".
            # Caught on the Sentinel guide 2026-08-16.
            if in_list:
                out.append("</%s>" % in_list)
                in_list = None
            para, paras = [], []
            while i < len(lines) and lines[i].startswith(">"):
                content = lines[i][1:].strip()
                if content:
                    para.append(content)
                elif para:
                    paras.append(para)
                    para = []
                i += 1
            if para:
                paras.append(para)
            for p in paras:
                out.append("<blockquote>%s</blockquote>" % _inline(" ".join(p)))
            continue

        m_li = re.match(r"^([-*]|\d+\.)\s+", line)
        if m_li:
            tag = "ul" if m_li.group(1) in ("-", "*") else "ol"
            # Switching marker type closes the open list rather than nesting the
            # new items inside it.
            if in_list != tag:
                if in_list:
                    out.append("</%s>" % in_list)
                out.append("<%s>" % tag)
                in_list = tag
            # Absorb indented continuation lines into this same <li>. Without
            # this, a wrapped bullet emitted a <p> *inside* the <ul> -- invalid
            # HTML that Medium's importer responded to by dropping the whole
            # list. That silently removed the LLMjacking figures and the entire
            # US/EU provider list from the imported Bundle D post (2026-07-30).
            item = line[m_li.end():]
            i += 1
            while (i < len(lines) and lines[i].strip()
                   and not re.match(r"^([-*]|\d+\.)\s+", lines[i])
                   and not lines[i].startswith("```")
                   and not re.match(r"^#{1,6}\s", lines[i])
                   and lines[i].startswith((" ", "\t"))):
                item += " " + lines[i].strip()
                i += 1
            out.append("<li>%s</li>" % _inline(item))
            continue

        if in_list and not line.strip():
            out.append("</%s>" % in_list)
            in_list = None

        if re.match(r"^---+\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            lvl = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (lvl, _inline(m.group(2)), lvl))
            i += 1
            continue

        if line.strip():
            # Gather the whole paragraph, not one <p> per source line. The
            # sources here are hard-wrapped at ~100 chars, so emitting a
            # paragraph per line broke every wrapped sentence into its own
            # block ("dangling sentences" on the Medium import) and stopped
            # **bold** spanning a line break from ever rendering, since the
            # opening and closing markers landed in different <p> elements.
            para = [line.strip()]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if (not nxt.strip() or nxt.startswith("```")
                        or re.match(r"^#{1,6}\s", nxt)
                        or re.match(r"^([-*]|\d+\.)\s+", nxt)
                        or nxt.startswith("> ")
                        or re.match(r"^---+\s*$", nxt)
                        or re.match(r"^\s*\|.*\|\s*$", nxt)):
                    break
                para.append(nxt.strip())
                i += 1
            out.append("<p>%s</p>" % _inline(" ".join(para)))
            continue
        i += 1

    if in_list:
        out.append("</%s>" % in_list)
    return "\n".join(out)


def main():
    by_slug = {}

    # Frozen local snapshot is the base — the blog survives Hashnode going away.
    for post in from_local():
        by_slug[post["slug"]] = post

    # Hashnode RSS: RETIRED 2026-08-11, deliberately not called.
    #
    # Hashnode is not to be used again. It silently unpublished the Elastic
    # guide twice and its AutoMod archived a post three times. Every one of the
    # 21 posts is now frozen in blog_content/ or authored in blog_source/, so
    # this fetch had nothing left to contribute: the last build that ran it
    # reported "0 from RSS". from_rss() is kept only so old frozen posts remain
    # explainable, and calling it again would reintroduce a live dependency on
    # a service we have deliberately left.
    #
    # for post in from_rss():
    #     by_slug.setdefault(post["slug"], post)

    # Exports win: they carry archived posts and any corrected copy.
    for post in from_exports():
        by_slug[post["slug"]] = post

    posts = sorted(by_slug.values(), key=lambda p: p["date"], reverse=True)
    if not posts:
        print("ERROR: no posts found from any source", file=sys.stderr)
        return 1

    if "--freeze" in sys.argv:
        freeze(posts)
        posts = sorted(from_local() + from_exports(), key=lambda p: p["date"], reverse=True)
        seen, deduped = set(), []
        for p in posts:
            if p["slug"] not in seen:
                seen.add(p["slug"])
                deduped.append(p)
        posts = deduped

    payload = json.dumps(posts, ensure_ascii=False, indent=0)
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write("// Generated by build_blog.py. Do not edit by hand.\n")
        fh.write("export const POSTS = %s;\n" % payload)

    from_rss_n = sum(1 for p in posts if p.get("source") == "rss")
    from_exp_n = sum(1 for p in posts if p.get("source") == "export")
    print(
        "wrote %s\n  %d posts total (%d from RSS, %d from blog_source/)\n  %.0f KB"
        % (OUT, len(posts), from_rss_n, from_exp_n, os.path.getsize(OUT) / 1024)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
