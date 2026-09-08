#!/usr/bin/env python3
"""Invariants for the Telegram Mini App. No network, no boto3, no node.

Every assertion here exists because of a specific failure this repo has already
paid for. They are not general good practice.
"""

import ast
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKER = ROOT / "cloudflare_worker_miniapp.js"
SIGNUP = ROOT / "relayshield_developer_signup.py"
WRANGLER = ROOT / "wrangler.miniapp.toml"


def _worker() -> str:
    return WORKER.read_text(encoding="utf-8")


def _registered_source_keys() -> set:
    """Every ?source= value that resolves to a banner, read from the real tables."""
    tree = ast.parse(SIGNUP.read_text(encoding="utf-8"))

    def grab(name):
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == name:
                        return node.value
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == name:
                return node.value
        raise AssertionError(f"{name} not found")

    banners = {ast.literal_eval(k) for k in grab("_SOURCE_BANNERS").keys}
    aliases = ast.literal_eval(grab("_SOURCE_ALIASES"))
    return banners | {k for k, v in aliases.items() if v in banners}


class TestAttribution(unittest.TestCase):
    def test_every_allowed_source_is_registered(self):
        """FD-8 is four months of unattributed arrivals from an unregistered key.

        The Worker forwards startapp as ?source=. A value it allows but which no
        banner resolves logs `unmatched:` and renders nothing, which looks like
        attribution and is none.
        """
        block = re.search(r"ALLOWED_SOURCES = new Set\(\[(.*?)\]\)", _worker(), re.S)
        self.assertIsNotNone(block, "ALLOWED_SOURCES not found in the Worker")
        allowed = set(re.findall(r'"([^"]+)"', block.group(1)))
        self.assertTrue(allowed, "ALLOWED_SOURCES is empty")
        missing = sorted(allowed - _registered_source_keys())
        self.assertEqual(missing, [], f"unregistered ?source= keys: {missing}")

    def test_unknown_start_param_falls_back_rather_than_forwarding(self):
        self.assertIn("ALLOWED_SOURCES.has(startParam)", _worker())


class TestEmbeddedWidget(unittest.TestCase):
    def test_embedded_widget_is_current(self):
        """One implementation, two surfaces. A stale embed is the four-pattern-table
        failure with a build step in front of it."""
        r = subprocess.run(["python3", "tools/build_miniapp.py", "--check"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_embedded_widget_is_a_valid_js_string_literal(self):
        m = re.search(r"^const WIDGET_JS = (\".*\");\s*$", _worker(), re.M)
        self.assertIsNotNone(m, "WIDGET_JS literal missing or not on one line")
        decoded = json.loads(m.group(1))
        self.assertIn("export const API_BASE", decoded)
        self.assertIn("export async function check", decoded.replace("export function check",
                                                                    "export async function check"))


class TestRendering(unittest.TestCase):
    def test_reasons_are_never_written_as_html(self):
        """Reasons quote attacker-supplied strings. The widget's own header says
        so; rendering one with innerHTML would put a hostile URL into the DOM."""
        worker = _worker()
        self.assertIn("li.textContent = r;", worker)
        self.assertNotIn(".innerHTML", worker)

    def test_it_never_says_safe(self):
        """The ceiling is 'nothing known against it'. This is a product rule, and
        the same one the endpoints state in their own responses."""
        worker = _worker()
        self.assertIn("nothing known against it", worker.lower())
        heads = re.search(r"const HEADS = \{(.*?)\};", worker, re.S)
        self.assertIsNotNone(heads)
        self.assertNotRegex(heads.group(1).lower(), r'"\s*safe\s*"')

    def test_unknown_is_not_presented_as_clear(self):
        self.assertIn("Treat that as unknown, not as clear.", _worker())


class TestHeaders(unittest.TestCase):
    def test_telegram_can_frame_it(self):
        """Telegram renders a Mini App in an iframe. A DENY here is a blank app,
        and it would look like the app is broken rather than blocked."""
        worker = _worker()
        self.assertIn("frame-ancestors https://web.telegram.org https://telegram.org", worker)
        self.assertNotIn("X-Frame-Options", worker)

    def test_connect_src_is_limited_to_our_api(self):
        self.assertIn("connect-src https://api.relayshield.net", _worker())


class TestWrangler(unittest.TestCase):
    def test_config_points_at_this_worker(self):
        cfg = WRANGLER.read_text(encoding="utf-8")
        self.assertIn('main = "cloudflare_worker_miniapp.js"', cfg)
        self.assertIn("app.relayshield.net", cfg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
