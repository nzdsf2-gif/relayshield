#!/usr/bin/env python3
"""Well-Architected SEC 2, phase 2 ("Use temporary credentials"): retire long-lived IAM credentials, one at a time.

    AWS_PROFILE=relayshield python3 tools/wafr_keys.py                              # read-only report, ranked
    AWS_PROFILE=relayshield python3 tools/wafr_keys.py --deactivate KEYID           # dry run (or user:NAME for that user's one Active key)
    AWS_PROFILE=relayshield python3 tools/wafr_keys.py --deactivate KEYID --apply   # Inactive (reversible)
    AWS_PROFILE=relayshield python3 tools/wafr_keys.py --reactivate KEYID --apply   # the rollback
    AWS_PROFILE=relayshield python3 tools/wafr_keys.py --delete KEYID --apply       # permanent, after the observe window
    AWS_PROFILE=relayshield python3 tools/wafr_keys.py --remove-console USER --apply

The order, which the tool enforces rather than asks you to remember:

  1. REPORT.        Every IAM user's access keys and console password, how old, when and WHERE last used, ranked so the
                    safest candidate is first. Also whether the root account holds an access key.
  2. DEACTIVATE.    One key. Reversible: --reactivate puts it back. A key used in the last 7 days is a service depending
                    on it and is REFUSED unless --allow-recent is added by hand.
  3. OBSERVE.       7 days with the key inactive, watching whatever it could have been serving.
  4. DELETE.        One key, permanent. Refused unless the key is already Inactive AND CloudTrail shows it was deactivated
                    at least 7 days ago (or you attest a date with --observed-since, used only when CloudTrail has no
                    record; the later of the two dates wins).

Every WRITE here (deactivate, delete, remove-console) requires that THIS command is running on an IAM Identity Center
session. That one rule does three jobs: it proves SSO sign-in works before the old way is removed, it stops the tool
deactivating the very key that is running it, and it means a lockout is recoverable by signing in the new way.
--reactivate is exempt on purpose: the rollback must work when the new way is what broke.

Never deletes a user, never touches the root account (root keys are reported; removing one is a console action as root),
never writes outside IAM, and refuses unless credentials resolve to the RelayShield account.

OUTPUT GOES TO YOUR TERMINAL ONLY. Key ids and user names appear in it. Never wire this into a workflow: Actions logs of a
public repository are public. Never paste its output into a repo file or an issue.

WHAT THIS EVIDENCES. "Use temporary credentials" once the report shows no human credential and every remaining key is a
documented service key. It does not move a service to a role: that is its own build. Say both in the Note when ticking.
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

SPEC = Path(__file__).resolve().parent / "wafr_identity_spec.json"
SSO_MARK = ":assumed-role/AWSReservedSSO_"
RECENT_DAYS = 7
OBSERVE_DAYS = 7
KEY_ID = re.compile(r"^[A-Z0-9]{16,128}$")
USER = re.compile(r"^[\w+=,.@-]{1,64}$")
UTC = datetime.timezone.utc


def code(e):
    return getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)


def paged_marker(fn, key, **kw):
    marker = None
    while True:
        r = fn(**kw, **({"Marker": marker} if marker else {}))
        yield from r.get(key, [])
        if not r.get("IsTruncated"):
            return
        marker = r["Marker"]


def paged_token(fn, key, **kw):
    token = None
    while True:
        r = fn(**kw, **({"NextToken": token} if token else {}))
        yield from r.get(key, [])
        token = r.get("NextToken")
        if not token:
            return


def aware(when):
    return when if when is None or when.tzinfo else when.replace(tzinfo=UTC)


def days_since(when, now):
    return None if when is None else (now - aware(when)).days


# --------------------------------------------------------------------- report
def inventory(iam, now):
    """-> (keys, passwords, problems). Reads only. A user it cannot read is a problem row, never a silent skip."""
    keys, passwords, problems = [], [], []
    try:
        users = list(paged_marker(iam.list_users, "Users"))
    except Exception as e:
        return [], [], [("IAM users", f"cannot read ({code(e)})")]
    for u in users:
        name = u["UserName"]
        try:
            metas = iam.list_access_keys(UserName=name).get("AccessKeyMetadata", [])
        except Exception as e:
            problems.append((name, f"cannot list access keys ({code(e)})"))
            metas = []
        for k in metas:
            lu = {}
            try:
                lu = iam.get_access_key_last_used(AccessKeyId=k["AccessKeyId"]).get("AccessKeyLastUsed", {})
            except Exception as e:
                problems.append((name, f"cannot read last use of a key ({code(e)})"))
            keys.append({"user": name, "id": k["AccessKeyId"], "status": k.get("Status"),
                         "age": days_since(k.get("CreateDate"), now), "used": days_since(lu.get("LastUsedDate"), now),
                         "where": "/".join(x for x in (lu.get("ServiceName"), lu.get("Region")) if x and x != "N/A")})
        try:
            iam.get_login_profile(UserName=name)
            passwords.append({"user": name, "used": days_since(u.get("PasswordLastUsed"), now)})
        except Exception as e:
            if code(e) != "NoSuchEntity":
                problems.append((name, f"console password unreadable ({code(e)})"))
    return keys, passwords, problems


def rank(k):
    """Safest to retire first: never used, then longest idle. Inactive keys are not candidates for deactivation."""
    return (0, 0) if k["used"] is None else (1, -k["used"])


def classify(k):
    if k["status"] != "Active":
        return "inactive"
    if k["used"] is None:
        return "never-used"
    return "idle" if k["used"] >= RECENT_DAYS else "recent"


def report(iam, now, out):
    keys, passwords, problems = inventory(iam, now)
    remaining = 0
    out("\n== access keys (ranked: safest to retire first)")
    for k in sorted(keys, key=rank):
        c = classify(k)
        used = "never used" if k["used"] is None else f"last used {k['used']}d ago" + (f" via {k['where']}" if k["where"] else "")
        note = {"inactive": "INACTIVE, delete after the observe window",
                "never-used": "candidate: nothing has ever used it",
                "idle": f"candidate: idle {k['used']} days",
                "recent": "IN USE: a service depends on it until proven otherwise"}[c]
        out(f"  {c.upper():<10} {k['user']}  {k['id']}  age {k['age']}d, {used}  -> {note}")
        remaining += c != "inactive"
    if not keys:
        out("  none")
    out("\n== console passwords")
    for p in passwords:
        used = "never signed in" if p["used"] is None else f"last sign-in {p['used']}d ago"
        out(f"  PASSWORD   {p['user']}  {used}")
        remaining += 1
    if not passwords:
        out("  none")
    out("\n== root account")
    try:
        s = iam.get_account_summary().get("SummaryMap", {})
        n = s.get("AccountAccessKeysPresent")
        if n:
            out(f"  ELSEWHERE  the root account holds {n} access key(s). Not removable here: sign in as root, Security credentials, delete.")
            remaining += n
        else:
            out("  ok         the root account holds no access key")
    except Exception as e:
        out(f"  BLOCKED    cannot read the account summary ({code(e)})")
        problems.append(("root", "unreadable"))
    for who, why in problems:
        out(f"  BLOCKED    {who}: {why}")
    cands = sorted((k for k in keys if classify(k) in ("never-used", "idle")), key=rank)
    out("")
    if cands:
        c = cands[0]
        out(f"NEXT: python3 tools/wafr_keys.py --deactivate {c['id']}     (dry run; add --apply from your SSO profile)")
    elif remaining:
        out("NEXT: nothing is safe to retire yet. Every remaining credential was used recently: find what uses it, or wait.")
    out(f"{remaining} long-lived credential(s) remain, {len(problems)} unreadable.")
    return 1 if remaining or problems else 0


# -------------------------------------------------------------------- guards
def require_sso(arn, out, what):
    if SSO_MARK in (arn or ""):
        return True
    out(f"REFUSED   {what} must run on an IAM Identity Center session, and this one is not ({'unknown' if not arn else 'not SSO'}).")
    out("          Sign in with `aws sso login --profile relayshield` (runbook step 7b), then run it again. This is what proves the new way works")
    out("          BEFORE the old way is removed, and it keeps this command from deactivating the key that is running it.")
    return False


def resolve(iam, ref, want, out):
    """A key id passes through. `user:NAME` picks that user's ONE key in state `want`; zero or several is refused, never guessed."""
    if not (ref or "").startswith("user:"):
        return ref
    name = ref[5:]
    if not USER.match(name):
        out(f"REFUSED   '{name}' is not an IAM user name.")
        return None
    try:
        ids = [k["AccessKeyId"] for k in iam.list_access_keys(UserName=name).get("AccessKeyMetadata", []) if k.get("Status") == want]
    except Exception as e:
        out(f"BLOCKED   cannot list the keys of {name} ({code(e)}). Nothing was changed.")
        return None
    if len(ids) != 1:
        out(f"REFUSED   {name} has {len(ids)} {want} access keys; this needs exactly one. Use the key id from the report instead.")
        return None
    return ids[0]


def locate(iam, key_id, out):
    if not KEY_ID.match(key_id or ""):
        out(f"REFUSED   '{key_id}' is not an access key id (16 to 128 capital letters and digits).")
        return None
    try:
        lu = iam.get_access_key_last_used(AccessKeyId=key_id)
        user = lu["UserName"]
        for k in iam.list_access_keys(UserName=user).get("AccessKeyMetadata", []):
            if k["AccessKeyId"] == key_id:
                return user, k, lu.get("AccessKeyLastUsed", {})
    except Exception as e:
        out(f"BLOCKED   cannot look up that key ({code(e)}). Nothing was changed.")
        return None
    out("BLOCKED   that key is not on the user AWS says owns it. Nothing was changed.")
    return None


def deactivation_date(ct, key_id, now):
    """-> (datetime or None, reason). The newest UpdateAccessKey event for this key must be an Inactive one."""
    best = None
    try:
        for ev in paged_token(ct.lookup_events, "Events",
                              LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": "UpdateAccessKey"}],
                              StartTime=now - datetime.timedelta(days=90), EndTime=now):
            try:
                rp = {k.lower(): v for k, v in (json.loads(ev["CloudTrailEvent"]).get("requestParameters") or {}).items()}
            except Exception:
                continue
            if rp.get("accesskeyid") != key_id:
                continue
            when = aware(ev["EventTime"])
            if best is None or when > best[0]:
                best = (when, str(rp.get("status")))
    except Exception as e:
        return None, f"CloudTrail unreadable ({code(e)})"
    if best is None:
        return None, "CloudTrail has no UpdateAccessKey record for it in the last 90 days"
    if best[1] != "Inactive":
        return None, f"the newest CloudTrail record sets it {best[1]}, not Inactive"
    return best[0], ""


# -------------------------------------------------------------------- actions
def do_deactivate(iam, key_id, apply, allow_recent, now, out):
    found = locate(iam, key_id, out)
    if not found:
        return 1
    user, k, lu = found
    if k.get("Status") != "Active":
        out(f"ok        {key_id} is already {k.get('Status')}. Nothing to do.")
        return 0
    used = days_since(lu.get("LastUsedDate"), now)
    if used is not None and used < RECENT_DAYS and not allow_recent:
        via = "/".join(x for x in (lu.get("ServiceName"), lu.get("Region")) if x and x != "N/A")
        out(f"REFUSED   {key_id} was used {used} day(s) ago" + (f" via {via}" if via else "") + ". Something is depending on it, and "
            "deactivating it takes that something down.")
        out(f"          Find what uses it first. Only if you are certain it is yours to break, add --allow-recent.")
        return 1
    out(f"TODO      deactivate {key_id} of {user} (" + ("never used" if used is None else f"last used {used}d ago") + ")")
    if not apply:
        out("Dry run only. Add --apply to deactivate. Rollback, any time: --reactivate " + key_id + " --apply")
        return 0
    iam.update_access_key(UserName=user, AccessKeyId=key_id, Status="Inactive")
    out(f"CHANGED   {key_id} is now Inactive.")
    out(f"          Rollback, any time:  python3 tools/wafr_keys.py --reactivate {key_id} --apply")
    out(f"          Now OBSERVE for {OBSERVE_DAYS} days. Delete is refused before that.")
    return 0


def do_reactivate(iam, key_id, apply, out):
    found = locate(iam, key_id, out)
    if not found:
        return 1
    user, k, _lu = found
    if k.get("Status") == "Active":
        out(f"ok        {key_id} is already Active.")
        return 0
    out(f"TODO      reactivate {key_id} of {user}")
    if not apply:
        out("Dry run only. Add --apply.")
        return 0
    iam.update_access_key(UserName=user, AccessKeyId=key_id, Status="Active")
    out(f"CHANGED   {key_id} is Active again.")
    return 0


def do_delete(iam, ct, key_id, apply, observed_since, now, out):
    found = locate(iam, key_id, out)
    if not found:
        return 1
    user, k, _lu = found
    if k.get("Status") != "Inactive":
        out(f"REFUSED   {key_id} is {k.get('Status')}. Deactivate it first and observe; delete is for a key that is already Inactive.")
        return 1
    since, why = deactivation_date(ct, key_id, now)
    if observed_since:
        try:
            attested = datetime.datetime.strptime(observed_since, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            out("REFUSED   --observed-since must be a date like 2026-12-01.")
            return 2
        if since is None:
            out(f"NOTE      {why}. Using YOUR attested date {observed_since} (recorded nowhere but this terminal).")
            since = attested
        else:
            since = max(since, attested)
    if since is None:
        out(f"BLOCKED   {why}, so the observe window cannot be shown. Nothing was changed.")
        out(f"          If you deactivated it with this tool on a known date: add --observed-since YYYY-MM-DD. Otherwise reactivate it, then deactivate it again with this tool.")
        return 1
    waited = days_since(since, now)
    if waited < OBSERVE_DAYS:
        out(f"REFUSED   {key_id} has been Inactive for {waited} day(s); the window is {OBSERVE_DAYS}. Come back in {OBSERVE_DAYS - waited}.")
        return 1
    out(f"TODO      PERMANENTLY delete {key_id} of {user} (Inactive {waited} days). This cannot be undone.")
    if not apply:
        out("Dry run only. Add --apply to delete.")
        return 0
    iam.delete_access_key(UserName=user, AccessKeyId=key_id)
    out(f"CHANGED   {key_id} is deleted.")
    return 0


def do_remove_console(iam, user, apply, allow_recent, now, out):
    if not USER.match(user or ""):
        out(f"REFUSED   '{user}' is not an IAM user name.")
        return 2
    try:
        u = iam.get_user(UserName=user)["User"]
        iam.get_login_profile(UserName=user)
    except Exception as e:
        if code(e) == "NoSuchEntity":
            out(f"ok        {user} has no console password (or no such user). Nothing to do.")
            return 0
        out(f"BLOCKED   cannot read {user} ({code(e)}). Nothing was changed.")
        return 1
    used = days_since(u.get("PasswordLastUsed"), now)
    if used is not None and used < RECENT_DAYS and not allow_recent:
        out(f"REFUSED   {user} signed in {used} day(s) ago. Prove the SSO sign-in is the one you use, then wait a week, or add --allow-recent.")
        return 1
    out(f"TODO      remove the console password of {user} (" + ("never signed in" if used is None else f"last sign-in {used}d ago") + ")")
    if not apply:
        out("Dry run only. Add --apply. The user and any keys stay; a password can be set again by an administrator.")
        return 0
    iam.delete_login_profile(UserName=user)
    out(f"CHANGED   the console password of {user} is removed.")
    return 0


# ----------------------------------------------------------------------- main
def run(iam, ct, caller_of, spec, args, now=None, out=print):
    now = now or datetime.datetime.now(UTC)
    account, arn = caller_of()
    if account != spec["account"]:
        out(f"Refusing to run: credentials resolve to account {account}, not {spec['account']}. Use AWS_PROFILE=relayshield.")
        return 2
    chosen = [n for n in ("deactivate", "reactivate", "delete", "remove_console") if getattr(args, n)]
    if len(chosen) > 1:
        out("One action at a time: that is the point.")
        return 2
    if not chosen:
        if args.apply:
            out("--apply needs an action: --deactivate, --reactivate, --delete or --remove-console.")
            return 2
        return report(iam, now, out)
    action = chosen[0]
    want = {"reactivate": "Inactive", "deactivate": "Active", "delete": "Inactive"}.get(action)
    if want:
        ref = resolve(iam, getattr(args, action), want, out)
        if ref is None:
            return 1
        setattr(args, action, ref)
    if action == "reactivate":
        return do_reactivate(iam, args.reactivate, args.apply, out)
    # every other action is a write or a decision about one: it must be SSO, dry run included, so a dry run is a true preview
    if not require_sso(arn, out, "this"):
        return 2
    if action == "deactivate":
        return do_deactivate(iam, args.deactivate, args.apply, args.allow_recent, now, out)
    if action == "delete":
        return do_delete(iam, ct, args.delete, args.apply, args.observed_since, now, out)
    return do_remove_console(iam, args.remove_console, args.apply, args.allow_recent, now, out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--deactivate", metavar="KEYID")
    ap.add_argument("--reactivate", metavar="KEYID")
    ap.add_argument("--delete", metavar="KEYID")
    ap.add_argument("--remove-console", metavar="USER", dest="remove_console")
    ap.add_argument("--allow-recent", action="store_true", help="deactivate/remove something used in the last 7 days")
    ap.add_argument("--observed-since", metavar="YYYY-MM-DD", help="delete only: the date you deactivated it, if CloudTrail has no record")
    ap.add_argument("--spec", default=str(SPEC))
    a = ap.parse_args(argv)
    spec = json.load(open(a.spec))
    import boto3
    r = spec["region"]
    sts = boto3.client("sts", region_name=r)

    def caller():
        i = sts.get_caller_identity()
        return i["Account"], i["Arn"]
    return run(boto3.client("iam", region_name=r), boto3.client("cloudtrail", region_name=r), caller, spec, a)


if __name__ == "__main__":
    sys.exit(main())
