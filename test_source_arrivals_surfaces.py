#!/usr/bin/env python3
"""Guards for the two attribution surfaces tools/source_arrivals.py reads.

WHY THESE EXIST. tools/miniapp_funnel.py shipped with two of its seven filters
wrong on the first draft, BOTH in the direction that reports a live channel as
dead: one searched for the deep-link payload `SRC_miniapp` while the webhook
strips the prefix and lower-cases it before logging, so the filter would have
matched nothing forever. A zero from a measurement tool GETS ACTED ON, which
makes a wrong filter more expensive than no tool at all.

So every assertion here reads the filter out of the TOOL and matches it against
the line the handler ACTUALLY WRITES, taken out of the handler's own source.
Neither side is retyped. Proven by reintroducing each defect.

    python3 test_source_arrivals_surfaces.py

Needs no AWS and no boto3: it imports the module, exercises report() against
fabricated counts, and parses the handlers with ast.
"""
import ast
import io
import json
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import source_arrivals as sa  # noqa: E402


def strip_py_comments(src: str) -> str:
    """Drop comments and docstrings.

    SIX TIMES a guard in this repo has passed on a real defect because it
    matched the PROSE describing the rule rather than the rule. The natural way
    to write a guard is to search the file and the natural way to write good
    code is to explain the rule beside it; they collide every time. Stripped in
    the FIRST version of this guard, not the second.
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def logged_format_strings(path: Path) -> list:
    """Every literal passed as a logger call's first argument, comments gone."""
    tree = ast.parse(strip_py_comments(path.read_text()))
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logger" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            out.append(node.args[0].value)
    return out


def render(fmt: str, *args) -> str:
    """What logging actually puts in CloudWatch for this call."""
    return fmt % args


class TestBotSurfaceMatchesTheHandler(unittest.TestCase):
    """The bot filter against relayshield_telegram_webhook.py's own line."""

    def setUp(self):
        self.spec = sa.SURFACES["bot"]
        self.fmts = logged_format_strings(ROOT / "relayshield_telegram_webhook.py")

    def test_the_acquisition_line_still_exists_in_the_handler(self):
        hits = [f for f in self.fmts if f.startswith("acquisition source=")]
        self.assertTrue(
            hits,
            "relayshield_telegram_webhook.py no longer logs an 'acquisition "
            "source=' line. The bot surface is measuring nothing and would "
            "report every directory as zero.")

    def test_the_regex_matches_the_rendered_line(self):
        fmt = next(f for f in self.fmts if f.startswith("acquisition source="))
        line = render(fmt, "storebot", "deadbeef")
        m = self.spec["line"].search(line)
        self.assertIsNotNone(
            m, f"the bot filter does not match the line the handler writes: {line!r}")
        self.assertEqual(
            m.group(1), "storebot",
            "the filter matched but captured the wrong field. A key that is "
            "captured wrong is a channel reported as zero.")

    def test_the_cloudwatch_filter_pattern_is_a_substring_of_that_line(self):
        fmt = next(f for f in self.fmts if f.startswith("acquisition source="))
        line = render(fmt, "storebot", "deadbeef")
        self.assertIn(
            self.spec["filter"], line,
            "filter_log_events would reject every event. The server-side "
            "filter and the client-side regex must agree, and only the first "
            "of them is visible in the output.")

    def test_the_key_is_lower_cased_by_the_handler_before_logging(self):
        """SRC_StoreBot must be countable as `storebot`, or the route table lies.

        This is the exact defect miniapp_funnel.py shipped: a filter written
        against the DEEP LINK payload rather than against the line the handler
        emits after transforming it.
        """
        src = ROOT / "relayshield_telegram_webhook.py"
        code = strip_py_comments(src.read_text())
        self.assertIn(
            'payload.upper()[4:].lower()', code,
            "the SRC_ payload is no longer lower-cased before it is logged, so "
            "bot_directories.json's lower-case keys will not match the log.")


class TestDevelopersSurfaceStillMatches(unittest.TestCase):
    def test_the_regex_matches_the_signup_line(self):
        fmts = logged_format_strings(ROOT / "relayshield_developer_signup.py")
        hits = [f for f in fmts if "developer-signup request" in f]
        self.assertTrue(hits, "the developers surface lost its log line")
        for fmt in hits:
            line = render(fmt, *(["rsscan"] * fmt.count("%s")))
            if "source=" in line:
                self.assertIsNotNone(
                    sa.SURFACES["developers"]["line"].search(line),
                    f"the developers filter no longer matches: {line!r}")
                break
        else:
            self.fail("no rendered signup line carried a source= field")


class TestTheTwoSurfacesStayDistinct(unittest.TestCase):
    def test_log_groups_differ(self):
        groups = {s["log_group"] for s in sa.SURFACES.values()}
        self.assertEqual(len(groups), len(sa.SURFACES),
                         "two surfaces reading one log group is one surface")

    def test_only_the_developers_surface_is_gated(self):
        """The gate is what makes an unmatched: row possible, and the bot has none.

        Reporting an 'UNREGISTERED key' on the bot surface would send the
        reader to register a key in a table the webhook never consults.
        """
        self.assertTrue(sa.SURFACES["developers"]["gated"])
        self.assertFalse(sa.SURFACES["bot"]["gated"])


class TestBotDirectoriesTable(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "bot_directories.json").read_text())

    def test_keys_are_unique(self):
        keys = [r["key"] for r in self.data["routes"]]
        self.assertEqual(len(keys), len(set(keys)),
                         "two destinations sharing one key makes the delta "
                         "uninterpretable, which is the tg-miniapp-channel defect")

    def test_keys_survive_the_handler_transform(self):
        for r in self.data["routes"]:
            k = r["key"]
            self.assertEqual(
                k, ("SRC_" + k).upper()[4:].lower()[:32],
                f"{k!r} is not what the webhook would log for SRC_{k}")

    def test_the_link_form_is_the_one_the_handler_parses(self):
        form = self.data["link_form"]
        self.assertIn("?start=SRC_", form,
                      "a bare t.me link logs NOTHING and leaves no unmatched "
                      "row; omission is the unrecoverable mistake on this surface")

    def test_no_bot_key_is_registered_on_the_landing_page_tables(self):
        """A bot key in _SOURCE_BANNERS is a key in the wrong table.

        It would measure nothing -- the bot never consults those tables -- and
        it would make the developers surface report arrivals it never had.
        """
        landing = strip_py_comments((ROOT / "relayshield_developer_signup.py").read_text())
        for r in self.data["routes"]:
            self.assertNotIn(
                f'"{r["key"]}"', landing,
                f'bot key {r["key"]!r} appears in relayshield_developer_signup.py')


class TestReportWording(unittest.TestCase):
    """Execute report(), because reading it does not answer what it prints."""

    def _run(self, surface, counts, want):
        from collections import Counter
        buf = io.StringIO()
        with redirect_stdout(buf):
            sa.report(Counter(counts), sum(counts.values()) or 1,
                      1757000000000, 30, want, surface)
        return buf.getvalue()

    def test_bot_report_names_the_omission_failure(self):
        out = self._run("bot", {"storebot": 4}, [])
        self.assertIn("SRC_", out)
        self.assertIn("EVERY COUNT ABOVE EXCLUDES", out)

    def test_bot_zero_does_not_read_as_a_dead_channel(self):
        out = self._run("bot", {"tgbotlist": 2}, ["storebot"])
        self.assertIn("ZERO ARRIVALS", out)
        self.assertIn("BARE t.me/relayshield_bot", out,
                      "a zero here has two causes and the report owes the "
                      "reader the one that looks identical")

    def test_bot_report_never_tells_you_to_register_a_key(self):
        out = self._run("bot", {"storebot": 1}, ["storebot", "tgbotlist"])
        self.assertNotIn("UNREGISTERED", out)
        self.assertNotIn("_SOURCE_BANNERS", out)

    def test_an_unknown_bot_key_is_not_reported_as_lost(self):
        out = self._run("bot", {"mystery": 3}, ["mystery"])
        self.assertIn("NOT IN bot_directories.json", out)
        self.assertIn("real count", out,
                      "the count IS real on an ungated surface; calling it lost "
                      "would send the reader to fix a link that works")

    def test_developers_report_is_unchanged(self):
        out = self._run("developers", {"rsscan": 3, "unmatched:nope": 1}, ["rsscan"])
        self.assertIn("UNMATCHED KEYS", out)
        self.assertIn("developers page", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
