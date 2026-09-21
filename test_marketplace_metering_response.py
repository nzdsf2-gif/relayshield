#!/usr/bin/env python3
"""BatchMeterUsage returns 200 for a record it rejected. Read the response.

WHAT THIS COST. On 2026-09-21 the fulfillment log said

    Marketplace usage reported account=... dimension=threat_actor_calls

and AWS's public-visibility audit said, for the same product on the same day,
"no successful metering records". BOTH WERE TRUE. The log was describing the
REQUEST; the audit was describing the RESULT.

BatchMeterUsage puts each record's outcome in Results[].Status -- Success,
CustomerNotSubscribed or DuplicateRecord -- and anything it could not process
at all in UnprocessedRecords. None of that raises, and the old code discarded
the response entirely, so the success line was logged unconditionally on any
call that did not throw.

EXECUTED AGAINST A STUBBED CLIENT, not grepped, because every defect here is in
what the function does with a value it already has.

    python3 test_marketplace_metering_response.py
"""
import ast
import io
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "relayshield_api.py"


def _load_fn():
    """Compile just _report_marketplace_usage, with its module-level deps stubbed.

    relayshield_api.py is ~13,000 lines and imports boto3 at module scope, so
    importing it here would be slower and would test more than this function.
    """
    tree = ast.parse(io.open(SRC, encoding="utf-8").read())
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "_report_marketplace_usage")
    import datetime as _dt
    logs = []
    ns = {
        "boto3": mock.MagicMock(),
        "datetime": _dt.datetime,
        "timezone": _dt.timezone,
        "logger": mock.MagicMock(
            info=lambda m, *a: logs.append(("INFO", m % a if a else m)),
            warning=lambda m, *a: logs.append(("WARN", m % a if a else m)),
        ),
    }
    exec(compile(ast.Module([node], []), "<fn>", "exec"), ns)
    return ns["_report_marketplace_usage"], ns, logs


class MeteringResponse(unittest.TestCase):
    def _run(self, response, raises=None):
        fn, ns, logs = _load_fn()
        client = mock.MagicMock()
        if raises:
            client.batch_meter_usage.side_effect = raises
        else:
            client.batch_meter_usage.return_value = response
        ns["boto3"].client.return_value = client
        fn("442429445748", "arn:aws:license-manager::l-abc", "threat_actor_calls")
        return logs

    def _said(self, logs, needle):
        return any(needle in m for _, m in logs)

    def test_a_success_status_is_reported_as_success(self):
        logs = self._run({"Results": [{"Status": "Success", "MeteringRecordId": "m1"}],
                          "UnprocessedRecords": []})
        self.assertTrue(self._said(logs, "status=Success"))
        self.assertTrue(any(lvl == "INFO" for lvl, _ in logs))

    def test_customer_not_subscribed_is_NOT_reported_as_success(self):
        # THE DEFECT. This is a 200 response carrying a rejection, and the old
        # code logged "Marketplace usage reported" for it.
        logs = self._run({"Results": [{"Status": "CustomerNotSubscribed"}],
                          "UnprocessedRecords": []})
        self.assertFalse(self._said(logs, "usage reported"),
                         "a rejected record must never log as reported")
        self.assertTrue(self._said(logs, "NOT metered"))
        self.assertTrue(self._said(logs, "CustomerNotSubscribed"),
                        "the status must appear verbatim: it names the fix")

    def test_duplicate_record_is_named_rather_than_hidden(self):
        # AWS deduplicates an identical (customer, dimension, hour). Not an
        # error, and not a success either, and the reader needs to know which.
        logs = self._run({"Results": [{"Status": "DuplicateRecord"}],
                          "UnprocessedRecords": []})
        self.assertTrue(self._said(logs, "DuplicateRecord"))
        self.assertFalse(self._said(logs, "usage reported"))

    def test_unprocessed_records_are_reported(self):
        logs = self._run({"Results": [],
                          "UnprocessedRecords": [{"Dimension": "threat_actor_calls"}]})
        self.assertTrue(self._said(logs, "UNPROCESSED"))
        self.assertFalse(self._said(logs, "usage reported"))

    def test_an_empty_response_is_not_a_success(self):
        # Neither list present. The old code would have logged success.
        for resp in ({}, {"Results": [], "UnprocessedRecords": []}, None):
            logs = self._run(resp)
            self.assertFalse(self._said(logs, "usage reported"),
                             f"empty response {resp!r} must not read as metered")

    def test_a_raise_is_still_non_fatal_and_named(self):
        logs = self._run(None, raises=RuntimeError("boom"))
        self.assertTrue(self._said(logs, "reporting failed"))
        self.assertFalse(self._said(logs, "usage reported"))

    def test_missing_license_arn_skips_before_calling(self):
        # The pre-existing guard. A key provisioned outside subscribe-success
        # carries no LicenseArn, and metering without one is not possible.
        fn, ns, logs = _load_fn()
        fn("442429445748", "", "threat_actor_calls")
        self.assertTrue(self._said(logs, "Skipping bundle usage report"))
        ns["boto3"].client.assert_not_called()

    def test_the_response_is_actually_inspected(self):
        # A guard against the whole class returning: no behavioural test can
        # see the response being assigned and then ignored again.
        src = io.open(SRC, encoding="utf-8").read()
        i = src.index("def _report_marketplace_usage")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertIn('.get("Results")', body)
        self.assertIn('.get("UnprocessedRecords")', body)
        self.assertIn("resp = mp_client.batch_meter_usage", body,
                      "the response must be captured, not discarded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
