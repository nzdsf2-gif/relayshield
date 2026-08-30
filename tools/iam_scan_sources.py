#!/usr/bin/env python3
"""
Work out, from the source alone, which AWS resources each Lambda actually touches.

No AWS credentials needed. This runs anywhere, including in the container, which
is the point: it produces the resource half of the per-function IAM policies that
tools/iam_split_roles.py builds, without anyone having to read 26 inline policies
in the console and guess.

Why this exists
---------------
Every Lambda in the account runs as one shared role,
relayshield-breach-check-role-1sapnwdl, whose convention is one inline policy per
table. That convention is what filled the role's 10,240-byte inline budget on
2026-08-29 and it will fill the managed-policy budget next. The way out is a role
per function, and a role per function needs to know what that function uses.

What it does NOT do
-------------------
It does not decide which ACTIONS a function needs. Guessing actions from source
is how you ship a role that works until the first quarterly code path runs. The
actions come from the shared role's existing policies, which are known to work --
see tools/iam_split_roles.py, which intersects the two.

Output
------
iam/required_resources.json, keyed by Lambda function name.

Usage
-----
    python3 tools/iam_scan_sources.py            # write iam/required_resources.json
    python3 tools/iam_scan_sources.py --print    # write it and dump a summary
    python3 tools/iam_scan_sources.py --check    # exit 1 if the file is stale
"""

import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "deploy_lambdas.yml")
OUT = os.path.join(REPO, "iam", "required_resources.json")
KNOWN_NON_RESOURCES = os.path.join(REPO, "iam", "known_non_resources.json")

# ---------------------------------------------------------------------------
# The handler -> function map is READ from deploy_lambdas.yml rather than copied
# here. A second copy would drift from the first, and a drifted IAM map produces
# a role that is missing a permission -- which fails at runtime, in production,
# on whatever code path happens to need it.
# ---------------------------------------------------------------------------
_MAP_LINE = re.compile(r'^\s*\["(?P<src>[^"]+)"\]="(?P<func>[^"]+)"')


def load_lambda_map(path=WORKFLOW):
    mapping = {}
    inside = False
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if "declare -A LAMBDA_MAP=(" in line:
                inside = True
                continue
            if inside:
                if line.strip().startswith(")"):
                    break
                m = _MAP_LINE.match(line)
                if m:
                    mapping[m.group("src")] = m.group("func")
    if not mapping:
        raise SystemExit("could not parse LAMBDA_MAP out of %s" % path)
    return mapping


# ---------------------------------------------------------------------------
# Import closure. Deliberately the same walk deploy_lambdas.yml does, for the
# same reason: a handler's permissions are the union of every local module it
# pulls in, not just the ones named in its own file.
# ---------------------------------------------------------------------------
_IMPORT = re.compile(r'^[ \t]*(?:import|from)[ \t]+(relayshield_[a-z0-9_]+)', re.M)


def resolve_deps(seeds):
    seen, queue = set(seeds), list(seeds)
    while queue:
        cur = queue.pop(0)
        path = os.path.join(REPO, cur)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            body = fh.read()
        for mod in _IMPORT.findall(body):
            dep = mod + ".py"
            if dep not in seen:
                seen.add(dep)
                queue.append(dep)
    return sorted(seen)


# ---------------------------------------------------------------------------
# Resource extraction.
#
# Classification is by CONTEXT, never by shape. A bare "any relayshield_* string
# literal is a table" rule looks like it works and is wrong: relayshield_internal
# is an alert `source` field and relayshield_key is a secret-scanner regex label.
# Neither is a table, and granting dynamodb:* on them would be noise in a policy
# that is meant to be readable.
# ---------------------------------------------------------------------------

# NAME = "relayshield_foo"  where NAME says table
_ASSIGN_TABLE = re.compile(
    r'^[ \t]*(?P<name>[A-Za-z_][A-Za-z0-9_]*(?:TABLE|Table|table)[A-Za-z0-9_]*)'
    r'[ \t]*=[ \t]*["\'](?P<val>relayshield_[a-z0-9_]+)["\']', re.M)

# NAME = os.environ.get("X_TABLE", "relayshield_foo")   -- the default is the
# real table; the env var only ever overrides it in a test rig.
_ENV_TABLE = re.compile(
    r'os\.environ(?:\.get)?[\(\[][ \t]*["\'][A-Za-z0-9_]*(?:TABLE|Table|table)[A-Za-z0-9_]*["\']'
    r'[ \t]*,[ \t]*["\'](?P<val>relayshield_[a-z0-9_]+)["\']')

# .Table("relayshield_foo")  /  TableName="relayshield_foo"
_CALL_TABLE = re.compile(
    r'(?:\.Table\([ \t]*|TableName[ \t]*=[ \t]*)["\'](?P<val>relayshield_[a-z0-9_]+)["\']')

# Secrets Manager ids are namespaced with a slash, which is what tells them apart
# from everything else in the file.
_SECRET = re.compile(r'["\'](?P<val>relayshield/[A-Za-z0-9/_.-]+)["\']')

_BOTO = re.compile(r'boto3\.(?:client|resource)\([ \t]*["\'](?P<val>[a-z0-9-]+)["\']')

_FUNCTION_NAME = re.compile(
    r'FunctionName[ \t]*=[ \t]*["\'](?P<val>relayshield[A-Za-z0-9_-]*)["\']')

_S3_BUCKET = re.compile(r'Bucket[ \t]*=[ \t]*["\'](?P<val>[A-Za-z0-9._-]+)["\']')

_KMS_KEY = re.compile(r'["\'](?P<val>(?:alias/[A-Za-z0-9/_-]+|'
                      r'arn:aws:kms:[a-z0-9-]+:\d{12}:key/[a-f0-9-]+))["\']')

# Table-shaped literals we saw but could not attribute to a table context. Kept
# in the output on purpose: an unclassified literal is either harmless or a table
# reached by a pattern this scanner does not know, and silently dropping it is
# how a function ends up one permission short.
_ANY_UNDERSCORE = re.compile(r'["\'](?P<val>relayshield_[a-z0-9_]+)["\']')


def scan_module(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        body = fh.read()

    tables = set()
    for rx in (_ASSIGN_TABLE, _ENV_TABLE, _CALL_TABLE):
        tables.update(m.group("val") for m in rx.finditer(body))

    seen_any = {m.group("val") for m in _ANY_UNDERSCORE.finditer(body)}

    return {
        "tables": tables,
        "secrets": {m.group("val") for m in _SECRET.finditer(body)},
        "services": {m.group("val") for m in _BOTO.finditer(body)},
        "invokes": {m.group("val") for m in _FUNCTION_NAME.finditer(body)},
        "buckets": {m.group("val") for m in _S3_BUCKET.finditer(body)},
        "kms_keys": {m.group("val") for m in _KMS_KEY.finditer(body)},
        "unclassified": seen_any - tables,
    }


KEYS = ("tables", "secrets", "services", "invokes", "buckets", "kms_keys", "unclassified")
# Derived during the build rather than scanned for, so it is listed separately.
OUT_KEYS = KEYS + ("reviewed_non_resources",)


def load_known_non_resources(path=KNOWN_NON_RESOURCES):
    """Literals a human has already confirmed are not AWS resources.

    Suppressing them is cosmetic and grants nothing: this scanner only ever
    produces the resource list a policy is NARROWED to. The value is that the
    'unclassified' bucket stays small enough that a genuinely new literal in it
    is noticed rather than skimmed past.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return set(json.load(fh).get("entries", {}))
    except FileNotFoundError:
        return set()


def build():
    lambda_map = load_lambda_map()
    reviewed = load_known_non_resources()

    # function -> the handler files that ship in its package
    by_func = {}
    for src, func in lambda_map.items():
        by_func.setdefault(func, []).append(src)

    result = {}
    for func in sorted(by_func):
        seeds = sorted(s for s in by_func[func] if os.path.isfile(os.path.join(REPO, s)))
        if not seeds:
            continue
        modules = resolve_deps(seeds)
        acc = {k: set() for k in KEYS}
        for mod in modules:
            path = os.path.join(REPO, mod)
            if not os.path.isfile(path):
                continue
            found = scan_module(path)
            for k in KEYS:
                acc[k] |= found[k]
        # A literal classified as a table anywhere in the package is a table
        # everywhere in it.
        acc["unclassified"] -= acc["tables"]
        # Already looked at once; see iam/known_non_resources.json.
        acc["reviewed_non_resources"] = acc["unclassified"] & reviewed
        acc["unclassified"] -= reviewed
        result[func] = {
            "modules": modules,
            **{k: sorted(acc[k]) for k in OUT_KEYS},
        }

    unmapped = sorted(
        f for f in os.listdir(REPO)
        if f.startswith("relayshield_") and f.endswith(".py") and f not in lambda_map
        and os.path.isfile(os.path.join(REPO, f))
    )

    return {
        "_generated_by": "tools/iam_scan_sources.py",
        "_source_of_truth": ".github/workflows/deploy_lambdas.yml LAMBDA_MAP",
        "_note": (
            "Resources only. Actions come from the shared role's existing policies -- "
            "see tools/iam_split_roles.py. Regenerate with "
            "'python3 tools/iam_scan_sources.py' after changing any handler."
        ),
        "_unmapped_sources": unmapped,
        "functions": result,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", dest="show", action="store_true",
                    help="dump a per-function summary as well as writing the file")
    ap.add_argument("--check", action="store_true",
                    help="do not write; exit 1 if iam/required_resources.json is stale")
    args = ap.parse_args()

    data = build()
    rendered = json.dumps(data, indent=2, sort_keys=False) + "\n"

    if args.check:
        try:
            with open(OUT, encoding="utf-8") as fh:
                current = fh.read()
        except FileNotFoundError:
            print("iam/required_resources.json is missing -- run tools/iam_scan_sources.py")
            return 1
        if current != rendered:
            print("iam/required_resources.json is stale -- run tools/iam_scan_sources.py")
            return 1
        print("iam/required_resources.json is up to date")
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(rendered)
    print("wrote %s (%d functions)" % (os.path.relpath(OUT, REPO), len(data["functions"])))

    if data["_unmapped_sources"]:
        print("\n%d relayshield_*.py sources are not in LAMBDA_MAP. Any of them that is a"
              % len(data["_unmapped_sources"]))
        print("deployed handler has no deploy path and no drift detection -- see CLAUDE.md.")

    if args.show:
        for func, info in data["functions"].items():
            print("\n%s" % func)
            print("  modules  : %d" % len(info["modules"]))
            for k in ("services", "tables", "secrets", "invokes", "buckets", "kms_keys"):
                if info[k]:
                    print("  %-9s: %s" % (k, ", ".join(info[k])))
            if info["unclassified"]:
                print("  unclassified (check these are not tables): %s"
                      % ", ".join(info["unclassified"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
