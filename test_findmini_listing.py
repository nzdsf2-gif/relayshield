"""Guards for the findmini.app listing watcher.

The two that matter are the ones that separate LISTED from CANNOT TELL: a
soft 404 served at 200 must not read as published, and an unreachable site
must not read as "not published yet".
"""
import importlib.util
import pathlib
import unittest

# Loaded BY PATH rather than as tools.check_findmini_listing, deliberately.
# Importing it as a package needs a tools/__init__.py, and adding one changes
# how every other script in that directory resolves -- a repo-wide semantic
# change to make one test's import line shorter.
_spec = importlib.util.spec_from_file_location(
    "check_findmini_listing",
    pathlib.Path(__file__).resolve().parent / "tools" / "check_findmini_listing.py",
)
w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w)


class NamesUs(unittest.TestCase):
    def test_a_page_carrying_the_bot_link_is_proof(self):
        self.assertEqual(
            w.names_us('<a href="https://t.me/relayshield_bot/idcheck?startapp=x">open</a>'),
            "t.me/relayshield_bot",
        )

    def test_the_app_name_is_proof(self):
        self.assertEqual(w.names_us("<h1>RelayShield IDCheck</h1>"), "RelayShield IDCheck")

    def test_case_does_not_matter(self):
        self.assertIsNotNone(w.names_us("<h1>relayshield idcheck</h1>"))

    def test_a_soft_404_at_200_is_NOT_proof(self):
        # The defect this exists to stop: a catalogue serving a placeholder or
        # a search page with HTTP 200. A status code alone would flip the
        # watcher to LISTED over a page that says the app does not exist.
        body = "<html><body><h1>App not found</h1><p>Try our catalog.</p></body></html>"
        self.assertIsNone(w.names_us(body))

    def test_another_app_page_is_not_proof(self):
        self.assertIsNone(w.names_us('<a href="https://t.me/tapps_bot">Telegram Apps Center</a>'))


class Verdicts(unittest.TestCase):
    """main() classifies from fetch(), so stub fetch() and read the status line."""

    def run_with(self, responses):
        original = w.fetch
        seq = list(responses)
        w.fetch = lambda url: seq.pop(0)
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                w.main()
            return buf.getvalue()
        finally:
            w.fetch = original

    def test_all_404_is_not_listed_and_is_not_an_error(self):
        out = self.run_with([(404, "", "")] * len(w.CANDIDATES))
        self.assertIn("FINDMINI_LISTING_STATUS=not_listed", out)

    def test_all_unreachable_is_undetermined_never_not_listed(self):
        out = self.run_with([(None, "", "URLError: blocked")] * len(w.CANDIDATES))
        self.assertIn("FINDMINI_LISTING_STATUS=undetermined", out)
        self.assertNotIn("STATUS=not_listed", out)

    def test_a_403_is_undetermined_rather_than_absent(self):
        # Cloudflare refusing a client is a fact about the request, not about
        # whether the listing exists.
        out = self.run_with([(403, "denied", "")] * len(w.CANDIDATES))
        self.assertIn("FINDMINI_LISTING_STATUS=undetermined", out)

    def test_one_real_hit_wins_over_other_candidates_404ing(self):
        out = self.run_with([
            (404, "", ""),
            (200, '<a href="https://t.me/relayshield_bot/idcheck">go</a>', ""),
            (404, "", ""),
        ])
        self.assertIn("FINDMINI_LISTING_STATUS=listed", out)

    def test_a_200_soft_404_does_not_report_listed(self):
        out = self.run_with([(200, "<h1>App not found</h1>", "")] * len(w.CANDIDATES))
        self.assertIn("FINDMINI_LISTING_STATUS=not_listed", out)
        self.assertNotIn("STATUS=listed", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
