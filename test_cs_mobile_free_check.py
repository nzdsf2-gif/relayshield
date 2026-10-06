"""Crypto Shield Mobile v1.7.0: the free email check, the funnel counters, and the
first-run wiring.

Reads the TypeScript sources, because the app cannot run in a container, and
EXECUTES the one pure module (exposureCopy.ts) under node when a TypeScript
compiler is reachable. Server behaviour is in test_free_exposure_check.py.

THE RULES PINNED HERE
  1. The counters carry no identifier, and the funnel tool's regexes match the
     lines the handlers ACTUALLY write (a counter nobody reads, or reads with a
     wrong filter, is a confident zero).
  2. The free check is keyless and is routed to ONLY when there is no key: a
     subscriber keeps the full paid Email Check.
  3. The words never say an email is safe, and a check that did not complete is
     never worded as a clean one.
  4. The Stripe channel tag equals CHANNEL, so the funnel's platform split and
     the weekly report's agree.
  5. Onboarding reaches value without a key: connect, scan, one free check.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
APP = ROOT / "crypto-shield-app"


def read(rel: str) -> str:
    return (APP / rel).read_text(encoding="utf-8")


def strip_ts_comments(src: str) -> str:
    """Remove // and /* */ comments while respecting string and template literals.
    A regex version ate 10 KB of ScanScreen.tsx because a '/*' or '//' sat inside a
    string, and a guard that reads half the file passes on the other half."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1]); i = j + 1
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c); i += 1
    return "".join(out)


class TheCountersAreAnonymousAndRead(unittest.TestCase):
    def test_analytics_sends_no_identifier(self):
        code = strip_ts_comments(read("src/utils/analytics.ts"))
        for banned in ("installId", "getInstallId", "SecureStore", "email", "apiKey",
                       "address", "pushToken", "X-RS-API-KEY"):
            self.assertNotIn(banned, code, f"analytics.ts must not touch {banned}")
        body = re.search(r"JSON\.stringify\(\{(.*?)\}\)", code, re.S)
        self.assertIsNotNone(body, "analytics body not found")
        fields = {p.strip().split(":")[0].strip() for p in body.group(1).split(",") if p.strip()}
        self.assertEqual(fields, {"event", "ctx", "version", "platform"},
                         f"analytics must send exactly the four anonymous fields: {fields}")

    def test_the_tracker_never_throws(self):
        code = strip_ts_comments(read("src/utils/analytics.ts"))
        self.assertIn("catch", code)
        self.assertIn("abort", code.lower())

    def test_the_paywall_is_counted_on_view_and_on_tap(self):
        pay = strip_ts_comments(read("src/screens/PaywallScreen.tsx"))
        self.assertIn('track("paywall_viewed"', pay)
        self.assertIn('track("checkout_tapped"', pay)

    def test_funnel_filters_match_the_line_the_handler_writes(self):
        api = (ROOT / "relayshield_api.py").read_text(encoding="utf-8")
        tool = (ROOT / "tools" / "miniapp_funnel.py").read_text(encoding="utf-8")
        # What the handlers write, parsed out of the code rather than retyped.
        ev_fmt = re.search(r'logger\.info\("(app_event name=[^"]+)"', api)
        fx_fmt = re.search(r'logger\.info\("(free_exposure_check outcome=%s[^"]*)"', api)
        self.assertIsNotNone(ev_fmt)
        self.assertIsNotNone(fx_fmt)
        ev_line = ev_fmt.group(1) % ("paywall_viewed", "free_check", "1.7.0", "solana")
        fx_line = fx_fmt.group(1) % ("served", "found")
        for name, line in (("paywall_viewed", ev_line), ("free", fx_line)):
            self.assertTrue(line)
        stage_rx = {}
        for m in re.finditer(r'\("(APP [A-Z]+)[^"]*",\s*"[^"]+",\s*"([^"]+)",\s*re\.compile\(r"([^"]+)"\)', tool):
            stage_rx[m.group(1)] = (m.group(2), re.compile(m.group(3)))
        self.assertEqual(set(stage_rx), {"APP FREE", "APP PAYWALL", "APP TAPPED"})
        pat, rx = stage_rx["APP PAYWALL"]
        self.assertIn(pat, ev_line)
        self.assertTrue(rx.search(ev_line), "paywall stage regex misses the real line")
        tap_line = ev_fmt.group(1) % ("checkout_tapped", "monthly", "1.7.0", "solana")
        pat, rx = stage_rx["APP TAPPED"]
        self.assertIn(pat, tap_line)
        self.assertTrue(rx.search(tap_line))
        self.assertFalse(rx.search(ev_line), "tap stage must not count paywall views")
        pat, rx = stage_rx["APP FREE"]
        self.assertIn(pat, fx_line)
        self.assertTrue(rx.search(fx_line))
        self.assertFalse(rx.search("free_exposure_check outcome=ip_capped"),
                         "a refused check must not count as a served one")
        self.assertFalse(rx.search("free_exposure_check outcome=already_used"))

    def test_the_stripe_channel_tag_equals_channel(self):
        chan = re.search(r'export const CHANNEL\s*=\s*"([a-z]+)"', read("src/utils/analytics.ts"))
        self.assertIsNotNone(chan)
        pay = read("src/screens/PaywallScreen.tsx")
        tags = set(re.findall(r"client_reference_id=([a-z]+)", pay))
        self.assertEqual(tags, {chan.group(1)},
                         "the Stripe tag and the app's CHANNEL disagree, so the two "
                         "platform splits would report different channels")


class TheFreeCheckIsKeyless(unittest.TestCase):
    def test_the_client_sends_no_key(self):
        code = strip_ts_comments(read("src/api/relayshield.ts"))
        m = re.search(r"export (?:async )?function freeExposureCheck.*?\n\}", code, re.S)
        self.assertIsNotNone(m)
        self.assertIn('"/v1/app/free-exposure-check"', m.group(0))
        self.assertRegex(m.group(0), r"null\s*\)")

    def test_a_subscriber_keeps_the_paid_check(self):
        scan = strip_ts_comments(read("src/screens/ScanScreen.tsx"))
        self.assertRegex(scan, r'scanType\s*===\s*"infostealer"\s*&&\s*!apiKey')

    def test_the_wallet_scan_no_longer_needs_a_key(self):
        w = strip_ts_comments(read("src/screens/WalletsScreen.tsx"))
        self.assertNotIn("Subscription required", w)
        self.assertIn("scanWalletRisk(wallet.address, apiKey ?? null)", w)

    def test_the_paid_infostealer_result_reads_the_real_field(self):
        scan = strip_ts_comments(read("src/screens/ScanScreen.tsx"))
        self.assertIn("stealer_count", scan)


class TheFirstRunReachesValue(unittest.TestCase):
    def setUp(self):
        self.src = strip_ts_comments(read("src/screens/OnboardingScreen.tsx"))

    def test_connect_scan_and_free_check_are_wired(self):
        for needle in ("connectSolanaWallet", "RS.scanWalletRisk(addr, null)",
                       "RS.freeExposureCheck", "ExposureCard", 'track("wallet_connected"',
                       'track("onboarding_completed"'):
            self.assertIn(needle, self.src)

    def test_the_trial_cta_is_handed_to_the_app(self):
        self.assertIn("finish({ openPaywall: true })", self.src)
        app = strip_ts_comments(read("App.tsx"))
        self.assertIn("pendingPaywall", app)
        self.assertIn('navigate("Paywall"', app)

    def test_the_press_event_is_not_passed_as_options(self):
        self.assertIn("() => finish()", self.src)
        self.assertNotRegex(self.src, r"step === TOTAL - 1 \? finish :")

    def test_consent_links_point_at_pages_that_exist(self):
        # relayshield.net/terms and /privacy are a Carrd 404 (CLAUDE.md, 2026-08-01).
        self.assertNotIn("https://relayshield.net/terms", self.src)
        self.assertNotIn("https://relayshield.net/privacy", self.src)
        self.assertIn("https://privacy.relayshield.net", self.src)
        self.assertIn("https://terms.relayshield.net", self.src)

    def test_a_scanned_wallet_keeps_its_result(self):
        self.assertIn("lastRiskLevel", self.src)

    def test_scan_wording_never_says_safe(self):
        for m in re.finditer(r'"([^"\n]*)"', self.src):
            s = m.group(1).lower()
            if " safe" in s or s.startswith("safe"):
                self.assertTrue("not a guarantee" in s or "not proof" in s or "don't" in s,
                                f"onboarding copy implies safety: {m.group(1)!r}")


class TheWordsAreHonest(unittest.TestCase):
    """Executes exposureCopy.ts. Skipped, loudly, when no compiler is reachable."""

    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        cls.ts_dir = None
        for cand in (os.environ.get("CS_TS_DIR"), str(APP / "node_modules"),
                     *[str(p) for p in pathlib.Path("/tmp").glob("**/app/node_modules")][:3]):
            if cand and (pathlib.Path(cand) / "typescript" / "lib" / "typescript.js").exists():
                cls.ts_dir = cand
                break

    def run_view(self, result: dict) -> dict:
        if not (self.node and self.ts_dir):
            self.skipTest("node or typescript unavailable; set CS_TS_DIR to a node_modules with typescript")
        src = read("src/utils/exposureCopy.ts")
        script = r"""
const ts = require(process.argv[2] + "/typescript");
const out = ts.transpileModule(process.argv[3], {compilerOptions:{module:"commonjs",target:"es2019"}}).outputText;
const m = {exports:{}}; new Function("module","exports",out)(m,m.exports);
console.log(JSON.stringify(m.exports.exposureView(JSON.parse(process.argv[4]))));
"""
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "run.js"
            f.write_text(script)
            p = subprocess.run([self.node, str(f), self.ts_dir, src, json.dumps(result)],
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_found_is_stated_with_actions(self):
        v = self.run_view({"level": "found", "complete": True,
                           "breach": {"checked": True, "count": 3, "names": ["A", "B"], "password_exposed": True},
                           "infostealer": {"checked": True, "found": False}})
        self.assertEqual(v["tone"], "found")
        self.assertTrue(any("3" in l for l in v["lines"]))
        self.assertTrue(v["actions"])

    def test_nothing_known_never_says_safe(self):
        v = self.run_view({"level": "nothing_known", "complete": True,
                           "breach": {"checked": True, "count": 0}, "infostealer": {"checked": True, "found": False}})
        self.assertEqual(v["tone"], "nothing")
        text = (v["title"] + " " + " ".join(v["lines"]) + " " + v["note"]).lower()
        # Any affirmative "safe"/"clean"/"all clear" is banned. The one legitimate
        # use is the disclaimer itself ("not proof it's safe"), so that exact
        # lead-in is the only thing allowed to precede the word.
        for m in re.finditer(r"\b(safe|secure|clean|protected|all clear)\b", text):
            lead = text[max(0, m.start() - 14):m.start()]
            self.assertTrue(lead.endswith("proof it's ") or lead.endswith("proof it is "),
                            f"copy implies safety: ...{text[max(0, m.start()-30):m.end()+10]}...")
        self.assertIn("not proof", text)

    def test_an_incomplete_check_is_never_clean(self):
        v = self.run_view({"level": "incomplete", "complete": False,
                           "breach": {"checked": False}, "infostealer": {"checked": True, "found": False}})
        self.assertEqual(v["tone"], "incomplete")
        self.assertTrue(v["canRetry"])
        self.assertNotIn("nothing known", v["title"].lower())

    def test_a_partial_find_is_still_reported(self):
        v = self.run_view({"level": "found", "complete": False,
                           "breach": {"checked": False},
                           "infostealer": {"checked": True, "found": True, "count": 2, "newest": "2026-08-01"}})
        self.assertEqual(v["tone"], "incomplete")
        self.assertTrue(any("2" in l for l in v["lines"]), "what WAS found must be shown")

    def test_already_used_is_a_way_forward_not_an_error(self):
        v = self.run_view({"already_used": True, "allowance": {"used": True, "remaining": 0}})
        self.assertEqual(v["tone"], "used")
        self.assertIsNotNone(v["cta"])
        self.assertFalse(v["canRetry"])


class TheListingMatchesTheBuild(unittest.TestCase):
    def test_version_was_bumped(self):
        cfg = json.loads((APP / "app.json").read_text())["expo"]
        self.assertEqual(cfg["version"], "1.7.0")
        self.assertGreaterEqual(cfg["android"]["versionCode"], 7)

    def test_the_subtitle_fits_the_portal(self):
        md = (APP / "store-assets" / "dapp-store-metadata.md").read_text(encoding="utf-8")
        m = re.search(r"\*\*Subtitle\*\* \(50 char max\): `([^`]+)`", md)
        self.assertIsNotNone(m)
        self.assertLessEqual(len(m.group(1)), 50)

    def test_the_copy_does_not_claim_a_stale_count_or_an_only(self):
        md = (APP / "store-assets" / "dapp-store-metadata.md").read_text(encoding="utf-8")
        body = re.sub(r"<!--.*?-->", "", md, flags=re.S)
        self.assertNotRegex(body, r"\b\d+\+ monitored")
        self.assertNotIn("is the only consumer", body)
        self.assertNotIn("The only wallet security app", body)

    def test_the_privacy_policy_discloses_the_free_check(self):
        p = (ROOT / "cloudflare_worker_privacy.js").read_text(encoding="utf-8")
        for needle in ("Free email check", "third-party data providers", "Anonymous usage counters"):
            self.assertIn(needle, p)

    def test_no_customer_facing_surface_names_a_data_vendor(self):
        """House rule: we never attribute a third-party partner in anything a
        customer reads. The privacy policy still DISCLOSES that the address goes
        to third parties; it just does not name them."""
        banned = re.compile(r"have i been pwned|hudson ?rock|\bhibp\b", re.I)
        files = [ROOT / "cloudflare_worker_privacy.js",
                 APP / "store-assets" / "dapp-store-metadata.md",
                 *[p for p in (APP / "src").rglob("*.ts*")], APP / "App.tsx"]
        self.assertGreater(len(files), 10, "guard scoped itself down to nothing")
        hits = []
        for f in files:
            text = f.read_text(encoding="utf-8")
            text = strip_ts_comments(text) if f.suffix in (".ts", ".tsx", ".js") else text
            if banned.search(text):
                hits.append(str(f.relative_to(ROOT)))
        self.assertEqual(hits, [], f"vendor named in customer-facing copy: {hits}")


if __name__ == "__main__":
    unittest.main()
