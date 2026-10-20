"""tools/backfill_first_seen.py -- the write phase, executed (2026-10-20).

It wrote ~470,000 rows one at a time with no output, about two hours of silence,
and was apparently never run to completion. It now writes in parallel with a
heartbeat. These pin what must stay true: writes are CONDITIONAL (a row the live
monitor already wrote is never overwritten), every distinct indicator is
attempted exactly once, the EARLIEST sighting wins, and the wrong AWS account is
refused before anything is read or written.
"""
import contextlib
import importlib.util
import io
import pathlib
import sys
import types
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent


class ConditionalCheckFailedException(Exception):
    pass


class _Table:
    def __init__(self, rows):
        self.rows = rows

    def scan(self, ExclusiveStartKey=None, **kw):
        start = (ExclusiveStartKey or {}).get("o", 0)
        page = self.rows[start:start + 7]
        out = {"Items": page}
        if start + 7 < len(self.rows):
            out["LastEvaluatedKey"] = {"o": start + 7}
        return out


class _Client:
    def __init__(self, existing=()):
        self.existing, self.puts = set(existing), []

    def put_item(self, **kw):
        self.puts.append(kw)
        if kw["Item"]["ioc_value"] in self.existing:
            raise ConditionalCheckFailedException()


def _run(rows, existing=(), account="239677749008", apply=True):
    client = _Client(existing)
    ddb = types.SimpleNamespace(Table=lambda name: _Table(rows),
                                meta=types.SimpleNamespace(client=client))
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda *a, **k: types.SimpleNamespace(
        get_caller_identity=lambda: {"Account": account})
    boto3.resource = lambda *a, **k: ddb
    spec = importlib.util.spec_from_file_location(
        "backfill_first_seen", ROOT / "tools" / "backfill_first_seen.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out, err = io.StringIO(), io.StringIO()
    argv = ["backfill_first_seen"] + (["--apply"] if apply else [])
    with unittest.mock.patch.dict(sys.modules, {"boto3": boto3}), \
            unittest.mock.patch.object(sys, "argv", argv), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = mod.main()
    return rc, out.getvalue(), err.getvalue(), client


def _row(v, ts, ch="c", cat="threat_feed"):
    return {"ioc_value": v, "seen_ts": ts, "channel": ch, "category": cat}


class Backfill(unittest.TestCase):
    def test_every_distinct_indicator_is_written_once_with_its_earliest_sighting(self):
        rows = [_row("a.example", "2026-09-02", "late"),
                _row("a.example", "2026-07-01", "early"),
                _row("a.example", "2026-08-01", "mid"),
                _row("b.example", "2026-10-01")]
        rc, out, _, client = _run(rows)
        self.assertEqual(rc, 0)
        by = {p["Item"]["ioc_value"]: p["Item"] for p in client.puts}
        self.assertEqual(set(by), {"a.example", "b.example"})
        self.assertEqual(len(client.puts), 2)
        self.assertEqual(by["a.example"]["first_seen"], "2026-07-01")
        self.assertEqual(by["a.example"]["first_channel"], "early")
        self.assertIn("wrote 2, skipped 0 already present, 0 failure(s)", out)

    def test_writes_are_conditional_so_an_existing_row_is_never_overwritten(self):
        rows = [_row(f"h{n}.example", "2026-07-01") for n in range(50)]
        rc, out, _, client = _run(rows, existing={"h3.example", "h40.example"})
        self.assertTrue(all(p["ConditionExpression"] ==
                            "attribute_not_exists(ioc_value)" for p in client.puts))
        self.assertTrue(all(p["TableName"] == "relayshield_intel_first_seen"
                            for p in client.puts))
        self.assertIn("wrote 48, skipped 2 already present, 0 failure(s)", out)

    def test_large_runs_use_every_worker_and_lose_nothing(self):
        rows = [_row(f"h{n}.example", "2026-07-01") for n in range(3000)]
        rc, out, _, client = _run(rows)
        self.assertEqual(len({p["Item"]["ioc_value"] for p in client.puts}), 3000)
        self.assertIn("wrote 3000", out)

    def test_a_failed_write_is_counted_and_makes_the_exit_code_nonzero(self):
        rows = [_row("a.example", "2026-07-01")]
        client = _Client()
        client.put_item = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        with unittest.mock.patch.object(_Client, "put_item", client.put_item):
            rc, out, err, _ = _run(rows)
        self.assertEqual(rc, 1)
        self.assertIn("1 failure(s)", out)
        self.assertIn("failed a.example", err)

    def test_dry_run_writes_nothing(self):
        rc, out, _, client = _run([_row("a.example", "2026-07-01")], apply=False)
        self.assertEqual(rc, 0)
        self.assertEqual(client.puts, [])
        self.assertIn("READ-ONLY", out)

    def test_the_wrong_account_is_refused_before_anything_is_read(self):
        rc, out, err, client = _run([_row("a.example", "2026-07-01")],
                                    account="620534471984")
        self.assertEqual(rc, 2)
        self.assertEqual(client.puts, [])
        self.assertIn("AWS_PROFILE=relayshield", err)
        self.assertNotIn("scanned", out)

    def test_the_write_phase_announces_itself_instead_of_going_silent(self):
        _, _, err, _ = _run([_row("a.example", "2026-07-01")])
        self.assertIn("writing up to 1", err)


if __name__ == "__main__":
    unittest.main()
