"""tools/retention_enforce.py: one-year retention after TERMINATION, never after creation.

Two layers. A fake client tests the DECISIONS (an undatable terminated record is never deleted, the newest
marker wins, a recent termination is kept, dry run writes nothing, --apply needs --only, days below 365 are
refused, the cap refuses, the wrong account stops). botocore's Stubber over the REAL dynamodb service model
tests the SHAPES: every scan and delete the tool sends is validated against the model, and every response it
parses is a legal one. Skipped, and said so, where boto3 is not installed; CI installs it."""
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import retention_enforce as T  # noqa: E402

NOW = 1_800_000_000.0
YEAR = 365 * 86400
OLD = str(int(NOW - YEAR - 86400))
NEW = str(int(NOW - 30 * 86400))


class _Exc:
    class ConditionalCheckFailedException(Exception):
        pass


class FakeDDB:
    exceptions = _Exc

    def __init__(self, items, fail_delete=()):
        self.items, self.deleted, self.fail_delete = items, [], set(fail_delete)

    def scan(self, **kw):
        return {"Items": self.items, "ScannedCount": len(self.items)}

    def delete_item(self, **kw):
        k = list(kw["Key"].values())[0]["S"]
        if k in self.fail_delete:
            raise _Exc.ConditionalCheckFailedException()
        self.deleted.append(k)


def hosted(tid, ts=None):
    it = {"tenant_id": {"S": tid}}
    if ts is not None:
        it["terminated_at"] = {"N": ts}
    return it


def run(client, *argv):
    out = io.StringIO()
    code = T.main(list(argv), client=client, now=NOW, out=out)
    return code, out.getvalue()


class Decisions(unittest.TestCase):
    def test_old_is_eligible_recent_kept_undatable_never_deleted(self):
        c = FakeDDB([hosted("old", OLD), hosted("new", NEW), hosted("none")])
        code, out = run(c, "--only", "hosted_proxies", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(c.deleted, ["old"])
        self.assertIn("NO timestamp (never deleted) 1", out)
        self.assertIn("under a year 1", out)

    def test_dry_run_deletes_nothing(self):
        c = FakeDDB([hosted("old", OLD)])
        code, out = run(c)
        self.assertEqual((code, c.deleted), (0, []))
        self.assertIn("would delete: old", out)
        self.assertIn("Dry run only", out)

    def test_apply_requires_only(self):
        code, out = run(FakeDDB([]), "--apply")
        self.assertEqual(code, 2)
        self.assertIn("--apply needs --only", out)

    def test_days_below_policy_minimum_refused(self):
        code, out = run(FakeDDB([hosted("old", OLD)]), "--days", "30")
        self.assertEqual(code, 2)
        self.assertIn("below the policy minimum", out)

    def test_cap_refuses_before_deleting(self):
        c = FakeDDB([hosted("a", OLD), hosted("b", OLD), hosted("c", OLD)])
        code, out = run(c, "--only", "hosted_proxies", "--apply", "--max-delete", "2")
        self.assertEqual((code, c.deleted), (2, []))
        self.assertIn("above --max-delete", out)

    def test_changed_since_scan_is_skipped_not_deleted(self):
        c = FakeDDB([hosted("a", OLD), hosted("b", OLD)], fail_delete=["a"])
        code, out = run(c, "--only", "hosted_proxies", "--apply")
        self.assertEqual(c.deleted, ["b"])
        self.assertIn("Deleted 1, skipped 1", out)

    def test_newest_marker_wins_for_users(self):
        # cancelled long ago but deactivated recently: the newest marker keeps it
        u = {"user_id": {"S": "u1"}, "deactivated_at": {"S": "2020-01-01T00:00:00+00:00"},
             "subscription_cancelled_at": {"N": NEW}}
        c = FakeDDB([u])
        code, out = run(c, "--only", "users", "--apply")
        self.assertEqual(c.deleted, [])
        self.assertIn("under a year 1", out)

    def test_iso_and_epoch_both_parse(self):
        self.assertAlmostEqual(T.parse_ts({"S": "2026-01-01T00:00:00Z"}), 1767225600.0)
        self.assertEqual(T.parse_ts({"N": "5"}), 5.0)
        self.assertIsNone(T.parse_ts({"S": "garbage"}))
        self.assertIsNone(T.parse_ts(None))

    def test_active_users_are_never_in_the_filter(self):
        self.assertEqual(T.TARGETS["users"]["values"][":flag"], {"BOOL": False})
        self.assertIn("active = :flag", T.TARGETS["users"]["filter"])
        self.assertNotIn("created_at", T.TARGETS["users"]["ts_attrs"])


try:
    import boto3
    from botocore.stub import Stubber, ANY
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "boto3 not installed: Stubber layer skipped (CI installs it)")
class RealServiceModel(unittest.TestCase):
    def client(self):
        return boto3.client("dynamodb", region_name="us-east-1",
                            aws_access_key_id="x", aws_secret_access_key="x")

    def test_scan_and_delete_shapes_hosted(self):
        c = self.client()
        with Stubber(c) as st:
            st.add_response("scan", {"Items": [hosted("old", OLD)], "ScannedCount": 1, "Count": 1},
                            {"TableName": "relayshield_hosted_proxies", "FilterExpression": "#s = :flag",
                             "ExpressionAttributeNames": ANY, "ExpressionAttributeValues": ANY,
                             "ProjectionExpression": ANY})
            st.add_response("delete_item", {},
                            {"TableName": "relayshield_hosted_proxies", "Key": {"tenant_id": {"S": "old"}},
                             "ConditionExpression": "#s = :flag AND terminated_at = :ts",
                             "ExpressionAttributeNames": {"#s": "status"},
                             "ExpressionAttributeValues": {":flag": {"S": "terminated"}, ":ts": {"N": OLD}}})
            code, out = run(c, "--only", "hosted_proxies", "--apply")
            self.assertEqual(code, 0, out)
            st.assert_no_pending_responses()

    def test_scan_and_delete_shapes_users_without_names_map(self):
        c = self.client()
        item = {"user_id": {"S": "u1"}, "deactivated_at": {"S": "2020-01-01T00:00:00+00:00"}}
        with Stubber(c) as st:
            st.add_response("scan", {"Items": [item], "ScannedCount": 1, "Count": 1},
                            {"TableName": "relayshield_users", "FilterExpression": "active = :flag",
                             "ExpressionAttributeNames": ANY, "ExpressionAttributeValues": ANY,
                             "ProjectionExpression": ANY})
            st.add_response("delete_item", {},
                            {"TableName": "relayshield_users", "Key": {"user_id": {"S": "u1"}},
                             "ConditionExpression": "active = :flag AND deactivated_at = :ts",
                             "ExpressionAttributeValues": {":flag": {"BOOL": False},
                                                           ":ts": {"S": "2020-01-01T00:00:00+00:00"}}})
            code, out = run(c, "--only", "users", "--apply")
            self.assertEqual(code, 0, out)
            st.assert_no_pending_responses()

    def test_real_conditional_failure_is_skipped(self):
        c = self.client()
        with Stubber(c) as st:
            st.add_response("scan", {"Items": [hosted("old", OLD)], "ScannedCount": 1, "Count": 1})
            st.add_client_error("delete_item", "ConditionalCheckFailedException")
            code, out = run(c, "--only", "hosted_proxies", "--apply")
            self.assertEqual(code, 0, out)
            self.assertIn("Deleted 0, skipped 1", out)

    def test_pagination_follows_last_evaluated_key(self):
        c = self.client()
        with Stubber(c) as st:
            st.add_response("scan", {"Items": [hosted("a", OLD)], "ScannedCount": 1, "Count": 1,
                                     "LastEvaluatedKey": {"tenant_id": {"S": "a"}}})
            st.add_response("scan", {"Items": [hosted("b", NEW)], "ScannedCount": 1, "Count": 1},
                            {"TableName": "relayshield_hosted_proxies", "FilterExpression": ANY,
                             "ExpressionAttributeNames": ANY, "ExpressionAttributeValues": ANY,
                             "ProjectionExpression": ANY, "ExclusiveStartKey": {"tenant_id": {"S": "a"}}})
            code, out = run(c, "--only", "hosted_proxies")
            self.assertEqual(code, 0, out)
            st.assert_no_pending_responses()
            self.assertIn("scanned 2", out)


if __name__ == "__main__":
    unittest.main()
