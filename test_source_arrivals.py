"""Tests for tools/source_arrivals.py.

THE FIRST VERSION OF registered_keys() WAS WRONG IN THE MOST MISLEADING WAY
AVAILABLE, and these tests exist to pin the fix rather than to describe it.

It walked only ast.Assign, so it read _SOURCE_ALIASES and silently skipped
_SOURCE_BANNERS, which is written as `_SOURCE_BANNERS: dict[...] = {` and is
therefore an ast.AnnAssign. It returned 117 keys, which looks like a working
parse, with every actual banner key absent. The tool would then have reported
`rsscan` -- the exact key the IDE-widget question turns on -- as UNREGISTERED,
and an unregistered key is a completely different finding from a channel that
produced nothing.

A test that reads the same wrong thing as the code proves nothing (2026-09-05,
the plugin.json mcpServers case), so these assert against keys grepped out of
the handler by hand, not against whatever the walker happens to return.
"""

import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import source_arrivals as sa  # noqa: E402


class TestRegisteredKeys(unittest.TestCase):
    def setUp(self):
        self.keys = sa.registered_keys()

    def test_reads_both_tables(self):
        # One key from _SOURCE_BANNERS (AnnAssign) and one from _SOURCE_ALIASES
        # (plain Assign). The bug returned the second and not the first.
        self.assertIn("rsscan", self.keys, "banner table (AnnAssign) not parsed")
        self.assertIn("tg-miniapp-blog", self.keys, "alias table not parsed")

    def test_base_keys_the_distribution_questions_turn_on(self):
        # Each of these is a key a live link already carries. Reporting any of
        # them as UNREGISTERED would send someone to fix a registration that is
        # already correct, and would read as "the channel is broken".
        for key in ("rsscan", "rsscan-deps", "tg-widget", "tg-miniapp",
                    "pypi", "mcp-registry", "github"):
            self.assertIn(key, self.keys, f"{key} should be registered")

    def test_agrees_with_a_direct_parse_of_the_handler(self):
        # The independent check: parse the handler here, in this file, without
        # using the tool's own walker, and require the tool to be a superset.
        src = (ROOT / "relayshield_developer_signup.py").read_text()
        tree = ast.parse(src)
        direct = set()
        for node in ast.walk(tree):
            target = None
            if isinstance(node, ast.AnnAssign):
                target = getattr(node.target, "id", None)
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = getattr(node.targets[0], "id", None)
            if target in ("_SOURCE_BANNERS", "_SOURCE_ALIASES") and \
                    isinstance(node.value, ast.Dict):
                for k in node.value.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        direct.add(k.value)
        self.assertTrue(direct, "the direct parse found nothing -- fix this test")
        self.assertEqual(direct, self.keys)

    def test_an_unregistered_key_is_absent(self):
        self.assertNotIn("definitely-not-a-registered-key", self.keys)


class TestMiniAppSourcesAreRegistered(unittest.TestCase):
    """Every ?source= the Mini App Worker will forward must resolve.

    The Worker drops an unknown start_param and falls back to "tg-miniapp", so
    that fallback in particular has to exist: an unregistered key logs
    `unmatched:` and renders no banner, which looks like attribution and is
    none. That is FD-8, four months of it, and the Worker's own header says so.
    """

    def test_worker_allowed_sources_all_registered(self):
        worker = (ROOT / "cloudflare_worker_miniapp.js").read_text()
        block = worker.split("ALLOWED_SOURCES = new Set([", 1)[1].split("]);", 1)[0]
        allowed = [line.strip().strip('",') for line in block.splitlines()
                   if line.strip().startswith('"')]
        self.assertTrue(allowed, "parsed no sources out of the Worker")
        keys = sa.registered_keys()
        for key in allowed:
            self.assertIn(key, keys, f"Worker forwards ?source={key}, unregistered")


class TestCli(unittest.TestCase):
    def test_list_registered_needs_no_aws(self):
        # The whole point of the offline half: it must work in a container with
        # no credentials, or the check gets skipped, and a skipped check is how
        # this repo ends up quoting an unmeasured number.
        out = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "source_arrivals.py"),
             "--list-registered"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("rsscan", out.stdout.split())


if __name__ == "__main__":
    unittest.main()
