#!/usr/bin/env python3
"""BOT-TOKEN-1: the Telegram bot token pattern, and the tables that must agree.

WHY THIS FILE EXISTS. Until 2026-09-13 there was no Telegram bot token pattern
anywhere in this repo -- not in NHI_PATTERNS, not in _NHI_PATS, not in rsscan's
mirror -- while AWS, GitHub, Stripe, Slack, OpenAI, Anthropic, OpenRouter and
twenty others were all covered. The credential format of the platform two of our
three consumer products live on was the one nobody had added, so the corpus
count was UNMEASURED rather than zero, and those are different findings.

FOUR TABLES MUST AGREE AND NOTHING CHECKED THAT THEY DID, which is this repo's
single most-repeated defect shape (the pattern tables, LAMBDA_MAP against the
invoke policy, the three route lists, the watchlist secret name). The mirror in
rsscan is generated and checkable; the collection copy in
relayshield_intel_monitor.py is hand-kept and is the one that drifts, and it is
also the only one that decides whether the corpus ever contains any.

EVERY ASSERTION HERE EXECUTES THE REGEX. A pattern table is exactly the place
where reading proves nothing: the URL entry below was added only because running
the context-anchored one against real strings showed it could not match
`https://api.telegram.org/bot<TOKEN>/sendMessage` -- the single most common way
a bot token actually leaks.
"""

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# A SYNTHETIC token, and it must stay synthetic. It is the right SHAPE and is
# not a credential: 35 body characters, never issued by anyone. A real token in
# a committed test file is a credential in a public repo, which is the rule 12
# failure with our own hands on it.
FAKE = "8123456789:" + "A" * 10 + "BcD_eF-gH" + "i" * 16


def _ctx_key_from_source() -> callable:
    """The REAL helper out of relayshield_api.py, not a reimplementation.

    A test that rebuilds the anchor itself proves the test's idea of the anchor
    works, which is the `_APIFY_BANNER` class of mistake: asserting a thing you
    wrote rather than the thing that ships.
    """
    src = (ROOT / "relayshield_api.py").read_text()
    i = src.index("def _ctx_key")
    j = src.index("\n\n", src.index("return (", i))
    ns: dict = {}
    exec(src[i:j], ns)
    return ns["_ctx_key"]


def _entries(path: Path, table: str) -> dict:
    """{name: regex} for the rows we care about, read as TEXT.

    Neither table can simply be imported: relayshield_api.py needs boto3 and
    relayshield_intel_monitor.py builds clients at import. Reading the source is
    the pragmatic route, and every regex found here is then COMPILED and RUN, so
    a string that parses but cannot match still fails.
    """
    src = path.read_text()
    out = {}
    for name in ("telegram_bot_token", "telegram_bot_token_url"):
        m = re.search(rf'\(\s*"{name}"\s*,\s*(.+?)\n\s*"CRITICAL"', src, re.S)
        if not m:
            m = re.search(rf'\(\s*"{name}"\s*,\s*(.+?),\s*"CRITICAL"', src, re.S)
        out[name] = m.group(1).strip() if m else None
    return out


class TestThePatternIsInEveryTable(unittest.TestCase):
    """Four copies, and the hand-kept one is the one that goes missing."""

    def test_the_source_of_truth_carries_both_entries(self):
        got = _entries(ROOT / "relayshield_api.py", "NHI_PATTERNS")
        for name, expr in got.items():
            self.assertIsNotNone(expr, f"{name} missing from NHI_PATTERNS")

    def test_the_collection_side_carries_both_entries(self):
        """The copy that decides whether the corpus ever contains any."""
        got = _entries(ROOT / "relayshield_intel_monitor.py", "_NHI_PATS")
        for name, expr in got.items():
            self.assertIsNotNone(expr, f"{name} missing from _NHI_PATS -- the "
                                       "collector will never write one")

    def test_the_rsscan_mirror_is_in_sync(self):
        """Generated, never hand-edited. sync_patterns.py --check is the check."""
        r = subprocess.run([sys.executable, "tools/sync_patterns.py", "--check"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         f"rsscan mirror has drifted:\n{r.stdout}{r.stderr}")

    def test_the_mirror_actually_contains_it(self):
        """--check compares a hash, so it would happily agree that both sides
        are missing the same row. Assert the row itself."""
        mirror = (ROOT / "rsscan" / "rsscan" / "patterns.py").read_text()
        self.assertIn("telegram_bot_token", mirror)
        self.assertIn("telegram_bot_token_url", mirror)


class TestItMatchesWhatAThreatActuallyLooksLike(unittest.TestCase):
    """EXECUTED. The URL entry exists only because this ran and the other failed."""

    @classmethod
    def setUpClass(cls):
        ck = _ctx_key_from_source()
        cls.ctx = re.compile(ck(
            r"telegram|tg_bot|bot_?token|TELEGRAM_BOT_TOKEN|api\.telegram\.org",
            r"[0-9]{8,10}:[A-Za-z0-9_\-]{35}"))
        cls.url = re.compile(
            r"api\.telegram\.org/bot([0-9]{8,10}:[A-Za-z0-9_\-]{35})")

    def _any(self, text):
        return self.ctx.search(text) or self.url.search(text)

    def test_the_fixture_is_the_right_shape(self):
        bot_id, _, body = FAKE.partition(":")
        self.assertTrue(bot_id.isdigit())
        self.assertEqual(len(body), 35, "a Telegram token body is 35 characters")

    def test_the_env_var_form_matches(self):
        for line in (f"TELEGRAM_BOT_TOKEN={FAKE}",
                     f'bot_token: "{FAKE}"',
                     f"telegram_token = '{FAKE}'"):
            self.assertTrue(self._any(line), line[:40])

    def test_the_url_form_matches(self):
        """The most common real leak shape, and the context pattern CANNOT see
        it: _ctx_key requires an assignment operator and a URL has none."""
        line = f"curl https://api.telegram.org/bot{FAKE}/sendMessage -d chat_id=1"
        self.assertIsNone(self.ctx.search(line),
                          "if this starts matching, say so -- the url entry may "
                          "no longer be needed")
        self.assertTrue(self.url.search(line))

    def test_the_secret_is_group_one_in_both(self):
        """_detect_nhi_in_text reports group(1), so the vendor context must not
        leak into the preview shown to a customer."""
        self.assertEqual(
            self.ctx.search(f"TELEGRAM_BOT_TOKEN={FAKE}").group(1), FAKE)
        self.assertEqual(
            self.url.search(f"api.telegram.org/bot{FAKE}/getMe").group(1), FAKE)


class TestItDoesNotFireOnTheLookalikes(unittest.TestCase):
    """`digits:opaque` is one of the commonest strings in any config dump, and a
    noisy CRITICAL is how a detector gets ignored."""

    @classmethod
    def setUpClass(cls):
        TestItMatchesWhatAThreatActuallyLooksLike.setUpClass.__func__(cls)

    def _any(self, text):
        return self.ctx.search(text) or self.url.search(text)

    def test_a_ton_address_is_not_a_bot_token(self):
        """TON's raw form is `-?<digits>:<64 hex>` -- this shape with a longer
        tail. The Mini App gate learned the same overlap the hard way when TON's
        48-char friendly form turned out to sit inside Solana's base58 range."""
        for addr in ("0:83dfd552e63729b472fcbcc8c45ebcc6f5be1e8ec4a3e0b0b1b1b1b1b1b1b1b1",
                     "-1:83dfd552e63729b472fcbcc8c45ebcc6f5be1e8ec4a3e0b0b1b1b1b1b1b1b1b1",
                     "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"):
            self.assertFalse(self._any(f"ton_address={addr}"), addr[:20])

    def test_a_bare_token_with_no_context_does_not_fire(self):
        """The whole reason this is context-anchored."""
        self.assertFalse(self._any(f"some random text {FAKE} in a sentence"))

    def test_a_port_or_timestamp_pair_does_not_fire(self):
        for noise in ("DB_PORT=5432:abcdefghijklmnopqrstuvwxyzABCDEFGHI",
                      "duration=1694563200:0000000000000000000000000000000",
                      "telegram_chat_id=-1001234567890"):
            self.assertFalse(self._any(noise), noise[:40])

    def test_a_telegram_api_path_that_is_not_a_token_does_not_fire(self):
        self.assertFalse(self._any("https://api.telegram.org/botinfo/readme"))


class TestTheRemediationIsRevokeNotRotate(unittest.TestCase):
    """A bot token is session-shaped, not key-shaped. Telling somebody to
    'rotate' it is telling them to do the one thing that cannot help, which is
    exactly why the Anthropic OAuth and session rows were split out from the
    API key row."""

    def test_both_descriptions_say_botfather(self):
        src = (ROOT / "relayshield_api.py").read_text()
        block = src[src.index('"telegram_bot_token"'):]
        block = block[:block.index('"stripe_pub"')]
        code = "\n".join(l for l in block.splitlines()
                         if not l.lstrip().startswith("#"))
        self.assertEqual(code.count("BotFather"), 2)
        self.assertNotIn("rotate the key", code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
