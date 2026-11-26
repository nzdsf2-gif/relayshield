#!/usr/bin/env python3
"""Can the GitHub OIDC deploy role do what the five intel workflows ask of it? Ask IAM as the role, then add what is missing.

    AWS_PROFILE=relayshield python3 tools/oidc_workflow_grants.py            # read-only: simulate every needed action AS THE ROLE
    AWS_PROFILE=relayshield python3 tools/oidc_workflow_grants.py --apply    # put the missing grants as ONE new inline policy

WHY. intel_channel_discovery, intel_channel_review, intel_feed, intel_kev and intel_substack used a long-lived access key
stored as a GitHub secret. Moving them to the OIDC role relayshield-github-deploy removes that key's reason to exist, but the
role's rights are an explicit list, and a workflow switched onto a role that lacks one fails with a 403 on whatever day it next
runs. Two of them run on a schedule. So this asks IAM the same question the workflow will ask, BEFORE the workflows reach main.

What it does: simulate_principal_policy as the ROLE (not as you) for every action and resource in
iam_github_deploy_intel_ops.json. With --apply and at least one denial, it writes that file as a NEW inline policy named
relayshield-deploy-intel-ops. It never edits, replaces or removes any existing policy, then simulates again to prove it.
It also PRINTS the role's trust conditions for the GitHub subject, because a simulation does not evaluate trust, and says
whether a run from main would match them. Dry run by default; refuses the wrong account.
"""
import argparse
import fnmatch
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "iam_github_deploy_intel_ops.json"
ACCOUNT = "239677749008"
ROLE = "relayshield-github-deploy"
POLICY_NAME = "relayshield-deploy-intel-ops"
SUB = "repo:nzdsf2-gif/relayshield:ref:refs/heads/main"  # what a scheduled or main-dispatched run presents
SUB_KEY = "token.actions.githubusercontent.com:sub"


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


def needs(doc):
    """[(sid, actions, resources)] straight from the policy file, so the file is the single source of what is asked."""
    return [(s["Sid"], list(s["Action"]), list(s["Resource"])) for s in doc["Statement"] if s.get("Effect") == "Allow"]


def simulate(iam, doc):
    """-> list of (action, resource, decision), ONE simulation per action and resource pair. Reads only.

    Asking for several resources at once returned a single result named '${ResourceId}' for lambda:InvokeFunction on a real
    account (2026-11-26), which cannot be read as a verdict on any one function. One pair per call is unambiguous, and the
    result is reported against the resource that was ASKED about, never the name the simulator echoes back."""
    out = []
    arn = f"arn:aws:iam::{ACCOUNT}:role/{ROLE}"
    for _sid, actions, resources in needs(doc):
        for a in actions:
            for r in resources:
                res = list(paged_marker(iam.simulate_principal_policy, "EvaluationResults",
                                        PolicySourceArn=arn, ActionNames=[a], ResourceArns=[r]))
                decision = res[0]["EvalDecision"] if len(res) == 1 else "unclear:%d results" % len(res)
                out.append((a, r, decision))
    return out


def trust_report(iam, out):
    try:
        doc = iam.get_role(RoleName=ROLE)["Role"]["AssumeRolePolicyDocument"]
    except Exception as e:
        out(f"  BLOCKED   cannot read the role's trust policy ({code(e)})")
        return False
    if isinstance(doc, str):
        doc = json.loads(doc)
    seen, ok, other = [], False, []
    for st in doc.get("Statement", []):
        for op, conds in (st.get("Condition") or {}).items():
            for k, v in conds.items():
                vals = v if isinstance(v, list) else [v]
                if k == SUB_KEY:
                    seen += vals
                    ok |= any(fnmatch.fnmatchcase(SUB, x) for x in vals) if "Like" in op else SUB in vals
                elif k.startswith("token.actions.githubusercontent.com:") and k != "token.actions.githubusercontent.com:aud":
                    other.append(k.rsplit(":", 1)[-1])
    for s in seen:
        out(f"  trust sub  {s}")
    if other:
        out(f"  NOTE      trust also constrains: {', '.join(sorted(set(other)))}. A simulation cannot test that; the first run will.")
    if not seen:
        out("  NOTE      no subject condition on the trust policy: any workflow in a repo the provider trusts could assume it. That is a separate finding.")
        return True
    out(f"  {'ok' if ok else 'MISMATCH'}        a run from main presents '{SUB}': " + ("matches." if ok else "does NOT match any trust subject above."))
    return ok


def run(iam, account_of, apply, out=print, doc=None):
    got = account_of()
    if got != ACCOUNT:
        out(f"Refusing to run: credentials resolve to account {got}, not {ACCOUNT}. Use AWS_PROFILE=relayshield.")
        return 2
    doc = doc or json.load(open(DOC))
    out("== trust (can a run from main assume the role?)")
    trust_ok = trust_report(iam, out)
    out("\n== what IAM says the role can do (simulated as the role)")
    try:
        res = simulate(iam, doc)
    except Exception as e:
        out(f"  BLOCKED   cannot simulate ({code(e)}). Needs iam:SimulatePrincipalPolicy; run it from the Identity Center admin session.")
        return 1
    denied = [(a, r) for a, r, d in res if d != "allowed"]
    for a, r, d in res:
        out(f"  {'allowed ' if d == 'allowed' else 'DENIED  '}  {a}  {r.split('function:')[-1] if a.startswith('lambda') else r}" + ('' if d == 'allowed' else f'   [{d}]'))
    if not denied:
        out("\nEvery grant is already in place. Nothing to apply.")
        return 0 if trust_ok else 1
    if not apply:
        out(f"\n{len(denied)} grant(s) missing. Dry run only: add --apply to put {DOC.name} as the new inline policy {POLICY_NAME}.")
        return 1
    iam.put_role_policy(RoleName=ROLE, PolicyName=POLICY_NAME, PolicyDocument=json.dumps(doc))
    out(f"\nCHANGED   put inline policy {POLICY_NAME} on {ROLE} (nothing existing was touched).")
    after = [(a, r) for a, r, d in simulate(iam, doc) if d != "allowed"]
    out("PROVED    every grant is now allowed." if not after else f"STILL DENIED {len(after)}: {after}")
    return 0 if not after and trust_ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    import boto3
    iam, sts = boto3.client("iam", region_name="us-east-1"), boto3.client("sts", region_name="us-east-1")
    return run(iam, lambda: sts.get_caller_identity()["Account"], a.apply)


if __name__ == "__main__":
    sys.exit(main())
