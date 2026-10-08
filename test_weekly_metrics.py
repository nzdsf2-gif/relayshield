"""relayshield_weekly_metrics.py -- the metrics added 2026-09-28: the
active-marketplace count, the all-time DISTINCT indicator count, and the
CS Mobile trial/activation breakdown by distribution platform.

Both are new definitions layered onto an existing report, and both are the
kind of thing this repo has gotten wrong before (a sightings count wearing an
indicators label, a filter that silently matches nothing). So these are
EXECUTED against a fake DynamoDB that actually applies the filter expression,
not just asserted by reading the source -- a stub that answers every scan the
same way regardless of the filter would pass on a broken filter exactly the
way test_muse_connector_features.py's own MagicMock defect did.

relayshield_weekly_metrics.py has no existing test suite (confirmed by grep
before writing this) and this file does not attempt full coverage of it --
only the two new functions, their wiring into lambda_handler's metrics dict,
and that _build_email renders them.
"""
import ast
import pathlib
import sys
import types
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent


class _FakeAttr:
    """A real predicate, not a MagicMock -- so a filter that doesn't actually
    filter shows up as a wrong COUNT, not as "the mock didn't complain"."""

    def __init__(self, name):
        self.name = name

    def eq(self, value):
        name, val = self.name, value
        return lambda item: item.get(name) == val

    def gte(self, value):
        name, val = self.name, value
        return lambda item: (item.get(name) or "") >= val


def _stub_aws():
    boto3 = types.ModuleType("boto3"); boto3.__path__ = []
    boto3.resource = lambda *a, **k: unittest.mock.MagicMock()
    boto3.client = lambda *a, **k: unittest.mock.MagicMock()
    conditions = types.ModuleType("boto3.dynamodb.conditions")
    conditions.Attr = _FakeAttr
    conditions.Key = lambda *a, **k: unittest.mock.MagicMock()
    dynamodb_mod = types.ModuleType("boto3.dynamodb"); dynamodb_mod.__path__ = []
    dynamodb_mod.conditions = conditions
    boto3.dynamodb = dynamodb_mod
    sess = types.ModuleType("boto3.session")
    sys.modules.setdefault("boto3", boto3)
    sys.modules.setdefault("boto3.dynamodb", dynamodb_mod)
    sys.modules.setdefault("boto3.dynamodb.conditions", conditions)
    sys.modules.setdefault("boto3.session", sess)
    bc = types.ModuleType("botocore"); bc.__path__ = []
    ex = types.ModuleType("botocore.exceptions")

    class _CE(Exception):
        pass

    ex.ClientError = _CE; ex.BotoCoreError = _CE; bc.exceptions = ex
    sys.modules.setdefault("botocore", bc)
    sys.modules.setdefault("botocore.exceptions", ex)


_stub_aws()
sys.path.insert(0, str(ROOT))
import relayshield_weekly_metrics as wm  # noqa: E402


class _FakeTable:
    """Paginates in fixed-size pages regardless of Select, so pagination is
    exercised on every call rather than only when a test asks for it."""

    PAGE_SIZE = 2

    def __init__(self, items):
        self.items = items

    def scan(self, FilterExpression=None, Select=None, ExclusiveStartKey=None,
              **kwargs):
        matched = [i for i in self.items
                   if FilterExpression is None or FilterExpression(i)]
        start = (ExclusiveStartKey or {}).get("offset", 0)
        page = matched[start:start + self.PAGE_SIZE]
        result = {"Count": len(page)}
        if start + self.PAGE_SIZE < len(matched):
            result["LastEvaluatedKey"] = {"offset": start + self.PAGE_SIZE}
        return result


class _FakeDynamo:
    def __init__(self, tables: dict):
        self._tables = tables

    def Table(self, name):
        return self._tables.get(name, _FakeTable([]))


class FilteredCount(unittest.TestCase):
    def test_paginates_across_multiple_pages(self):
        wm.dynamodb = _FakeDynamo({
            "t": _FakeTable([{"active": True} for _ in range(5)]),
        })
        self.assertEqual(wm._filtered_count("t", wm.Attr("active").eq(True)), 5)

    def test_filter_actually_excludes_non_matching_rows(self):
        items = [{"active": True}] * 3 + [{"active": False}] * 7
        wm.dynamodb = _FakeDynamo({"c": _FakeTable(items)})
        self.assertEqual(
            wm._filtered_count("c", wm.Attr("active").eq(True)), 3)


class MonitoredMarketplaces(unittest.TestCase):
    def test_counts_only_active_channels(self):
        items = [{"active": True, "username": "a"},
                  {"active": True, "username": "b"},
                  {"active": False, "username": "c"}]
        wm.dynamodb = _FakeDynamo({"relayshield_intel_channels": _FakeTable(items)})
        self.assertEqual(wm._monitored_marketplaces(), 2)

    def test_reads_from_intel_channels_table_specifically(self):
        # A different table under the same name with 0 active rows must not
        # silently read from the channels table and report a stale number.
        wm.dynamodb = _FakeDynamo({
            "relayshield_intel_channels": _FakeTable([]),
            "some_other_table": _FakeTable([{"active": True}] * 50),
        })
        self.assertEqual(wm._monitored_marketplaces(), 0)


class UniqueIndicators(unittest.TestCase):
    def test_is_the_row_count_of_first_seen_not_iocs(self):
        # relayshield_intel_iocs has 5x the rows (sightings) that
        # relayshield_intel_first_seen has (distinct indicators) -- the exact
        # shape of the defect this function exists to avoid repeating.
        wm.dynamodb = _FakeDynamo({
            "relayshield_intel_first_seen": _FakeTable([{"ioc_value": "x"}] * 4),
            "relayshield_intel_iocs":       _FakeTable([{"ioc_value": "x"}] * 20),
        })
        self.assertEqual(wm._unique_indicators(), 4)


class NewUniqueIndicators(unittest.TestCase):
    def test_counts_only_indicators_first_seen_inside_the_window(self):
        old = "2026-01-01T00:00:00+00:00"
        new = wm.datetime.now(wm.timezone.utc).isoformat()
        wm.dynamodb = _FakeDynamo({
            "relayshield_intel_first_seen": _FakeTable(
                [{"ioc_value": "a", "first_seen": old}] * 5
                + [{"ioc_value": "b", "first_seen": new}] * 3),
        })
        self.assertEqual(wm._unique_indicators(), 8)
        self.assertEqual(wm._new_unique_indicators(), 3)

    def test_reads_first_seen_not_the_sightings_table(self):
        new = wm.datetime.now(wm.timezone.utc).isoformat()
        wm.dynamodb = _FakeDynamo({
            "relayshield_intel_first_seen": _FakeTable([{"first_seen": new}] * 2),
            "relayshield_intel_iocs": _FakeTable([{"first_seen": new}] * 50),
        })
        self.assertEqual(wm._new_unique_indicators(), 2)


class LambdaHandlerWiring(unittest.TestCase):
    """Read-only check that the metrics dict built inside lambda_handler
    actually calls the two new functions, via ast rather than by running the
    full handler (which needs Stripe, SES and a dozen other tables stubbed).
    A dispatcher-registration gap is invisible to a suite that only tests the
    functions in isolation, per this repo's own recorded lesson."""

    def test_metrics_dict_wires_both_new_fields(self):
        src = pathlib.Path(ROOT / "relayshield_weekly_metrics.py").read_text()
        tree = ast.parse(src)
        handler = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "lambda_handler")
        dict_keys_to_calls = {}
        for node in ast.walk(handler):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if (isinstance(k, ast.Constant) and isinstance(v, ast.Call)
                            and isinstance(v.func, ast.Name)):
                        dict_keys_to_calls[k.value] = v.func.id
        self.assertEqual(dict_keys_to_calls.get("monitored_marketplaces"),
                          "_monitored_marketplaces")
        self.assertEqual(dict_keys_to_calls.get("unique_indicators"),
                          "_unique_indicators")
        self.assertEqual(dict_keys_to_calls.get("unique_indicators_new"),
                          "_new_unique_indicators")


class CheckoutPlatformTag(unittest.TestCase):
    """_checkout_platform_tag reads a Checkout Session's client_reference_id
    back via the subscription it created -- added 2026-09-28 alongside the
    ?client_reference_id=solana tag on the Payment Link URLs in
    PaywallScreen.tsx. urlopen is stubbed directly since this hits Stripe,
    not DynamoDB."""

    def _stub_stripe(self, sessions: list):
        import json as _json

        class _Resp:
            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _fake_urlopen(req, timeout=10):
            return _Resp(_json.dumps({"data": sessions}).encode())

        wm.urllib.request.urlopen = _fake_urlopen

    def test_reads_the_tag_off_the_originating_session(self):
        self._stub_stripe([{"client_reference_id": "solana"}])
        self.assertEqual(wm._checkout_platform_tag("sub_1", "sk_test"), "solana")

    def test_a_subscription_with_no_session_is_unattributed(self):
        self._stub_stripe([])
        self.assertEqual(wm._checkout_platform_tag("sub_1", "sk_test"), "unattributed")

    def test_a_session_with_no_reference_id_is_unattributed(self):
        # Every subscription created before the tag shipped -- which today is
        # all of them, since the tagged build has not reached a device yet.
        self._stub_stripe([{"client_reference_id": None}])
        self.assertEqual(wm._checkout_platform_tag("sub_1", "sk_test"), "unattributed")


class ByPlatform(unittest.TestCase):
    def test_empty_dict_renders_a_dash_not_a_crash(self):
        self.assertEqual(wm._by_platform({}), "-")

    def test_renders_every_platform_present(self):
        out = wm._by_platform({"solana": 2, "unattributed": 1})
        self.assertIn("solana: 2", out)
        self.assertIn("unattributed: 1", out)


class EmailRendering(unittest.TestCase):
    def _fixture(self, **overrides):
        base = {
            "users_total": 1, "users_new": 0,
            "users_by_channel": {"whatsapp": 1, "telegram": 0, "unknown": 0},
            "telemetry": {f"{pre}_{suf}": 0
                           for pre in ("chrome_installs", "miniapp_opens", "checkemail_users")
                           for suf in ("unique", "total", "new_week")},
            "monitored_emails": 1, "monitored_emails_new": 0,
            "api_keys": {"total": 1, "new_this_week": 0, "intel_enabled": 0,
                          "intel_calls_period": 0,
                          "by_source": {"direct": 1, "n8n": 0, "tines": 0,
                                        "hf-smolagents": 0},
                          "by_source_week": {}, "apify_total": 0, "apify_week": 0,
                          "unmatched_sources": {}},
            "meter_calls": {},
            "breach_alerts_total": 0, "breach_alerts_new": 0,
            "sim_alerts_total": 0, "sim_alerts_new": 0,
            "intel_alerts_total": 0, "intel_alerts_new": 0,
            "monitored_marketplaces": 115,
            "unique_indicators": 512345,
            "unique_indicators_new": 4321,
            "ioc_total": 7602575,
            "stolen_sessions": 0, "identity_graph": 0, "ransomware_victims": 0,
            "stripe": {"active_subscriptions": 0, "mrr_usd": 0.0,
                        "mrr_by_source": {"direct": 0.0, "n8n": 0.0,
                                          "tines": 0.0, "hf-smolagents": 0.0}},
            "ytd_revenue": 0.0,
            "x402": {"total_calls": 0, "calls_this_week": 0, "total_revenue": 0,
                      "revenue_this_week": 0, "top_endpoints": []},
            "hf_mcp": {"total_calls": 0, "calls_this_week": 0, "total_revenue": 0,
                        "revenue_this_week": 0, "by_endpoint": []},
            "aws_marketplace": {"activations_month": 0, "activations_ytd": 0,
                                  "active_total": 0, "revenue_month_est": 0,
                                  "revenue_ytd_est": 0},
            "cs_mobile_stats": {"activations_month": 0, "activations_ytd": 0,
                                  "revenue_month": 0.0, "revenue_ytd": 0.0,
                                  "trials_started_week": 0, "trials_active": 0,
                                  "trials_converted": 0, "trials_lapsed": 0,
                                  "trial_conversion_pct": None,
                                  "activations_month_by_platform": {"solana": 1},
                                  "trials_started_week_by_platform": {"solana": 1,
                                                                        "unattributed": 1}},
            "cs_mobile_feedback": {"total": 0, "up": 0, "down": 0,
                                     "pct_positive": None,
                                     "testimonial_candidates": []},
            "lambda_health": {"errored": [], "silent": [], "total": 0},
        }
        base.update(overrides)
        return base

    def test_renders_both_new_rows_with_their_values(self):
        html = wm._build_email(self._fixture())
        self.assertIn("Monitored Telegram marketplaces", html)
        self.assertIn("115", html)
        self.assertIn("Unique indicators", html)
        self.assertIn("512,345", html)

    def test_renders_cumulative_and_weekly_increment_together(self):
        html = wm._build_email(self._fixture())
        self.assertIn("cumulative", html)
        self.assertIn("512,345", html)
        self.assertIn("+4,321", html)

    def test_does_not_drop_the_existing_sightings_row(self):
        # The pre-existing ioc_total row must survive relabeling, not be
        # silently removed in favor of the new distinct count.
        html = wm._build_email(self._fixture())
        self.assertIn("7,602,575", html)

    def test_renders_the_platform_breakdown_for_trials(self):
        html = wm._build_email(self._fixture())
        self.assertIn("solana: 1", html)
        self.assertIn("unattributed: 1", html)


class TelemetryStats(unittest.TestCase):
    """_telemetry_stats executed against a fake table, so the first-seen logic
    is checked by what it returns, not by what the source looks like."""

    class _Table:
        def __init__(self, items):
            self.items = items

        def scan(self, ProjectionExpression=None, ExclusiveStartKey=None, **kw):
            start = (ExclusiveStartKey or {}).get("o", 0)
            page = self.items[start:start + 2]
            out = {"Items": page}
            if start + 2 < len(self.items):
                out["LastEvaluatedKey"] = {"o": start + 2}
            return out

    def _run(self, items):
        fake = _FakeDynamo({"relayshield_telemetry": self._Table(items)})
        with unittest.mock.patch.object(wm, "dynamodb", fake):
            return wm._telemetry_stats()

    @staticmethod
    def _ts(days_ago):
        from datetime import datetime, timedelta, timezone
        return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()

    def test_new_means_first_seen_this_week_not_seen_this_week(self):
        items = [
            {"event_type": "checkemail_use", "client_hash": "old", "created_at": self._ts(30)},
            {"event_type": "checkemail_use", "client_hash": "old", "created_at": self._ts(1)},
            {"event_type": "checkemail_use", "client_hash": "new", "created_at": self._ts(2)},
        ]
        st = self._run(items)
        self.assertEqual(st["checkemail_users_unique"], 2)
        self.assertEqual(st["checkemail_users_total"], 3)
        self.assertEqual(st["checkemail_users_new_week"], 1)

    def test_order_of_rows_does_not_change_who_is_new(self):
        a = {"event_type": "checkemail_use", "client_hash": "x", "created_at": self._ts(1)}
        b = {"event_type": "checkemail_use", "client_hash": "x", "created_at": self._ts(40)}
        self.assertEqual(self._run([a, b])["checkemail_users_new_week"], 0)
        self.assertEqual(self._run([b, a])["checkemail_users_new_week"], 0)

    def test_event_types_are_counted_separately(self):
        items = [
            {"event_type": "checkemail_use", "client_hash": "h", "created_at": self._ts(1)},
            {"event_type": "chrome_install", "client_hash": "h", "created_at": self._ts(1)},
            {"event_type": "miniapp_open", "client_hash": "h", "created_at": self._ts(40)},
            {"event_type": "unknown_event", "client_hash": "h", "created_at": self._ts(1)},
        ]
        st = self._run(items)
        self.assertEqual(st["checkemail_users_unique"], 1)
        self.assertEqual(st["chrome_installs_new_week"], 1)
        self.assertEqual(st["miniapp_opens_new_week"], 0)

    def test_a_ping_with_no_hash_counts_toward_total_only(self):
        st = self._run([{"event_type": "checkemail_use", "created_at": self._ts(1)}])
        self.assertEqual(st["checkemail_users_total"], 1)
        self.assertEqual(st["checkemail_users_unique"], 0)
        self.assertEqual(st["checkemail_users_new_week"], 0)

    def test_a_missing_timestamp_is_not_new(self):
        st = self._run([{"event_type": "checkemail_use", "client_hash": "h"}])
        self.assertEqual(st["checkemail_users_unique"], 1)
        self.assertEqual(st["checkemail_users_new_week"], 0)

    def test_an_unreadable_table_yields_zeros_not_a_crash(self):
        class Boom:
            def Table(self, n):
                raise RuntimeError("no table")
        with unittest.mock.patch.object(wm, "dynamodb", Boom()):
            st = wm._telemetry_stats()
        self.assertEqual(st["checkemail_users_unique"], 0)
        self.assertIn("checkemail_users_new_week", st)

    def test_the_email_renders_the_checker_rows(self):
        er = EmailRendering()
        fx = er._fixture()
        fx["telemetry"]["checkemail_users_unique"] = 7
        fx["telemetry"]["checkemail_users_new_week"] = 3
        html = wm._build_email(fx)
        self.assertIn("Email checker users (unique)", html)
        self.assertRegex(html, r"Email checker users \(unique\)</td><td><b>7<")
        self.assertRegex(html, r"Email checker users \(new this week\)</td><td><b>3<")


class TelemetryWiring(unittest.TestCase):
    def test_the_lambda_accepts_the_event_the_worker_sends(self):
        import re
        tele = (ROOT / "relayshield_telemetry.py").read_text()
        worker = (ROOT / "cloudflare_worker_checkemail.js").read_text()
        sent = re.search(r'event_type:\s*"([a-z_]+)"', worker).group(1)
        self.assertEqual(sent, "checkemail_use")
        m = re.search(r"VALID_EVENTS\s*=\s*\{([^}]*)\}", tele)
        self.assertIn(f'"{sent}"', m.group(1))

    def test_every_valid_event_is_reported_on(self):
        import re
        tele = (ROOT / "relayshield_telemetry.py").read_text()
        m = re.search(r"VALID_EVENTS\s*=\s*\{([^}]*)\}", tele)
        valid = set(re.findall(r'"([a-z_]+)"', m.group(1)))
        self.assertEqual(valid, set(wm.TELEMETRY_EVENTS))

    def test_the_worker_never_sends_the_address(self):
        import re
        worker = (ROOT / "cloudflare_worker_checkemail.js").read_text()
        worker = re.sub(r"/\*.*?\*/", "", worker, flags=re.S)
        worker = re.sub(r"(?m)^\s*//.*$", "", worker)
        body = re.search(r"async function recordUse.*?\n}\n", worker, re.S).group(0)
        self.assertIn("senderHash(sender", body)
        self.assertNotRegex(body, r"JSON\.stringify\(\{[^}]*\bsender\b")

    def test_the_ping_is_skipped_for_exempt_senders_and_is_fail_open(self):
        import re
        worker = (ROOT / "cloudflare_worker_checkemail.js").read_text()
        worker = re.sub(r"/\*.*?\*/", "", worker, flags=re.S)
        worker = re.sub(r"(?m)^\s*//.*$", "", worker)
        self.assertIn("if (!exempt && ctx && ctx.waitUntil) ctx.waitUntil(recordUse(sender, env));", worker)
        body = re.search(r"async function recordUse.*?\n}\n", worker, re.S).group(0)
        self.assertIn("catch", body)

    def test_the_ping_precedes_the_rate_limit_so_limited_users_still_count(self):
        import re
        worker = (ROOT / "cloudflare_worker_checkemail.js").read_text()
        worker = re.sub(r"/\*.*?\*/", "", worker, flags=re.S)
        worker = re.sub(r"(?m)^\s*//.*$", "", worker)
        self.assertLess(worker.index("ctx.waitUntil(recordUse(sender, env))"),
                        worker.index("await rateLimited(env.CHECKEMAIL_RL, sender)"))


if __name__ == "__main__":
    unittest.main()
