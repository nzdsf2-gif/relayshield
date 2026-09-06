#!/usr/bin/env python3
"""FD-8, FD-9 and FD-10 in one pass: fix server.json, then publish once.

    python3 tools/fd8_prepare_republish.py --dir ~/mcp-live            # report only
    python3 tools/fd8_prepare_republish.py --dir ~/mcp-live --write    # make the edits

Reports first, edits only with --write, and never publishes: the publish is one
command you run yourself once you have read the diff.

WHAT ONE RE-PUBLISH FIXES, and why it is three things rather than one:

  FD-8   websiteUrl is a bare https://relayshield.net with no ?source= key, so
         four months of arrivals from the canonical MCP directory logged
         unmatched: and rendered no banner.
  FD-9   repository.url says github.com/relayshield/relayshield-mcp, which
         404s. The Glama listing path mirrors that same owner, so a broken
         repository URL is not cosmetic: it is a dead link on a live listing
         somebody else built for us.
  FD-10  the registry's latest version is 0.2.7 while PyPI is on 0.2.9, so a
         client installing from the registry record gets an older package than
         one installing from PyPI. And pyproject.toml's Documentation link
         points at the developers page with no ?source= at all, so every
         arrival from the place the package is actually installed from logs
         unattributed. Both are fixed here.

The registry is versioned, so all three land in a single new version.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

SOURCE_KEY = "mcp-registry"
WEBSITE = f"https://relayshield.net?source={SOURCE_KEY}"


def git_remote(d):
    try:
        out = subprocess.run(["git", "-C", d, "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=20)
        url = out.stdout.strip()
    except Exception:
        return ""
    if not url:
        return ""
    # git@github.com:owner/repo.git and https://github.com/owner/repo.git both
    # have to end up as the browser URL the registry wants.
    m = re.search(r"github\.com[:/]+([^/]+)/(.+?)(?:\.git)?$", url)
    return f"https://github.com/{m.group(1)}/{m.group(2)}" if m else url


def pypi_latest(name):
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=20) as r:
            return json.loads(r.read())["info"]["version"]
    except Exception as exc:
        print(f"   (could not read PyPI: {exc})")
        return ""


def registry_latest(server_name):
    try:
        url = "https://registry.modelcontextprotocol.io/v0/servers?search=relayshield"
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
        for entry in data.get("servers", []):
            meta = entry.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {})
            if meta.get("isLatest") and entry["server"].get("name") == server_name:
                return entry["server"].get("version", "")
    except Exception as exc:
        print(f"   (could not read the registry: {exc})")
    return ""


def publish_command(d):
    """Find the publish command the repo already documents. Never invent one."""
    for name in ("README.md", "PUBLISHING.md", "CONTRIBUTING.md", "Makefile"):
        path = os.path.join(d, name)
        if not os.path.exists(path):
            continue
        with open(path, errors="replace") as fh:
            for line in fh:
                if "mcp-publisher" in line:
                    return name, line.strip()
    return "", ""


def _semver(v):
    """(major, minor, patch) for comparison. Anything unparseable sorts lowest,
    so a weird local value can never look 'ahead' and suppress a real update."""
    parts = []
    for chunk in str(v or "").split(".")[:3]:
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else -1)
    while len(parts) < 3:
        parts.append(-1)
    return tuple(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="the MCP server repo, e.g. ~/mcp-live")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    d = os.path.expanduser(args.dir)
    sj = os.path.join(d, "server.json")
    if not os.path.exists(sj):
        sys.exit(f"no server.json in {d}. Is that the MCP server repo?")

    with open(sj) as fh:
        doc = json.load(fh)

    name = doc.get("name", "")
    print("== 1. What server.json says now")
    print(f"   name        {name}")
    print(f"   version     {doc.get('version')}")
    print(f"   websiteUrl  {doc.get('websiteUrl')}")
    print(f"   repository  {(doc.get('repository') or {}).get('url')}")
    print()

    print("== 2. What it should say")
    remote = git_remote(d)
    print(f"   git remote origin resolves to  {remote or '(none found)'}")
    pypi = pypi_latest("relayshield-mcp")
    reg = registry_latest(name)
    print(f"   PyPI latest      {pypi or '?'}")
    print(f"   registry latest  {reg or '?'}")
    if pypi and reg and pypi != reg:
        print(f"   -> the registry is behind PyPI. Publish {pypi}.")
    print()

    changes = {}
    if doc.get("websiteUrl") != WEBSITE:
        changes["websiteUrl"] = (doc.get("websiteUrl"), WEBSITE)
    if remote and (doc.get("repository") or {}).get("url") != remote:
        changes["repository.url"] = ((doc.get("repository") or {}).get("url"), remote)
    # NEVER LOWER THE VERSION. On 2026-09-05 this wrote 0.2.9 over a local 0.2.11,
    # because it compared for inequality and assumed "different" meant "behind".
    # A registry record must name a package version that EXISTS on PyPI, so being
    # ahead is a real state with a real meaning -- the package has not been
    # uploaded yet -- and the fix is to upload it, not to move the record back.
    local_v = doc.get("version")
    if pypi and local_v != pypi:
        if _semver(local_v) > _semver(pypi):
            print(f"   NOTE: server.json is at {local_v}, AHEAD of PyPI's {pypi}.")
            print("   Not touching it. A registry record naming a version that is not on")
            print("   PyPI advertises a package nobody can install, so the order is:")
            print(f"   fix the pin, build, upload {local_v} to PyPI, THEN publish the record.")
        else:
            changes["version"] = (local_v, pypi)

    print("== 3. Changes")
    if not changes:
        print("   none. server.json already says everything above.")
    for field, (was, now) in changes.items():
        print(f"   {field}\n      was  {was}\n      now  {now}")
    print()

    # NOT a return. Sections 4, 4b and 5 are independent of server.json, and the
    # pin in 4b is the one that decides whether the published package starts at
    # all. Returning here because server.json happened to be correct is how the
    # urgent fix silently never runs -- the quiet-alarm shape, in this file.
    if changes and not args.write:
        print("Report only. Re-run with --write to apply, then read the diff before publishing.")
    if changes and args.write:
        _apply_server_json(doc, changes, sj, remote, pypi)
    print()

    _pyproject_sections(d, args)

    where, cmd = publish_command(d)
    print("== 5. Publish")
    print("   Read the diff first:  git -C %s --no-pager diff server.json" % args.dir)
    if cmd:
        print(f"   The command this repo already documents, from {where}:")
        print(f"     {cmd}")
    else:
        print("   No mcp-publisher command found in README.md, PUBLISHING.md, CONTRIBUTING.md")
        print("   or Makefile. Do NOT invent one: find how the last version was published")
        print("   before running anything.")


def _apply_server_json(doc, changes, sj, remote, pypi):
    if "websiteUrl" in changes:
        doc["websiteUrl"] = WEBSITE
    if "repository.url" in changes:
        doc.setdefault("repository", {})["url"] = remote
        doc["repository"].setdefault("source", "github")
    if "version" in changes:
        doc["version"] = pypi
        # The package version has to move with it, or the registry advertises a
        # version whose package does not exist.
        for pkg in doc.get("packages", []):
            if pkg.get("identifier") == "relayshield-mcp":
                pkg["version"] = pypi

    with open(sj + ".bak", "w") as fh:
        json.dump(json.load(open(sj)), fh, indent=2)
    with open(sj, "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print(f"   written. previous file kept as {sj}.bak")


def _pyproject_sections(d, args):
    # FD-10's other half: the package's own links.
    print("== 4. pyproject.toml links (FD-10)")
    pyproj = os.path.join(d, "pyproject.toml")
    if not os.path.exists(pyproj):
        print("   no pyproject.toml here. Skipping; it may live in a subdirectory.")
    else:
        with open(pyproj) as fh:
            text = fh.read()
        want = "https://api.relayshield.net/developers?source=pypi"
        current = re.search(r'Documentation\s*=\s*"([^"]+)"', text)
        print(f"   Documentation  {current.group(1) if current else '(not set)'}")
        if current and current.group(1) == want:
            print("   already attributed.")
        elif not args.write:
            print(f"   should be     {want}")
            print("   --write will change it.")
        else:
            if current:
                text = text.replace(current.group(0), f'Documentation = "{want}"')
            else:
                # No Documentation key: add one under [project.urls] if present.
                if "[project.urls]" in text:
                    text = text.replace("[project.urls]",
                                        f'[project.urls]\nDocumentation = "{want}"', 1)
                else:
                    print("   no [project.urls] section. Add one by hand:")
                    print(f'     [project.urls]\n     Documentation = "{want}"')
                    text = None
            if text is not None:
                with open(pyproj, "w") as fh:
                    fh.write(text)
                print(f"   written -> {want}")
                print("   This ships with the NEXT PyPI release, not with the registry publish.")
    # THE URGENT ONE, added 2026-09-05. Not a link, a live outage.
    print("== 4b. The `mcp` dependency pin - THE PACKAGE IS BROKEN WITHOUT THIS")
    print("   relayshield-mcp declares `mcp` with NO UPPER BOUND, so a fresh")
    print("   `pip install relayshield-mcp` resolves mcp 2.x and the server dies at")
    print("   import with: AttributeError: 'Server' object has no attribute 'list_tools'.")
    print("   Reproduced in a clean venv 2026-09-05. The wheel is fine; the range is not.")
    _fix_mcp_pin(d, args)


# A dependency on `mcp` can be written a dozen ways, and the first version of
# this matched exactly one of them -- it reported "no bare mcp>= dependency
# found" against a real package whose own PyPI metadata says mcp>=1.0.0. "Not
# found" from a narrow matcher looks identical to "nothing to fix", which is the
# quiet-alarm shape for the third time in one file. So: search several files,
# match several syntaxes, and when nothing matches, SHOW what was searched.
_DEP_FILES = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")

# PEP 508 inside a list, and Poetry's table form. `relayshield-mcp` must never
# match, which is what the preceding-character guard is for.
_PIN_LIST = re.compile(
    r"""(?P<q>["'])(?<![-\w])mcp\s*(?P<op>>=|>|==|~=)\s*(?P<ver>[0-9][^"']*?)(?P=q)"""
)
_PIN_POETRY = re.compile(
    r"""^(?P<lead>\s*mcp\s*=\s*)(?P<q>["'])(?P<spec>[\^~>=][^"']*)(?P=q)""", re.M
)


def _fix_mcp_pin(d, args):
    found = []
    for fname in _DEP_FILES:
        path = os.path.join(d, fname)
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            text = fh.read()
        for pat in (_PIN_LIST, _PIN_POETRY):
            for m in pat.finditer(text):
                line = text[: m.start()].count("\n") + 1
                found.append((path, fname, text, pat, m, line))

    if not found:
        print("   NO `mcp` DEPENDENCY MATCHED in: " + ", ".join(_DEP_FILES))
        print("   under " + d)
        print("   That is NOT the same as 'nothing to fix'. PyPI's own metadata for")
        print("   relayshield-mcp says `mcp>=1.0.0`, so the declaration exists somewhere")
        print("   this did not look. The pin must end up bounded at <2. Grep for it:")
        print("     grep -rn mcp " + d + "/pyproject.toml " + d + "/setup.py 2>/dev/null | grep -v relayshield")
        _show_dep_context(d)
        return

    for path, fname, text, pat, m, line in found:
        raw = m.group(0).strip()
        if "<2" in raw:
            print("   " + fname + ":" + str(line) + "  already bounded: " + raw)
            continue
        if pat is _PIN_LIST:
            fixed = m.group("q") + "mcp" + m.group("op") + m.group("ver") + ",<2" + m.group("q")
        else:
            spec = m.group("spec")
            if spec.startswith("^"):
                # Poetry's caret ALREADY excludes 2.0 for a 1.x floor. Say so
                # rather than rewriting it into something that means the same.
                print("   " + fname + ":" + str(line) + "  " + raw)
                print("        Poetry's ^1.x already excludes 2.0, so this file is fine.")
                print("        The PUBLISHED metadata is what decides, though. Confirm with:")
                print("          python3 tools/mcp_selftest.py --pypi")
                continue
            fixed = m.group("lead") + m.group("q") + spec + ",<2" + m.group("q")
        if not args.write:
            print("   " + fname + ":" + str(line) + "  currently  " + raw)
            print("                  should be  " + fixed.strip())
            print("   --write will change it.")
        else:
            with open(path, "w") as fh:
                fh.write(text[: m.start()] + fixed + text[m.end():])
            print("   " + fname + ":" + str(line) + "  written -> " + fixed.strip())
            print()
            print("   THIS NEEDS A NEW PYPI RELEASE, NOT THE REGISTRY PUBLISH. Bump the")
            print("   package version, build, and upload to PyPI FIRST; then publish the")
            print("   registry record so it pins a version that works.")
            print("   Verify AFTER uploading, never before:")
            print("     python3 tools/mcp_selftest.py --pypi")
            print("   That installs what a NEW USER gets. Our own venv passing proves")
            print("   nothing: it holds an older pin the resolver would never choose.")


def _show_dep_context(d):
    """Print the real dependency block, so the operator can see the syntax the
    matcher missed instead of guessing at it."""
    path = os.path.join(d, "pyproject.toml")
    if not os.path.exists(path):
        return
    with open(path) as fh:
        lines = fh.read().splitlines()
    hits = [i for i, l in enumerate(lines)
            if "dependencies" in l.lower() or "install_requires" in l]
    if not hits:
        return
    print()
    print("   What pyproject.toml actually says around its dependencies:")
    for i in hits[:3]:
        for j in range(i, min(i + 8, len(lines))):
            print("     %4d| %s" % (j + 1, lines[j]))
        print()
    print()


if __name__ == "__main__":
    main()
