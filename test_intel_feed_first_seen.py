"""relayshield_intel_feed.py -- first-seen recording for feed indicators (2026-10-20).

Only the Telegram monitor wrote relayshield_intel_first_seen, so it covered ~16K of
~724K indicators and the weekly report's "all-time" count read 256,779 against a
measured 723,810. The feed now notes each indicator in memory and flushes ONCE at
the end of the run. These pin the properties that matter:

  * OFF by default. Recording before tools/backfill_first_seen.py --apply has run
    stamps today's date on old indicators permanently (first writer wins).
  * No network per indicator: a first-seen write inside _write_ioc would double
    the cost of sources that already call it once per row inside a 900 s budget.
  * Fail open: a denied or throttled write must never stop collection.
  * A missing grant costs one warning, not tens of thousands of failing calls.
"""
import ast
import os
import pathlib
import sys
import types
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent


def _stub_boto3():
    boto3 = types.ModuleType("boto3")
    boto3.resource = lambda *a, **k: unittest.mock.MagicMock()
    boto3.client = lambda *a, **k: unittest.mock.MagicMock()
    sys.modules.setdefault("boto3", boto3)


_stub_boto3()
sys.path.insert(0, str(ROOT))
import relayshield_intel_feed as feed  # noqa: E402


class ConditionalCheckFailedException(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class AccessDeniedException(Exception):
    response = {"Error": {"Code": "AccessDeniedException"}}


class _Client:
    """Records every put_item; `behaviour(value)` may raise to simulate AWS."""

    def __init__(self, behaviour=None):
        self.calls = []
        self.behaviour = behaviour or (lambda value: None)

    def put_item(self, **kw):
        self.calls.append(kw)
        self.behaviour(kw["Item"]["ioc_value"])


class _Ctx:
    def __init__(self, seconds):
        self._s = seconds

    def get_remaining_time_in_millis(self):
        return int(self._s * 1000)


class _Table:
    """Just enough of a Table for _write_ioc and _batch_write_iocs."""

    def __init__(self, fail_batch=False):
        self.puts, self.fail_batch = [], fail_batch

    def put_item(self, Item, ConditionExpression=None):
        self.puts.append(Item)

    def batch_writer(self):
        table = self

        class _W:
            def __enter__(self):
                return self

            def put_item(self, Item):
                table.puts.append(Item)

            def __exit__(self, *a):
                if table.fail_batch:
                    raise RuntimeError("batch flush failed")
                return False
        return _W()


class Base(unittest.TestCase):
    def setUp(self):
        feed._FIRST_SEEN_PENDING.clear()
        self._env = unittest.mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(feed.FIRST_SEEN_FLAG, None)
        self.client = _Client()
        self._ddb = unittest.mock.patch.object(
            feed, "_dynamodb", types.SimpleNamespace(
                meta=types.SimpleNamespace(client=self.client)))
        self._ddb.start()

    def tearDown(self):
        self._ddb.stop()
        self._env.stop()
        feed._FIRST_SEEN_PENDING.clear()

    def on(self):
        os.environ[feed.FIRST_SEEN_FLAG] = "1"


class OffByDefault(Base):
    def test_flag_is_off_without_the_variable(self):
        self.assertFalse(feed._first_seen_enabled())

    def test_only_the_exact_value_one_turns_it_on(self):
        for bad in ("0", "true", "yes", ""):
            os.environ[feed.FIRST_SEEN_FLAG] = bad
            self.assertFalse(feed._first_seen_enabled(), bad)
        self.on()
        self.assertTrue(feed._first_seen_enabled())

    def test_writes_still_work_and_nothing_is_noted_when_off(self):
        table = _Table()
        self.assertTrue(feed._write_ioc(table, "Evil.Example", "domain", "urlhaus"))
        feed._batch_write_iocs(table, [("1.2.3.4", "ip", "ipsum", "")])
        self.assertEqual(len(table.puts), 2)
        self.assertEqual(feed._FIRST_SEEN_PENDING, {})
        self.assertEqual(feed._flush_first_seen(None)["pending"], 0)
        self.assertEqual(self.client.calls, [])


class Noting(Base):
    def test_write_ioc_notes_the_stored_lowercase_value_and_source(self):
        self.on()
        feed._write_ioc(_Table(), "Evil.Example", "domain", "urlhaus")
        self.assertIn("evil.example", feed._FIRST_SEEN_PENDING)
        self.assertEqual(feed._FIRST_SEEN_PENDING["evil.example"][0], "urlhaus")

    def test_batch_notes_each_distinct_value_once(self):
        self.on()
        feed._batch_write_iocs(_Table(), [
            ("1.1.1.1", "ip", "ipsum", ""), (" 1.1.1.1 ", "ip", "ipsum", ""),
            ("2.2.2.2", "ip", "ipsum", "")])
        self.assertEqual(set(feed._FIRST_SEEN_PENDING), {"1.1.1.1", "2.2.2.2"})

    def test_a_failed_batch_flush_notes_nothing(self):
        self.on()
        feed._batch_write_iocs(_Table(fail_batch=True),
                               [("1.1.1.1", "ip", "ipsum", "")])
        self.assertEqual(feed._FIRST_SEEN_PENDING, {})

    def test_noting_does_no_network_io(self):
        self.on()
        for n in range(500):
            feed._write_ioc(_Table(), f"h{n}.example", "domain", "x")
        self.assertEqual(self.client.calls, [])
        self.assertEqual(len(feed._FIRST_SEEN_PENDING), 500)


class Flush(Base):
    def test_one_conditional_put_per_indicator_with_the_right_shape(self):
        self.on()
        feed._write_ioc(_Table(), "a.example", "domain", "threatfox")
        stats = feed._flush_first_seen(None)
        self.assertEqual((stats["new"], stats["known"], stats["skipped"]), (1, 0, 0))
        call = self.client.calls[0]
        self.assertEqual(call["TableName"], "relayshield_intel_first_seen")
        self.assertEqual(call["ConditionExpression"],
                         "attribute_not_exists(ioc_value)")
        self.assertEqual(call["Item"]["ioc_value"], "a.example")
        self.assertEqual(call["Item"]["first_channel"], "threatfox")
        self.assertEqual(call["Item"]["first_category"], "threat_feed")
        self.assertTrue(call["Item"]["first_seen"].startswith("20"))

    def test_an_already_known_indicator_is_counted_known_not_new(self):
        self.on()

        def behaviour(value):
            if value.startswith("old"):
                raise ConditionalCheckFailedException()
        self.client.behaviour = behaviour
        for v in ("old1.example", "old2.example", "new1.example"):
            feed._write_ioc(_Table(), v, "domain", "x")
        stats = feed._flush_first_seen(None)
        self.assertEqual((stats["new"], stats["known"]), (1, 2))
        self.assertEqual(stats["error"], "")

    def test_every_indicator_is_attempted_across_the_workers(self):
        self.on()
        for n in range(200):
            feed._write_ioc(_Table(), f"h{n}.example", "domain", "x")
        stats = feed._flush_first_seen(None)
        self.assertEqual(stats["new"], 200)
        self.assertEqual(len({c["Item"]["ioc_value"] for c in self.client.calls}), 200)

    def test_the_pending_set_is_emptied_by_a_flush(self):
        self.on()
        feed._write_ioc(_Table(), "a.example", "domain", "x")
        feed._flush_first_seen(None)
        self.assertEqual(feed._FIRST_SEEN_PENDING, {})

    def test_access_denied_stops_the_flush_and_names_the_remedy(self):
        self.on()

        def behaviour(value):
            raise AccessDeniedException()
        self.client.behaviour = behaviour
        for n in range(2000):
            feed._write_ioc(_Table(), f"h{n}.example", "domain", "x")
        stats = feed._flush_first_seen(None)
        self.assertIn("dynamodb:PutItem", stats["error"])
        self.assertIn("relayshield_intel_first_seen", stats["error"])
        self.assertEqual(stats["new"], 0)
        # one denial per worker at most, never one per indicator
        self.assertLessEqual(len(self.client.calls), feed.FIRST_SEEN_WORKERS * 2)
        self.assertEqual(stats["skipped"], 2000 - 0 - stats["known"])

    def test_any_other_failure_is_swallowed_and_reported(self):
        self.on()

        def behaviour(value):
            raise RuntimeError("throttled")
        self.client.behaviour = behaviour
        feed._write_ioc(_Table(), "a.example", "domain", "x")
        stats = feed._flush_first_seen(None)      # must not raise
        self.assertEqual(stats["error"], "RuntimeError")
        self.assertEqual(stats["skipped"], 1)

    def test_no_lambda_time_left_skips_everything_without_a_call(self):
        self.on()
        for n in range(10):
            feed._write_ioc(_Table(), f"h{n}.example", "domain", "x")
        stats = feed._flush_first_seen(_Ctx(feed.FIRST_SEEN_RESERVE_S - 1))
        self.assertEqual(stats["skipped"], 10)
        self.assertEqual(self.client.calls, [])
        self.assertIn("no Lambda time", stats["error"])

    def test_it_runs_when_there_is_time(self):
        self.on()
        feed._write_ioc(_Table(), "a.example", "domain", "x")
        stats = feed._flush_first_seen(_Ctx(600))
        self.assertEqual(stats["new"], 1)


class HandlerWiring(unittest.TestCase):
    def _handler(self):
        tree = ast.parse((ROOT / "relayshield_intel_feed.py").read_text())
        return next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "lambda_handler")

    def test_pending_is_cleared_at_the_start_of_every_invocation(self):
        """A warm container keeps module state, so a leftover set from a failed
        run would be flushed into the next one."""
        src = ast.get_source_segment(
            (ROOT / "relayshield_intel_feed.py").read_text(), self._handler())
        self.assertIn("_FIRST_SEEN_PENDING.clear()", src)
        self.assertLess(src.index("_FIRST_SEEN_PENDING.clear()"),
                        src.index("_ingest_threatfox"))

    def test_the_flush_runs_after_ingestion_and_with_the_context(self):
        src = ast.get_source_segment(
            (ROOT / "relayshield_intel_feed.py").read_text(), self._handler())
        self.assertIn("_flush_first_seen(context)", src)
        self.assertGreater(src.index("_flush_first_seen(context)"),
                           src.index("_ingest_paste_sites"))

    def test_the_result_carries_the_first_seen_stats(self):
        src = ast.get_source_segment(
            (ROOT / "relayshield_intel_feed.py").read_text(), self._handler())
        self.assertIn('"first_seen":', src)


if __name__ == "__main__":
    unittest.main()
