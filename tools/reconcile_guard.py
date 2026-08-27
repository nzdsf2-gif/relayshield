#!/usr/bin/env python3
"""Assert a reconciled handler kept every symbol from BOTH of its parents.

WHY THIS EXISTS
---------------
On 2026-08-26 four live Lambdas were found to hold ~1,900 lines that exist in
no repository, while main held work that was never deployed. Reconciling those
by hand means merging two large files where each side has real code the other
lacks, and the failure mode is silent: a dropped function does not break the
build, it just stops doing its job in production. That is how the Telegram help
shortcuts were lost on 2026-08-19.

So reconciliation is not finished when it looks right. It is finished when this
says every top-level symbol from the live file AND from main is present in the
result:

    python3 tools/reconcile_guard.py --live LIVE.py --main MAIN.py --result NEW.py

Exit 1 and a named list if anything went missing. A symbol that is meant to
disappear (a genuine rename or removal) is allowed only by naming it
explicitly, so the decision is recorded rather than implied:

    ... --allow-dropped _old_name,_other_name

This checks presence, not behaviour. It cannot tell you a function still works;
it tells you nobody deleted it while merging 800 lines by hand.
"""
from __future__ import annotations

import argparse
import ast
import io
import sys


def symbols(path: str) -> dict[str, str]:
    """Top-level defs, classes and constants, mapped to their kind."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = "function"
        elif isinstance(node, ast.ClassDef):
            out[node.name] = "class"
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                # Module-level CONSTANTS only. Lowercase module globals are
                # usually incidental (a logger, a client), and demanding they
                # match would make the guard noisy enough to be ignored, which
                # is the one way a guard actually fails.
                if isinstance(t, ast.Name) and t.id.isupper():
                    out[t.id] = "constant"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", required=True, help="handler recovered from the deployed package")
    ap.add_argument("--main", required=True, help="handler as committed on main")
    ap.add_argument("--result", required=True, help="the reconciled handler to check")
    ap.add_argument("--allow-dropped", default="",
                    help="comma-separated symbols deliberately removed")
    args = ap.parse_args()

    live, mainf, result = symbols(args.live), symbols(args.main), symbols(args.result)
    allowed = {s.strip() for s in args.allow_dropped.split(",") if s.strip()}

    missing_live = {k: v for k, v in live.items() if k not in result and k not in allowed}
    missing_main = {k: v for k, v in mainf.items() if k not in result and k not in allowed}

    print(f"live   : {len(live):>4} symbols")
    print(f"main   : {len(mainf):>4} symbols")
    print(f"result : {len(result):>4} symbols")
    print(f"union  : {len(set(live) | set(mainf)):>4} expected (minus {len(allowed)} allowed drops)")

    for label, missing, src in (("LIVE", missing_live, args.live), ("MAIN", missing_main, args.main)):
        if missing:
            print(f"\nMISSING, present in {label} ({src}) and absent from the result:")
            for name, kind in sorted(missing.items()):
                print(f"  {kind:<9} {name}")

    only_new = sorted(set(result) - set(live) - set(mainf))
    if only_new:
        print("\nNew in the result, in neither parent (expected only for deliberate additions):")
        for name in only_new:
            print(f"  {name}")

    if missing_live or missing_main:
        print(f"\nFAIL: {len(missing_live) + len(missing_main)} symbol(s) lost in reconciliation.")
        print("Restore them, or name them in --allow-dropped with a reason in the commit.")
        return 1
    print("\nOK: every symbol from both parents survives.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
