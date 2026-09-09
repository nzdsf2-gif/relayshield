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


class TestPrivacy(unittest.TestCase):
    """The Mini App is the first thing that stores a record about a PERSON."""

    def test_the_client_sends_signed_initdata_not_a_raw_user_id(self):
        """A per-user store that believes a client-supplied id has no access
        control. The first draft of the handler had exactly that hole."""
        worker = _worker()
        self.assertIn("init_data: initData", worker)
        self.assertNotIn("telegram_user_id: uid", worker)

    def test_scan_history_never_leaves_the_device(self):
        """A server-side record of what somebody checked is a profile of their
        financial anxieties. The watchlist is the ONE thing that legitimately
        leaves the device, and it is encrypted."""
        worker = _worker()
        self.assertIn("localStorage.getItem(HKEY", worker)
        self.assertIn("localStorage.setItem(HKEY", worker)
        # The only POSTs may be the three watchlist routes.
        posts = set(re.findall(r'post\("(/v1/[^"]+)"', worker))
        self.assertEqual(posts, {"/v1/watchlist/add", "/v1/watchlist/list",
                                 "/v1/watchlist/remove"}, f"unexpected POST targets: {posts}")

    def test_history_reads_are_wrapped_against_a_throwing_accessor(self):
        """localStorage THROWS in a private window and in some embedded webviews,
        which would take the whole app down rather than losing a nicety."""
        worker = _worker()
        block = worker[worker.index("function readHistory"):worker.index("function renderHistory")]
        self.assertIn("catch", block)


class TestWatchlistHandler(unittest.TestCase):
    """Read from the handler source with ast: no boto3 in this container."""

    def setUp(self):
        self.src = (ROOT / "relayshield_watchlist.py").read_text(encoding="utf-8")

    def test_the_user_id_comes_only_from_a_verified_signature(self):
        for fn in ("def add_watch", "def list_watches", "def remove_watch"):
            block = self.src[self.src.index(fn):]
            block = block[:block.index("\n\n\n")] if "\n\n\n" in block else block
            self.assertIn("verified_user_id(", block, f"{fn} does not verify the caller")
            self.assertNotIn('params.get("telegram_user_id")', block)

    def test_the_signature_check_is_constant_time(self):
        block = self.src[self.src.index("def verified_user_id"):self.src.index("def user_key")]
        self.assertIn("hmac.compare_digest", block)
        self.assertIn("auth_date", block)

    def test_the_partition_key_is_an_HMAC_not_a_bare_hash(self):
        """Telegram ids are sequential integers in a space small enough to
        enumerate, so an unpeppered digest is a reversible encoding wearing a
        hash's clothes."""
        block = self.src[self.src.index("def user_key"):self.src.index("def encrypt_field")]
        self.assertIn("hmac.new", block)
        self.assertIn("_get_secret(PEPPER_SECRET)", block)
        self.assertNotRegex(block, r"hashlib\.sha256\(\s*str\(")

    def test_the_target_fingerprint_is_peppered_too(self):
        """An unpeppered digest of a domain is trivially reversed against a
        wordlist of every domain that exists."""
        block = self.src[self.src.index("def _fingerprint"):self.src.index("def add_watch")]
        self.assertIn("hmac.new", block)

    def test_values_are_encrypted_and_reversible_on_purpose(self):
        """The chat_id and the target MUST be recoverable: an alert cannot be
        sent without one and a re-check cannot run without the other."""
        self.assertIn('"target_enc":   encrypt_field(', self.src)
        self.assertIn('"chat_id_enc":  encrypt_field(', self.src)
        self.assertIn("def decrypt_field", self.src)

    def test_nothing_is_stored_in_the_clear(self):
        """The put_item must carry no raw target and no raw chat id."""
        put = self.src[self.src.index("table.put_item(Item={"):]
        put = put[:put.index("})")]
        for forbidden in ('"target":', '"chat_id":', '"telegram_user_id":'):
            self.assertNotIn(forbidden, put, f"{forbidden} would be stored in the clear")

    def test_it_reuses_the_existing_kms_alias(self):
        """A second key means a second rotation story and a second set of grants."""
        self.assertIn('"alias/relayshield-data-key"', self.src)

    def test_the_secret_read_has_a_TTL(self):
        """A module-level cache with no expiry silently under-billed for hours
        after a rotation. Every secret read in this repo carries a TTL now."""
        self.assertIn("_SECRET_TTL", self.src)

    def test_the_target_is_never_logged(self):
        for m in re.findall(r"logger\.\w+\((.*?)\)", self.src, re.S):
            self.assertNotIn("normalised", m)
            self.assertNotIn("target_enc", m)

    def test_the_import_probe_returns_before_touching_dynamodb(self):
        """The deployer invokes what it deploys. A handler that does real work
        on invoke needs this, and two already did."""
        self.assertIn('event.get("source") == "ci.import-probe"', self.src)


class TestGame(unittest.TestCase):
    def test_the_game_teaches_the_products_own_skill(self):
        """Points, streaks and leaderboards were rejected: they move DAU by
        attracting people who want points. This one makes the user better at
        spotting a homoglyph, which is what the typosquat engine does."""
        worker = _worker()
        self.assertIn("Spot the fake", worker)
        self.assertIn("function fakeOf", worker)
        # Scoped to the RUNNABLE page, because this file's own comments name the
        # mechanics it rejects and the first version of this test matched them.
        page = worker[worker.index("const PAGE = `"):worker.index("export default {")]
        page = re.sub(r"/\*.*?\*/", "", page, flags=re.S)
        self.assertNotIn("leaderboard", page.lower())
        self.assertNotIn("streak", page.lower())

    def test_no_daily_quota_gate(self):
        """A free-scan quota converts genuine need into a paywall at the instant
        somebody is about to be defrauded."""
        w = _worker().lower()
        for phrase in ("come back tomorrow", "daily limit", "out of scans"):
            self.assertNotIn(phrase, w)


class TestWrangler(unittest.TestCase):
    def test_config_points_at_this_worker(self):
        cfg = WRANGLER.read_text(encoding="utf-8")
        self.assertIn('main = "cloudflare_worker_miniapp.js"', cfg)
        self.assertIn("app.relayshield.net", cfg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
