"""tools/wafr_keys.py: SEC 2 phase 2, retiring long-lived IAM credentials one at a time.

Two layers, because a fake written by the same hand as the code proves nothing about the library:
  * Fake clients test the DECISIONS: the report never writes; every write needs an Identity Center session; a key used
    in the last 7 days is refused; delete needs an Inactive key AND a 7 day record; one action at a time; the wrong
    account is refused; the rollback works without SSO.
  * botocore's Stubber, over the REAL iam / cloudtrail / sts models, tests the SHAPES: every request the tool makes is
    validated against the model and every response it parses is a legal one.
    Skipped (and said so) where boto3 is not installed; CI installs it from tests_requirements.txt."""
import argparse
import datetime
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import wafr_keys as T  # noqa: E402

SPEC = json.load(open(ROOT / "tools" / "wafr_identity_spec.json"))
ACCT = SPEC["account"]
NOW = datetime.datetime(2026, 12, 20, 12, 0, tzinfo=datetime.timezone.utc)
SSO_ARN = f"arn:aws:sts::{ACCT}:assumed-role/AWSReservedSSO_RelayShieldAdmin_0123456789abcdef/someone"
USER_ARN = f"arn:aws:iam::{ACCT}:user/someone"
K_NEVER, K_OLD, K_RECENT, K_OFF = "AKIAEXAMPLENEVER001", "AKIAEXAMPLEOLD00002", "AKIAEXAMPLERECENT03", "AKIAEXAMPLEOFF000004"


def ago(days, hours=0):
    return NOW - datetime.timedelta(days=days, hours=hours)


class CE(Exception):
    def __init__(self, c):
        self.response = {"Error": {"Code": c}}


class FakeIam:
    def __init__(self, keys=None, pw=None, root_keys=0):
        # keys: id -> dict(user, status, created, used(datetime|None), service, region)
        self.keys = keys if keys is not None else {
            K_NEVER: dict(user="svc-a", status="Active", created=ago(900), used=None),
            K_OLD: dict(user="human", status="Active", created=ago(1200), used=ago(200), service="dynamodb", region="us-east-1"),
            K_RECENT: dict(user="svc-b", status="Active", created=ago(300), used=ago(1), service="s3", region="us-east-1"),
            K_OFF: dict(user="svc-c", status="Inactive", created=ago(500), used=ago(60), service="s3", region="us-east-1"),
        }
        self.pw = pw if pw is not None else {"human": ago(3)}
        self.root_keys = root_keys
        self.calls = []

    def writes(self):
        return [c for c in self.calls if c[0].startswith(("update_", "delete_", "create_", "put_", "attach_", "detach_"))]

    def users(self):
        return sorted({k["user"] for k in self.keys.values()} | set(self.pw))

    def list_users(self, **kw):
        self.calls.append(("list_users",))
        return {"Users": [dict(UserName=u, **({"PasswordLastUsed": self.pw[u]} if self.pw.get(u) else {})) for u in self.users()], "IsTruncated": False}

    def list_access_keys(self, UserName):
        self.calls.append(("list_access_keys", UserName))
        return {"AccessKeyMetadata": [dict(UserName=UserName, AccessKeyId=i, Status=k["status"], CreateDate=k["created"])
                                      for i, k in self.keys.items() if k["user"] == UserName]}

    def get_access_key_last_used(self, AccessKeyId):
        self.calls.append(("get_access_key_last_used", AccessKeyId))
        if AccessKeyId not in self.keys:
            raise CE("NoSuchEntity")
        k = self.keys[AccessKeyId]
        lu = {"ServiceName": k.get("service", "N/A"), "Region": k.get("region", "N/A")}
        if k.get("used"):
            lu["LastUsedDate"] = k["used"]
        return {"UserName": k["user"], "AccessKeyLastUsed": lu}

    def get_login_profile(self, UserName):
        self.calls.append(("get_login_profile", UserName))
        if UserName not in self.pw:
            raise CE("NoSuchEntity")
        return {"LoginProfile": {"UserName": UserName}}

    def get_user(self, UserName):
        self.calls.append(("get_user", UserName))
        if UserName not in self.users():
            raise CE("NoSuchEntity")
        return {"User": dict(UserName=UserName, **({"PasswordLastUsed": self.pw[UserName]} if self.pw.get(UserName) else {}))}

    def get_account_summary(self):
        self.calls.append(("get_account_summary",))
        return {"SummaryMap": {"AccountAccessKeysPresent": self.root_keys}}

    def update_access_key(self, UserName, AccessKeyId, Status):
        self.calls.append(("update_access_key", UserName, AccessKeyId, Status))
        self.keys[AccessKeyId]["status"] = Status

    def delete_access_key(self, UserName, AccessKeyId):
        self.calls.append(("delete_access_key", UserName, AccessKeyId))
        del self.keys[AccessKeyId]

    def delete_login_profile(self, UserName):
        self.calls.append(("delete_login_profile", UserName))
        del self.pw[UserName]


class FakeCt:
    def __init__(self, events=None, fail=False):
        self.events, self.fail, self.calls = events or [], fail, []

    def lookup_events(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise CE("AccessDeniedException")
        return {"Events": self.events}


def event(key_id, status, when, shape="camel"):
    rp = {"userName": "svc-c", "accessKeyId": key_id, "status": status}
    if shape == "pascal":
        rp = {k[0].upper() + k[1:]: v for k, v in rp.items()}
    return {"EventId": "e", "EventName": "UpdateAccessKey", "EventTime": when, "CloudTrailEvent": json.dumps({"requestParameters": rp})}


def args(**kw):
    d = dict(apply=False, deactivate=None, reactivate=None, delete=None, remove_console=None, allow_recent=False, observed_since=None)
    d.update(kw)
    return argparse.Namespace(**d)


def go(iam=None, ct=None, arn=SSO_ARN, account=ACCT, **kw):
    iam, ct, lines = iam or FakeIam(), ct or FakeCt(), []
    rc = T.run(iam, ct, lambda: (account, arn), SPEC, args(**kw), now=NOW, out=lines.append)
    return rc, "\n".join(lines), iam


class Report(unittest.TestCase):
    def test_report_never_writes_and_ranks_safest_first(self):
        rc, out, iam = go(arn=USER_ARN)
        self.assertEqual(iam.writes(), [])
        self.assertEqual(rc, 1)  # credentials remain
        order = [out.index(k) for k in (K_NEVER, K_OLD, K_RECENT)]
        self.assertEqual(order, sorted(order), "never-used first, then longest idle, then recently used")
        self.assertIn(f"NEXT: python3 tools/wafr_keys.py --deactivate {K_NEVER}", out)
        self.assertIn("IN USE", out.split(K_RECENT)[1].split("\n")[0])

    def test_report_shows_where_a_key_was_last_used(self):
        _rc, out, _ = go(arn=USER_ARN)
        self.assertIn("via dynamodb/us-east-1", out)

    def test_inactive_keys_are_not_counted_as_remaining(self):
        iam = FakeIam(keys={K_OFF: dict(user="svc-c", status="Inactive", created=ago(500), used=ago(60))}, pw={})
        rc, out, _ = go(iam, arn=USER_ARN)
        self.assertEqual(rc, 0)
        self.assertIn("0 long-lived credential(s) remain", out)

    def test_console_passwords_and_root_keys_count(self):
        iam = FakeIam(keys={}, pw={"human": ago(3)}, root_keys=1)
        rc, out, _ = go(iam, arn=USER_ARN)
        self.assertEqual(rc, 1)
        self.assertIn("2 long-lived credential(s) remain", out)
        self.assertIn("root account holds 1 access key", out)

    def test_nothing_safe_when_everything_is_recent(self):
        iam = FakeIam(keys={K_RECENT: dict(user="svc-b", status="Active", created=ago(300), used=ago(1))}, pw={})
        _rc, out, _ = go(iam, arn=USER_ARN)
        self.assertIn("nothing is safe to retire yet", out)

    def test_unreadable_user_is_reported_not_skipped(self):
        iam = FakeIam()
        orig = iam.list_access_keys

        def boom(UserName):
            if UserName == "svc-a":
                raise CE("AccessDenied")
            return orig(UserName)
        iam.list_access_keys = boom
        rc, out, _ = go(iam, arn=USER_ARN)
        self.assertIn("BLOCKED    svc-a", out)
        self.assertEqual(rc, 1)


class Guards(unittest.TestCase):
    def test_wrong_account_refused_and_nothing_touched(self):
        rc, out, iam = go(account="620534471984", deactivate=K_NEVER, apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("620534471984", out)
        self.assertEqual(iam.calls, [])

    def test_every_write_refused_off_sso_dry_run_included(self):
        for kw in (dict(deactivate=K_NEVER), dict(delete=K_OFF), dict(remove_console="human")):
            rc, out, iam = go(arn=USER_ARN, apply=True, **kw)
            self.assertEqual(rc, 2, kw)
            self.assertIn("IAM Identity Center session", out)
            self.assertEqual(iam.calls, [], f"{kw}: nothing may even be read before the SSO check")

    def test_an_unknown_caller_is_not_sso(self):
        rc, _out, iam = go(arn="", deactivate=K_NEVER, apply=True)
        self.assertEqual((rc, iam.writes()), (2, []))

    def test_an_iam_user_named_like_sso_is_not_sso(self):
        rc, _o, iam = go(arn=f"arn:aws:iam::{ACCT}:user/AWSReservedSSO_fake", deactivate=K_NEVER, apply=True)
        self.assertEqual((rc, iam.writes()), (2, []))

    def test_one_action_at_a_time(self):
        rc, _o, iam = go(deactivate=K_NEVER, delete=K_OFF, apply=True)
        self.assertEqual((rc, iam.calls), (2, []))

    def test_bare_apply_does_nothing(self):
        rc, out, iam = go(apply=True)
        self.assertEqual((rc, iam.calls), (2, []))
        self.assertIn("needs an action", out)

    def test_malformed_ids_refused_before_any_call(self):
        for bad in ("short", "akiaexampleexample1", "AKIA EXAMPLE 0000001", "AKIA;rm -rf /0000000"):
            rc, out, iam = go(deactivate=bad, apply=True)
            self.assertEqual((rc, iam.calls), (1, []), bad)
            self.assertIn("is not an access key id", out)


class Deactivate(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        rc, out, iam = go(deactivate=K_NEVER)
        self.assertEqual((rc, iam.writes()), (0, []))
        self.assertIn("Dry run only", out)
        self.assertIn(f"--reactivate {K_NEVER}", out)

    def test_apply_deactivates_exactly_that_key_and_names_the_rollback(self):
        rc, out, iam = go(deactivate=K_OLD, apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(iam.writes(), [("update_access_key", "human", K_OLD, "Inactive")])
        self.assertEqual(iam.keys[K_NEVER]["status"], "Active")
        self.assertIn(f"--reactivate {K_OLD} --apply", out)

    def test_never_used_key_is_a_valid_candidate(self):
        _rc, _o, iam = go(deactivate=K_NEVER, apply=True)
        self.assertEqual(iam.keys[K_NEVER]["status"], "Inactive")

    def test_recently_used_key_is_refused_with_where_it_was_used(self):
        rc, out, iam = go(deactivate=K_RECENT, apply=True)
        self.assertEqual((rc, iam.writes()), (1, []))
        self.assertIn("via s3/us-east-1", out)
        self.assertIn("--allow-recent", out)

    def test_the_boundary_is_seven_days(self):
        for days, want in ((6, []), (7, ["update_access_key"])):
            iam = FakeIam(keys={K_RECENT: dict(user="u", status="Active", created=ago(300), used=ago(days))}, pw={})
            go(iam, deactivate=K_RECENT, apply=True)
            self.assertEqual([c[0] for c in iam.writes()], want, days)

    def test_allow_recent_overrides_only_the_recency_guard(self):
        _rc, _o, iam = go(deactivate=K_RECENT, apply=True, allow_recent=True)
        self.assertEqual(iam.keys[K_RECENT]["status"], "Inactive")
        _rc, _o, iam = go(arn=USER_ARN, deactivate=K_RECENT, apply=True, allow_recent=True)
        self.assertEqual(iam.writes(), [], "allow-recent never overrides the SSO guard")

    def test_already_inactive_is_a_no_op(self):
        rc, _o, iam = go(deactivate=K_OFF, apply=True)
        self.assertEqual((rc, iam.writes()), (0, []))

    def test_unknown_key_is_blocked_not_guessed(self):
        rc, out, iam = go(deactivate="AKIAEXAMPLEMISSING01", apply=True)
        self.assertEqual((rc, iam.writes()), (1, []))
        self.assertIn("BLOCKED", out)


class ByUser(unittest.TestCase):
    def test_user_ref_picks_that_users_single_key(self):
        _rc, _o, iam = go(deactivate="user:human", apply=True)
        self.assertEqual(iam.writes(), [("update_access_key", "human", K_OLD, "Inactive")])

    def test_user_ref_for_delete_wants_the_inactive_one(self):
        ct = FakeCt([event(K_OFF, "Inactive", ago(9))])
        _rc, _o, iam = go(delete="user:svc-c", apply=True, ct=ct)
        self.assertEqual(iam.writes(), [("delete_access_key", "svc-c", K_OFF)])

    def test_zero_or_several_keys_is_refused_never_guessed(self):
        rc, out, iam = go(deactivate="user:svc-c", apply=True)  # svc-c has only an Inactive key
        self.assertEqual((rc, iam.writes()), (1, []))
        self.assertIn("exactly one", out)
        iam = FakeIam(keys={K_OLD: dict(user="u", status="Active", created=ago(9), used=ago(50)),
                            K_NEVER: dict(user="u", status="Active", created=ago(9), used=None)}, pw={})
        rc, out, iam = go(iam, deactivate="user:u", apply=True)
        self.assertEqual((rc, iam.writes()), (1, []))
        self.assertIn("has 2 Active", out)

    def test_user_ref_does_not_bypass_the_sso_or_recency_guards(self):
        rc, _o, iam = go(arn=USER_ARN, deactivate="user:human", apply=True)
        self.assertEqual((rc, iam.writes()), (2, []))
        rc, _o, iam = go(deactivate="user:svc-b", apply=True)  # used 1 day ago
        self.assertEqual((rc, iam.writes()), (1, []))

    def test_bad_user_name_refused(self):
        rc, _o, iam = go(deactivate="user:a b;c", apply=True)
        self.assertEqual((rc, iam.writes()), (1, []))


class Reactivate(unittest.TestCase):
    def test_rollback_works_without_sso(self):
        rc, _o, iam = go(arn=USER_ARN, reactivate=K_OFF, apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(iam.writes(), [("update_access_key", "svc-c", K_OFF, "Active")])

    def test_reactivate_dry_run_and_noop(self):
        _rc, _o, iam = go(reactivate=K_OFF)
        self.assertEqual(iam.writes(), [])
        _rc, out, iam = go(reactivate=K_NEVER, apply=True)
        self.assertEqual(iam.writes(), [])
        self.assertIn("already Active", out)


class Delete(unittest.TestCase):
    def ct(self, days, status="Inactive", shape="camel"):
        return FakeCt([event(K_OFF, status, ago(days), shape)])

    def test_active_key_is_never_deleted(self):
        rc, out, iam = go(delete=K_NEVER, apply=True, ct=self.ct(30))
        self.assertEqual((rc, iam.writes()), (1, []))
        self.assertIn("Deactivate it first", out)

    def test_inside_the_window_is_refused_and_says_when(self):
        rc, out, iam = go(delete=K_OFF, apply=True, ct=self.ct(3))
        self.assertEqual((rc, iam.writes()), (1, []))
        self.assertIn("Come back in 4", out)

    def test_after_the_window_deletes_exactly_that_key(self):
        rc, _o, iam = go(delete=K_OFF, apply=True, ct=self.ct(8))
        self.assertEqual(rc, 0)
        self.assertEqual(iam.writes(), [("delete_access_key", "svc-c", K_OFF)])
        self.assertIn(K_NEVER, iam.keys)

    def test_dry_run_deletes_nothing_and_says_permanent(self):
        _rc, out, iam = go(delete=K_OFF, ct=self.ct(8))
        self.assertEqual(iam.writes(), [])
        self.assertIn("cannot be undone", out)

    def test_cloudtrail_field_case_does_not_matter(self):
        _rc, _o, iam = go(delete=K_OFF, apply=True, ct=self.ct(9, shape="pascal"))
        self.assertEqual(len(iam.writes()), 1)

    def test_newest_event_wins_a_reactivation_after_deactivation_blocks_delete(self):
        ct = FakeCt([event(K_OFF, "Inactive", ago(20)), event(K_OFF, "Active", ago(10))])
        rc, out, iam = go(delete=K_OFF, apply=True, ct=ct)
        self.assertEqual((rc, iam.writes()), (1, []))
        self.assertIn("sets it Active", out)

    def test_another_keys_events_do_not_count(self):
        ct = FakeCt([event("AKIAEXAMPLEOTHER0009", "Inactive", ago(30))])
        rc, out, iam = go(delete=K_OFF, apply=True, ct=ct)
        self.assertEqual((rc, iam.writes()), (1, []))
        self.assertIn("no UpdateAccessKey record", out)

    def test_unreadable_cloudtrail_blocks_it_never_assumes(self):
        rc, out, iam = go(delete=K_OFF, apply=True, ct=FakeCt(fail=True))
        self.assertEqual((rc, iam.writes()), (1, []))
        self.assertIn("CloudTrail unreadable", out)

    def test_attested_date_is_used_only_where_cloudtrail_is_silent(self):
        since = (NOW - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
        _rc, out, iam = go(delete=K_OFF, apply=True, ct=FakeCt(), observed_since=since)
        self.assertEqual(len(iam.writes()), 1)
        self.assertIn("YOUR attested date", out)

    def test_attested_date_cannot_shorten_what_cloudtrail_shows(self):
        old = (NOW - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        rc, _o, iam = go(delete=K_OFF, apply=True, ct=self.ct(2), observed_since=old)
        self.assertEqual((rc, iam.writes()), (1, []), "the later date wins")

    def test_bad_attested_date_refused(self):
        rc, _o, iam = go(delete=K_OFF, apply=True, ct=FakeCt(), observed_since="yesterday")
        self.assertEqual((rc, iam.writes()), (2, []))


class RemoveConsole(unittest.TestCase):
    def test_recent_sign_in_refused(self):
        rc, out, iam = go(remove_console="human", apply=True)
        self.assertEqual((rc, iam.writes()), (1, []))
        self.assertIn("signed in 3 day(s) ago", out)

    def test_idle_password_removed_and_keys_untouched(self):
        iam = FakeIam(pw={"human": ago(40)})
        rc, _o, iam = go(iam, remove_console="human", apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(iam.writes(), [("delete_login_profile", "human")])
        self.assertEqual(iam.keys[K_OLD]["status"], "Active")

    def test_never_signed_in_is_removable_and_dry_run_is_safe(self):
        iam = FakeIam(pw={"human": None})
        _rc, _o, iam = go(iam, remove_console="human")
        self.assertEqual(iam.writes(), [])
        _rc, _o, iam = go(FakeIam(pw={"human": None}), remove_console="human", apply=True)
        self.assertEqual(len(iam.writes()), 1)

    def test_no_password_is_a_no_op(self):
        rc, _o, iam = go(remove_console="svc-a", apply=True)
        self.assertEqual((rc, iam.writes()), (0, []))

    def test_malformed_user_refused(self):
        rc, _o, iam = go(remove_console="a b;c", apply=True)
        self.assertEqual((rc, iam.calls), (2, []))


class Repo(unittest.TestCase):
    def test_the_tool_never_deletes_a_user_or_touches_root(self):
        src = (ROOT / "tools" / "wafr_keys.py").read_text()
        for forbidden in ("delete_user", "create_access_key", "put_user_policy", "attach_user_policy", "delete_virtual_mfa", "deactivate_mfa"):
            self.assertNotIn(forbidden + "(", src)

    def test_no_workflow_runs_it(self):
        """Its output names users and key ids; Actions logs of a public repository are public."""
        wf = ROOT / ".github" / "workflows"
        hits = [p.name for p in wf.glob("*.y*ml") if "wafr_keys" in p.read_text()] if wf.exists() else []
        self.assertEqual(hits, [])

    def test_no_key_id_or_person_in_the_files_of_this_feature(self):
        import re
        for f in (ROOT / "tools" / "wafr_keys.py", ROOT / "docs" / "security" / "identity_center_runbook.md"):
            txt = f.read_text()
            for m in re.findall(r"\bAKIA[A-Z0-9]{12,}\b", txt):
                self.assertTrue("EXAMPLE" in m, f"{f.name}: a real-looking access key id: {m}")
            self.assertNotRegex(txt, r"[\w.+-]+@[\w-]+\.[a-z]{2,}", f"{f.name}: an e-mail address in a public repo")


try:
    import boto3
    from botocore.stub import Stubber
    HAVE_BOTO = True
except Exception:  # pragma: no cover
    HAVE_BOTO = False


@unittest.skipUnless(HAVE_BOTO, "boto3 not installed: the real-model layer did not run")
class RealModels(unittest.TestCase):
    """Every call below is validated against the REAL service model by Stubber (request AND response)."""

    def client(self, name):
        c = boto3.client(name, region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x")
        return c, Stubber(c)

    def test_report_shapes(self):
        iam, s = self.client("iam")
        s.add_response("list_users", {"Users": [{"Path": "/", "UserName": "u", "UserId": "AIDAEXAMPLE0000000", "Arn": f"arn:aws:iam::{ACCT}:user/u",
                                                  "CreateDate": ago(900), "PasswordLastUsed": ago(2)}], "IsTruncated": False})
        s.add_response("list_access_keys", {"AccessKeyMetadata": [{"UserName": "u", "AccessKeyId": K_OLD, "Status": "Active", "CreateDate": ago(900)}]},
                       {"UserName": "u"})
        s.add_response("get_access_key_last_used", {"UserName": "u", "AccessKeyLastUsed": {"LastUsedDate": ago(200), "ServiceName": "s3", "Region": "us-east-1"}},
                       {"AccessKeyId": K_OLD})
        s.add_response("get_login_profile", {"LoginProfile": {"UserName": "u", "CreateDate": ago(900)}}, {"UserName": "u"})
        s.add_response("get_account_summary", {"SummaryMap": {"AccountAccessKeysPresent": 0}})
        with s:
            lines = []
            rc = T.report(iam, NOW, lines.append)
            s.assert_no_pending_responses()
        self.assertEqual(rc, 1)
        self.assertIn(K_OLD, "\n".join(lines))

    def test_never_used_key_response_has_no_date_and_parses(self):
        """The real model returns ServiceName 'N/A' and no LastUsedDate for a key that was never used."""
        iam, s = self.client("iam")
        s.add_response("list_users", {"Users": [{"Path": "/", "UserName": "u", "UserId": "AIDAEXAMPLE0000000", "Arn": f"arn:aws:iam::{ACCT}:user/u",
                                                  "CreateDate": ago(9)}], "IsTruncated": False})
        s.add_response("list_access_keys", {"AccessKeyMetadata": [{"UserName": "u", "AccessKeyId": K_NEVER, "Status": "Active", "CreateDate": ago(9)}]},
                       {"UserName": "u"})
        s.add_response("get_access_key_last_used", {"UserName": "u", "AccessKeyLastUsed": {"ServiceName": "N/A", "Region": "N/A"}}, {"AccessKeyId": K_NEVER})
        s.add_client_error("get_login_profile", "NoSuchEntity")
        with s:
            keys, pw, problems = T.inventory(iam, NOW)
        self.assertEqual((keys[0]["used"], keys[0]["where"], pw, problems), (None, "", [], []))

    def test_deactivate_and_reactivate_and_delete_shapes(self):
        iam, s = self.client("iam")
        lu = {"UserName": "u", "AccessKeyLastUsed": {"ServiceName": "N/A", "Region": "N/A"}}

        def meta(status):
            return {"AccessKeyMetadata": [{"UserName": "u", "AccessKeyId": K_NEVER, "Status": status, "CreateDate": ago(9)}]}
        # the order the calls happen in: locate (last_used, list) then the write, three times
        for status, write, params in (("Active", "update_access_key", {"Status": "Inactive"}),
                                      ("Inactive", "update_access_key", {"Status": "Active"}),
                                      ("Inactive", "delete_access_key", {})):
            s.add_response("get_access_key_last_used", lu, {"AccessKeyId": K_NEVER})
            s.add_response("list_access_keys", meta(status), {"UserName": "u"})
            s.add_response(write, {}, {"UserName": "u", "AccessKeyId": K_NEVER, **params})
        ct, cs = self.client("cloudtrail")
        cs.add_response("lookup_events", {"Events": [{"EventId": "e", "EventName": "UpdateAccessKey", "EventTime": ago(9),
                                                      "CloudTrailEvent": json.dumps({"requestParameters": {"userName": "u", "accessKeyId": K_NEVER, "status": "Inactive"}})}]},
                        {"LookupAttributes": [{"AttributeKey": "EventName", "AttributeValue": "UpdateAccessKey"}], "StartTime": NOW - datetime.timedelta(days=90), "EndTime": NOW})
        with s, cs:
            sink = lambda *_: None  # noqa: E731
            self.assertEqual(T.do_deactivate(iam, K_NEVER, True, False, NOW, sink), 0)
            self.assertEqual(T.do_reactivate(iam, K_NEVER, True, sink), 0)
            self.assertEqual(T.do_delete(iam, ct, K_NEVER, True, None, NOW, sink), 0)
            s.assert_no_pending_responses()
            cs.assert_no_pending_responses()

    def test_remove_console_shapes(self):
        iam, s = self.client("iam")
        s.add_response("get_user", {"User": {"Path": "/", "UserName": "u", "UserId": "AIDAEXAMPLE0000000", "Arn": f"arn:aws:iam::{ACCT}:user/u", "CreateDate": ago(900),
                                              "PasswordLastUsed": ago(40)}}, {"UserName": "u"})
        s.add_response("get_login_profile", {"LoginProfile": {"UserName": "u", "CreateDate": ago(900)}}, {"UserName": "u"})
        s.add_response("delete_login_profile", {}, {"UserName": "u"})
        with s:
            self.assertEqual(T.do_remove_console(iam, "u", True, False, NOW, lambda *_: None), 0)
            s.assert_no_pending_responses()

    def test_caller_identity_shape_carries_the_arn_the_sso_check_reads(self):
        sts, s = self.client("sts")
        s.add_response("get_caller_identity", {"UserId": "AROAEXAMPLE0000000:someone", "Account": ACCT, "Arn": SSO_ARN})
        with s:
            r = sts.get_caller_identity()
        self.assertIn(T.SSO_MARK, r["Arn"])

    def test_the_real_sso_arn_form_is_matched_and_a_plain_role_is_not(self):
        self.assertIn(T.SSO_MARK, SSO_ARN)
        self.assertNotIn(T.SSO_MARK, f"arn:aws:sts::{ACCT}:assumed-role/relayshield-ir-responder/x")


if __name__ == "__main__":
    unittest.main()
