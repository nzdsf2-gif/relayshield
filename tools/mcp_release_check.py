#!/usr/bin/env python3
"""Is ~/mcp-live ready to publish, and to what version? Read-only.

    python3 tools/mcp_release_check.py --dir ~/mcp-live

WHY THIS IS NOT JUST `twine upload`
------------------------------------
PyPI refuses to replace an existing version, so an upload with a stale version
number fails after the build, with an error about the FILE rather than about the
number. And the thing being fixed here is a dependency range, which means a
successful upload of the wrong version would leave the break in place while
looking like a release.

Three numbers have to agree before anything is built, and on 2026-09-05 they did
not: pyproject.toml's version, server.json's version, and what PyPI already has.

WHAT THE 2026-09-05 STATE ACTUALLY WAS, because it is easy to misread
--------------------------------------------------------------------
`~/mcp-live/pyproject.toml` line 26 already said `mcp>=1.0.0,<2.0.0`. The SOURCE
was never broken. PyPI's published 0.2.9 says `mcp>=1.0.0`, unbounded, because
the fix was made locally and never released.

So this is not "fix the pin". It is "ship the fix that already exists", and the
only thing standing between a working package and a broken one for every new
installer is an upload that nobody ran.
"""

import argparse
import json
import os
import re
import sys
import urllib.request

PYPI = "https://pypi.org/pypi/{}/json"


def semver(v):
    out = []
    for chunk in str(v or "").split(".")[:3]:
        digits = "".join(c for c in chunk if c.isdigit())
        out.append(int(digits) if digits else -1)
    while len(out) < 3:
        out.append(-1)
    return tuple(out)


def bump_patch(v):
    a, b, c = semver(v)
    return f"{max(a,0)}.{max(b,0)}.{max(c,0) + 1}"


def pypi_info(pkg):
    try:
        with urllib.request.urlopen(PYPI.format(pkg), timeout=15) as r:
            doc = json.load(r)
        return doc["info"]["version"], doc["info"].get("requires_dist") or []
    except Exception as exc:
        print(f"   could not read PyPI: {exc}")
        return None, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="~/mcp-live")
    ap.add_argument("--package", default="relayshield-mcp")
    args = ap.parse_args()
    d = os.path.expanduser(args.dir)

    if not os.path.isdir(d):
        sys.exit(f"STOP: {d} does not exist.")

    print("== 1. The three version numbers")
    pyproj = os.path.join(d, "pyproject.toml")
    local_v = None
    pin = None
    if os.path.exists(pyproj):
        text = open(pyproj).read()
        m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', text, re.M)
        local_v = m.group(1) if m else None
        p = re.search(r'''["'](?<![-\w])mcp\s*([><=~^][^"']*)["']''', text)
        pin = p.group(0) if p else None
    print(f"   pyproject.toml version   {local_v or '(not found)'}")

    sj = os.path.join(d, "server.json")
    reg_v = None
    if os.path.exists(sj):
        try:
            reg_v = json.load(open(sj)).get("version")
        except Exception:
            pass
    print(f"   server.json version      {reg_v or '(not found)'}")

    pypi_v, requires = pypi_info(args.package)
    print(f"   PyPI published version   {pypi_v or '?'}")
    print()

    print("== 2. The pin, in the SOURCE and in what is PUBLISHED")
    print(f"   local pyproject   {pin or '(no mcp dependency matched)'}")
    published_pin = next((r for r in requires
                          if r.split(";")[0].strip().lower().startswith("mcp")), None)
    print(f"   published on PyPI {published_pin or '(none)'}")
    src_ok = bool(pin and ("<2" in pin or "^1" in pin))
    pub_ok = bool(published_pin and "<2" in published_pin)
    if src_ok and not pub_ok:
        print()
        print("   THE SOURCE IS FIXED AND THE RELEASE IS NOT.")
        print("   Every new `pip install` still resolves mcp 2.x and dies at import.")
        print("   Nothing needs editing. This needs UPLOADING.")
    elif not src_ok:
        print()
        print("   The source pin is NOT bounded. Fix it before building:")
        print("     python3 tools/fd8_prepare_republish.py --dir %s --write" % args.dir)
    else:
        print()
        print("   Both bounded. Nothing to fix here.")
    print()

    print("== 3. What version to publish")
    if not local_v:
        sys.exit("STOP: no version in pyproject.toml. Cannot advise a number.")
    target = local_v
    if pypi_v and semver(local_v) <= semver(pypi_v):
        target = bump_patch(pypi_v)
        print(f"   pyproject is {local_v}, which PyPI already has (or is behind {pypi_v}).")
        print(f"   PyPI never replaces a version, so the upload would fail.")
        print(f"   BUMP pyproject.toml to {target} first.")
    else:
        print(f"   {local_v} is ahead of PyPI's {pypi_v}. Publish it as is.")
    if reg_v and reg_v != target:
        print(f"   NOTE: server.json says {reg_v}. After the upload succeeds, set it to")
        print(f"   {target} so the registry record names a version that exists.")
    print()

    print("== 4. The commands, in this order")
    print(f"   cd {d}")
    print("   ~/.rsvenv/bin/pip install --quiet build twine")
    print("   rm -rf dist")
    print("   ~/.rsvenv/bin/python -m build")
    print("   ~/.rsvenv/bin/twine upload dist/*")
    print("      username: __token__")
    print("      password: the relayshield-mcp project token, pasted at the prompt")
    print("      (never inline in a command -- it lands in shell history)")
    print()
    print("== 5. Verify AFTER the upload, never before")
    print("   python3 tools/mcp_selftest.py --pypi")
    print("   That builds a throwaway venv and installs what a NEW USER gets.")
    print("   Our own venv passing proves nothing: it holds an older pin the")
    print("   resolver would never choose.")
    print()
    print("   Only once that says ACTIVE:")
    print("     - publish the registry record (FD-8)")
    print("     - enable the MCP server in the Claude Code plugin")


if __name__ == "__main__":
    main()
