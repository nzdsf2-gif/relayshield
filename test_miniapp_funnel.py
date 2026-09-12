#!/usr/bin/env python3
"""Offline tests for tools/miniapp_funnel.py.

THE DEFECT THESE EXIST FOR. The tool printed its header and then nothing else,
twice, and was reported as producing "no reply". Nothing raised and no output
was lost: filter_log_events is a SCAN that keeps handing back a nextToken while
it walks log streams, so eight sweeps over 30 days of the busiest Lambda group
we have ran before a single number could be printed. A measurement tool that
cannot be told apart from a hung one is not a measurement tool.

There are no AWS credentials in the container, so the logs client is stubbed --
the same move test_miniapp.py makes with boto3 for the dispatcher. What is
proven here is the part that is ours: the query we build, the status we derive,
and that the counting still goes through the SAME Python regexes the stage
table declares, rather than a second copy written in Insights' parse syntax.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import miniapp_funnel as F  # noqa: E402


class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _FakeBotocoreExceptions:
    ClientError = FakeClientError


def _install_fake_botocore():
    """run_insights imports botocore lazily; there is no botocore here."""
    mod = type(sys)("botocore")
    exc = type(sys)("botocore.exceptions")
    exc.ClientError = FakeClientError
    mod.exceptions = exc
    sys.modules.setdefault("botocore", mod)
    sys.modules.setdefault("botocore.exceptions", exc)


_install_fake_botocore()
F.INSIGHTS_POLL_S = 0


class FakeLogs:
    """Answers start_query/get_query_results from a canned plan."""

    def __init__(self, plan, missing=(), fail=()):
        self.plan = plan            # {(group, 'stats'|'filter'): rows}
        self.missing = set(missing)
        self.fail = set(fail)
        self.queries = []           # every (group, queryString) issued
        self._pending = {}
        self._n = 0
        self.filter_log_events_calls = 0

    # The API the OLD version used. Nothing may call it.
    def filter_log_events(self, **kw):
        self.filter_log_events_calls += 1
        raise AssertionError("filter_log_events must not be used: it is the "
                             "scan that made this tool appear to hang.")

    def start_query(self, **kw):
        group, q = kw["logGroupName"], kw["queryString"]
        self.queries.append((group, q))
        if group in self.missing:
            raise FakeClientError("ResourceNotFoundException")
        self._n += 1
        qid = f"q{self._n}"
        kind = "stats" if q.startswith("stats") else "filter"
        self._pending[qid] = (group, kind, kw.get("limit"))
        return {"queryId": qid}

    def get_query_results(self, queryId):
        group, kind, limit = self._pending[queryId]
        if group in self.fail:
            return {"status": "Failed"}
        rows = self.plan.get((group, kind), [])
        results = [[{"field": k, "value": v} for k, v in row.items()]
                   for row in rows]
        matched = len(rows)
        if limit and len(results) > limit:
            results = results[:limit]
        return {"status": "Complete", "results": results,
                "statistics": {"recordsMatched": float(matched)}}

    def stop_query(self, queryId):
        return {}


def msgs(*texts):
    return [{"@message": t} for t in texts]


def stats_row(n, first_ms=1_700_000_000_000):
    return [{"n": str(n), "first_ms": str(first_ms)}]


GROUP = "/aws/lambda/relayshield-api"
RX = re.compile(r"source=(tg-miniapp[a-z-]*)")


class TestTheScanApiIsNeverUsed(unittest.TestCase):
    """The regression guard for the actual defect."""

    def test_no_call_site_mentions_filter_log_events(self):
        src = (ROOT / "tools" / "miniapp_funnel.py").read_text()
        code = "\n".join(l for l in src.split("\n")
                         if not l.lstrip().startswith("#"))
        # The prose above the helpers names it on purpose; code must not.
        self.assertNotIn("logs.filter_log_events", code)
        self.assertNotIn(".filter_log_events(", code)

    def test_pull_stage_issues_insights_queries_only(self):
        logs = FakeLogs({(GROUP, "stats"): stats_row(5),
                         (GROUP, "filter"): msgs("a source=tg-miniapp b")})
        F.pull_stage(logs, GROUP, "tg-miniapp", RX, 0, 1000, {})
        self.assertEqual(logs.filter_log_events_calls, 0)
        self.assertTrue(logs.queries)


class TestStatusesAreNotCollapsed(unittest.TestCase):
    def test_missing_group_is_not_zero(self):
        logs = FakeLogs({}, missing={GROUP})
        total, _c, _e, status = F.pull_stage(logs, GROUP, "x", RX, 0, 1, {})
        self.assertEqual(status, "NO LOG GROUP")
        self.assertEqual(total, 0)

    def test_an_idle_function_is_not_the_same_as_no_matches(self):
        logs = FakeLogs({(GROUP, "stats"): stats_row(0, 0)})
        _t, _c, _e, status = F.pull_stage(logs, GROUP, "x", RX, 0, 1, {})
        self.assertEqual(status, "NEVER INVOKED")

    def test_events_present_but_nothing_matched_is_zero(self):
        logs = FakeLogs({(GROUP, "stats"): stats_row(99),
                         (GROUP, "filter"): msgs("unrelated line")})
        total, _c, _e, status = F.pull_stage(logs, GROUP, "x", RX, 0, 1, {})
        self.assertEqual((total, status), (0, "ZERO"))

    def test_a_failed_query_is_not_zero(self):
        logs = FakeLogs({(GROUP, "stats"): stats_row(9)}, fail={GROUP})
        _t, _c, _e, status = F.pull_stage(logs, GROUP, "x", RX, 0, 1, {})
        self.assertEqual(status, "QUERY FAILED")

    def test_a_capped_result_reports_a_floor_and_says_so(self):
        F_limit = F.INSIGHTS_LIMIT
        F.INSIGHTS_LIMIT = 2
        try:
            logs = FakeLogs({(GROUP, "stats"): stats_row(50),
                             (GROUP, "filter"): msgs(
                                 "source=tg-miniapp", "source=tg-miniapp",
                                 "source=tg-miniapp")})
            total, _c, _e, status = F.pull_stage(logs, GROUP, "tg-miniapp",
                                                 RX, 0, 1, {})
            self.assertEqual(status, "CAPPED")
            self.assertEqual(total, 2)   # a floor, and rendered as ">=2"
        finally:
            F.INSIGHTS_LIMIT = F_limit


class TestCountingStillGoesThroughTheStageRegex(unittest.TestCase):
    """The reason the queries filter coarsely and match in Python."""

    def test_breakdown_comes_from_the_python_regex(self):
        logs = FakeLogs({(GROUP, "stats"): stats_row(10),
                         (GROUP, "filter"): msgs(
                             "check source=tg-miniapp-blog ok",
                             "check source=tg-miniapp-blog ok",
                             "check source=tg-miniapp ok",
                             "mentions tg-miniapp but carries no source")})
        total, counts, _e, status = F.pull_stage(
            logs, GROUP, "tg-miniapp", RX, 0, 1, {})
        self.assertEqual(status, "OK")
        self.assertEqual(total, 3)
        self.assertEqual(counts["tg-miniapp-blog"], 2)
        self.assertEqual(counts["tg-miniapp"], 1)

    def test_no_stage_regex_is_restated_as_an_insights_parse(self):
        """Two regexes that must agree is the shape that costs us false
        absences. There is exactly one copy and it is the stage table."""
        src = (ROOT / "tools" / "miniapp_funnel.py").read_text()
        self.assertNotIn("| parse ", src)
        self.assertNotIn("(?<", src)


class TestTheQueryWeBuild(unittest.TestCase):
    def test_the_filter_is_a_substring_predicate_on_the_pattern(self):
        logs = FakeLogs({(GROUP, "stats"): stats_row(3),
                         (GROUP, "filter"): []})
        F.pull_stage(logs, GROUP, "watchlist add", RX, 0, 1, {})
        built = [q for _g, q in logs.queries if q.startswith("fields")]
        self.assertEqual(built, ['fields @message | filter '
                                 '@message like "watchlist add"'])

    def test_route_queries_require_both_terms(self):
        keys = {"tg-miniapp-blog"}
        plan = {}
        for group, _p in F.ROUTE_SOURCES:
            plan[(group, "stats")] = stats_row(4)
            plan[(group, "filter")] = msgs("source=tg-miniapp-blog")
        logs = FakeLogs(plan)
        counts, unknown, reachable = F.pull_routes(logs, 0, 1, keys, {})
        self.assertTrue(reachable)
        self.assertEqual(counts["tg-miniapp-blog"], len(F.ROUTE_SOURCES))
        self.assertFalse(unknown)
        for _g, q in logs.queries:
            if q.startswith("fields"):
                self.assertIn(' and ', q)
                self.assertIn('like "tg-miniapp"', q)

    def test_an_unregistered_key_lands_in_unknown_not_in_counts(self):
        plan = {}
        for group, _p in F.ROUTE_SOURCES:
            plan[(group, "stats")] = stats_row(4)
            plan[(group, "filter")] = msgs("source=tg-miniapp-nowhere")
        logs = FakeLogs(plan)
        counts, unknown, _r = F.pull_routes(logs, 0, 1, {"tg-miniapp-blog"}, {})
        self.assertFalse(counts)
        self.assertEqual(unknown["tg-miniapp-nowhere"], len(F.ROUTE_SOURCES))

    def test_a_missing_route_group_makes_the_counts_incomplete(self):
        group0 = F.ROUTE_SOURCES[0][0]
        plan = {}
        for group, _p in F.ROUTE_SOURCES[1:]:
            plan[(group, "stats")] = stats_row(4)
            plan[(group, "filter")] = []
        logs = FakeLogs(plan, missing={group0})
        _c, _u, reachable = F.pull_routes(logs, 0, 1, {"tg-miniapp-blog"}, {})
        self.assertFalse(reachable)


class TestOneGroupIsProbedOnce(unittest.TestCase):
    def test_the_window_probe_is_cached_across_stages(self):
        logs = FakeLogs({(GROUP, "stats"): stats_row(7),
                         (GROUP, "filter"): []})
        cache = {}
        F.pull_stage(logs, GROUP, "a", RX, 0, 1, cache)
        F.pull_stage(logs, GROUP, "b", RX, 0, 1, cache)
        stats_queries = [q for _g, q in logs.queries if q.startswith("stats")]
        self.assertEqual(len(stats_queries), 1)

    def test_the_window_comes_from_the_group_not_the_filter(self):
        logs = FakeLogs({(GROUP, "stats"): stats_row(7, 1_699_000_000_000),
                         (GROUP, "filter"): []})
        _t, _c, earliest, status = F.pull_stage(logs, GROUP, "a", RX, 0, 1, {})
        self.assertEqual(status, "ZERO")
        self.assertEqual(earliest, 1_699_000_000_000)


class TestQuoting(unittest.TestCase):
    def test_a_quote_in_a_pattern_cannot_break_out_of_the_predicate(self):
        self.assertEqual(F._like('a"b'), '@message like "a\\"b"')
        self.assertEqual(F._like('a\\b'), '@message like "a\\\\b"')


if __name__ == "__main__":
    unittest.main(verbosity=2)
