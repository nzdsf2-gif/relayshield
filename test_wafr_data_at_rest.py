"""tools/wafr_data_at_rest.py: SEC 8, data at rest.

Two layers, because a fake written by the same hand as the code proves nothing about the library:
  * Fake clients test the DECISIONS (never block a public bucket, never touch an expected-public one,
    never encrypt-and-block in one go where the bucket is public, account switch waits for public buckets,
    dry run writes nothing, check mode fails on a gap, wrong account refused).
  * botocore's Stubber, over the REAL s3 / sqs / dynamodb / s3control models, tests the SHAPES: every request
    the tool makes is validated against the model and every response it parses is a legal one.
    Skipped (and said so) where boto3 is not installed; CI installs it from tests_requirements.txt."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import wafr_data_at_rest as T  # noqa: E402

SPEC = json.load(open(ROOT / "tools" / "wafr_data_at_rest_spec.json"))
ACCT = SPEC["account"]


class CE(Exception):
    def __init__(self, c):
        self.response = {"Error": {"Code": c}}


class FakeS3:
    """buckets: name -> dict(enc, pab (None or dict), public_policy, website, acl_public, region)"""

    def __init__(self, buckets):
        self.b, self.puts = buckets, []

    def list_buckets(self):
        return {"Buckets": [{"Name": n} for n in self.b]}

    def get_bucket_location(self, Bucket):
        r = self.b[Bucket].get("region", "us-east-1")
        return {"LocationConstraint": None if r == "us-east-1" else r}

    def get_bucket_encryption(self, Bucket):
        if not self.b[Bucket].get("enc"):
            raise CE("ServerSideEncryptionConfigurationNotFoundError")
        return {}

    def get_public_access_block(self, Bucket):
        p = self.b[Bucket].get("pab")
        if p is None:
            raise CE("NoSuchPublicAccessBlockConfiguration")
        return {"PublicAccessBlockConfiguration": p}

    def get_bucket_policy_status(self, Bucket):
        if self.b[Bucket].get("denied"):
            raise CE("AccessDenied")
        return {"PolicyStatus": {"IsPublic": bool(self.b[Bucket].get("public_policy"))}}

    def get_bucket_website(self, Bucket):
        if not self.b[Bucket].get("website"):
            raise CE("NoSuchWebsiteConfiguration")
        return {}

    def get_bucket_acl(self, Bucket):
        g = [{"Grantee": {"URI": T.ALL_USERS[0]}}] if self.b[Bucket].get("acl_public") else []
        return {"Grants": g}

    def put_bucket_encryption(self, Bucket, ServerSideEncryptionConfiguration):
        self.puts.append(("enc", Bucket))

    def put_public_access_block(self, Bucket, PublicAccessBlockConfiguration):
        self.puts.append(("pab", Bucket))


FULL = {f: True for f in T.PAB_FLAGS}
GOOD = {"enc": True, "pab": FULL}


class FakeSQS:
    def __init__(self, q):
        self.q, self.puts = q, []

    def list_queues(self, **kw):
        return {"QueueUrls": [f"https://sqs/x/{n}" for n in self.q]}

    def get_queue_attributes(self, QueueUrl, AttributeNames):
        return {"Attributes": self.q[QueueUrl.rsplit("/", 1)[-1]]}

    def set_queue_attributes(self, QueueUrl, Attributes):
        self.puts.append((QueueUrl.rsplit("/", 1)[-1], Attributes))


class FakeDDB:
    def __init__(self, t):
        self.t = t

    def list_tables(self, **kw):
        return {"TableNames": list(self.t)}

    def describe_table(self, TableName):
        return {"Table": {"DeletionProtectionEnabled": self.t[TableName]["dp"], **({"SSEDescription": self.t[TableName]["sse"]} if "sse" in self.t[TableName] else {})}}

    def describe_continuous_backups(self, TableName):
        return {"ContinuousBackupsDescription": {"PointInTimeRecoveryDescription": {"PointInTimeRecoveryStatus": "ENABLED" if self.t[TableName]["pitr"] else "DISABLED"}}}


class FakeCtl:
    def __init__(self, cfg=None):
        self.cfg, self.puts = cfg, []

    def get_public_access_block(self, AccountId):
        if self.cfg is None:
            raise CE("NoSuchPublicAccessBlockConfiguration")
        return {"PublicAccessBlockConfiguration": self.cfg}

    def put_public_access_block(self, AccountId, PublicAccessBlockConfiguration):
        self.puts.append(AccountId)


def go(clients, apply=False, check=False, steps=T.STEPS, acct=ACCT, spec=SPEC):
    lines = []
    rc = T.run(clients, lambda: acct, spec, apply, steps, check, out=lines.append)
    return rc, "\n".join(lines)


class S3Decisions(unittest.TestCase):
    def test_wrong_account_refused_and_nothing_written(self):
        s3 = FakeS3({"a": {"enc": False, "pab": None}})
        rc, out = go({"s3": s3}, apply=True, steps=("s3",), acct="620534471984")
        self.assertEqual((rc, s3.puts), (2, []))
        self.assertIn("Refusing to run", out)

    def test_dry_run_writes_nothing_and_says_so(self):
        s3 = FakeS3({"a": {"enc": False, "pab": None}})
        rc, out = go({"s3": s3}, steps=("s3",))
        self.assertEqual((rc, s3.puts), (0, []))
        self.assertIn("Dry run only", out)

    def test_apply_encrypts_and_blocks_a_private_bucket(self):
        s3 = FakeS3({"a": {"enc": False, "pab": None}})
        go({"s3": s3}, apply=True, steps=("s3",))
        self.assertEqual(sorted(s3.puts), [("enc", "a"), ("pab", "a")])

    def test_apply_leaves_a_fine_bucket_alone(self):
        s3 = FakeS3({"a": GOOD})
        rc, _ = go({"s3": s3}, apply=True, steps=("s3",))
        self.assertEqual((rc, s3.puts), (0, []))

    def test_public_bucket_is_never_blocked_but_is_still_encrypted(self):
        for how in ("public_policy", "website", "acl_public"):
            s3 = FakeS3({"a": {"enc": False, "pab": None, how: True}})
            rc, out = go({"s3": s3}, apply=True, steps=("s3",))
            self.assertEqual(s3.puts, [("enc", "a")], how)
            self.assertIn("CONFLICT", out)
            self.assertEqual(rc, 1)

    def test_unreadable_policy_counts_as_public_so_we_do_not_block_blind(self):
        s3 = FakeS3({"a": {"enc": True, "pab": None, "denied": True}})
        rc, out = go({"s3": s3}, apply=True, steps=("s3",))
        self.assertEqual(s3.puts, [])
        self.assertIn("CONFLICT", out)

    def test_expected_public_bucket_gets_no_block(self):
        spec = {**SPEC, "expected_public_buckets": ["site"]}
        s3 = FakeS3({"site": {"enc": False, "pab": None, "website": True}})
        rc, out = go({"s3": s3}, apply=True, steps=("s3",), spec=spec)
        self.assertEqual(s3.puts, [("enc", "site")])
        self.assertEqual(rc, 0)

    def test_other_region_bucket_is_skipped_not_touched(self):
        s3 = FakeS3({"eu": {"enc": False, "pab": None, "region": "eu-west-1"}})
        rc, out = go({"s3": s3}, apply=True, steps=("s3",))
        self.assertEqual((rc, s3.puts), (0, []))
        self.assertIn("1 skipped on purpose", out)

    def test_check_fails_on_a_gap_and_passes_when_clean(self):
        self.assertEqual(go({"s3": FakeS3({"a": {"enc": False, "pab": None}})}, check=True, steps=("s3",))[0], 1)
        self.assertEqual(go({"s3": FakeS3({"a": GOOD})}, check=True, steps=("s3",))[0], 0)

    def test_apply_and_check_together_refused(self):
        self.assertEqual(go({"s3": FakeS3({})}, apply=True, check=True, steps=("s3",))[0], 2)


class OtherSteps(unittest.TestCase):
    def test_sqs_encrypts_only_unencrypted_queues(self):
        q = FakeSQS({"a": {}, "b": {"SqsManagedSseEnabled": "true"}, "c": {"KmsMasterKeyId": "k"}, "d": {"SqsManagedSseEnabled": "false"}})
        go({"sqs": q}, apply=True, steps=("sqs",))
        self.assertEqual(sorted(n for n, _ in q.puts), ["a", "d"])
        self.assertEqual(q.puts[0][1], {"SqsManagedSseEnabled": "true"})

    def test_dynamodb_is_read_only_and_names_the_writer(self):
        d = FakeDDB({"t1": {"dp": False, "pitr": False}, "t2": {"dp": True, "pitr": True}})
        rc, out = go({"dynamodb": d}, apply=True, steps=("dynamodb",))
        self.assertEqual(rc, 1)
        self.assertIn("ELSEWHERE", out)
        self.assertIn("protect_dynamodb_tables.sh", out)
        self.assertIn("1 already fine", out)

    def test_account_block_waits_while_a_bucket_is_public(self):
        s3, ctl = FakeS3({"a": {**GOOD, "public_policy": True}}), FakeCtl()
        rc, out = go({"s3": s3, "s3control": ctl}, apply=True, steps=("account",))
        self.assertEqual(ctl.puts, [])
        self.assertIn("BLOCKED", out)
        self.assertEqual(rc, 1)

    def test_account_block_applied_when_nothing_is_public(self):
        s3, ctl = FakeS3({"a": GOOD}), FakeCtl()
        go({"s3": s3, "s3control": ctl}, apply=True, steps=("account",))
        self.assertEqual(ctl.puts, [ACCT])

    def test_account_block_already_on_is_left_alone(self):
        ctl = FakeCtl(FULL)
        rc, _ = go({"s3": FakeS3({}), "s3control": ctl}, apply=True, steps=("account",))
        self.assertEqual((rc, ctl.puts), (0, []))

    def test_account_block_partial_counts_as_not_on(self):
        ctl = FakeCtl({**FULL, "RestrictPublicBuckets": False})
        go({"s3": FakeS3({"a": GOOD}), "s3control": ctl}, apply=True, steps=("account",))
        self.assertEqual(ctl.puts, [ACCT])


try:
    import boto3
    from botocore.stub import Stubber
except ImportError:  # pragma: no cover
    boto3 = None


@unittest.skipIf(boto3 is None, "boto3 not installed: the Stubber shape checks did not run")
class RealServiceModels(unittest.TestCase):
    def client(self, name):
        c = boto3.client(name, region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="y")
        return c, Stubber(c)

    def err(self, st, op, c, **p):
        st.add_client_error(op, service_error_code=c, service_message="m", **({"expected_params": p} if p else {}))

    def test_s3_private_unencrypted_bucket_requests_are_valid_and_applied(self):
        s3, st = self.client("s3")
        st.add_response("list_buckets", {"Buckets": [{"Name": "b"}], "Owner": {}})
        st.add_response("get_bucket_location", {}, {"Bucket": "b"})
        self.err(st, "get_bucket_encryption", "ServerSideEncryptionConfigurationNotFoundError", Bucket="b")
        self.err(st, "get_public_access_block", "NoSuchPublicAccessBlockConfiguration", Bucket="b")
        self.err(st, "get_bucket_policy_status", "NoSuchBucketPolicy", Bucket="b")
        self.err(st, "get_bucket_website", "NoSuchWebsiteConfiguration", Bucket="b")
        st.add_response("get_bucket_acl", {"Grants": [{"Grantee": {"Type": "CanonicalUser", "ID": "x"}, "Permission": "FULL_CONTROL"}]}, {"Bucket": "b"})
        st.add_response("put_bucket_encryption", {}, {"Bucket": "b", "ServerSideEncryptionConfiguration": {
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}, "BucketKeyEnabled": True}]}})
        st.add_response("put_public_access_block", {}, {"Bucket": "b", "PublicAccessBlockConfiguration": FULL})
        with st:
            rows = T.plan_s3(s3, SPEC)
            self.assertEqual([r[1] for r in rows], ["todo"])
            self.assertEqual(len(list(T.apply_s3(s3, rows))), 2)
            st.assert_no_pending_responses()

    def test_s3_policy_status_response_shape_is_parsed(self):
        s3, st = self.client("s3")
        st.add_response("get_bucket_policy_status", {"PolicyStatus": {"IsPublic": True}}, {"Bucket": "b"})
        with st:
            self.assertEqual(T.is_public(s3, "b"), (True, "bucket policy is public"))

    def test_s3_fully_configured_bucket_is_ok(self):
        s3, st = self.client("s3")
        st.add_response("list_buckets", {"Buckets": [{"Name": "b"}], "Owner": {}})
        st.add_response("get_bucket_location", {"LocationConstraint": "us-east-1"} if False else {}, {"Bucket": "b"})
        st.add_response("get_bucket_encryption", {"ServerSideEncryptionConfiguration": {"Rules": [
            {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}}, {"Bucket": "b"})
        st.add_response("get_public_access_block", {"PublicAccessBlockConfiguration": FULL}, {"Bucket": "b"})
        self.err(st, "get_bucket_policy_status", "NoSuchBucketPolicy", Bucket="b")
        self.err(st, "get_bucket_website", "NoSuchWebsiteConfiguration", Bucket="b")
        st.add_response("get_bucket_acl", {"Grants": []}, {"Bucket": "b"})
        with st:
            self.assertEqual([r[1] for r in T.plan_s3(s3, SPEC)], ["ok"])

    def test_sqs_requests_and_responses(self):
        sqs, st = self.client("sqs")
        url = "https://sqs.us-east-1.amazonaws.com/239677749008/q"
        st.add_response("list_queues", {"QueueUrls": [url]})
        st.add_response("get_queue_attributes", {"Attributes": {}}, {"QueueUrl": url, "AttributeNames": ["KmsMasterKeyId", "SqsManagedSseEnabled"]})
        st.add_response("set_queue_attributes", {}, {"QueueUrl": url, "Attributes": {"SqsManagedSseEnabled": "true"}})
        with st:
            rows = T.plan_sqs(sqs, SPEC)
            self.assertEqual([r[1] for r in rows], ["todo"])
            self.assertEqual(list(T.apply_sqs(sqs, rows)), ["q"])
            st.assert_no_pending_responses()

    def test_dynamodb_requests_and_responses(self):
        d, st = self.client("dynamodb")
        st.add_response("list_tables", {"TableNames": ["tbl"]})
        st.add_response("describe_table", {"Table": {"TableName": "tbl", "DeletionProtectionEnabled": True}}, {"TableName": "tbl"})
        st.add_response("describe_continuous_backups", {"ContinuousBackupsDescription": {
            "ContinuousBackupsStatus": "ENABLED", "PointInTimeRecoveryDescription": {"PointInTimeRecoveryStatus": "ENABLED"}}}, {"TableName": "tbl"})
        with st:
            self.assertEqual([r[1] for r in T.plan_dynamodb(d, SPEC)], ["ok"])

    def test_dynamodb_list_tables_pagination_token_is_a_real_parameter(self):
        d, st = self.client("dynamodb")
        st.add_response("list_tables", {"TableNames": ["aaa"], "LastEvaluatedTableName": "aaa"})
        st.add_response("list_tables", {"TableNames": ["bbb"]}, {"ExclusiveStartTableName": "aaa"})
        with st:
            self.assertEqual(list(T.paged(d.list_tables, "TableNames", "ExclusiveStartTableName", "LastEvaluatedTableName")), ["aaa", "bbb"])

    def test_s3control_account_block_requests_are_valid(self):
        ctl, st = self.client("s3control")
        self.err(st, "get_public_access_block", "NoSuchPublicAccessBlockConfiguration", AccountId=ACCT)
        st.add_response("put_public_access_block", {}, {"AccountId": ACCT, "PublicAccessBlockConfiguration": FULL})
        s3 = FakeS3({"a": GOOD})
        with st:
            rows = T.plan_account(s3, ctl, ACCT, SPEC)
            self.assertEqual(rows[0][1], "todo")
            self.assertEqual(len(list(T.apply_account(ctl, rows, ACCT))), 1)
            st.assert_no_pending_responses()


if __name__ == "__main__":
    unittest.main()
