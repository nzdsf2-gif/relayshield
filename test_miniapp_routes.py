"""The route table, its two deployed mirrors, and the before/after mechanism.

THREE LISTS THAT MUST AGREE WITH NOTHING CHECKING THAT THEY DO is the shape
that produced run 134's red probe and four months of FD-8, so this file is the
check. miniapp_routes.json is the source of truth; ALLOWED_SOURCES in
cloudflare_worker_miniapp.js gates the ?startapp= value at the edge, and
_SOURCE_ALIASES in relayshield_developer_signup.py maps the key to a banner.

A key missing from either mirror does not error. The Worker silently downgrades
it to the generic "tg-miniapp" and the landing page logs "unmatched:". Both are
attribution that LOOKS like it worked, which is worse than none: a zero from a
measurement tool gets acted on.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROUTES = json.loads((ROOT / "miniapp_routes.json").read_text())
WORKER = (ROOT / "cloudflare_worker_miniapp.js").read_text()
SIGNUP = (ROOT / "relayshield_developer_signup.py").read_text()
FUNNEL = (ROOT / "tools" / "miniapp_funnel.py").read_text()

KEYS = [r["key"] for r in ROUTES["routes"] if r["key"]]
LOOP_KEYS = [k["key"] for k in ROUTES["loop_keys"]]


def worker_allowed():
    block = WORKER[WORKER.index("const ALLOWED_SOURCES"):]
    return set(re.findall(r'"([a-z0-9-]+)"', block[:block.index("]);")]))


def signup_aliases():
    return set(re.findall(r'"(tg-miniapp[a-z0-9-]*)":\s*"tg-miniapp"', SIGNUP))


class TestTheThreeListsAgree(unittest.TestCase):

    def test_every_route_key_is_allowed_by_the_worker(self):
        """Missing here and the app opens, the check answers, and the route is
        gone -- sourceFor() falls back to the generic key with no error."""
        missing = set(KEYS) - worker_allowed()
        self.assertFalse(missing, f"not in ALLOWED_SOURCES: {sorted(missing)}")

    def test_every_route_key_resolves_on_the_landing_page(self):
        """Missing here and the arrival logs `unmatched:` and renders no banner
        -- FD-8 exactly, which ran for four months."""
        missing = set(KEYS) - signup_aliases()
        self.assertFalse(missing, f"not in _SOURCE_ALIASES: {sorted(missing)}")

    def test_the_loop_keys_are_registered_too(self):
        for k in LOOP_KEYS:
            if k == "tg-miniapp":
                self.assertIn('"tg-miniapp": (', SIGNUP)
                continue
            self.assertIn(k, worker_allowed(), f"{k} not gated by the Worker")
            self.assertIn(k, signup_aliases(), f"{k} has no alias")

    def test_the_worker_still_honours_the_retired_shared_key(self):
        """Links published before 2026-09-11 carry tg-miniapp-channel. Dropping
        it would break attribution on every one of them at once."""
        self.assertIn("tg-miniapp-channel", worker_allowed())
        self.assertIn("tg-miniapp-channel", signup_aliases())

    def test_keys_are_valid_telegram_start_params(self):
        """Telegram allows A-Za-z0-9_- in a deep-link payload, up to 64 bytes.
        A key with a dot in it is a link that silently carries nothing."""
        for k in KEYS + LOOP_KEYS:
            self.assertRegex(k, r"^[A-Za-z0-9_-]{1,64}$", k)

    def test_the_worker_regex_accepts_every_key(self):
        """sourceFor() is gated by ALLOWED_SOURCES, but the ?s= fallback path is
        gated by a character-class regex as well, and a key the regex rejects
        would be dropped before the set is ever consulted."""
        m = re.search(r"\^\[a-z0-9-\]\{1,(\d+)\}\$", WORKER)
        self.assertIsNotNone(m, "the ?s= validation regex moved or changed shape")
        limit = int(m.group(1))
        for k in KEYS + LOOP_KEYS:
            self.assertRegex(k, r"^[a-z0-9-]+$", f"{k} fails the ?s= regex")
            self.assertLessEqual(len(k), limit, f"{k} is longer than the ?s= cap")


class TestTheTableItself(unittest.TestCase):

    def test_ranks_are_unique_and_contiguous(self):
        ranks = sorted(r["rank"] for r in ROUTES["routes"])
        self.assertEqual(ranks, list(range(1, len(ranks) + 1)))

    def test_keys_are_unique(self):
        self.assertEqual(len(KEYS), len(set(KEYS)))

    def test_one_key_per_destination_not_per_category(self):
        """The regression this whole change exists to prevent. Five announcement
        channels behind one key makes the 3.9M one and the 9,671 one
        indistinguishable, and which of those works is the entire question."""
        channels = [r for r in ROUTES["routes"]
                    if r["destination"].startswith("@")]
        self.assertGreaterEqual(len(channels), 5)
        self.assertEqual(len({r["key"] for r in channels}), len(channels))

    def test_the_menu_button_has_no_key_on_purpose(self):
        menu = next(r for r in ROUTES["routes"] if r["id"] == "menu")
        self.assertIsNone(menu["key"])
        self.assertEqual(menu["status"], "not_shipped_by_decision")
        self.assertIn("REPLACES", menu["why_first"])

    def test_every_route_says_where_its_audience_number_came_from(self):
        """A number with no source is not a number. MEASUREMENT DOCTRINE applies
        to the numbers we use to RANK work, not only to the ones we publish."""
        for r in ROUTES["routes"]:
            self.assertTrue(r.get("audience_note"), r["id"])
            if r.get("audience") is None:
                self.assertIn("unmeasured", r["audience_note"].lower(), r["id"])


class TestTheFunnelReadsTheTable(unittest.TestCase):

    def test_it_refuses_to_guess_when_the_table_is_missing(self):
        """A built-in fallback list would report a live channel as dead the day
        somebody renames the file. source_arrivals.py had exactly this defect in
        a different costume and returned 117 plausible keys with every real one
        missing."""
        self.assertIn("cannot guess them", FUNNEL)
        self.assertIn("false absence", FUNNEL)

    def test_it_counts_wallet_risk_not_only_ton_address(self):
        """check() routes EVERY address, TON included, to /v1/wallet-risk. A
        source logged only on /v1/ton-address measures an endpoint the Mini App
        never calls."""
        api = (ROOT / "relayshield_api.py").read_text()
        self.assertIn('logger.info("wallet-risk address=%s chain=%s risk=%s '
                      'flags=%d sanctioned=%s source=%s"', api)
        self.assertIn('logger.info("wallet-risk address=%s chain=bitcoin '
                      'risk=%s flags=%d source=%s"', api)

    def test_list_routes_runs_with_no_aws_and_names_every_route(self):
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "miniapp_funnel.py"),
                              "--list-routes"],
                             capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stderr)
        for r in ROUTES["routes"]:
            self.assertIn(r["destination"], out.stdout)
        for k in KEYS:
            self.assertIn(f"startapp={k}", out.stdout)

    def test_the_link_it_prints_is_the_registered_mini_app(self):
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "miniapp_funnel.py"),
                              "--list-routes"], capture_output=True, text=True, cwd=ROOT)
        self.assertIn("t.me/relayshield_bot/idcheck?startapp=", out.stdout)
        self.assertNotIn("/relayshield_bot/app?", out.stdout)


class TestSnapshotAndCompare(unittest.TestCase):
    """The before/after mechanism, exercised with no AWS.

    It exists because 'run it before and after' is a discipline and this makes
    it a mechanism. A baseline held in a terminal that has scrolled away is not
    a baseline, and a comparison done from memory is not a comparison."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import importlib
        self.mod = importlib.import_module("miniapp_funnel")
        self.tmp = tempfile.TemporaryDirectory()
        self.mod.SNAPSHOT_DIR = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _snap(self, routes):
        return {"generated_at": "2026-09-11T00:00:00+00:00", "days_requested": 30,
                "stages": {"CHECKED": 10}, "routes": routes, "unknown_route_keys": {}}

    def test_a_snapshot_round_trips(self):
        self.mod.save_snapshot(self._snap({"tg-miniapp-blog": 5}), "before-blog")
        p = Path(self.tmp.name) / "before-blog.json"
        self.assertTrue(p.exists())
        self.assertEqual(json.loads(p.read_text())["routes"]["tg-miniapp-blog"], 5)

    def test_it_REFUSES_to_overwrite_a_baseline(self):
        """THE IMPORTANT ONE. Overwriting the baseline after the submission has
        run turns the before-and-after into a comparison of a number with
        itself, which reads as 'the channel did nothing'."""
        self.mod.save_snapshot(self._snap({"tg-miniapp-blog": 5}), "before-blog")
        self.mod.save_snapshot(self._snap({"tg-miniapp-blog": 900}), "before-blog")
        p = Path(self.tmp.name) / "before-blog.json"
        self.assertEqual(json.loads(p.read_text())["routes"]["tg-miniapp-blog"], 5,
                         "the baseline was overwritten")

    def test_compare_prints_the_delta(self):
        import io, contextlib
        self.mod.save_snapshot(self._snap({"tg-miniapp-blog": 5}), "before-blog")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.mod.print_comparison(self._snap({"tg-miniapp-blog": 41}), "before-blog")
        out = buf.getvalue()
        self.assertIn("+36", out)
        self.assertIn("tg-miniapp-blog", out)

    def test_a_missing_baseline_is_not_a_zero(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.mod.print_comparison(self._snap({}), "never-taken")
        self.assertIn("NOT a result of zero", buf.getvalue())

    def test_compare_warns_about_the_sliding_window(self):
        """Both runs count a rolling window back from now, so a delta taken five
        weeks after a 30-day baseline measures the window moving, not the
        channel. Silently reporting that as a channel result would be the
        confident-wrong-number failure this repo has paid for twice."""
        import io, contextlib
        self.mod.save_snapshot(self._snap({"tg-miniapp-blog": 5}), "before-blog")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.mod.print_comparison(self._snap({"tg-miniapp-blog": 5}), "before-blog")
        self.assertIn("WINDOW CAVEAT", buf.getvalue())

    def test_a_new_unknown_key_is_surfaced(self):
        import io, contextlib
        self.mod.save_snapshot(self._snap({}), "before-x")
        cur = self._snap({})
        cur["unknown_route_keys"] = {"tg-miniapp-typo": 12}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.mod.print_comparison(cur, "before-x")
        self.assertIn("tg-miniapp-typo", buf.getvalue())


class TestTonOnlyCheckTab(unittest.TestCase):
    """The Check tab screens links and TON, and nothing else.

    A Telegram Mini App lives inside Telegram's rules and TON is the chain
    Telegram ships. This is the founder's instruction; the precise clause is
    UNVERIFIED from the container because core.telegram.org is egress-blocked,
    and the instruction is the conservative direction either way."""

    def setUp(self):
        self.w = WORKER if False else open(ROOT / "cloudflare_worker_miniapp.js").read()

    def test_the_placeholder_does_not_advertise_other_chains(self):
        """The first thing a user reads. Inviting a Solana address and then
        refusing it is worse than never offering."""
        m = re.search(r'id="in" placeholder="([^"]+)"', self.w)
        self.assertIsNotNone(m)
        ph = m.group(1).lower()
        for chain in ("solana", "bitcoin", "0x"):
            self.assertNotIn(chain, ph, f"the placeholder still offers {chain}")
        self.assertIn("ton", ph)

    def test_other_chains_are_named_and_refused(self):
        self.assertIn("OTHER_CHAINS", self.w)
        for name in ("Ethereum or EVM", "Bitcoin", "Solana", "Ronin"):
            self.assertIn(name, self.w, f"{name} is not named in the refusal")

    def test_a_refused_address_is_not_redirected_anywhere(self):
        """Pointing an Ethereum address at another of our surfaces from in here
        is the same rule broken one link further out, which is exactly the
        Stars-to-Stripe trap."""
        i = self.w.index("function offChainReason")
        j = self.w.index("async function run()")
        body = self.w[i:j]
        for rail in ("http", "t.me", "developers", "relayshield.net"):
            self.assertNotIn(rail, body,
                             f"the refusal path links out to {rail}")

    def test_a_refused_address_cannot_be_watched_or_shared(self):
        """Watching an EVM address would put a row in the table that the TON
        monitor will never re-check -- a promise nothing keeps, which is the
        defect the monitor was built to end."""
        i = self.w.index("const off = offChainReason(value);")
        block = self.w[i:i + 900]
        self.assertIn("last = null", block)
        self.assertIn('["watch", "share", "cta"]', block)

    def test_the_gate_is_NOT_in_the_shared_widget(self):
        """widget/relayshield-widget.js is copied into other people's bots and
        called from servers that are not Telegram. Restricting it there would
        break every other caller to satisfy one host's terms."""
        wid = (ROOT / "widget" / "relayshield-widget.js").read_text()
        self.assertNotIn("OTHER_CHAINS", wid)
        self.assertIn("EVM", wid)
        self.assertIn("BTC", wid)
        self.assertIn("SOL", wid)

    def test_ton_wins_over_solana_on_the_overlapping_range(self):
        """A 48-character TON friendly address also matches the Solana base58
        range. The TON test must return FIRST or every TON address is refused
        as Solana -- which would break the only chain this app checks."""
        i = self.w.index("function offChainReason")
        body = self.w[i:i + 900]
        self.assertLess(body.index("TON_ADDR.test(t)"), body.index("OTHER_CHAINS"),
                        "the Solana pattern is tested before TON")


def page_script(src: str) -> str:
    """The PAGE template literal's contents: the code the BROWSER runs.

    Everything outside it runs in the Cloudflare Worker, in a different process
    on a different machine, and the two scopes share nothing but the __TOKEN__
    substitutions done at request time."""
    start = src.index("const PAGE = `")
    i = start + len("const PAGE = `")
    while True:
        j = src.index("`", i)
        if src[j - 1] != "\\":
            break
        i = j + 1
    return src[start:j]


class TestPageScopeIsSelfContained(unittest.TestCase):
    """THE BUG node --check CANNOT SEE, and it shipped once in this session.

    INLINE_TEXT was first declared in the Worker's own scope, forty lines above
    the template literal, and used inside the page. Both syntax checks passed --
    the file parses, the string is a valid string -- and the browser would have
    thrown ReferenceError on load, leaving a blank tip and no error anywhere we
    look. Same family as the stray backtick: syntactically valid, runtime dead.

    So: every SCREAMING_CASE constant the page reads must be declared in the
    page, or be one of the values substituted into it at request time."""

    SUBSTITUTED = {"__SOURCE__", "__API__", "__BOT__", "__WIDGET__"}

    @staticmethod
    def _strip_comments(js: str) -> str:
        """Comments out, for the third time in this suite's history.

        The first run of this very test flagged BOT, because a comment two lines
        above says "sat in the Worker's own scope alongside BOT". Prose
        describing a defect is not the defect -- the same correction
        test_telegram_markdown_escapes.py and code_only() already carry, and it
        keeps arriving in new costumes because the natural way to write a guard
        is to search the file."""
        js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
        return re.sub(r"(?m)^\s*//.*$", " ", js)

    def test_every_constant_the_page_uses_is_declared_in_the_page(self):
        src = (ROOT / "cloudflare_worker_miniapp.js").read_text()
        page = self._strip_comments(page_script(src))
        declared = set(re.findall(r"\bconst\s+([A-Z][A-Z0-9_]{2,})\s*=", page))
        used = set(re.findall(r"\b([A-Z][A-Z0-9_]{2,})\b", page))
        # Browser and Telegram globals, plus our own placeholder tokens.
        known = {"JSON", "URL", "DOM", "SVG", "HTML", "API", "GET", "POST",
                 "OK", "ID", "UTC", "CSS", "TON", "EQ", "UQ", "USD"}
        missing = {u for u in used - declared - known - self.SUBSTITUTED
                   if not u.startswith("__")}
        # Anything left must appear in the Worker scope, which is the defect.
        worker_only = {m for m in missing
                       if re.search(r"\bconst\s+" + m + r"\s*=", src.replace(page, ""))}
        self.assertFalse(
            worker_only,
            f"declared in the Worker scope and read by the page: {sorted(worker_only)}. "
            "The browser will throw ReferenceError; no syntax check sees this.")


class TestTheGateActuallyRuns(unittest.TestCase):
    """EXECUTES the gate against real address shapes, rather than reading its
    regexes. test_miniapp.py already learned that a file which parses as text
    can still be code that does the wrong thing, and a regex is the single
    easiest thing in this file to get subtly wrong -- TON's 48-character
    friendly form sits inside Solana's base58 range, so an ordering mistake
    refuses every address this app exists to check and nothing errors."""

    CASES = [
        ("EQCD39VS5jcptHL8vMjEXrzGaRcCVYto7HUn4bpAOg8xqB2N", "", "TON friendly EQ"),
        ("UQCD39VS5jcptHL8vMjEXrzGaRcCVYto7HUn4bpAOg8xqB2N", "", "TON friendly UQ"),
        ("0:" + "a" * 64, "", "TON raw"),
        ("-1:" + "b" * 64, "", "TON masterchain"),
        ("0x" + "a" * 40, "Ethereum", "EVM"),
        ("ronin:0x" + "b" * 40, "Ronin", "Ronin"),
        ("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "Bitcoin", "BTC bech32"),
        ("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", "Bitcoin", "BTC legacy"),
        ("7EYnhQoR9YM3N7UoaKRoA44Uy8JeaZV3qyouov87awMs", "Solana", "SOL"),
        ("https://evil.example/x", "", "url"),
        ("evil.example", "", "bare domain"),
        ("", "", "empty"),
    ]

    def test_every_shape_is_classified_correctly(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        w = (ROOT / "cloudflare_worker_miniapp.js").read_text()
        gate = w[w.index("const TON_ADDR ="):w.index("async function run()")]
        harness = gate + "\nconst cases = " + json.dumps(self.CASES) + ";\n" + """
const out = [];
for (const [input, expect, label] of cases) {
  const got = offChainReason(input);
  const ok = expect ? got.includes(expect) : got === "";
  if (!ok) out.push(label + ": " + JSON.stringify(got));
}
console.log(JSON.stringify(out));
"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(harness)
            path = f.name
        try:
            r = subprocess.run(["node", path], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            failures = json.loads(r.stdout.strip().splitlines()[-1])
        finally:
            os.unlink(path)
        self.assertEqual(failures, [], f"misclassified: {failures}")


class TestTheExample(unittest.TestCase):
    """An empty box is the worst first screen for a product whose most common
    honest answer is 'nothing known'."""

    def setUp(self):
        self.w = open(ROOT / "cloudflare_worker_miniapp.js").read()

    def test_the_example_runs_a_real_check(self):
        """Not a canned card. A rendered verdict nobody can check is a claim
        about our own product, and it goes stale silently."""
        i = self.w.index('$("try-bad").addEventListener')
        block = self.w[i:i + 300]
        self.assertIn("run()", block)
        self.assertIn('$("in").value = EXAMPLE_URL', block)

    def test_the_example_is_flagged_by_construction_not_by_our_say_so(self):
        """Google's own Safe Browsing test host, which /v1/link-check consults.
        A domain we merely assert is in our corpus would be unverifiable, and
        shipping a REAL criminal link inside our own app and inviting a tap is
        worse than either."""
        self.assertIn("testsafebrowsing.appspot.com", self.w)
        i = self.w.index("const EXAMPLE_URL")
        self.assertIn("UNVERIFIED", self.w[max(0, i - 1800):i],
                      "the example is not run from this container and must say so")

    def test_the_example_is_a_url_not_an_invented_ton_address(self):
        """No TON address is shipped as an example. Naming one is a claim about
        a live address that cannot be verified from here, and an address that
        stops being flagged turns the example into a false negative on the
        app's own front screen."""
        block = self.w[self.w.index("const EXAMPLE_URL"):][:400]
        self.assertNotRegex(block, r"EQ[A-Za-z0-9_-]{46}")
        self.assertNotRegex(block, r"\b-?\d+:[0-9a-fA-F]{64}\b")


class TestShareCardTeachesTheMechanic(unittest.TestCase):
    """The share card is the compounding loop: a forwarded verdict lands in
    front of somebody who is, right then, in the chat where the scam was posted.
    Naming the bot and leaving them to work it out is three steps away from the
    moment they are in."""

    def setUp(self):
        self.w = open(ROOT / "cloudflare_worker_miniapp.js").read()

    def test_the_card_names_the_inline_mechanic(self):
        i = self.w.index('g.fillText("Check one yourself')
        self.assertIn("@relayshield_bot in any chat", self.w[i:i + 200])

    def test_the_footer_lines_fit_the_canvas(self):
        """Canvas text does not wrap. A line longer than the card runs off the
        edge, and the only place that shows up is a screenshot somebody has
        already forwarded."""
        m = re.search(r'<canvas id="card"[^>]*width="(\d+)"[^>]*height="(\d+)"', self.w)
        self.assertIsNotNone(m, "the canvas dimensions moved")
        width, height = int(m.group(1)), int(m.group(2))
        footer = re.findall(r'g\.fillText\("([^"]+)", 48, (3\d\d)\)', self.w)
        self.assertGreaterEqual(len(footer), 2, "the second footer line is gone")
        for text, y in footer:
            # 20px system sans, conservative 10.2px per character.
            self.assertLess(48 + len(text) * 10.2, width, f"overflows: {text}")
            self.assertLess(int(y), height - 20, f"below the card: {text}")

    def test_it_does_not_collide_with_the_reasons_block(self):
        ys = [int(y) for _, y in re.findall(r'g\.fillText\("([^"]*)", 48, (\d+)\)', self.w)]
        self.assertTrue(all(y >= 340 or y <= 300 for y in ys),
                        "a footer line sits inside the reasons band")


class TestWatchTabExplainsItself(unittest.TestCase):
    def setUp(self):
        self.w = open(ROOT / "cloudflare_worker_miniapp.js").read()

    def test_it_names_every_kind_that_holds_money(self):
        for kind in ("Jettons", "Wallets", "Vaults", "DeFi", "NFT"):
            self.assertIn(kind, self.w, f"the watch tab does not mention {kind}")

    def test_the_kinds_match_what_the_monitor_actually_detects(self):
        """Naming a kind the monitor cannot act on is a promise nothing keeps --
        the exact defect the watchlist shipped with for two days."""
        mon = (ROOT / "relayshield_watchlist_monitor.py").read_text()
        for signal in ("LIQUIDITY_GONE", "BALANCE_DRAINED", "CONTRACT_DEPLOYED",
                       "SCAM_FLAGGED"):
            self.assertIn(signal, mon)

    def test_it_says_ton_and_does_not_offer_other_chains(self):
        i = self.w.index('class="watch-intro"')
        block = self.w[i:self.w.index('id="watchlist"')]
        self.assertIn("TON", block)
        for chain in ("Ethereum", "Solana", "Bitcoin"):
            self.assertNotIn(chain, block)


if __name__ == "__main__":
    unittest.main(verbosity=1)
