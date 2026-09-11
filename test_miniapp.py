#!/usr/bin/env python3
"""Invariants for the Telegram Mini App. No network, no boto3, no node.

Every assertion here exists because of a specific failure this repo has already
paid for. They are not general good practice.
"""

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import types
import unittest
import unittest.mock
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
        """The invariant, not the sentence.

        This pinned the literal string "Treat that as unknown, not as clear."
        and failed on 2026-09-10 when that copy was rewritten -- correctly, since
        it guards a safety claim, but it could not tell a rewrite that KEPT the
        meaning from one that lost it. `unknown` is the MOST COMMON outcome
        (_link_check_level returns it for anything not in the corpus, not on Safe
        Browsing and older than 30 days), so its wording is the wording most
        users will read, and it must never imply the target is fine.
        """
        worker = _worker()
        caveat = re.search(r'\$\("caveat"\)\.textContent\s*=(.*?);\n', worker, re.S)
        self.assertIsNotNone(caveat, "the caveat assignment moved; re-point this test")
        block = caveat.group(1)
        i = block.find('level === "unknown"')
        self.assertGreater(i, -1, "the unknown branch is gone")
        branch = block[i:i + 400].lower()
        self.assertTrue(
            any(p in branch for p in ("not proof", "not the same as safe",
                                      "absence of evidence", "not as clear")),
            "the unknown branch must explicitly deny that this means safe")
        # Every mention of "safe" must sit inside a NEGATION. A naive
        # assertNotRegex on "is safe" fails on "not proof it is safe", which is
        # the denial we want, and on "Google Safe Browsing", which is a product
        # name -- so both are handled explicitly rather than by banning a word.
        scan = branch.replace("safe browsing", "")
        for m in re.finditer(r"\bsafe\b|\bfine\b|\bclear\b", scan):
            before = scan[max(0, m.start() - 45):m.start()]
            self.assertRegex(
                before, r"\bnot\b|\bnever\b|\bno\b|\bisn't\b|\brather than\b",
                f"'{m.group(0)}' appears without a negation near it: ...{before}")


class TestBotCallToAction(unittest.TestCase):
    """The bot link. `BOT` was declared and never used until 2026-09-10, so the
    only call to action in the app was the DEVELOPER page -- an API pitched to a
    consumer who had just been shown a flagged scam. The stickiness plan's own
    mechanism depends on this path existing, so it is pinned rather than trusted."""

    def test_the_bot_constant_is_actually_used(self):
        src = _worker()
        self.assertIn("__BOT__", src, "the page must reference the bot placeholder")
        self.assertIn('.replaceAll("__BOT__", BOT)', src,
                      "the placeholder must be substituted, or the href ships literal")

    def test_the_bot_link_carries_attribution(self):
        src = _worker()
        self.assertIn("start=SRC_miniapp", src,
                      "an unattributed bot link makes Mini App conversions invisible")

    def test_attribution_uses_the_scheme_the_bot_actually_parses(self):
        # handle_start matches payload.upper().startswith("SRC_"). A bare label
        # would fall through to the Coinbase charge-code branch instead.
        bot_src = (ROOT / "relayshield_telegram_webhook.py").read_text(encoding="utf-8")
        self.assertIn('startswith("SRC_")', bot_src,
                      "the bot no longer parses SRC_; the Mini App link needs updating")

    def test_the_offer_is_shown_only_after_a_result(self):
        src = _worker()
        self.assertIn('id="cta"', src)
        self.assertIn('class="cta hidden"', src,
                      "the offer must start hidden, not greet a first-time user")

    def test_the_wording_differs_by_severity(self):
        src = _worker()
        i = src.index('$("cta-line").textContent')
        block = src[i:i + 700]
        self.assertIn("critical", block)
        self.assertIn("high", block)
        self.assertIn("breach", block.lower())

    def test_it_opens_the_chat_rather_than_a_browser(self):
        src = _worker()
        self.assertIn("openTelegramLink", src,
                      "a bare t.me anchor in a webview lands the user on a web page "
                      "asking them to open Telegram, from inside Telegram")
        self.assertIn('href="__BOT__"', src,
                      "the href must stay real so the link works without the SDK")


class TestTheWorkerActuallyParses(unittest.TestCase):
    """NOTHING IN THIS SUITE PARSED THE WORKER UNTIL 2026-09-10.

    A code comment containing a BACKTICK was added inside the `const PAGE = ` ... ``
    template literal. A backtick terminates a template literal, so the file was
    no longer valid JavaScript -- and every check here passed anyway, because
    they all read the file as TEXT. build_miniapp.py --check passed too. The
    deploy would have failed at wrangler, which is late, red, and reads like a
    Cloudflare problem rather than a stray character.

    `node --check` is one command and catches it in a second, so it belongs
    beside the checks that cannot.
    """

    def test_worker_is_valid_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        out = subprocess.run([node, "--check", str(WORKER)],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0,
                         f"cloudflare_worker_miniapp.js is not valid JS:\n{out.stderr}")

    def test_no_stray_backtick_inside_the_page_template(self):
        # The specific trap, named. An escaped \` is fine and the widget embed
        # relies on it; a bare one closes the template early.
        src = _worker()
        page = src.split("const PAGE = `", 1)[1]
        body = page.rsplit("`;", 1)[0]
        stray = [i for i, ch in enumerate(body)
                 if ch == "`" and (i == 0 or body[i - 1] != "\\")]
        self.assertEqual(stray, [],
                         "a bare backtick inside the PAGE template ends it early")


class TestGettingBackIn(unittest.TestCase):
    """A direct-link Mini App leaves no way back. The founder could not find his
    own app on 2026-09-10: t.me/<bot>/<app> opens without creating a bot chat, so
    there was nothing to pin and nothing in the Apps tab. Every return mechanic in
    the stickiness plan assumes the user can get back."""

    def test_the_home_screen_offer_is_feature_detected(self):
        src = _worker()
        self.assertIn("addToHomeScreen", src)
        self.assertIn('typeof tg.addToHomeScreen === "function"', src,
                      "an unconditional call breaks on clients without the method")

    def test_it_starts_hidden(self):
        src = _worker()
        self.assertIn('class="ghost hidden" id="pin"', src,
                      "a button that does nothing is worse than no button")

    def test_it_is_not_offered_when_already_added(self):
        src = _worker()
        self.assertIn("checkHomeScreenStatus", src)
        self.assertIn('status !== "added"', src)

    def test_the_call_cannot_throw_into_the_page(self):
        src = _worker()
        i = src.index("tg.addToHomeScreen()")
        self.assertIn("try", src[max(0, i - 120):i],
                      "a refusing client must not take the page down with it")


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
        # The only POSTs may be the watchlist routes. This is an ALLOWLIST and
        # the point is that adding one is a deliberate act with a reason: every
        # new POST from this page is a new thing leaving somebody's device.
        # /v1/watchlist/invoice sends init_data and nothing else -- it mints a
        # Stars invoice link and carries no target, no history and no amount
        # chosen by the client.
        posts = set(re.findall(r'post\("(/v1/[^"]+)"', worker))
        self.assertEqual(posts, {"/v1/watchlist/add", "/v1/watchlist/list",
                                 "/v1/watchlist/remove", "/v1/watchlist/invoice"},
                         f"unexpected POST targets: {posts}")

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


class TestWatchlistCORS(unittest.TestCase):
    """These EXECUTE the dispatcher, with boto3 stubbed, rather than grepping it.

    CORS is the one thing curl cannot tell you about. It ignores CORS entirely,
    so the endpoint can pass every terminal test and still be dead in the only
    client that uses it -- and the browser reports it as a button that does
    nothing, with no request in the Lambda's log at all, because the request was
    never sent. That is the quiet-alarm shape, so it gets executed tests.
    """

    @classmethod
    def setUpClass(cls):
        # No boto3 in this container, and the module builds three clients at
        # import. Stub the whole thing: nothing these tests reach touches AWS.
        boto3 = types.ModuleType("boto3")
        boto3.resource = lambda *a, **k: unittest.mock.MagicMock()
        boto3.client = lambda *a, **k: unittest.mock.MagicMock()
        conditions = types.ModuleType("boto3.dynamodb.conditions")
        conditions.Key = unittest.mock.MagicMock()
        dynamodb_mod = types.ModuleType("boto3.dynamodb")
        dynamodb_mod.conditions = conditions
        boto3.dynamodb = dynamodb_mod
        sys.modules.setdefault("boto3", boto3)
        sys.modules.setdefault("boto3.dynamodb", dynamodb_mod)
        sys.modules.setdefault("boto3.dynamodb.conditions", conditions)
        spec = importlib.util.spec_from_file_location(
            "relayshield_watchlist", ROOT / "relayshield_watchlist.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_the_preflight_is_answered_on_every_route(self):
        """A preflight that 403s means the POST is never sent."""
        for path in ("/v1/watchlist/add", "/v1/watchlist/list", "/v1/watchlist/remove"):
            r = self.mod.lambda_handler({"path": path, "httpMethod": "OPTIONS"}, None)
            self.assertEqual(r["statusCode"], 204, path)
            h = {k.lower(): v for k, v in r["headers"].items()}
            self.assertEqual(h["access-control-allow-origin"], "*", path)
            self.assertIn("content-type", h["access-control-allow-headers"].lower(), path)

    def test_the_preflight_works_on_the_v2_payload_shape_too(self):
        """REST puts the method at the top level; an HTTP API nests it. Reading
        only one of them means the preflight silently falls through to the POST
        branch and 404s on a path with no body."""
        r = self.mod.lambda_handler(
            {"rawPath": "/v1/watchlist/list",
             "requestContext": {"http": {"method": "OPTIONS"}}}, None)
        self.assertEqual(r["statusCode"], 204)

    def test_every_real_response_carries_allow_origin(self):
        """A 200 without this header is discarded by the browser after the fact,
        which is indistinguishable from an outage in the UI."""
        for event in ({"path": "/v1/watchlist/list", "httpMethod": "POST", "body": "{}"},
                      {"path": "/v1/nope", "httpMethod": "POST", "body": "{}"},
                      {"path": "/v1/watchlist/add", "httpMethod": "POST", "body": "not json"}):
            r = self.mod.lambda_handler(event, None)
            h = {k.lower(): v for k, v in r["headers"].items()}
            self.assertEqual(h.get("access-control-allow-origin"), "*",
                             f"{event['path']} -> {r['statusCode']} has no allow-origin")

    def test_an_unsigned_request_is_refused_and_that_is_the_wiring_proof(self):
        """create_watchlist_routes.sh asserts this exact string end to end: it
        proves the gateway routed the path AND that our handler ran AND that the
        identity gate is on, in one response."""
        r = self.mod.lambda_handler(
            {"path": "/v1/watchlist/list", "httpMethod": "POST", "body": "{}"}, None)
        self.assertEqual(r["statusCode"], 400)
        self.assertIn("unverified", r["body"])

    def test_the_import_probe_still_returns_early(self):
        r = self.mod.lambda_handler({"source": "ci.import-probe"}, None)
        self.assertEqual(r["statusCode"], 200)
        self.assertIn('"probe": true', r["body"])


class TestWatchlistRouteScript(unittest.TestCase):
    """Two files that must agree, with nothing checking that they do, is the
    shape that produced run 134's red probe. The script wires paths; the handler
    serves them."""

    def test_the_script_wires_exactly_the_routes_the_handler_serves(self):
        script = (ROOT / "tools" / "create_watchlist_routes.sh").read_text(encoding="utf-8")
        src = (ROOT / "relayshield_watchlist.py").read_text(encoding="utf-8")
        served = set(re.findall(r'"(/v1/watchlist/\w+)":', src))
        parts = re.search(r'^PARTS="([^"]+)"', script, re.M).group(1).split()
        wired = {f"/v1/watchlist/{p}" for p in parts}
        self.assertEqual(served, wired,
                         "the route script and the handler disagree about the routes")

    def test_the_script_creates_the_OPTIONS_method(self):
        script = (ROOT / "tools" / "create_watchlist_routes.sh").read_text(encoding="utf-8")
        self.assertIn("for M in POST OPTIONS", script)

    def test_the_script_refuses_the_pre_audit_account(self):
        script = (ROOT / "tools" / "create_watchlist_routes.sh").read_text(encoding="utf-8")
        self.assertIn("ACCOUNT=239677749008", script)
        self.assertIn("620534471984", script)

    def test_the_preflight_check_prints_the_body_not_just_the_status(self):
        """Its first real run reported "-> 404, allow-origin: NONE" and nothing
        else, which is unactionable: an API Gateway 404 and our handler's 404
        are different problems and only the body separates them. That is this
        repo's own status-code rule broken inside the tool enforcing it."""
        # ASSERT THE PROPERTY, NOT THE INCANTATION. The first version of this
        # pinned the literal `curl -sS -i -X OPTIONS`, so moving the probe into
        # the shared helper broke a test about a behaviour that had not changed.
        # A test that names one command tests that command, not the rule.
        script = (ROOT / "tools" / "create_watchlist_routes.sh").read_text(encoding="utf-8")
        self.assertIn("$AWAIT_HEADERS", script,
                      "the preflight must capture response headers")
        self.assertIn("$AWAIT_BODY", script,
                      "the preflight must capture the response body")
        self.assertTrue(re.search(r'sed .*AWAIT_BODY', script),
                        "the body must be PRINTED, not merely captured")
        self.assertIn("diagnose_watchlist_routes.sh", script,
                      "the failure path must name the one command that settles it")

    def test_every_route_script_waits_for_the_edge(self):
        """create-deployment returns before the edge serves the new resource
        set. Three scripts create a deployment and then immediately prove it;
        every one must poll, or it is a coin flip that reports as a routing bug.

        The knowledge existed in create_mpp_settlement_lambda.sh's comments
        since 2026-09-05 and did not reach the script written on 2026-09-09,
        which is precisely why it is a shared file now instead of a comment."""
        for name in ("create_watchlist_routes.sh", "create_link_check_endpoint.sh",
                     "create_agent_bait_scan_routes.sh"):
            src = (ROOT / "tools" / name).read_text(encoding="utf-8")
            self.assertIn("create-deployment", src, f"{name} premise changed")
            self.assertIn("lib_await_route.sh", src, f"{name} does not source the wait")
            self.assertIn("await_http", src, f"{name} does not use it")

    def test_the_wait_only_retries_propagation_shaped_answers(self):
        """A loop that waits out a 500 turns a clear fault into a slow one. Only
        403, 404 and a failed connection are what an undeployed route returns."""
        lib = (ROOT / "tools" / "lib_await_route.sh").read_text(encoding="utf-8")
        self.assertIn("403|404|000) ;;", lib)
        self.assertIn("*) return 1 ;;", lib)

    def test_the_diagnostic_is_read_only(self):
        """It runs against a live published API. A diagnostic that changes
        something cannot be run twice to compare."""
        # COMMANDS, NOT PROSE. The first version of this asserted against the
        # whole file and failed on the word "update-function-code" inside a
        # comment explaining the fix -- the same mistake as asserting "uvx" is
        # absent from a file whose comments explain why uvx was removed. A file
        # is allowed to name the thing it warns about.
        lines = [l for l in (ROOT / "tools" / "diagnose_watchlist_routes.sh")
                 .read_text(encoding="utf-8").splitlines()
                 if not l.lstrip().startswith("#")]
        for mutating in ("create-resource", "put-method", "put-integration",
                         "create-deployment", "add-permission", "update-function-code",
                         "delete-"):
            hit = [l for l in lines if mutating in l and not l.lstrip().startswith("echo")]
            self.assertEqual(hit, [], f"{mutating} is not a read: {hit}")

    def test_the_diagnostic_asks_the_function_directly(self):
        """When two causes produce the same symptom, ask the component with the
        gateway taken out of the path. That is what separates stale code from a
        gateway fault, and it is the move that paid for
        diagnose_agent_bait_routes.sh on its first run."""
        d = (ROOT / "tools" / "diagnose_watchlist_routes.sh").read_text(encoding="utf-8")
        self.assertIn("lambda invoke", d)
        self.assertIn('"httpMethod":"OPTIONS"', d)

    def test_the_lambda_script_waits_for_active_before_invoking(self):
        """create-function returns before the function can be invoked, so the
        probe hit ResourceConflictException: state Pending."""
        script = (ROOT / "tools" / "create_watchlist_lambda.sh").read_text(encoding="utf-8")
        wait = script.index("wait function-active-v2")
        probe = script.index("ci.import-probe")
        self.assertLess(wait, probe, "the Active wait must come BEFORE the probe")


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
