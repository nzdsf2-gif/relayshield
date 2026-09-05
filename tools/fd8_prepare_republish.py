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
    if pypi and doc.get("version") != pypi:
        changes["version"] = (doc.get("version"), pypi)

    print("== 3. Changes")
    if not changes:
        print("   none. server.json already says everything above.")
    for field, (was, now) in changes.items():
        print(f"   {field}\n      was  {was}\n      now  {now}")
    print()

    if not changes:
        return
    if not args.write:
        print("Report only. Re-run with --write to apply, then read the diff before publishing.")
        return

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
    print()

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
    print()

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


if __name__ == "__main__":
    main()
