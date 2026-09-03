#!/usr/bin/env python3
"""Every function in LAMBDA_MAP must be invocable by the deploy role.

    python3 tools/check_deploy_invoke_policy.py          # check, exit 1 on a gap
    python3 tools/check_deploy_invoke_policy.py --write  # add the missing ARNs

WHY THIS EXISTS
---------------
deploy_lambdas.yml ends by INVOKING every function it deployed, because
update-function-code succeeding only proves bytes uploaded, not that the handler
imports. That probe runs as relayshield-github-deploy, whose invoke rights are
an EXPLICIT LIST OF ARNS in iam_github_deploy_invoke.json.

So adding a function to LAMBDA_MAP without adding it to that file deploys the
code correctly and then fails the run on AccessDeniedException. That happened on
2026-09-03 with relayshield-discord-bot: run 134 shipped the code -- the log
says "deployed" -- and went red on the probe, which reads at a glance like a
failed deploy and is not one.

Two files that must agree, with nothing checking that they do, is the same shape
as the four pattern tables in CLAUDE.md. This is the check.
"""

import json
import re
import sys

WORKFLOW = ".github/workflows/deploy_lambdas.yml"
POLICY = "iam_github_deploy_invoke.json"
ARN = "arn:aws:lambda:us-east-1:239677749008:function:{}"

# ["relayshield_x.py"]="relayshield-x", inside the LAMBDA_MAP block only. The
# drift check has a map of its own with the same shape, which is why this is
# anchored to the file that owns the probe.
_ENTRY = re.compile(r'^\s*\["(relayshield_[a-z0-9_]+\.py)"\]="([A-Za-z0-9_-]+)"', re.M)


def mapped_functions(text: str) -> set[str]:
    start = text.find("declare -A LAMBDA_MAP=(")
    if start == -1:
        sys.exit(f"{WORKFLOW}: no LAMBDA_MAP found -- has the deployer changed shape?")
    end = text.find("\n          )", start)
    block = text[start:end if end != -1 else len(text)]
    return {func for _, func in _ENTRY.findall(block)}


def main() -> int:
    write = "--write" in sys.argv

    funcs = mapped_functions(open(WORKFLOW).read())
    doc = json.load(open(POLICY))
    stmts = [s for s in doc["Statement"] if "lambda:InvokeFunction" in s["Action"]]
    if len(stmts) != 1:
        sys.exit(f"{POLICY}: expected exactly one InvokeFunction statement, found {len(stmts)}")
    granted = set(stmts[0]["Resource"])

    missing = sorted(ARN.format(f) for f in funcs if ARN.format(f) not in granted)
    extra = sorted(a for a in granted if a.rsplit(":", 1)[-1] not in funcs)

    for arn in extra:
        # Not a failure. A function can be dropped from the deployer and keep a
        # harmless grant, and over-granting invoke on our own functions is not a
        # security finding worth failing a check over.
        print(f"  note    granted but not in LAMBDA_MAP: {arn.rsplit(':', 1)[-1]}")

    if not missing:
        print(f"All {len(funcs)} mapped functions are invocable by the deploy role.")
        return 0

    for arn in missing:
        print(f"  MISSING {arn.rsplit(':', 1)[-1]}")

    if not write:
        print()
        print(f"{len(missing)} function(s) would deploy and then fail the import probe with")
        print("AccessDeniedException, which reads like a failed deploy and is not one.")
        print(f"Fix:  python3 tools/check_deploy_invoke_policy.py --write")
        print("Then apply it to AWS:  sh tools/apply_deploy_invoke_policy.sh")
        return 1

    stmts[0]["Resource"] = sorted(granted | set(missing))
    with open(POLICY, "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print()
    print(f"Added {len(missing)} ARN(s) to {POLICY}. That is the repo half only --")
    print("AWS still has the old policy until:  sh tools/apply_deploy_invoke_policy.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
