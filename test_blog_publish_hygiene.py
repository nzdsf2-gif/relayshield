"""Guards on what reaches the live blog.

WHY THIS EXISTS. `build_blog.py` does NOT strip the `NOT FOR PUBLICATION`
section. Every file in blog_markdown/ happens to be pre-stripped by hand, so
the omission has never fired -- but the convention is written in CLAUDE.md
("Blog files carry a NOT FOR PUBLICATION line; everything below it is internal
plan and checklist") and nothing in the repo enforced it.

On 2026-09-16 a post was written with its internal section attached, exactly as
that convention prescribes, and dropping it into blog_markdown/ unedited would
have published the verification notes, the attribution key table and a list of
what shipped alongside it, to a live page, with no error anywhere.

A convention that is followed by hand every time is a convention that fails the
first time somebody is in a hurry. This is the quiet-alarm shape pointed at the
publish path.
"""

import glob
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

# Phrases that only ever appear in the internal half of a blog file. Matched
# case-insensitively against the SERVED html, not against the source, because
# the source and the served text are different documents.
INTERNAL_MARKERS = [
    "not for publication",
    "unverified from the container",
    "attribution keys, registered",
    "channel order and what changes per channel",
    "what shipped alongside this post",
]


def markdown_files():
    return sorted(glob.glob(os.path.join(HERE, "blog_markdown", "*.md")))


def built_posts():
    """The posts as blog_posts.js actually carries them.

    Reads the BUILT artifact rather than the markdown, because what publishes
    is what the builder emitted. A check that reads the source cannot see a
    builder that failed to strip something.
    """
    path = os.path.join(HERE, "blog_posts.js")
    if not os.path.exists(path):
        raise unittest.SkipTest("blog_posts.js not built; run python3 build_blog.py")
    js = open(path, encoding="utf-8").read()
    m = re.search(r"(\[\s*\{.*\}\s*\])", js, re.S)
    assert m, "could not extract the post array from blog_posts.js"
    return json.loads(m.group(1))


class TestNoInternalTextIsPublished(unittest.TestCase):

    def test_no_markdown_source_carries_the_internal_marker(self):
        """The first line of defence, and the cheap one: a file in
        blog_markdown/ is a PUBLISHED file, so it holds published copy only."""
        for path in markdown_files():
            with self.subTest(post=os.path.basename(path)):
                body = open(path, encoding="utf-8").read().lower()
                for marker in INTERNAL_MARKERS:
                    self.assertNotIn(
                        marker, body,
                        f"internal text in a published source: {marker!r}. "
                        "Keep the working copy at the repo root and put only "
                        "the published body in blog_markdown/.",
                    )

    def test_no_built_post_carries_the_internal_marker(self):
        """The line that actually matters: the served html.

        Catches the same defect arriving through blog_content/*.json, which
        bypasses blog_markdown/ entirely.
        """
        for post in built_posts():
            with self.subTest(slug=post.get("slug")):
                blob = (post.get("html", "") + post.get("excerpt", "")).lower()
                for marker in INTERNAL_MARKERS:
                    self.assertNotIn(marker, blob,
                                     f"{post.get('slug')} would publish {marker!r}")


class TestHouseStyle(unittest.TestCase):
    """House style applies to posts written AFTER the conventions were settled.

    CLAUDE.md is explicit that this is not retroactive: "Posts already frozen in
    blog_content/ keep whatever html they were published with. Do not rewrite
    them to match; they are live pages."

    The first version of this test ignored that and failed on fifteen published
    posts. A check that forces you to edit a live page to go green is a check
    that gets loosened rather than obeyed, which is the CSM-SIMSWAP-1 mistake.

    THE CUTOFF IS TAKEN FROM THE DATA, NOT PICKED. The newest post carrying an
    em-dash is 2026-07-29 and the newest carrying a <blockquote> is 2026-08-12,
    so 2026-08-31 sits after every historical offender and before every post
    written under the current conventions. If a NEW post trips these, the post
    is wrong.
    """

    CUTOFF = "2026-08-31"

    def in_scope(self):
        return [p for p in built_posts() if p.get("date", "") >= self.CUTOFF]

    def test_the_cutoff_still_has_posts_behind_it(self):
        """A scoped guard that scopes itself down to nothing passes forever.

        Same shape as a measurement tool reporting a zero: an empty set and a
        clean set produce the identical OK.
        """
        self.assertGreater(len(self.in_scope()), 0,
                           "no posts are in scope; this suite is asserting nothing")

    def test_no_em_dashes_in_new_published_copy(self):
        """CLAUDE.md: no em-dashes in published copy, syndication included.

        CHECKS EVERY PUBLISHED FIELD, not just html. The first version looked
        only at the body, and proving it by injecting an em-dash put it in the
        TITLE, where the guard could not see it and reported OK. The title is
        the most visible string on the page and the one syndication copies
        first.
        """
        for post in self.in_scope():
            for field in ("title", "excerpt", "html"):
                with self.subTest(slug=post.get("slug"), field=field):
                    self.assertNotIn("\u2014", post.get(field, ""))

    def test_no_quote_bars_in_new_published_copy(self):
        """Decided 2026-08-30: quoted text renders as an ordinary paragraph.

        Checked on the rendered HTML, NOT on `> ` in the markdown source. A
        `> ` block still legitimately means "this is quoted" and build_blog.py
        renders it as a plain <p>; the first version of this test read the
        source and failed on markdown that was entirely correct.

        Markdown cannot trip this: build_blog.py already renders `> ` as a
        plain <p>, which is the house style implemented rather than remembered.
        The path this guards is a post added straight to blog_content/*.json,
        where the html is hand-written and nothing renders it.
        """
        for post in self.in_scope():
            with self.subTest(slug=post.get("slug")):
                self.assertNotIn("<blockquote", post.get("html", "").lower())


class TestAttributionOnTheLandingLink(unittest.TestCase):

    def test_a_source_param_is_never_hung_on_the_bare_host(self):
        """`api.relayshield.net?source=` is read by nothing and logs nothing
        under that key -- attribution that looks like it worked, which is FD-8's
        shape. Every attribution key is read by handle_landing_page, which
        serves /developers."""
        bad = re.compile(r"api\.relayshield\.net/?\?source=")
        for post in built_posts():
            with self.subTest(slug=post.get("slug")):
                hit = bad.search(post.get("html", ""))
                self.assertIsNone(
                    hit,
                    f"{post.get('slug')}: ?source= on the bare host. "
                    "It belongs on api.relayshield.net/developers",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
