#!/usr/bin/env python3
"""Every .github/workflows/*.yml must parse.

    python3 test_workflows_parse.py

WHY THIS EXISTS
---------------
On 2026-09-02 a comment was inserted into lambda_drift_check.yml at the wrong
indentation. The lines dedented out of the `run: |` block, which broke the YAML,
and GitHub's response to a workflow it cannot parse is:

    .github/workflows/lambda_drift_check.yml: No jobs were run

That is not a failure notification. It is quieter than a failure: the check that
exists to catch silent drift became silently dead itself, and stayed that way
across scheduled runs because "no jobs were run" reads like nothing happened.

A red workflow gets read. A workflow that does not run gets ignored. So the
class of bug worth guarding is not "the check found something" -- it is "the
check is not running at all".

Deliberately a standalone script and NOT a workflow. A workflow that validates
workflows fails the same way it is meant to detect: break its own YAML and it
silently stops guarding. This runs on the Mac, in a container, or from any
session, with no dependency on the thing it is checking.
"""

import glob
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML missing:  ~/.rsvenv/bin/pip install pyyaml\n"
             "then run with ~/.rsvenv/bin/python")

REQUIRED_KEYS = ("jobs",)


def main() -> int:
    files = sorted(glob.glob(".github/workflows/*.yml") +
                   glob.glob(".github/workflows/*.yaml"))
    if not files:
        print("no workflows found -- run this from the repository root")
        return 1

    bad = 0
    for path in files:
        try:
            doc = yaml.safe_load(open(path))
        except Exception as exc:
            bad += 1
            print(f"  BROKEN  {path}")
            print(f"          {str(exc).splitlines()[0]}")
            continue

        # A file that parses but has no jobs also runs nothing, and looks
        # identical from the outside.
        missing = [k for k in REQUIRED_KEYS if not (doc or {}).get(k)]
        if missing:
            bad += 1
            print(f"  EMPTY   {path} -- parses but has no {', '.join(missing)}")
            continue

        print(f"  ok      {path}  ({len(doc['jobs'])} job(s))")

    print()
    if bad:
        print(f"{bad} workflow(s) will not run. GitHub reports this as "
              f"'No jobs were run', which is quieter than a failure.")
        return 1
    print(f"All {len(files)} workflows parse and define jobs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
