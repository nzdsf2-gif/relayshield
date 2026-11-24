"""tools/ir_capture_evidence.py. Fakes test the DECISIONS (read-only, wrong account refused, never reuse a directory,
a failed capture is recorded not hidden, presigned code URL stripped, hashes match). botocore Stubber over the real
cloudtrail / lambda / iam models tests the SHAPES. The Stubber tests skip, and say so, where boto3 is absent."""
import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ir_capture_evidence as T  # noqa: E402

NOW = dt.datetime(2026, 11, 24, 12, 0, tzinfo=dt.timezone.utc)


class CE(Exception):
    def __init__(self, c):
        self.response = {"Error": {"Code": c}}


class FakeCT:
    def __init__(self):
        self.calls = []

    def lookup_events(self, **kw):
        self.calls.append(kw)
        if "NextToken" not in kw:
            return {"Events": [{"EventName": "A"}], "NextToken": "t"}
        return {"Events": [{"EventName": "B"}]}


class FakeLam:
    def __init__(self, missing=()):
        self.missing = missing

    def get_function(self, FunctionName):
        if FunctionName in self.missing:
            raise CE("ResourceNotFoundException")
        return {"Configuration": {"FunctionName": FunctionName}, "Code": {"Location": "https://presigned", "RepositoryType": "S3"}, "ResponseMetadata": {}}

    def list_versions_by_function(self, **kw):
        return {"Versions": [{"Version": "$LATEST"}]}

    def list_aliases(self, **kw):
        return {"Aliases": []}

    def get_function_concurrency(self, FunctionName):
        return {"ReservedConcurrentExecutions": 100}


class FakeIAM:
    def list_access_keys(self, UserName):
        return {"AccessKeyMetadata": [{"UserName": UserName, "AccessKeyId": "AKIAEXAMPLE12345A", "Status": "Active"}]}

    def get_access_key_last_used(self, AccessKeyId):
        return {"AccessKeyLastUsed": {"ServiceName": "s3"}}


def go(tmp, **kw):
    lines = []
    args = dict(clients={"cloudtrail": FakeCT(), "lambda": FakeLam(), "iam": FakeIAM()}, account_of=lambda: T.ACCOUNT, lookups=[("AccessKeyId", "AKIAEXAMPLE12345A")],
                functions=["relayshield-api"], iam_users=["u"], since_hours=24, outdir=Path(tmp) / "ev", now=NOW, out=lines.append)
    args.update(kw)
    rc = T.run(**args)
    return rc, "\n".join(lines), args


class Decisions(unittest.TestCase):
    def test_wrong_account_refused_and_nothing_written(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, a = go(d, account_of=lambda: "620534471984")
            self.assertEqual(rc, 2)
            self.assertFalse(a["outdir"].exists())

    def test_nothing_to_capture_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(go(d, lookups=[], functions=[], iam_users=[])[0], 2)

    def test_existing_directory_is_never_reused(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "ev").mkdir()
            self.assertEqual(go(d)[0], 2)

    def test_captures_everything_paginates_and_strips_presigned_url(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, a = go(d)
            self.assertEqual(rc, 0)
            ev = a["outdir"]
            self.assertEqual(json.load(open(ev / "cloudtrail_1.json"))["count"], 2)
            lam = json.load(open(ev / "lambda_relayshield-api.json"))
            self.assertNotIn("Location", lam["code"])
            self.assertNotIn("presigned", (ev / "lambda_relayshield-api.json").read_text())
            self.assertEqual(lam["reserved_concurrency"], 100)
            self.assertEqual(json.load(open(ev / "iam_u.json"))["access_keys"][0]["last_used"]["ServiceName"], "s3")

    def test_window_is_capped_at_ninety_days_and_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            ct = FakeCT()
            rc, out, a = go(d, since_hours=24 * 200, clients={"cloudtrail": ct, "lambda": FakeLam(), "iam": FakeIAM()})
            self.assertIn("cut from 4800 to 2160", out)
            self.assertEqual(ct.calls[0]["StartTime"], NOW - dt.timedelta(days=90))

    def test_a_failed_capture_is_recorded_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, a = go(d, clients={"cloudtrail": FakeCT(), "lambda": FakeLam(missing=("relayshield-api",)), "iam": FakeIAM()})
            self.assertEqual(rc, 1)
            self.assertIn("FAILED", out)
            self.assertEqual(json.load(open(a["outdir"] / "lambda_relayshield-api.json"))["error"], "ResourceNotFoundException")

    def test_manifest_hashes_match_the_files(self):
        with tempfile.TemporaryDirectory() as d:
            _, _, a = go(d)
            for line in (a["outdir"] / "SHA256SUMS").read_text().splitlines():
                h, name = line.split("  ")
                self.assertEqual(h, hashlib.sha256((a["outdir"] / name).read_bytes()).hexdigest())
            self.assertNotIn("SHA256SUMS", (a["outdir"] / "SHA256SUMS").read_text())

    def test_lookup_parsing_rejects_unknown_keys_and_empty_values(self):
        self.assertEqual(T.parse_lookup("Username=bob"), ("Username", "bob"))
        for bad in ("Foo=bar", "Username=", "nokey"):
            with self.assertRaises(ValueError):
                T.parse_lookup(bad)


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

    def test_cloudtrail_request_and_response_shape(self):
        ct, st = self.client("cloudtrail")
        start = NOW - dt.timedelta(hours=1)
        exp = {"LookupAttributes": [{"AttributeKey": "AccessKeyId", "AttributeValue": "AKIAEXAMPLE12345A"}], "StartTime": start, "MaxResults": 50}
        st.add_response("lookup_events", {"Events": [{"EventId": "1", "EventName": "GetObject", "EventTime": NOW, "Username": "u"}], "NextToken": "n"}, exp)
        st.add_response("lookup_events", {"Events": []}, {**exp, "NextToken": "n"})
        with st:
            r = T.cloudtrail(ct, "AccessKeyId", "AKIAEXAMPLE12345A", start)
            self.assertEqual(r["count"], 1)
            st.assert_no_pending_responses()

    def test_lambda_requests_and_responses(self):
        lam, st = self.client("lambda")
        fn = "relayshield-api"
        st.add_response("get_function", {"Configuration": {"FunctionName": fn}, "Code": {"RepositoryType": "S3", "Location": "https://x"}}, {"FunctionName": fn})
        st.add_response("list_versions_by_function", {"Versions": [{"Version": "1"}], "NextMarker": "m"}, {"FunctionName": fn})
        st.add_response("list_versions_by_function", {"Versions": [{"Version": "2"}]}, {"FunctionName": fn, "Marker": "m"})
        st.add_response("list_aliases", {"Aliases": []}, {"FunctionName": fn})
        st.add_response("get_function_concurrency", {"ReservedConcurrentExecutions": 100}, {"FunctionName": fn})
        with st:
            r = T.lambda_state(lam, fn)
            self.assertEqual(len(r["versions"]), 2)
            self.assertNotIn("Location", r["code"])
            st.assert_no_pending_responses()

    def test_iam_requests_and_responses(self):
        iam, st = self.client("iam")
        st.add_response("list_access_keys", {"AccessKeyMetadata": [{"UserName": "u", "AccessKeyId": "AKIAEXAMPLE12345A", "Status": "Active"}]}, {"UserName": "u"})
        st.add_response("get_access_key_last_used", {"UserName": "u", "AccessKeyLastUsed": {"LastUsedDate": NOW, "ServiceName": "s3", "Region": "us-east-1"}}, {"AccessKeyId": "AKIAEXAMPLE12345A"})
        with st:
            self.assertEqual(T.iam_state(iam, "u")["access_keys"][0]["last_used"]["ServiceName"], "s3")


if __name__ == "__main__":
    unittest.main()
