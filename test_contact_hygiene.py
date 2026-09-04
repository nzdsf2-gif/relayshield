"""Contact hygiene, tested against the real sweep that exposed the need.

    python3 test_contact_hygiene.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))

import contact_hygiene as ch  # noqa: E402


class TestEmails(unittest.TestCase):
    def test_the_real_placeholders_from_the_2026_09_03_sweep(self):
        for bad in ("root@203.0.113.4", "trial@telegram.bot",
                    "k7m2q9x1a3@yourdomain.com", "you@example.com"):
            self.assertFalse(ch.usable_email(bad), bad)
            self.assertTrue(ch.reject_reason(bad, "email"))

    def test_the_three_that_survived_the_first_filter(self):
        # Second sweep, 2026-09-03: a real domain with a stand-in local part, a
        # package version, and the textbook example domain.
        for bad in ("you@gmail.com", "esbuild@0.24.0", "john@acme.com"):
            self.assertFalse(ch.usable_email(bad), bad)

    def test_real_addresses_survive(self):
        # Every one of these is from a real sweep row that we DO want to keep.
        for good in ("chirag@oriz.in", "andrew@relayshield.net",
                     "devmainulislam@gmail.com", "mail@matteosillitti.com",
                     "info@cubevps.ir"):
            self.assertTrue(ch.usable_email(good), good)

    def test_noreply_is_not_a_person(self):
        self.assertFalse(ch.usable_email("noreply@github.com"))

    def test_a_filename_swallowed_from_a_readme_is_not_an_address(self):
        self.assertFalse(ch.usable_email("badge@shields.png"))


class TestSites(unittest.TestCase):
    def test_the_real_non_contacts_from_the_sweep(self):
        for bad in ("https://t.me/d2_schedule_bot",
                    "https://youtu.be/M-IRuWRrVUg",
                    "https://github.com/maleon17/claude-telegram-bridge",
                    "https://simple-tg-chat-mcp.onrender.com/",
                    "https://hearth-loganh.vercel.app"):
            self.assertFalse(ch.usable_site(bad), bad)

    def test_a_real_project_site_survives(self):
        for good in ("https://app.muxel.site", "https://journal.clearheadtrade.com",
                     "https://coolpac.github.io/telegram-mini-apps-catalog",
                     "https://magic-ai-factory.com/argus/"):
            self.assertTrue(ch.usable_site(good), good)

    def test_reason_is_explanatory_not_just_false(self):
        self.assertIn("t.me", ch.reject_reason("https://t.me/x", "site"))
        self.assertIn("github.com", ch.reject_reason("https://github.com/a/b", "site"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
