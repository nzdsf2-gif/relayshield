#!/usr/bin/env python3
"""Run every test_*.py at the repo root and fail on any NEW failure.

    python3 tools/run_test_suite.py                 # whole suite, parallel
    python3 tools/run_test_suite.py test_a.py ...   # just these files
    python3 tools/run_test_suite.py --list-known    # print the known-failing list

WHY THIS EXISTS. The Well-Architected review (OPS, REL 8) asks whether tests run before a change
ships. Until 2026-10-27 they did not: 104 test files existed and nothing ran them, so a red test
was invisible until someone happened to run it by hand. The suites are standalone scripts
(`python3 test_x.py`, exit code 0 or not), not a pytest tree, so this runs each as its own process.

THE RATCHET. 13 files already failed when this was written (tests_known_failing.txt, each one a
real failure, not an environment gap: the CI job installs the dependencies they need). The gate:

  * a file NOT in the list that fails            -> exit 1. This is the gate.
  * a file IN the list that now passes           -> printed as a notice, exit 0. Delete the line.
  * a file IN the list that still fails          -> expected, listed, exit 0.

The list may only shrink. Adding a line to hide a new failure defeats the gate, and the diff to
tests_known_failing.txt is what a reviewer reads. Fix the test instead.

The dependency set the suite needs is in tests_requirements.txt. boto3 is installed on purpose
and a few suites that stub it still pass; a different set gives a different baseline.
"""
import concurrent.futures
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KNOWN = ROOT / "tests_known_failing.txt"
TIMEOUT_S = 180
WORKERS = 8


def known_failing():
    if not KNOWN.exists():
        return set()
    out = set()
    for line in KNOWN.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line)
    return out


def run_one(name):
    try:
        p = subprocess.run(
            [sys.executable, name], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT_S
        )
        return name, p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return name, 124, f"TIMEOUT after {TIMEOUT_S}s"


def main(argv):
    if "--list-known" in argv:
        print("\n".join(sorted(known_failing())))
        return 0
    files = [a for a in argv if not a.startswith("-")] or sorted(
        p.name for p in ROOT.glob("test_*.py")
    )
    known = known_failing()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = sorted(ex.map(run_one, files))

    new_failures = [(n, rc, out) for n, rc, out in results if rc != 0 and n not in known]
    still_failing = [n for n, rc, _ in results if rc != 0 and n in known]
    now_passing = [n for n, rc, _ in results if rc == 0 and n in known]
    passed = sum(1 for _, rc, _ in results if rc == 0)

    print(f"{len(results)} test files: {passed} passed, "
          f"{len(still_failing)} known-failing, {len(new_failures)} NEW failures")
    for n in still_failing:
        print(f"  known   {n}")
    for n in now_passing:
        print(f"  NOTICE  {n} passes now: delete its line from tests_known_failing.txt")
    for n, rc, out in new_failures:
        print(f"\n=== NEW FAILURE: {n} (exit {rc}) ===")
        print("\n".join(out.strip().splitlines()[-40:]))
    if new_failures:
        print(f"\nFAIL: {len(new_failures)} test file(s) failed that are not in tests_known_failing.txt.")
        return 1
    print("\nOK: no new failures.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
