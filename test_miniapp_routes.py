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
import re
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
