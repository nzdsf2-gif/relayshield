"""The outreach generator must never diagnose a prospect's security.

    python3 test_generate_outreach.py

Runs the real generator over a synthetic prospect file. No network, no data
from the live sweep.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

TOOL = os.path.join("tools", "generate_outreach.py")

# Phrases that turn a capability offer into an assertion about someone else's
# product. The external study proposed all of these; none of them may ship.
FORBIDDEN = [
    "no url reputation", "no wallet risk", "security opportunities detected",
    "vulnerab", "you are exposed", "your bot is at risk", "we found a gap",
    "unprotected", "insecure",
]


def row(**kw):
    base = {
        "repo": "acme/example-bot", "url": "https://github.com/acme/example-bot",
        "stars": 30, "pushed_at": "2026-08-20T00:00:00Z", "handle": "examplebot",
        "capability_tags": ["links"], "source_query": "python-telegram-bot",
        "opportunity_score": 70, "contact_email": "dev@example.com",
    }
    base.update(kw)
    return base


def drafts_only(text):
    """Just the fenced message blocks.

    Scanning the whole file was wrong: the how-to-use section quotes the very
    phrases it forbids, in order to forbid them, and the first version of this
    test failed on its own instructions. The thing under test is what gets
    SENT.
    """
    blocks, inside = [], False
    for line in text.splitlines():
        if line.startswith("```text"):
            inside = True
            continue
        if line.startswith("```") and inside:
            inside = False
            continue
        if inside:
            blocks.append(line)
    return "\n".join(blocks)


def run(rows, *args):
    d = tempfile.mkdtemp()
    src, out = os.path.join(d, "p.jsonl"), os.path.join(d, "o.md")
    with open(src, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    proc = subprocess.run([sys.executable, TOOL, "--in", src, "--out", out, *args],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    with open(out) as fh:
        return fh.read()


class TestOutreach(unittest.TestCase):
    def test_never_asserts_anything_about_their_security(self):
        text = drafts_only(run([row(capability_tags=[t]) for t in
                    ("links", "wallets", "payments", "ugc", "files", "identity")])).lower()
        for phrase in FORBIDDEN:
            self.assertNotIn(phrase, text, f"draft diagnoses the prospect: {phrase!r}")

    def test_draft_is_keyed_to_the_capability_they_claim(self):
        self.assertIn("wallet addresses", run([row(capability_tags=["wallets"])]))
        self.assertIn("links from users", run([row(capability_tags=["links"])]))
        self.assertIn("moves money", run([row(capability_tags=["payments"])]))

    def test_evidence_line_names_the_tags_the_draft_rests_on(self):
        text = run([row(capability_tags=["wallets", "payments"])])
        self.assertIn("Evidence the draft rests on", text)
        self.assertIn("wallets, payments", text)

    def test_javascript_repos_get_the_javascript_snippet(self):
        self.assertIn("await check(", run([row(source_query="grammy telegram bot")]))
        self.assertIn("check(message.text)", run([row(source_query="python-telegram-bot")]))

    def test_github_only_prospects_are_excluded_by_default(self):
        gh = row(repo="acme/gh-only", contact_email="", contact_site="",
                 contact_github="https://github.com/acme/gh-only")
        self.assertNotIn("acme/gh-only", run([gh]))
        self.assertIn("acme/gh-only", run([gh], "--include-github-only"))

    def test_email_beats_website(self):
        text = run([row(contact_email="dev@example.com", contact_site="https://example.com")])
        self.assertIn("**Contact** email: dev@example.com", text)

    def test_low_scores_are_dropped(self):
        self.assertNotIn("acme/weak", run([row(repo="acme/weak", opportunity_score=10)]))

    def test_house_style_no_em_dashes(self):
        self.assertNotIn("—", drafts_only(run([row()])))

    def test_every_draft_says_the_first_calls_need_no_signup(self):
        for tag in ("links", "wallets", "payments", "ugc", "files"):
            self.assertIn("no key", drafts_only(run([row(capability_tags=[tag])])).lower(), tag)

    def test_tracking_table_lists_each_prospect(self):
        text = run([row(repo="acme/one"), row(repo="acme/two", contact_email="b@example.com")])
        self.assertIn("| acme/one | email |", text)
        self.assertIn("| acme/two | email |", text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
