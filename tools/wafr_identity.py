#!/usr/bin/env python3
"""Well-Architected SEC 2 (identities): move human sign-in to IAM Identity Center. Dry run by default.

    AWS_PROFILE=relayshield python3 tools/wafr_identity.py                          # read-only, every step
    AWS_PROFILE=relayshield python3 tools/wafr_identity.py --apply                  # permission sets, groups, assignments
    AWS_PROFILE=relayshield python3 tools/wafr_identity.py --apply --add-user NAME  # also put one existing user in both groups
    AWS_PROFILE=relayshield python3 tools/wafr_identity.py --step org --apply       # create the Organization (explicit only)
    AWS_PROFILE=relayshield python3 tools/wafr_identity.py --step responder --apply # let the SSO admin role assume the IR role

Steps, in order:

  org              Identity Center needs AWS Organizations with this account as the management account.
                   TODO if there is none. BLOCKED if this account is a member of another organization or the
                   organization is billing-only. Creating one is EXPLICIT ONLY (--step org --apply).
  instance         Is Identity Center enabled? Enabling it is a console action, so a missing instance is BLOCKED
                   with the instruction, not something this tool attempts.
  permission_sets  The permission sets in the spec: created if missing, the spec's managed policies attached,
                   session length checked. NEVER removes a policy or changes a session length; extras and drift are
                   reported as ELSEWHERE for a human to decide.
  groups           The groups in the spec, created if missing.
  assignments      Each group is assigned its permission set on this account.
  membership       Only with --add-user NAME (an existing Identity Center user, looked up by user name AT RUNTIME so
                   no person's name or email is ever written in this public repo).
  legacy           READ-ONLY. IAM users that still have an active access key or a console password: the long-lived
                   credentials that "Use temporary credentials" is about. Prints to the terminal only. Never wire
                   this step into a workflow: Actions logs of a public repository are public.
  responder        The IR responder role's trust policy only admits a principal with an MFA flag, and an Identity
                   Center session is not expected to carry one (UNVERIFIED here). This adds ONE statement admitting
                   the SSO admin role by ARN pattern, keeping the existing statement. Explicit only, merge not replace.

WHAT THIS EVIDENCES, AND WHAT IT DOES NOT. It supports "Rely on a centralized identity provider" (Identity Center),
"Employ user groups and attributes" (access by group and permission set, not by user) and, once the legacy report is
empty and SSO login is proven, "Use temporary credentials". It does not prove MFA is required: that is the Identity
Center console setting (Settings, Authentication, MFA, require always), which has no API here. It does not remove
anything: deactivating a key is a human decision after SSO login works. Say all of this in the Note when ticking.

Never touches a resource it could not read, and refuses to run unless the credentials resolve to the RelayShield
account, because the shell default profile is the pre-audit account.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

SPEC = Path(__file__).resolve().parent / "wafr_identity_spec.json"
STEPS = ("org", "instance", "permission_sets", "groups", "assignments", "membership", "legacy", "responder")
READ_ONLY_STEPS = ("legacy",)
EXPLICIT_ONLY = ("org", "responder")  # a write that changes the sign-in model or a trust policy: never part of a bare --apply
ATTENTION = ("blocked", "elsewhere")
SSO_PATH = "role/aws-reserved/sso.amazonaws.com/"


def code(e):
    return getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)


def paged(fn, key, **kw):
    token = None
    while True:
        r = fn(**kw, **({"NextToken": token} if token else {}))
        yield from r.get(key, [])
        token = r.get("NextToken")
        if not token:
            return


# ------------------------------------------------------------------------ org
def plan_org(c, ctx, spec):
    try:
        o = c["organizations"].describe_organization()["Organization"]
    except Exception as e:
        if code(e) == "AWSOrganizationsNotInUseException":
            return [("organization", "todo", "none exists; --step org --apply creates one with all features", "create")]
        return [("organization", "blocked", f"cannot read ({code(e)})", None)]
    if o.get("MasterAccountId") != spec["account"]:
        return [("organization", "blocked", "this account is a MEMBER of another organization; Identity Center must be "
                 "enabled in that one's management account. A decision for the founder, not a build.", None)]
    if o.get("FeatureSet") != "ALL":
        return [("organization", "blocked", f"feature set is {o.get('FeatureSet')}, Identity Center needs ALL", None)]
    return [("organization", "ok", "this account is the management account, all features", None)]


def apply_org(c, rows):
    for name, state, _d, act in rows:
        if state == "todo" and act == "create":
            c["organizations"].create_organization(FeatureSet="ALL")
            yield "created the organization (all features)"


# ------------------------------------------------------------------- instance
def plan_instance(c, ctx, spec):
    try:
        inst = c["sso-admin"].list_instances().get("Instances", [])
    except Exception as e:
        return [("identity center instance", "blocked", f"cannot read ({code(e)})", None)]
    if not inst:
        ctx["instance"] = None
        return [("identity center instance", "blocked",
                 f"not enabled in {spec['region']}. ANDREW CLICKS: console, IAM Identity Center, Enable, "
                 "organization instance, in that region. Then re-run.", None)]
    ctx["instance"] = inst[0]
    return [("identity center instance", "ok", "enabled", None)]


def need_instance(ctx):
    if not ctx.get("instance"):
        return [("(needs the instance)", "blocked", "Identity Center is not enabled or could not be read", None)]
    return None


# ------------------------------------------------------------ permission sets
def existing_sets(c, ctx):
    arn = ctx["instance"]["InstanceArn"]
    out = {}
    for psa in paged(c["sso-admin"].list_permission_sets, "PermissionSets", InstanceArn=arn):
        ps = c["sso-admin"].describe_permission_set(InstanceArn=arn, PermissionSetArn=psa)["PermissionSet"]
        out[ps["Name"]] = ps
    return out


def plan_permission_sets(c, ctx, spec):
    blocked = need_instance(ctx)
    if blocked:
        return blocked
    arn = ctx["instance"]["InstanceArn"]
    try:
        have = existing_sets(c, ctx)
    except Exception as e:
        return [("permission sets", "blocked", f"cannot read ({code(e)})", None)]
    rows = []
    for want in spec["permission_sets"]:
        name = want["name"]
        if name not in have:
            rows.append((name, "todo", f"create, session {want['session']}, attach {len(want['managed'])} policy(ies)",
                         {"create": want, "attach": list(want["managed"])}))
            continue
        ps = have[name]
        try:
            attached = {p["Arn"] for p in paged(c["sso-admin"].list_managed_policies_in_permission_set,
                                                "AttachedManagedPolicies", InstanceArn=arn, PermissionSetArn=ps["PermissionSetArn"])}
        except Exception as e:
            rows.append((name, "blocked", f"cannot read its policies ({code(e)})", None))
            continue
        missing = [p for p in want["managed"] if p not in attached]
        extra = sorted(attached - set(want["managed"]))
        notes = []
        if ps.get("SessionDuration") != want["session"]:
            notes.append(f"session is {ps.get('SessionDuration')}, spec says {want['session']}")
        if extra:
            notes.append("extra policies attached: " + ", ".join(extra))
        if notes:
            rows.append((name, "elsewhere", "; ".join(notes) + " (never changed by this tool)", None))
        if missing:
            rows.append((name, "todo", f"attach {len(missing)} missing policy(ies)",
                         {"attach": missing, "arn": ps["PermissionSetArn"]}))
        elif not notes:
            rows.append((name, "ok", "present, policies and session as specified", None))
    return rows


def apply_permission_sets(c, ctx, rows):
    arn = ctx["instance"]["InstanceArn"]
    sso = c["sso-admin"]
    for name, state, _d, act in rows:
        if state != "todo" or not act:
            continue
        existed = "create" not in act
        if existed:
            psa = act["arn"]
        else:
            w = act["create"]
            psa = sso.create_permission_set(InstanceArn=arn, Name=w["name"], Description=w["description"],
                                            SessionDuration=w["session"])["PermissionSet"]["PermissionSetArn"]
            yield f"created permission set {name}"
        for pol in act["attach"]:
            sso.attach_managed_policy_to_permission_set(InstanceArn=arn, PermissionSetArn=psa, ManagedPolicyArn=pol)
            yield f"attached {pol.rsplit('/', 1)[-1]} to {name}"
        if existed:  # policies added to a set already in use must be pushed to the accounts that use it
            sso.provision_permission_set(InstanceArn=arn, PermissionSetArn=psa, TargetType="ALL_PROVISIONED_ACCOUNTS")
            yield f"re-provisioned {name} to the accounts that use it"


# --------------------------------------------------------------------- groups
def group_id(c, ctx, name):
    try:
        return c["identitystore"].get_group_id(
            IdentityStoreId=ctx["instance"]["IdentityStoreId"],
            AlternateIdentifier={"UniqueAttribute": {"AttributePath": "displayName", "AttributeValue": name}})["GroupId"]
    except Exception as e:
        if code(e) == "ResourceNotFoundException":
            return None
        raise


def plan_groups(c, ctx, spec):
    blocked = need_instance(ctx)
    if blocked:
        return blocked
    rows = []
    for g in spec["groups"]:
        try:
            gid = group_id(c, ctx, g["name"])
        except Exception as e:
            rows.append((g["name"], "blocked", f"cannot read ({code(e)})", None))
            continue
        rows.append((g["name"], "ok" if gid else "todo", "present" if gid else "create", None if gid else g))
    return rows


def apply_groups(c, ctx, rows):
    for name, state, _d, act in rows:
        if state == "todo" and act:
            c["identitystore"].create_group(IdentityStoreId=ctx["instance"]["IdentityStoreId"],
                                            DisplayName=act["name"], Description=act["description"])
            yield f"created group {name}"


# ---------------------------------------------------------------- assignments
def plan_assignments(c, ctx, spec):
    blocked = need_instance(ctx)
    if blocked:
        return blocked
    arn = ctx["instance"]["InstanceArn"]
    try:
        sets = existing_sets(c, ctx)
    except Exception as e:
        return [("assignments", "blocked", f"cannot read permission sets ({code(e)})", None)]
    rows = []
    for g in spec["groups"]:
        label = f"{g['name']} -> {g['permission_set']}"
        ps = sets.get(g["permission_set"])
        try:
            gid = group_id(c, ctx, g["name"])
        except Exception as e:
            rows.append((label, "blocked", f"cannot read the group ({code(e)})", None))
            continue
        if not ps or not gid:
            rows.append((label, "todo", "waits for the " + ("permission set" if not ps else "group") + " to exist", None))
            continue
        try:
            have = list(paged(c["sso-admin"].list_account_assignments, "AccountAssignments", InstanceArn=arn,
                              AccountId=spec["account"], PermissionSetArn=ps["PermissionSetArn"]))
        except Exception as e:
            rows.append((label, "blocked", f"cannot read ({code(e)})", None))
            continue
        if any(a.get("PrincipalType") == "GROUP" and a.get("PrincipalId") == gid for a in have):
            rows.append((label, "ok", "assigned", None))
        else:
            rows.append((label, "todo", "assign", {"psa": ps["PermissionSetArn"], "gid": gid}))
    return rows


def apply_assignments(c, ctx, rows, spec):
    for label, state, _d, act in rows:
        if state == "todo" and act:
            c["sso-admin"].create_account_assignment(
                InstanceArn=ctx["instance"]["InstanceArn"], TargetId=spec["account"], TargetType="AWS_ACCOUNT",
                PermissionSetArn=act["psa"], PrincipalType="GROUP", PrincipalId=act["gid"])
            yield f"requested assignment {label} (asynchronous; re-run to confirm)"


# ----------------------------------------------------------------- membership
def plan_membership(c, ctx, spec, user):
    if not user:
        return [("membership", "skipped", "no --add-user given", None)]
    blocked = need_instance(ctx)
    if blocked:
        return blocked
    store = ctx["instance"]["IdentityStoreId"]
    try:
        uid = c["identitystore"].get_user_id(
            IdentityStoreId=store,
            AlternateIdentifier={"UniqueAttribute": {"AttributePath": "userName", "AttributeValue": user}})["UserId"]
    except Exception as e:
        if code(e) == "ResourceNotFoundException":
            return [("membership", "blocked", "no Identity Center user with that user name. ANDREW CLICKS: console, "
                     "IAM Identity Center, Users, Add user (his own e-mail; he sets the password from the invitation).", None)]
        return [("membership", "blocked", f"cannot look the user up ({code(e)})", None)]
    rows = []
    for g in spec["groups"]:
        try:
            gid = group_id(c, ctx, g["name"])
            if not gid:
                rows.append((f"user in {g['name']}", "todo", "waits for the group to exist", None))
                continue
            r = c["identitystore"].is_member_in_groups(IdentityStoreId=store, MemberId={"UserId": uid}, GroupIds=[gid])
            member = any(x.get("MembershipExists") for x in r.get("Results", []))
        except Exception as e:
            rows.append((f"user in {g['name']}", "blocked", f"cannot read ({code(e)})", None))
            continue
        rows.append((f"user in {g['name']}", "ok" if member else "todo", "member" if member else "add",
                     None if member else {"gid": gid, "uid": uid}))
    return rows


def apply_membership(c, ctx, rows):
    for label, state, _d, act in rows:
        if state == "todo" and act:
            c["identitystore"].create_group_membership(IdentityStoreId=ctx["instance"]["IdentityStoreId"],
                                                       GroupId=act["gid"], MemberId={"UserId": act["uid"]})
            yield f"added {label}"


# --------------------------------------------------------------------- legacy
def plan_legacy(c, ctx, spec):
    iam, rows = c["iam"], []
    try:
        users = list(paged_marker(iam.list_users, "Users"))
    except Exception as e:
        return [("IAM users", "blocked", f"cannot read ({code(e)})", None)]
    for u in users:
        name, notes = u["UserName"], []
        try:
            for k in iam.list_access_keys(UserName=name).get("AccessKeyMetadata", []):
                if k.get("Status") == "Active":
                    lu = iam.get_access_key_last_used(AccessKeyId=k["AccessKeyId"]).get("AccessKeyLastUsed", {})
                    when = lu.get("LastUsedDate")
                    notes.append("active access key, last used " + (when.strftime("%Y-%m-%d") if when else "never"))
            try:
                iam.get_login_profile(UserName=name)
                notes.append("console password")
            except Exception as e:
                if code(e) != "NoSuchEntity":
                    notes.append(f"login profile unreadable ({code(e)})")
        except Exception as e:
            rows.append((name, "blocked", f"cannot read ({code(e)})", None))
            continue
        if notes:
            rows.append((name, "elsewhere", "; ".join(notes), None))
    if not rows:
        rows.append(("IAM users", "ok", "none holds a long-lived credential", None))
    return rows


def paged_marker(fn, key, **kw):
    marker = None
    while True:
        r = fn(**kw, **({"Marker": marker} if marker else {}))
        yield from r.get(key, [])
        if not r.get("IsTruncated"):
            return
        marker = r["Marker"]


# ------------------------------------------------------------------ responder
def sso_statement(spec):
    return {"Sid": "IdentityCenterAdminRole", "Effect": "Allow",
            "Principal": {"AWS": f"arn:aws:iam::{spec['account']}:root"}, "Action": "sts:AssumeRole",
            "Condition": {"ArnLike": {"aws:PrincipalArn":
                          f"arn:aws:iam::{spec['account']}:{SSO_PATH}*AWSReservedSSO_{spec['responder_sso_permission_set']}_*"}}}


def plan_responder(c, ctx, spec):
    try:
        doc = c["iam"].get_role(RoleName=spec["responder_role"])["Role"]["AssumeRolePolicyDocument"]
    except Exception as e:
        return [(spec["responder_role"], "blocked", f"cannot read ({code(e)}); tools/apply_ir_responder_role.sh creates it", None)]
    if isinstance(doc, str):
        doc = json.loads(doc)
    if any(s.get("Sid") == "IdentityCenterAdminRole" for s in doc.get("Statement", [])):
        return [(spec["responder_role"], "ok", "trust already admits the SSO admin role", None)]
    return [(spec["responder_role"], "todo", "add one trust statement for the SSO admin role; the MFA statement stays", doc)]


def apply_responder(c, rows, spec):
    for name, state, _d, doc in rows:
        if state == "todo" and doc:
            new = copy.deepcopy(doc)
            new["Statement"] = list(new.get("Statement", [])) + [sso_statement(spec)]
            c["iam"].update_assume_role_policy(RoleName=name, PolicyDocument=json.dumps(new))
            yield f"added the SSO admin statement to {name}'s trust (existing statement kept)"


# ----------------------------------------------------------------------- main
def run(clients, account_of, spec, apply, steps, check=False, user=None, explicit=False, out=print):
    got = account_of()
    if got != spec["account"]:
        out(f"Refusing to run: credentials resolve to account {got}, not {spec['account']}. Use AWS_PROFILE=relayshield.")
        return 2
    if apply and check:
        out("--apply and --check are opposites; pick one.")
        return 2
    ctx = {}
    attention = todo_any = False
    # instance is always read: later steps need it, and reading it is free
    order = [s for s in STEPS if s in steps or s == "instance"]
    for step in order:
        shown = step in steps
        if shown:
            out(f"\n== {step}")
        done = []
        # explicit-only steps are SHOWN on a bare --apply (read) but written only when named with --step
        writes = apply and shown and step not in READ_ONLY_STEPS and (explicit or step not in EXPLICIT_ONLY)
        if step == "org":
            rows = plan_org(clients, ctx, spec)
            done = list(apply_org(clients, rows)) if writes else []
        elif step == "instance":
            rows = plan_instance(clients, ctx, spec)
        elif step == "permission_sets":
            rows = plan_permission_sets(clients, ctx, spec)
            done = list(apply_permission_sets(clients, ctx, rows)) if writes and ctx.get("instance") else []
        elif step == "groups":
            rows = plan_groups(clients, ctx, spec)
            done = list(apply_groups(clients, ctx, rows)) if writes and ctx.get("instance") else []
        elif step == "assignments":
            rows = plan_assignments(clients, ctx, spec)
            done = list(apply_assignments(clients, ctx, rows, spec)) if writes and ctx.get("instance") else []
        elif step == "membership":
            rows = plan_membership(clients, ctx, spec, user)
            done = list(apply_membership(clients, ctx, rows)) if writes and ctx.get("instance") else []
        elif step == "legacy":
            rows = plan_legacy(clients, ctx, spec)
        else:
            rows = plan_responder(clients, ctx, spec)
            done = list(apply_responder(clients, rows, spec)) if writes else []
        if not shown:
            continue
        for name, state, detail, _x in rows:
            if state != "ok":
                out(f"  {state.upper():<9} {name}  {detail}".rstrip())
        ok = sum(r[1] == "ok" for r in rows)
        todo = sum(r[1] == "todo" for r in rows)
        bad = [r for r in rows if r[1] in ATTENTION]
        attention |= bool(bad)
        todo_any |= bool(todo)
        for d in done:
            out(f"  CHANGED   {d}")
        out(f"  {step}: {ok} already fine, {todo} to change, {len(bad)} need attention.")
    if not apply:
        out("\nDry run only. Re-run with --apply to make the changes." if not check else "\nCheck only.")
    return 1 if attention or (check and todo_any) else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--step", choices=STEPS + ("all",), default="all")
    ap.add_argument("--add-user", default=None, help="an existing Identity Center user name, put into both groups")
    ap.add_argument("--spec", default=str(SPEC))
    a = ap.parse_args(argv)
    spec = json.load(open(a.spec))
    import boto3
    r = spec["region"]
    clients = {n: boto3.client(n, region_name=r) for n in ("organizations", "sso-admin", "identitystore", "iam")}
    sts = boto3.client("sts", region_name=r)
    steps = STEPS if a.step == "all" else (a.step,)
    return run(clients, lambda: sts.get_caller_identity()["Account"], spec, a.apply, steps, a.check, a.add_user,
               explicit=a.step != "all")


if __name__ == "__main__":
    sys.exit(main())
