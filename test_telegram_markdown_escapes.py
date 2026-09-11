"""Legacy Markdown has NO escape syntax, so a backslash-escaped underscore is
always a bug, never a fix.

The founder reported it on 2026-09-10 as "sloppy": "@relayshield\\_bot shows
relayshield in blue and _bot in same word as white characters" -- Telegram links
"@relayshield" as a mention and strands the rest. It was in ELEVEN places in
relayshield_telegram_webhook.py and one in relayshield_forward_analysis.py, and
CLAUDE.md had already recorded the cause on 2026-09-02 without anything
enforcing it.

A code span is literal in legacy Markdown, so the underscore survives.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [ROOT / "relayshield_telegram_webhook.py",
         ROOT / "relayshield_forward_analysis.py"]


class TestNoEscapedUnderscores(unittest.TestCase):
    def test_no_backslash_escaped_underscore_anywhere(self):
        for f in FILES:
            hits = []
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue          # a comment describing the bug is not the bug
                if re.search(r"\\\\_", line):
                    hits.append(f"  {f.name}:{n}: {line.strip()[:90]}")
            self.assertEqual(
                hits, [],
                "legacy Markdown has no escape syntax; use a code span:\n"
                + "\n".join(hits))

    def test_the_handle_constant_exists_and_is_a_code_span(self):
        src = FILES[0].read_text(encoding="utf-8")
        m = re.search(r'BOT_HANDLE_MD\s*=\s*"(.*?)"', src)
        self.assertIsNotNone(m, "BOT_HANDLE_MD is gone")
        self.assertTrue(m.group(1).startswith("`") and m.group(1).endswith("`"),
                        "must be a code span or the underscore breaks again")
        self.assertIn("_bot", m.group(1))

    def test_no_italic_entity_opened_across_the_handle(self):
        """DM_ @relayshield\\_bot _to  -- an italic run opened and closed AROUND
        the username, which emphasised the handle and swallowed the markers."""
        for f in FILES:
            src = f.read_text(encoding="utf-8")
            self.assertNotRegex(src, r"DM_ ", f"{f.name} opens an italic run after DM")


if __name__ == "__main__":
    unittest.main()
