"""tools/backfill_first_seen.py -- the apply path, executed against stubbed boto3.

2026-10-12: the table held 255,597 of roughly 687,000 indicators because an
earlier sequential, silent --apply was interrupted, and the weekly report printed
that partial count as the all-time total. These tests pin the properties that make
a re-run complete the table: writes are conditional (never overwrite), a row that
already exists is skipped rather than failed, and a real failure is counted and
makes the exit status non-zero."""
import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


class _CondFail(Exception):
    pass


_CondFail.__name__ = "ConditionalCheckFailedException"


class _Resource:
    def __init__(self, rows):
        self.rows = rows

    def Table(self, name):
        rows = self.rows

        class T:
            def scan(self, **kw):
                return {"Items": rows}
        return T()


class _Client:
    def __init__(self, existing=(), boom=()):
        self.existing, self.boom, self.puts = set(existing), set(boom), []

    def put_item(self, TableName, Item, ConditionExpression):
        v = Item["ioc_value"]["S"]
        assert ConditionExpression == "attribute_not_exists(ioc_value)"
        assert TableName == "relayshield_intel_first_seen"
        if v in self.boom:
            raise RuntimeError("throttled")
        if v in self.existing:
            raise _CondFail()
        self.existing.add(v)
        self.puts.append(Item)


def _run(rows, client, argv):
    boto3 = types.ModuleType("boto3")
    boto3.resource = lambda *a, **k: _Resource(rows)
    boto3.client = lambda *a, **k: client
    bc = types.ModuleType("botocore"); bc.__path__ = []
    cfg = types.ModuleType("botocore.config"); cfg.Config = lambda **k: None
    saved = {k: sys.modules.get(k) for k in ("boto3", "botocore", "botocore.config")}
    sys.modules.update({"boto3": boto3, "botocore": bc, "botocore.config": cfg})
    old_argv = sys.argv
    sys.argv = ["backfill"] + argv
    try:
        spec = importlib.util.spec_from_file_location("bf", ROOT / "tools" / "backfill_first_seen.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.main()
    finally:
        sys.argv = old_argv
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


ROWS = [
    {"ioc_value": "a", "seen_ts": "2026-07-02T00:00:00+00:00", "channel": "c1", "category": "x"},
    {"ioc_value": "a", "seen_ts": "2026-06-21T00:00:00+00:00", "channel": "c0", "category": "x"},
    {"ioc_value": "b", "seen_ts": "2026-08-01T00:00:00+00:00", "channel": "c2", "category": "y"},
    {"ioc_value": "c", "seen_ts": "2026-09-01T00:00:00+00:00", "channel": "c3", "category": "z"},
]


class Apply(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        c = _Client()
        self.assertEqual(_run(ROWS, c, []), 0)
        self.assertEqual(c.puts, [])

    def test_writes_each_distinct_indicator_once_with_its_earliest_sighting(self):
        c = _Client()
        self.assertEqual(_run(ROWS, c, ["--apply"]), 0)
        by = {p["ioc_value"]["S"]: p["first_seen"]["S"] for p in c.puts}
        self.assertEqual(set(by), {"a", "b", "c"})
        self.assertEqual(by["a"], "2026-06-21T00:00:00+00:00")

    def test_a_rerun_completes_a_partial_table_without_touching_existing_rows(self):
        c = _Client(existing={"a", "b"})
        self.assertEqual(_run(ROWS, c, ["--apply"]), 0)
        self.assertEqual([p["ioc_value"]["S"] for p in c.puts], ["c"])

    def test_a_real_failure_is_counted_and_fails_the_exit_status(self):
        c = _Client(boom={"b"})
        self.assertEqual(_run(ROWS, c, ["--apply"]), 1)
        self.assertEqual(sorted(p["ioc_value"]["S"] for p in c.puts), ["a", "c"])


if __name__ == "__main__":
    unittest.main()
