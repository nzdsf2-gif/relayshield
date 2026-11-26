"""tools/wafr_identity.py: SEC 2, identities (IAM Identity Center).

Two layers, because a fake written by the same hand as the code proves nothing about the library:
  * Fake clients test the DECISIONS (a bare --apply never creates the Organization or edits the responder trust,
    nothing is ever removed or changed on an existing permission set, a legacy report never writes,
    the wrong account is refused, a dry run writes nothing).
  * botocore's Stubber, over the REAL organizations / sso-admin / identitystore / iam models, tests the SHAPES:
    every request the tool makes is validated against the model and every response it parses is a legal one.
    Skipped (and said so) where boto3 is not installed; CI installs it from tests_requirements.txt."""
import copy
import datetime
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import wafr_identity as T  # noqa: E402

SPEC = json.load(open(ROOT / "tools" / "wafr_identity_spec.json"))
ACCT = SPEC["account"]
INST = {"InstanceArn": "arn:aws:sso:::instance/ssoins-0123456789abcdef", "IdentityStoreId": "d-0123456789"}
PSA = "arn:aws:sso:::permissionSet/ssoins-0123456789abcdef/ps-{}"
RID = "11111111-2222-3333-4444-555555555555"
ADMIN, RO = SPEC["permission_sets"][1], SPEC["permission_sets"][0]


class CE(Exception):
    def __init__(self, c):
        self.response = {"Error": {"Code": c}}


class Fake:
    """One object standing in for all four clients, recording every call. State is plain dicts."""

    def __init__(self, org="mine", instance=True, sets=None, groups=None, assignments=None, users=None, role_trust="mfa", iam_users=None):
        self.org, self.instance = org, instance
        self.sets = sets if sets is not None else {}          # name -> dict(arn, session, managed[])
        self.groups = groups if groups is not None else {}    # display name -> id
        self.assignments = assignments if assignments is not None else set()  # (psa, gid)
        self.users = users or {}                              # user name -> id
        self.members = set()
        self.trust = {"Version": "2012-10-17", "Statement": [{"Sid": "AccountPrincipalsWithMfaOnly", "Effect": "Allow"}]} if role_trust == "mfa" else None
        self.iam_users = iam_users or {}
        self.calls = []

    def writes(self):
        return [c for c in self.calls if c[0].split(".")[1].startswith(("create_", "attach_", "update_", "provision_", "put_", "delete_", "detach_"))]

    def _rec(self, n, *a):
        self.calls.append((n,) + a)

    # organizations
    def describe_organization(self):
        self._rec("org.describe_organization")
        if self.org is None:
            raise CE("AWSOrganizationsNotInUseException")
        return {"Organization": {"MasterAccountId": ACCT if self.org == "mine" else "111111111111",
                                 "FeatureSet": "CONSOLIDATED_BILLING" if self.org == "billing" else "ALL"}}

    def create_organization(self, FeatureSet):
        self._rec("org.create_organization", FeatureSet)
        self.org = "mine"

    # sso-admin
    def list_instances(self):
        return {"Instances": [INST] if self.instance else []}

    def list_permission_sets(self, InstanceArn, NextToken=None):
        return {"PermissionSets": [v["arn"] for v in self.sets.values()]}

    def describe_permission_set(self, InstanceArn, PermissionSetArn):
        for n, v in self.sets.items():
            if v["arn"] == PermissionSetArn:
                return {"PermissionSet": {"Name": n, "PermissionSetArn": PermissionSetArn, "SessionDuration": v["session"]}}
        raise CE("ResourceNotFoundException")

    def list_managed_policies_in_permission_set(self, InstanceArn, PermissionSetArn, NextToken=None):
        for v in self.sets.values():
            if v["arn"] == PermissionSetArn:
                return {"AttachedManagedPolicies": [{"Name": p.rsplit("/", 1)[-1], "Arn": p} for p in v["managed"]]}
        raise CE("ResourceNotFoundException")

    def create_permission_set(self, InstanceArn, Name, Description, SessionDuration):
        self._rec("sso.create_permission_set", Name, SessionDuration)
        arn = PSA.format(len(self.sets))
        self.sets[Name] = {"arn": arn, "session": SessionDuration, "managed": []}
        return {"PermissionSet": {"PermissionSetArn": arn, "Name": Name}}

    def attach_managed_policy_to_permission_set(self, InstanceArn, PermissionSetArn, ManagedPolicyArn):
        self._rec("sso.attach_managed_policy_to_permission_set", PermissionSetArn, ManagedPolicyArn)
        for v in self.sets.values():
            if v["arn"] == PermissionSetArn:
                v["managed"].append(ManagedPolicyArn)

    def provision_permission_set(self, InstanceArn, PermissionSetArn, TargetType):
        self._rec("sso.provision_permission_set", PermissionSetArn, TargetType)

    def list_account_assignments(self, InstanceArn, AccountId, PermissionSetArn, NextToken=None):
        return {"AccountAssignments": [{"AccountId": AccountId, "PermissionSetArn": p, "PrincipalType": "GROUP", "PrincipalId": g}
                                       for p, g in self.assignments if p == PermissionSetArn]}

    def create_account_assignment(self, InstanceArn, TargetId, TargetType, PermissionSetArn, PrincipalType, PrincipalId):
        self._rec("sso.create_account_assignment", TargetId, PermissionSetArn, PrincipalType, PrincipalId)
        self.assignments.add((PermissionSetArn, PrincipalId))

    # identitystore
    def get_group_id(self, IdentityStoreId, AlternateIdentifier):
        n = AlternateIdentifier["UniqueAttribute"]["AttributeValue"]
        if n not in self.groups:
            raise CE("ResourceNotFoundException")
        return {"GroupId": self.groups[n]}

    def create_group(self, IdentityStoreId, DisplayName, Description):
        self._rec("ids.create_group", DisplayName)
        self.groups[DisplayName] = f"gid-{len(self.groups)}"

    def get_user_id(self, IdentityStoreId, AlternateIdentifier):
        n = AlternateIdentifier["UniqueAttribute"]["AttributeValue"]
        if n not in self.users:
            raise CE("ResourceNotFoundException")
        return {"UserId": self.users[n]}

    def is_member_in_groups(self, IdentityStoreId, MemberId, GroupIds):
        return {"Results": [{"GroupId": g, "MemberId": MemberId, "MembershipExists": (MemberId["UserId"], g) in self.members} for g in GroupIds]}

    def create_group_membership(self, IdentityStoreId, GroupId, MemberId):
        self._rec("ids.create_group_membership", GroupId, MemberId["UserId"])
        self.members.add((MemberId["UserId"], GroupId))

    # iam
    def get_role(self, RoleName):
        if self.trust is None:
            raise CE("NoSuchEntity")
        return {"Role": {"AssumeRolePolicyDocument": copy.deepcopy(self.trust)}}

    def update_assume_role_policy(self, RoleName, PolicyDocument):
        self._rec("iam.update_assume_role_policy", RoleName)
        self.trust = json.loads(PolicyDocument)

    def list_users(self, Marker=None):
        return {"Users": [{"UserName": n} for n in self.iam_users], "IsTruncated": False}

    def list_access_keys(self, UserName):
        return {"AccessKeyMetadata": [{"AccessKeyId": f"AKIA{UserName}", "Status": s} for s in self.iam_users[UserName].get("keys", [])]}

    def get_access_key_last_used(self, AccessKeyId):
        return {"AccessKeyLastUsed": {"LastUsedDate": datetime.datetime(2026, 11, 1)}}

    def get_login_profile(self, UserName):
        if not self.iam_users[UserName].get("console"):
            raise CE("NoSuchEntity")
        return {}


def run(fake, apply=False, steps=T.STEPS, user=None, explicit=False, check=False, account=ACCT):
    lines = []
    clients = {k: fake for k in ("organizations", "sso-admin", "identitystore", "iam")}
    rc = T.run(clients, lambda: account, SPEC, apply, steps, check, user, explicit, out=lines.append)
    return rc, "\n".join(lines)


class Decisions(unittest.TestCase):
    def test_wrong_account_refused_and_nothing_touched(self):
        f = Fake()
        rc, out = run(f, apply=True, account="620534471984")
        self.assertEqual(rc, 2)
        self.assertIn("Refusing to run", out)
        self.assertEqual(f.calls, [])

    def test_dry_run_writes_nothing_and_reports_todo(self):
        f = Fake()
        rc, out = run(f)
        self.assertEqual(f.writes(), [])
        self.assertIn("TODO", out)

    def test_apply_builds_sets_groups_assignments(self):
        f = Fake()
        rc, out = run(f, apply=True)
        self.assertEqual(set(f.sets), {RO["name"], ADMIN["name"]})
        self.assertEqual(f.sets["RelayShieldAdmin"]["managed"], ADMIN["managed"])
        self.assertEqual(set(f.sets["RelayShieldReadOnly"]["managed"]), set(RO["managed"]))
        self.assertEqual(f.sets["RelayShieldAdmin"]["session"], "PT4H")
        self.assertEqual(set(f.groups), {g["name"] for g in SPEC["groups"]})
        self.assertEqual(len(f.assignments), 2)
        # each group got ITS permission set, not the other one
        want = {(f.sets[g["permission_set"]]["arn"], f.groups[g["name"]]) for g in SPEC["groups"]}
        self.assertEqual(f.assignments, want)
        self.assertEqual(rc, 0, out)

    def test_apply_is_idempotent(self):
        f = Fake()
        run(f, apply=True)
        n = len(f.writes())
        rc, out = run(f, apply=True)
        self.assertEqual(len(f.writes()), n, "a second apply must change nothing")
        self.assertEqual(rc, 0, out)

    def test_bare_apply_never_creates_org_or_edits_responder_trust(self):
        f = Fake(org=None)
        run(f, apply=True)
        run(f, apply=True, steps=T.STEPS, explicit=False)
        self.assertIsNone(f.org)
        self.assertFalse([c for c in f.calls if c[0] in ("org.create_organization", "iam.update_assume_role_policy")])

    def test_explicit_org_step_creates_it(self):
        f = Fake(org=None)
        run(f, apply=True, steps=("org",), explicit=True)
        self.assertEqual([c for c in f.calls if c[0] == "org.create_organization"], [("org.create_organization", "ALL")])

    def test_member_of_another_org_is_blocked_not_created(self):
        for org in ("other", "billing"):
            f = Fake(org=org)
            rc, out = run(f, apply=True, steps=("org",), explicit=True)
            self.assertEqual(rc, 1)
            self.assertIn("BLOCKED", out)
            self.assertFalse(f.writes())

    def test_no_instance_blocks_everything_after_it_and_writes_nothing(self):
        f = Fake(instance=False)
        rc, out = run(f, apply=True)
        self.assertEqual(rc, 1)
        self.assertIn("ANDREW CLICKS", out)
        self.assertEqual(f.writes(), [])

    def test_existing_set_is_never_changed_only_reported(self):
        f = Fake(sets={"RelayShieldReadOnly": {"arn": PSA.format("a"), "session": "PT12H",
                                              "managed": RO["managed"] + ["arn:aws:iam::aws:policy/PowerUserAccess"]}})
        rc, out = run(f, apply=True)
        self.assertIn("PowerUserAccess", out)
        self.assertIn("PT12H", out)
        self.assertEqual(rc, 1)
        bad = [c for c in f.calls if "detach" in c[0] or "update_permission_set" in c[0] or "delete" in c[0]]
        self.assertEqual(bad, [])
        self.assertIn("PowerUserAccess", " ".join(f.sets["RelayShieldReadOnly"]["managed"]))

    def test_missing_policy_on_existing_set_is_attached_and_reprovisioned(self):
        f = Fake(sets={"RelayShieldReadOnly": {"arn": PSA.format("a"), "session": "PT8H", "managed": RO["managed"][:1]}})
        run(f, apply=True)
        self.assertEqual(set(f.sets["RelayShieldReadOnly"]["managed"]), set(RO["managed"]))
        self.assertTrue([c for c in f.calls if c[0] == "sso.provision_permission_set" and c[2] == "ALL_PROVISIONED_ACCOUNTS"])

    def test_membership_unknown_user_blocked_known_user_added_to_both(self):
        f = Fake()
        rc, out = run(f, apply=True, user="nobody")
        self.assertIn("ANDREW CLICKS", out)
        f2 = Fake(users={"someone": "uid-1"})
        rc, out = run(f2, apply=True, user="someone")
        self.assertEqual(rc, 0, out)
        self.assertEqual({g for (u, g) in f2.members}, set(f2.groups.values()))
        n = len(f2.writes())
        run(f2, apply=True, user="someone")
        self.assertEqual(len(f2.writes()), n)

    def test_membership_skipped_without_add_user(self):
        f = Fake()
        run(f, apply=True)
        self.assertFalse([c for c in f.calls if c[0] == "ids.create_group_membership"])

    def test_legacy_reports_keys_and_passwords_and_never_writes(self):
        f = Fake(iam_users={"a": {"keys": ["Active"]}, "b": {"console": True}, "c": {"keys": ["Inactive"]}})
        rc, out = run(f, apply=True, steps=("legacy",), explicit=True)
        self.assertEqual(rc, 1)
        self.assertIn("active access key", out)
        self.assertIn("console password", out)
        self.assertNotIn("\n  ELSEWHERE c", out, "an inactive key with no console password is not a long-lived credential")
        self.assertEqual(f.writes(), [])

    def test_legacy_clean_account_passes(self):
        rc, out = run(Fake(iam_users={"c": {"keys": ["Inactive"]}}), steps=("legacy",))
        self.assertEqual(rc, 0, out)

    def test_responder_trust_is_merged_not_replaced_and_idempotent(self):
        f = Fake()
        before = copy.deepcopy(f.trust)
        run(f, apply=True, steps=("responder",), explicit=True)
        sids = [s["Sid"] for s in f.trust["Statement"]]
        self.assertEqual(sids, [s["Sid"] for s in before["Statement"]] + ["IdentityCenterAdminRole"])
        n = len(f.writes())
        run(f, apply=True, steps=("responder",), explicit=True)
        self.assertEqual(len(f.writes()), n)

    def test_responder_statement_admits_only_the_admin_sso_role(self):
        st = T.sso_statement(SPEC)
        pat = st["Condition"]["ArnLike"]["aws:PrincipalArn"]
        self.assertIn("AWSReservedSSO_RelayShieldAdmin_", pat)
        self.assertNotIn("ReadOnly", pat)
        self.assertNotIn("aws:MultiFactorAuthPresent", json.dumps(st))

    def test_missing_responder_role_is_blocked_not_created(self):
        f = Fake(role_trust=None)
        rc, out = run(f, apply=True, steps=("responder",), explicit=True)
        self.assertEqual(rc, 1)
        self.assertEqual(f.writes(), [])

    def test_check_mode_fails_on_a_todo(self):
        rc, _ = run(Fake(), check=True)
        self.assertEqual(rc, 1)

    def test_apply_and_check_are_opposites(self):
        self.assertEqual(run(Fake(), apply=True, check=True)[0], 2)


class Spec(unittest.TestCase):
    def test_spec_is_internally_consistent(self):
        names = {p["name"] for p in SPEC["permission_sets"]}
        for g in SPEC["groups"]:
            self.assertIn(g["permission_set"], names)
        self.assertIn(SPEC["responder_sso_permission_set"], names)
        for p in SPEC["permission_sets"]:
            self.assertRegex(p["session"], r"^PT\d+H$")
            self.assertTrue(1 <= int(p["session"][2:-1]) <= 12, "IAM Identity Center sessions run 1 to 12 hours")
            self.assertLessEqual(len(p["name"]), 32)
            self.assertRegex(p["name"], r"^[\w+=,.@-]+$")
            for m in p["managed"]:
                self.assertTrue(m.startswith("arn:aws:iam::aws:policy/"))

    def test_admin_is_only_on_the_admin_set_and_it_is_the_shorter_session(self):
        holders = [p["name"] for p in SPEC["permission_sets"] if any(m.endswith("/AdministratorAccess") for m in p["managed"])]
        self.assertEqual(holders, ["RelayShieldAdmin"])
        self.assertLess(int(ADMIN["session"][2:-1]), int(RO["session"][2:-1]))

    def test_no_person_or_contact_detail_in_this_public_repo(self):
        for path in (ROOT / "tools" / "wafr_identity.py", ROOT / "tools" / "wafr_identity_spec.json"):
            text = path.read_text()
            self.assertNotRegex(text, r"[\w.+-]+@[\w-]+\.[\w.]+", f"{path.name} contains an e-mail address")
        self.assertNotIn("620534471984", (ROOT / "tools" / "wafr_identity_spec.json").read_text())

    def test_the_legacy_step_is_not_in_any_workflow(self):
        for wf in (ROOT / ".github" / "workflows").glob("*.y*ml"):
            self.assertNotIn("wafr_identity", wf.read_text(), f"{wf.name}: Actions logs of a public repo are public")


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

    def test_org_shapes(self):
        c, s = self.client("organizations")
        org = {"Id": "o-abcdefghij", "Arn": "arn:aws:organizations::" + ACCT + ":organization/o-abcdefghij", "FeatureSet": "ALL",
               "MasterAccountArn": f"arn:aws:organizations::{ACCT}:account/o-abcdefghij/{ACCT}", "MasterAccountId": ACCT,
               "MasterAccountEmail": "x@example.com", "AvailablePolicyTypes": []}
        s.add_response("describe_organization", {"Organization": org})
        s.add_client_error("describe_organization", "AWSOrganizationsNotInUseException")
        s.add_response("create_organization", {"Organization": org}, {"FeatureSet": "ALL"})
        with s:
            ctx = {}
            self.assertEqual(T.plan_org({"organizations": c}, ctx, SPEC)[0][1], "ok")
            rows = T.plan_org({"organizations": c}, ctx, SPEC)
            self.assertEqual(rows[0][1], "todo")
            self.assertEqual(list(T.apply_org({"organizations": c}, rows)), ["created the organization (all features)"])
            s.assert_no_pending_responses()

    def test_instance_and_permission_set_create_path(self):
        sso, s = self.client("sso-admin")
        psa = PSA.format("1")
        s.add_response("list_instances", {"Instances": [{**INST, "OwnerAccountId": ACCT, "Status": "ACTIVE", "Name": "x"}]})
        s.add_response("list_permission_sets", {"PermissionSets": []}, {"InstanceArn": INST["InstanceArn"]})
        for p in SPEC["permission_sets"]:
            s.add_response("create_permission_set", {"PermissionSet": {"PermissionSetArn": psa, "Name": p["name"]}},
                           {"InstanceArn": INST["InstanceArn"], "Name": p["name"], "Description": p["description"], "SessionDuration": p["session"]})
            for m in p["managed"]:
                s.add_response("attach_managed_policy_to_permission_set", {},
                               {"InstanceArn": INST["InstanceArn"], "PermissionSetArn": psa, "ManagedPolicyArn": m})
        with s:
            c, ctx = {"sso-admin": sso}, {}
            self.assertEqual(T.plan_instance(c, ctx, SPEC)[0][1], "ok")
            rows = T.plan_permission_sets(c, ctx, SPEC)
            self.assertEqual([r[1] for r in rows], ["todo", "todo"])
            self.assertEqual(len(list(T.apply_permission_sets(c, ctx, rows))), 2 + 3)
            s.assert_no_pending_responses()

    def test_existing_set_read_and_reprovision_shapes(self):
        sso, s = self.client("sso-admin")
        psa = PSA.format("1")
        ia = INST["InstanceArn"]
        s.add_response("list_permission_sets", {"PermissionSets": [psa]}, {"InstanceArn": ia})
        s.add_response("describe_permission_set", {"PermissionSet": {"Name": "RelayShieldReadOnly", "PermissionSetArn": psa, "SessionDuration": "PT8H"}},
                       {"InstanceArn": ia, "PermissionSetArn": psa})
        s.add_response("list_managed_policies_in_permission_set",
                       {"AttachedManagedPolicies": [{"Name": "ReadOnlyAccess", "Arn": RO["managed"][0]}]}, {"InstanceArn": ia, "PermissionSetArn": psa})
        s.add_response("attach_managed_policy_to_permission_set", {}, {"InstanceArn": ia, "PermissionSetArn": psa, "ManagedPolicyArn": RO["managed"][1]})
        s.add_response("provision_permission_set",
                       {"PermissionSetProvisioningStatus": {"Status": "IN_PROGRESS", "RequestId": RID, "AccountId": ACCT, "PermissionSetArn": psa}},
                       {"InstanceArn": ia, "PermissionSetArn": psa, "TargetType": "ALL_PROVISIONED_ACCOUNTS"})
        spec = {**SPEC, "permission_sets": [RO]}
        with s:
            c, ctx = {"sso-admin": sso}, {"instance": INST}
            rows = T.plan_permission_sets(c, ctx, spec)
            self.assertEqual(rows[0][1], "todo")
            list(T.apply_permission_sets(c, ctx, rows))
            s.assert_no_pending_responses()

    def test_group_and_assignment_and_membership_shapes(self):
        ids, si = self.client("identitystore")
        sso, ss = self.client("sso-admin")
        store, ia, psa = INST["IdentityStoreId"], INST["InstanceArn"], PSA.format("1")
        gid, uid = "90670000-1111-2222-3333-444444444444", "90670000-5555-6666-7777-888888888888"
        alt = lambda a, v: {"IdentityStoreId": store, "AlternateIdentifier": {"UniqueAttribute": {"AttributePath": a, "AttributeValue": v}}}
        si.add_client_error("get_group_id", "ResourceNotFoundException")
        si.add_response("create_group", {"GroupId": gid, "IdentityStoreId": store, "GroupArn": "arn:aws:identitystore:::group/" + gid, "Revision": "1"},
                        {"IdentityStoreId": store, "DisplayName": "g1", "Description": "d"})
        si.add_response("get_user_id", {"UserId": uid, "IdentityStoreId": store, "UserArn": "arn:aws:identitystore:::user/" + uid}, alt("userName", "u"))
        si.add_response("get_group_id", {"GroupId": gid, "IdentityStoreId": store, "GroupArn": "arn:aws:identitystore:::group/" + gid}, alt("displayName", "g1"))
        si.add_response("is_member_in_groups", {"Results": [{"GroupId": gid, "MemberId": {"UserId": uid}, "MembershipExists": False}]},
                        {"IdentityStoreId": store, "MemberId": {"UserId": uid}, "GroupIds": [gid]})
        si.add_response("create_group_membership", {"MembershipId": gid, "IdentityStoreId": store, "MembershipArn": "arn:aws:identitystore:::membership/" + gid},
                        {"IdentityStoreId": store, "GroupId": gid, "MemberId": {"UserId": uid}})
        ss.add_response("create_account_assignment",
                        {"AccountAssignmentCreationStatus": {"Status": "IN_PROGRESS", "RequestId": RID}},
                        {"InstanceArn": ia, "TargetId": ACCT, "TargetType": "AWS_ACCOUNT", "PermissionSetArn": psa,
                         "PrincipalType": "GROUP", "PrincipalId": gid})
        one = {**SPEC, "groups": [{"name": "g1", "description": "d", "permission_set": "x"}]}
        with si, ss:
            c, ctx = {"identitystore": ids, "sso-admin": sso}, {"instance": INST}
            rows = T.plan_groups(c, ctx, one)
            self.assertEqual(rows[0][1], "todo")
            list(T.apply_groups(c, ctx, rows))
            m = T.plan_membership(c, ctx, one, "u")
            self.assertEqual(m[0][1], "todo")
            list(T.apply_membership(c, ctx, m))
            list(T.apply_assignments(c, ctx, [("g1 -> x", "todo", "", {"psa": psa, "gid": gid})], SPEC))
            si.assert_no_pending_responses()
            ss.assert_no_pending_responses()

    def test_assignment_listing_shape(self):
        sso, s = self.client("sso-admin")
        ia, psa, gid = INST["InstanceArn"], PSA.format("1"), "90670000-1111-2222-3333-444444444444"
        s.add_response("list_account_assignments",
                       {"AccountAssignments": [{"AccountId": ACCT, "PermissionSetArn": psa, "PrincipalType": "GROUP", "PrincipalId": gid}]},
                       {"InstanceArn": ia, "AccountId": ACCT, "PermissionSetArn": psa})
        with s:
            got = list(T.paged(sso.list_account_assignments, "AccountAssignments", InstanceArn=ia, AccountId=ACCT, PermissionSetArn=psa))
            self.assertEqual(got[0]["PrincipalId"], gid)

    def test_iam_shapes_legacy_and_responder(self):
        iam, s = self.client("iam")
        now = datetime.datetime(2026, 11, 1)
        s.add_response("list_users", {"Users": [{"Path": "/", "UserName": "u", "UserId": "AIDAEXAMPLE0000000", "Arn": f"arn:aws:iam::{ACCT}:user/u",
                                                  "CreateDate": now}], "IsTruncated": False})
        s.add_response("list_access_keys", {"AccessKeyMetadata": [{"UserName": "u", "AccessKeyId": "AKIAEXAMPLEEXAMPLE1", "Status": "Active", "CreateDate": now}]},
                       {"UserName": "u"})
        s.add_response("get_access_key_last_used", {"UserName": "u", "AccessKeyLastUsed": {"LastUsedDate": now, "ServiceName": "s3", "Region": "us-east-1"}},
                       {"AccessKeyId": "AKIAEXAMPLEEXAMPLE1"})
        s.add_client_error("get_login_profile", "NoSuchEntity")
        trust = {"Version": "2012-10-17", "Statement": [{"Sid": "AccountPrincipalsWithMfaOnly", "Effect": "Allow",
                                                         "Principal": {"AWS": f"arn:aws:iam::{ACCT}:root"}, "Action": "sts:AssumeRole"}]}
        role = {"Path": "/", "RoleName": SPEC["responder_role"], "RoleId": "AROAEXAMPLE0000000", "Arn": f"arn:aws:iam::{ACCT}:role/{SPEC['responder_role']}",
                "CreateDate": now, "AssumeRolePolicyDocument": json.dumps(trust)}
        s.add_response("get_role", {"Role": role}, {"RoleName": SPEC["responder_role"]})
        merged = copy.deepcopy(trust)
        merged["Statement"].append(T.sso_statement(SPEC))
        s.add_response("update_assume_role_policy", {}, {"RoleName": SPEC["responder_role"], "PolicyDocument": json.dumps(merged)})
        with s:
            c = {"iam": iam}
            rows = T.plan_legacy(c, {}, SPEC)
            self.assertEqual((rows[0][0], rows[0][1]), ("u", "elsewhere"))
            r = T.plan_responder(c, {}, SPEC)
            self.assertEqual(r[0][1], "todo")
            list(T.apply_responder(c, r, SPEC))
            s.assert_no_pending_responses()

    def test_the_trust_statement_is_a_legal_policy_per_the_model(self):
        """update_assume_role_policy validates length and shape of PolicyDocument; the merged document must fit the 2,048-character limit."""
        trust = json.load(open(ROOT / "iam_ir_responder_trust.json"))
        trust["Statement"].append(T.sso_statement(SPEC))
        self.assertLess(len(json.dumps(trust)), 2048)


if __name__ == "__main__":
    unittest.main()
