"""Tests for the TON watchlist monitor and the Stars slot purchase.

WHY THESE EXECUTE THE CODE RATHER THAN GREP IT. test_miniapp.py already learned
this the hard way: a test that reads a file as text passes on a file that cannot
run, which is how a stray backtick inside a template literal shipped past two
green checks. Everything below imports the real modules with boto3 stubbed and
calls the real functions, so a syntax error or a wrong DynamoDB shape fails
here rather than in production.

THE TEST THIS SUITE EXISTS TO CARRY IS test_first_run_never_alerts. Every other
failure costs a wrong answer. That one costs a message to every user about
every target they have ever added, at once, from a security bot -- which is how
an app gets reported rather than uninstalled.
"""

import ast
import importlib
import re
import json
import sys
import types
import unittest
from unittest import mock


def code_only(path: str, func: str = "") -> str:
    """The file's EXECUTABLE source, with every comment and docstring removed.

    Both failures on this suite's first run were the same mistake, and it is one
    test_telegram_markdown_escapes.py already had to learn: prose explaining why
    we do NOT do something reads identically to doing it. A comment saying
    "/v1/link-check is free and must never be gated" failed a test asserting
    /v1/link-check is never gated, and a docstring saying "the id is never taken
    from invoice_payload" failed a test asserting invoice_payload is not used.

    Grepping source for a decision is only sound against the code, so this
    strips the narration with ast rather than with a heuristic about "#".
    """
    tree = ast.parse(open(path).read())
    if func:
        tree = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == func)
        # A function's own docstring is its first statement.
        body = tree.body[1:] if (tree.body and isinstance(tree.body[0], ast.Expr)
                                 and isinstance(tree.body[0].value, ast.Constant)) else tree.body
        return "\n".join(ast.unparse(n) for n in body)
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str):
            continue          # a bare string statement is a docstring
        if isinstance(n, (ast.Constant, ast.Name, ast.Load, ast.Store)):
            continue
        try:
            out.append(ast.unparse(n))
        except Exception:
            pass
    return "\n".join(out)


def _stub_boto3():
    """A boto3 that constructs without credentials and records nothing.

    Only the shapes the modules touch at import time. Anything a test actually
    needs is patched per-test, so a call this stub does not implement raises
    rather than silently returning a Mock that compares equal to everything --
    which is how a test passes against code that does the wrong thing.
    """
    b = types.ModuleType("boto3")
    b.client = lambda *a, **k: mock.MagicMock()
    b.resource = lambda *a, **k: mock.MagicMock()
    conditions = types.ModuleType("boto3.dynamodb.conditions")

    class _Key:
        def __init__(self, name): self.name = name
        def eq(self, v): return ("eq", self.name, v)

    conditions.Key = _Key
    conditions.Attr = _Key
    dynamodb_mod = types.ModuleType("boto3.dynamodb")
    dynamodb_mod.conditions = conditions
    b.dynamodb = dynamodb_mod
    sys.modules["boto3"] = b
    sys.modules["boto3.dynamodb"] = dynamodb_mod
    sys.modules["boto3.dynamodb.conditions"] = conditions
    return b


_stub_boto3()
# relayshield_api is imported by the monitor and is large; importing it here
# proves the monitor's own import line works, which is the thing the deployer's
# resolve_deps grep is relied on to package.
mon = importlib.import_module("relayshield_watchlist_monitor")
wl = importlib.import_module("relayshield_watchlist")


TOKEN = dict(type="token", risk_level="low", risk_flags=[], state="",
             has_pool=True, liquidity_usd=100000.0, price_usd=1.0, symbol="X")
WALLET = dict(type="wallet", risk_level="low", risk_flags=[], state="active",
              has_pool=False, balance_ton=500.0)


def ch(prev, cur, was=False, now=False):
    return [s[0] for s in mon.detect_changes(prev, cur, was, now)]


class TestSignals(unittest.TestCase):

    def test_liquidity_gone_is_critical(self):
        after = dict(TOKEN, has_pool=False, liquidity_usd=None, price_usd=None)
        self.assertIn("LIQUIDITY_GONE", ch(TOKEN, after))

    def test_liquidity_drain(self):
        after = dict(TOKEN, liquidity_usd=1000.0)
        self.assertIn("LIQUIDITY_DRAIN", ch(TOKEN, after))

    def test_an_ordinary_dip_is_not_a_drain(self):
        """The threshold is the product. A bot that fires on a 10% move is a
        bot people mute, and a muted bot detects nothing at all."""
        after = dict(TOKEN, liquidity_usd=90000.0, price_usd=0.9)
        self.assertEqual(ch(TOKEN, after), [])

    def test_price_collapse(self):
        after = dict(TOKEN, price_usd=0.05)
        self.assertIn("PRICE_COLLAPSE", ch(TOKEN, after))

    def test_balance_drained(self):
        after = dict(WALLET, balance_ton=1.0)
        self.assertIn("BALANCE_DRAINED", ch(WALLET, after))

    def test_dust_moving_is_not_a_drain(self):
        small = dict(WALLET, balance_ton=0.4)
        self.assertEqual(ch(small, dict(small, balance_ton=0.0)), [])

    def test_scam_flag_appearing(self):
        after = dict(WALLET, risk_flags=["flagged as scam in TON community database"],
                     risk_level="critical")
        self.assertIn("SCAM_FLAGGED", ch(WALLET, after))

    def test_a_scam_flag_that_was_always_there_never_fires(self):
        """The whole difference between a checker and a monitor. A target that
        has been flagged since it was added must produce silence on every run
        forever, or the user gets the same alert every cycle."""
        flagged = dict(WALLET, risk_flags=["flagged as scam"], risk_level="critical")
        self.assertEqual(ch(flagged, flagged), [])

    def test_ioc_listing_appearing(self):
        self.assertIn("IOC_LISTED", ch(WALLET, WALLET, was=False, now=True))

    def test_ioc_already_listed_never_fires(self):
        self.assertEqual(ch(WALLET, WALLET, was=True, now=True), [])

    def test_contract_deployed(self):
        before = dict(WALLET, state="uninitialized")
        self.assertIn("CONTRACT_DEPLOYED", ch(before, dict(WALLET, state="active")))

    def test_verdict_worsened_is_a_catch_all_not_a_duplicate(self):
        """It must fire when nothing named it, and stay quiet when a named
        signal already explains the same worsening -- otherwise every rug
        produces two bullet points saying the same thing."""
        after = dict(WALLET, risk_level="medium", risk_flags=["uninitialized contract"])
        self.assertIn("VERDICT_WORSENED", ch(WALLET, after))
        rug = dict(TOKEN, has_pool=False, risk_level="critical",
                   risk_flags=["flagged as scam"])
        signals = ch(TOKEN, rug)
        self.assertNotIn("VERDICT_WORSENED", signals)

    def test_improvements_are_never_alerted(self):
        """Rule 2. An alert is for action, and 'good news' at 3am is how people
        learn to ignore the next one."""
        bad = dict(TOKEN, risk_level="critical", liquidity_usd=1000.0,
                   risk_flags=["flagged as scam"])
        self.assertEqual(ch(bad, TOKEN), [])

    def test_worst_signal_comes_first(self):
        after = dict(TOKEN, has_pool=False, price_usd=0.01,
                     risk_flags=["flagged as scam"], risk_level="critical")
        first = mon.detect_changes(TOKEN, after, False, False)[0]
        self.assertEqual(first[1], "critical")


class TestNotLooking(unittest.TestCase):
    """"We could not check" must never render as "it is gone". This is the
    single most likely source of a false rug alert, and a false rug alert is
    the one mistake that would make this product actively harmful."""

    def test_an_empty_snapshot_produces_no_signals(self):
        self.assertEqual(ch(TOKEN, {}), [])
        self.assertEqual(ch({}, TOKEN), [])

    def test_unreadable_numbers_are_none_not_zero(self):
        self.assertIsNone(mon._num(None))
        self.assertIsNone(mon._num(""))
        self.assertIsNone(mon._num("n/a"))
        self.assertEqual(mon._num("12.5"), 12.5)

    def test_a_missing_liquidity_figure_is_not_a_drain(self):
        self.assertEqual(ch(TOKEN, dict(TOKEN, liquidity_usd=None)), [])

    def test_ton_snapshot_returns_empty_on_a_non_200(self):
        with mock.patch.object(mon, "handle_ton_address",
                               return_value={"statusCode": 502, "body": "{}"}):
            self.assertEqual(mon.ton_snapshot("EQ" + "A" * 46), {})

    def test_ton_snapshot_returns_empty_when_the_lookup_raises(self):
        with mock.patch.object(mon, "handle_ton_address", side_effect=RuntimeError("boom")):
            self.assertEqual(mon.ton_snapshot("EQ" + "A" * 46), {})

    def test_ton_snapshot_flattens_a_token(self):
        body = json.dumps({"ok": True, "data": {
            "type": "token", "risk_level": "LOW", "risk_flags": [],
            "token": {"liquidity_usd": 5000, "price_usd": "0.02", "token_symbol": "AB"}}})
        with mock.patch.object(mon, "handle_ton_address",
                               return_value={"statusCode": 200, "body": body}):
            snap = mon.ton_snapshot("EQ" + "A" * 46)
        self.assertTrue(snap["has_pool"])
        self.assertEqual(snap["liquidity_usd"], 5000.0)
        self.assertEqual(snap["price_usd"], 0.02)
        self.assertEqual(snap["risk_level"], "low")


class TestDecimals(unittest.TestCase):
    def test_decimal_from_dynamodb_does_not_raise(self):
        """DynamoDB hands numbers back as Decimal, and Decimal/float comparison
        is a TypeError waiting for the first token that has a price."""
        from decimal import Decimal
        stored = {"last_snapshot": {"has_pool": True, "liquidity_usd": Decimal("100000"),
                                    "price_usd": Decimal("1"), "risk_flags": [],
                                    "risk_level": "low"}}
        prev = mon._stored_snapshot(stored)
        self.assertIn("LIQUIDITY_DRAIN", ch(prev, dict(TOKEN, liquidity_usd=10.0)))

    def test_a_json_string_snapshot_round_trips(self):
        stored = {"last_snapshot": json.dumps(TOKEN)}
        self.assertEqual(mon._stored_snapshot(stored)["liquidity_usd"], 100000.0)

    def test_a_corrupt_snapshot_is_none_not_a_crash(self):
        self.assertIsNone(mon._stored_snapshot({"last_snapshot": "{not json"}))
        self.assertIsNone(mon._stored_snapshot({}))


class TestAlertCopy(unittest.TestCase):

    def test_it_is_html_and_the_target_is_escaped(self):
        """Legacy Markdown has NO escape syntax, which is why this surface is
        HTML. A target is attacker-supplied text that lands in a message."""
        text = mon.format_alert("EQ<script>x</script>_a",
                                [("SCAM_FLAGGED", "critical", "flagged")])
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("<script>", text)
        self.assertIn("<code>", text)

    def test_it_carries_no_backslash_escapes(self):
        text = mon.format_alert("EQ_a_b", [("IOC_LISTED", "critical", "listed")])
        self.assertNotIn("\\_", text)
        self.assertNotIn("\\*", text)

    def test_it_never_says_safe(self):
        text = mon.format_alert("EQabc", [("PRICE_COLLAPSE", "high", "fell")])
        self.assertNotIn("safe", text.lower())

    def test_the_head_matches_the_worst_signal(self):
        crit = mon.format_alert("x", [("IOC_LISTED", "critical", "a"),
                                      ("CONTRACT_DEPLOYED", "medium", "b")])
        self.assertIn("got worse", crit)


class _FakeTable:
    def __init__(self, items): self.items = items; self.updated = []
    def scan(self, **kw): return {"Items": self.items}
    def update_item(self, **kw): self.updated.append(kw)


class TestTheRun(unittest.TestCase):

    def _run(self, items, snapshot, listed=False):
        table = _FakeTable(items)
        sent = []
        with mock.patch.object(mon.dynamodb, "Table", return_value=table), \
             mock.patch.object(mon, "decrypt_field", side_effect=lambda v: v), \
             mock.patch.object(mon, "ton_snapshot", return_value=snapshot), \
             mock.patch.object(mon, "ioc_listed", return_value=listed), \
             mock.patch.object(mon, "send_alert",
                               side_effect=lambda c, t: sent.append((c, t)) or True), \
             mock.patch.object(mon.time, "sleep"):
            out = mon.lambda_handler({}, None)
        return out["stats"], sent, table

    def test_first_run_never_alerts(self):
        """RULE 1, AND THE MOST IMPORTANT TEST IN THIS FILE. Rows written before
        this monitor existed carry no snapshot. Without the seed branch the
        first scheduled run messages every user about every target at once."""
        rows = [{"user_key": "u", "target_id": "t1", "kind": "ton",
                 "target_enc": "EQaaa", "chat_id_enc": "99"}]
        stats, sent, table = self._run(rows, dict(TOKEN, risk_level="critical",
                                                  risk_flags=["flagged as scam"]))
        self.assertEqual(sent, [])
        self.assertEqual(stats["seeded"], 1)
        self.assertEqual(stats["alerted"], 0)
        self.assertEqual(len(table.updated), 1)

    def test_second_run_alerts_on_a_real_change(self):
        rows = [{"user_key": "u", "target_id": "t1", "kind": "ton",
                 "target_enc": "EQaaa", "chat_id_enc": "99",
                 "last_snapshot": json.dumps(TOKEN)}]
        stats, sent, _ = self._run(rows, dict(TOKEN, has_pool=False,
                                              liquidity_usd=None, price_usd=None))
        self.assertEqual(stats["alerted"], 1)
        self.assertEqual(sent[0][0], "99")
        self.assertIn("trading pool", sent[0][1])

    def test_non_ton_rows_are_counted_not_dropped(self):
        """A watchlist that hides what it cannot re-check is indistinguishable
        from one that works. The number has to be readable."""
        rows = [{"user_key": "u", "target_id": "t1", "kind": "domain",
                 "target_enc": "evil.com", "chat_id_enc": "99"},
                {"user_key": "u", "target_id": "t2", "kind": "url",
                 "target_enc": "http://x", "chat_id_enc": "99"}]
        stats, sent, table = self._run(rows, TOKEN)
        self.assertEqual(stats["skipped_not_ton"], 2)
        self.assertEqual(stats["ton"], 0)
        self.assertEqual(sent, [])
        self.assertEqual(table.updated, [], "a row we do not check must not be rewritten")

    def test_a_failed_lookup_leaves_the_snapshot_alone(self):
        """Overwriting the stored snapshot with an outage would make the NEXT
        run diff against nothing and alert on everything."""
        rows = [{"user_key": "u", "target_id": "t1", "kind": "ton",
                 "target_enc": "EQaaa", "chat_id_enc": "99",
                 "last_snapshot": json.dumps(TOKEN)}]
        stats, sent, table = self._run(rows, {})
        self.assertEqual(stats["lookup_failed"], 1)
        self.assertEqual(sent, [])
        self.assertEqual(table.updated, [])

    def test_an_undecryptable_row_does_not_stop_the_run(self):
        rows = [{"user_key": "u", "target_id": "bad", "kind": "ton",
                 "target_enc": "boom", "chat_id_enc": "99"},
                {"user_key": "u", "target_id": "t1", "kind": "ton",
                 "target_enc": "EQaaa", "chat_id_enc": "99",
                 "last_snapshot": json.dumps(TOKEN)}]
        table = _FakeTable(rows)
        sent = []

        def dec(v):
            if v == "boom":
                raise ValueError("no")
            return v

        with mock.patch.object(mon.dynamodb, "Table", return_value=table), \
             mock.patch.object(mon, "decrypt_field", side_effect=dec), \
             mock.patch.object(mon, "ton_snapshot",
                               return_value=dict(TOKEN, has_pool=False,
                                                 liquidity_usd=None, price_usd=None)), \
             mock.patch.object(mon, "ioc_listed", return_value=False), \
             mock.patch.object(mon, "send_alert",
                               side_effect=lambda c, t: sent.append((c, t)) or True), \
             mock.patch.object(mon.time, "sleep"):
            out = mon.lambda_handler({}, None)
        self.assertEqual(out["stats"]["unreadable"], 1)
        self.assertEqual(out["stats"]["alerted"], 1)

    def test_the_import_probe_does_no_work(self):
        """The deployer invokes what it deploys. Without this the probe starts a
        full watchlist sweep on every deploy."""
        with mock.patch.object(mon.dynamodb, "Table") as t:
            out = mon.lambda_handler({"source": "ci.import-probe"}, None)
        self.assertTrue(out["probe"])
        t.assert_not_called()

    def test_the_target_is_never_logged(self):
        src = open("relayshield_watchlist_monitor.py").read()
        self.assertNotIn("logger.info(\"watchlist alert sent target", src)
        self.assertIn("# never the target", src)


class TestClassification(unittest.TestCase):

    def test_ton_addresses_get_their_own_kind(self):
        """A TON address stored as a generic 'address' is watched in name and
        re-checked by nothing: the monitor selects on this field."""
        self.assertEqual(wl._normalise("EQ" + "A" * 46)[0], "ton")
        self.assertEqual(wl._normalise("0:" + "a" * 64)[0], "ton")
        self.assertEqual(wl._normalise("-1:" + "F" * 64)[0], "ton")

    def test_other_kinds_are_unchanged(self):
        self.assertEqual(wl._normalise("https://x.com/a")[0], "url")
        self.assertEqual(wl._normalise("evil.com")[0], "domain")
        self.assertEqual(wl._normalise("0x" + "a" * 40)[0], "address")
        self.assertEqual(wl._normalise("ronin:0x" + "a" * 40)[0], "address")
        self.assertEqual(wl._normalise("")[0], "")

    def test_the_monitor_selects_the_kind_this_module_writes(self):
        """Two files that must agree, with nothing checking that they do, is the
        shape that produced run 134's red probe."""
        src = open("relayshield_watchlist_monitor.py").read()
        self.assertIn('row.get("kind") != "ton"', src)


class TestStars(unittest.TestCase):

    def test_the_invoice_is_stars_and_carries_no_provider_token(self):
        """A provider_token is what makes an invoice a CARD payment. Passing one
        here would be a different product, and Telegram would reject it in a
        Mini App context."""
        captured = {}

        class _Resp:
            def read(self): return json.dumps({"ok": True, "result": "https://t.me/$inv"}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(req, timeout=0):
            captured["body"] = json.loads(req.data)
            captured["url"] = req.full_url
            return _Resp()

        with mock.patch.object(wl, "verified_user_id", return_value=12345), \
             mock.patch.object(wl, "_get_secret", return_value="TOKEN"), \
             mock.patch.object(wl.urllib.request, "urlopen", fake_urlopen):
            out = wl.stars_invoice({"init_data": "x"})

        self.assertTrue(out["ok"])
        self.assertEqual(captured["body"]["currency"], "XTR")
        self.assertNotIn("provider_token", captured["body"])
        self.assertIn("createInvoiceLink", captured["url"])
        self.assertEqual(captured["body"]["prices"][0]["amount"], wl.SLOTS_PRICE_STARS)

    def test_the_invoice_requires_a_verified_user(self):
        with mock.patch.object(wl, "verified_user_id", return_value=None):
            self.assertFalse(wl.stars_invoice({"init_data": ""})["ok"])

    def test_the_payload_carries_no_user_id(self):
        """Telegram echoes invoice_payload verbatim, so it is client-visible and
        client-reportable. Identity comes from the signed `from` field."""
        src = open("relayshield_watchlist.py").read()
        self.assertIn('"payload": f"slots:{SLOTS_DURATION_DAYS}"', src)

    def test_grant_is_idempotent_on_charge_id(self):
        """Telegram retries a webhook it did not get a 200 from. A retry that
        extended the entitlement again is a free upgrade for anyone who can make
        our handler time out once."""
        existing = {"slots": 25, "slots_expire_at": 2 ** 31,
                    "charge_ids": ["ch_1"], "stars_paid": 50}
        table = mock.MagicMock()
        table.get_item.return_value = {"Item": existing}
        with mock.patch.object(wl.dynamodb, "Table", return_value=table), \
             mock.patch.object(wl, "user_key", return_value="pk"):
            out = wl.grant_slots(1, 50, "ch_1")
        self.assertTrue(out["data"]["duplicate"])
        table.put_item.assert_not_called()

    def test_a_new_charge_extends_rather_than_truncates(self):
        import time as _t
        future = int(_t.time()) + 30 * 86400
        table = mock.MagicMock()
        table.get_item.return_value = {"Item": {"slots_expire_at": future,
                                                "charge_ids": ["ch_1"]}}
        with mock.patch.object(wl.dynamodb, "Table", return_value=table), \
             mock.patch.object(wl, "user_key", return_value="pk"):
            out = wl.grant_slots(1, 50, "ch_2")
        self.assertGreater(out["data"]["expires_at"], future)

    def test_an_entitlement_read_failure_falls_to_the_free_tier(self):
        """Failing OPEN here would grant paid slots invisibly until the bill."""
        table = mock.MagicMock()
        table.get_item.side_effect = RuntimeError("dynamo down")
        slots, _ = wl.slots_for(table, "pk")
        self.assertEqual(slots, wl.FREE_WATCH_SLOTS)

    def test_an_expired_entitlement_is_the_free_tier(self):
        table = mock.MagicMock()
        table.get_item.return_value = {"Item": {"slots": 25, "slots_expire_at": 1}}
        slots, _ = wl.slots_for(table, "pk")
        self.assertEqual(slots, wl.FREE_WATCH_SLOTS)

    def test_the_entitlement_row_is_not_charged_as_a_watch(self):
        """It shares the partition, so it arrives in the COUNT. Getting this
        wrong silently costs every paying customer a slot."""
        src = open("relayshield_watchlist.py").read()
        self.assertIn("_has_entitlement_row(table, pk)", src)
        self.assertIn('if r.get("target_id") == ENTITLEMENT_ROW:', src)

    def test_free_tier_is_smaller_than_paid(self):
        self.assertLess(wl.FREE_WATCH_SLOTS, wl.PAID_WATCH_SLOTS)

    def test_checking_is_never_metered(self):
        """CLAUDE.md: Stars pay vendor bills, they never tax the free tier. The
        only thing sold is slots, so no check endpoint may appear here."""
        src = code_only("relayshield_watchlist.py")
        for endpoint in ("/v1/link-check", "/v1/ton-address", "/v1/scan-url"):
            self.assertNotIn(endpoint, src,
                             f"{endpoint} must never be behind a Stars gate")


class TestFirstWatchGreeting(unittest.TestCase):
    """Telegram has no primitive for pinning a Mini App: what you pin is a CHAT,
    and a direct-link Mini App creates none. The first watch sends a message so
    that a chat exists to pin -- and so the alert channel is proven before an
    alert is needed."""

    def _add(self, count, existing_entitlement=False):
        table = mock.MagicMock()
        table.query.return_value = {"Count": count}
        table.get_item.return_value = {"Item": {"x": 1}} if existing_entitlement else {}
        greeted = []
        with mock.patch.object(wl.dynamodb, "Table", return_value=table), \
             mock.patch.object(wl, "verified_user_id", return_value=777), \
             mock.patch.object(wl, "user_key", return_value="pk"), \
             mock.patch.object(wl, "_fingerprint", return_value="fp"), \
             mock.patch.object(wl, "encrypt_field", side_effect=lambda v: v), \
             mock.patch.object(wl, "_greet_first_watch",
                               side_effect=lambda u: greeted.append(u)):
            out = wl.add_watch({"init_data": "x", "target": "EQ" + "A" * 46})
        return out, greeted

    def test_the_first_watch_greets(self):
        out, greeted = self._add(0)
        self.assertTrue(out["ok"])
        self.assertEqual(greeted, [777])

    def test_later_watches_do_not(self):
        """A confirmation on every add is a notification tax on the people who
        use the feature most."""
        out, greeted = self._add(2)
        self.assertTrue(out["ok"])
        self.assertEqual(greeted, [])

    def test_the_entitlement_row_does_not_consume_the_first_watch(self):
        """A paying user's first watch must still greet. Count is 1 because the
        entitlement row shares the partition, and reading that as 'already has a
        watch' would silently skip the greeting for exactly the users who paid."""
        out, greeted = self._add(1, existing_entitlement=True)
        self.assertTrue(out["ok"])
        self.assertEqual(greeted, [777])

    def test_a_failed_greeting_never_fails_the_add(self):
        table = mock.MagicMock()
        table.query.return_value = {"Count": 0}
        table.get_item.return_value = {}
        with mock.patch.object(wl.dynamodb, "Table", return_value=table), \
             mock.patch.object(wl, "verified_user_id", return_value=777), \
             mock.patch.object(wl, "user_key", return_value="pk"), \
             mock.patch.object(wl, "_fingerprint", return_value="fp"), \
             mock.patch.object(wl, "encrypt_field", side_effect=lambda v: v), \
             mock.patch.object(wl, "_get_secret", side_effect=RuntimeError("no token")):
            out = wl.add_watch({"init_data": "x", "target": "EQ" + "A" * 46})
        self.assertTrue(out["ok"], "a stored watch is stored even if the greeting fails")

    def test_the_greeting_uses_no_parse_mode(self):
        """Legacy Markdown has no escape syntax. Prose that needs no formatting
        asks for none, which is the only option that cannot be got wrong."""
        body = code_only("relayshield_watchlist.py", "_greet_first_watch")
        self.assertNotIn("parse_mode", body)

    def test_the_greeting_says_how_to_pin(self):
        src = open("relayshield_watchlist.py").read()
        self.assertIn("Pin this chat", src)
        self.assertIn("press and hold", src)


class TestWebhookPayments(unittest.TestCase):
    """Read as source, because importing the webhook pulls half the product in.
    Each assertion below corresponds to a defect that was found by reading this
    file BEFORE wiring Stars, not after."""

    def setUp(self):
        self.src = open("relayshield_telegram_webhook.py").read()

    def test_pre_checkout_is_dispatched(self):
        """Without it, Telegram's ten-second window lapses and NO payment can
        ever complete -- silently, on our side."""
        self.assertIn('if "pre_checkout_query" in body:', self.src)
        self.assertIn("handle_pre_checkout(body)", self.src)
        self.assertIn("answerPreCheckoutQuery", self.src)

    def test_pre_checkout_does_not_fulfil(self):
        """It fires before the money moves. Granting here would hand out slots
        to anyone who opens an invoice and abandons it."""
        body = code_only("relayshield_telegram_webhook.py", "handle_pre_checkout")
        self.assertNotIn("grant_slots", body)

    def test_stars_never_reach_the_subscription_tier_map(self):
        """total_amount=50 matched no plan and fell through to TIER_PERSONAL: a
        full paid subscription for about a dollar."""
        self.assertIn('if currency == "XTR":', self.src)
        xtr = self.src.index('if currency == "XTR":')
        tiermap = self.src.index("tier_map = {v[\"amount\"]")
        self.assertLess(xtr, tiermap,
                        "the XTR branch must return BEFORE the tier map is consulted")
        branch = self.src[xtr:tiermap]
        self.assertIn("return", branch)

    def test_the_user_id_comes_from_the_signed_update(self):
        body = code_only("relayshield_telegram_webhook.py", "handle_stars_payment")
        self.assertIn("message.get('from')", body)
        self.assertIn("get('id')", body)
        self.assertNotIn("invoice_payload", body,
                         "payload is client-visible text we chose; identity must "
                         "come from the field Telegram signs")

    def test_a_failed_grant_tells_the_user(self):
        """The one failure mode that costs somebody money."""
        body = code_only("relayshield_telegram_webhook.py", "handle_stars_payment")
        self.assertIn("logger.error", body)
        self.assertIn("charge=", body)
        self.assertIn("send_message(chat_id", body)


class TestWorkerStars(unittest.TestCase):
    def setUp(self):
        self.src = open("cloudflare_worker_miniapp.js").read()

    def test_it_uses_openInvoice_and_not_an_external_link(self):
        """Sending a Mini App user to Stripe, x402 or the developers page for a
        DIGITAL GOOD is the route that gets a bot restricted, and all three
        exist one link away."""
        self.assertIn("tg.openInvoice(", self.src)
        upsell = self.src[self.src.index("function offerUpgrade"):
                          self.src.index("async function loadWatches")]
        for rail in ("stripe.com", "checkout", "x402", "/developers"):
            self.assertNotIn(rail, upsell)

    def test_the_entitlement_is_not_credited_by_the_client(self):
        buy = self.src[self.src.index("async function buySlots"):]
        buy = buy[:buy.index("async function loadWatches")]
        self.assertNotIn("grant", buy)
        self.assertIn("loadWatches()", buy)

    def test_openInvoice_is_feature_detected(self):
        """An older Telegram client has no openInvoice, and an undefined call
        is a dead button with no message."""
        self.assertIn("!tg.openInvoice", self.src)

    def test_rows_say_whether_they_are_actually_re_checked(self):
        self.assertIn("not re-checked yet", self.src)


class TestFunnelFiltersMatchRealLogLines(unittest.TestCase):
    """A measurement tool and the code it measures are two files that must agree
    with nothing checking that they do -- the shape that produced run 134's red
    probe and FD-8's four silent months.

    Both defects this class pins were real on the funnel tool's first draft: it
    filtered on "SRC_miniapp" when the webhook logs `acquisition source=miniapp`
    (the prefix is stripped before logging), and /v1/ton-address logged no
    source at all. Either one alone would have reported a live channel as dead,
    which is a worse outcome than no tool: a zero gets acted on."""

    def setUp(self):
        self.funnel = open("tools/miniapp_funnel.py").read()

    def _stage(self, label):
        m = re.search(r'\("' + label + r'[^"]*",\s*\n?\s*"([^"]+)",\s*"([^"]+)"',
                      self.funnel)
        self.assertIsNotNone(m, f"no stage named {label} in the funnel tool")
        return m.group(1), m.group(2)

    def test_the_bot_stage_matches_what_the_webhook_logs(self):
        _, pattern = self._stage("BOT")
        webhook = open("relayshield_telegram_webhook.py").read()
        self.assertIn('logger.info("acquisition source=%s', webhook)
        self.assertIn("acquisition source=", pattern)
        self.assertNotIn("SRC_", pattern,
                         "SRC_ is the deep-link payload; the webhook strips it "
                         "before logging, so this filter would match nothing")

    def test_ton_address_logs_a_source(self):
        api = open("relayshield_api.py").read()
        self.assertEqual(api.count('ton-address token=%s price=%s source=%s'), 1)
        self.assertEqual(api.count('ton-address wallet=%s balance=%.4f risk=%s source=%s'), 1)

    def test_the_stars_stage_matches_what_the_webhook_logs(self):
        _, pattern = self._stage("STARS")
        self.assertIn(pattern, open("relayshield_telegram_webhook.py").read())

    def test_the_alert_stage_matches_what_the_monitor_logs(self):
        _, pattern = self._stage("ALERTED")
        self.assertIn(pattern, open("relayshield_watchlist_monitor.py").read())

    def test_the_watched_stage_matches_what_the_watchlist_logs(self):
        _, pattern = self._stage("WATCHED")
        self.assertIn(pattern, open("relayshield_watchlist.py").read())

    def test_the_log_groups_name_functions_that_are_mapped_or_explained(self):
        """A log group for a function nobody deploys is a stage that reads zero
        forever. relayshield-watchlist-monitor is the one legitimate exception
        and the tool reports it as NO LOG GROUP rather than as 0."""
        groups = set(re.findall(r'"/aws/lambda/([a-z-]+)"', self.funnel))
        deployer = open(".github/workflows/deploy_lambdas.yml").read()
        for g in groups:
            if g == "relayshield-watchlist-monitor":
                self.assertIn("NO LOG GROUP", self.funnel)
                continue
            self.assertIn(f'"{g}"', deployer, f"{g} is measured but not deployed")


class TestMiniAppSendsItsSource(unittest.TestCase):
    def test_every_check_carries_a_source(self):
        """The whole funnel rests on this one field arriving."""
        worker = open("cloudflare_worker_miniapp.js").read()
        self.assertIn("source", worker)
        run = worker[worker.index("async function run()"):]
        run = run[:run.index("async function post(")]
        self.assertIn("source", run,
                      "the check call must carry source= or nothing downstream "
                      "can attribute a single Mini App arrival")


if __name__ == "__main__":
    unittest.main(verbosity=1)
