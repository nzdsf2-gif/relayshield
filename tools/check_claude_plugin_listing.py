#!/usr/bin/env python3
"""Has RelayShield appeared in Anthropic's plugin directory yet? FD-12.

WHY THIS EXISTS. FD-12's form was submitted on 2026-09-06 and the FRONT_DOORS
row still said "ROUTE OPEN, ARTEFACT BUILT" thirteen days later, two hundred
lines above a sentence in the same file saying it had been submitted. A status
that nothing measures drifts, and re-deriving it costs a round every time.

THERE IS NO TICKET AND NO FOLLOW-UP ROUTE. The form returns no reference, the
repo has no issue template, and -- read from their own workflows rather than
assumed -- `close-external-prs.yml` AUTO-CLOSES a pull request from anyone who
is not a member, unless it adds an entry whose source repo ALREADY backs a live
listing. Ours does not, so a PR would be closed unread. That is the FD-2
failure with the evidence read beforehand instead of afterwards.

So the only thing left is to watch, and watching is cheap: the directory IS a
single JSON file, public, and it either names us or it does not.

    python3 tools/check_claude_plugin_listing.py

Exit 0 whatever the answer. A watcher that fails on "not yet" is a red run
nobody reads by the third week. The workflow opens an issue on LISTED.

UNREACHABLE is printed as a fact about the network, never as absence: this
container reaches raw.githubusercontent.com, but a runner behind a proxy might
not, and "the directory does not list us" and "I could not read the directory"
are different findings with different next steps.
"""
import json
import re
import sys
import urllib.error
import urllib.request

CATALOG = ("https://raw.githubusercontent.com/anthropics/"
           "claude-plugins-official/main/.claude-plugin/marketplace.json")

# Match on the NAME we submitted and on our repo, because either one appearing
# means we are in. A name can be renamed by the maintainer on the way in; the
# source url cannot, since it is what the entry fetches.
OUR_NAME = "relayshield"
OUR_REPOS = ("nzdsf2-gif/relayshield", "relayshield/relayshield-plugin")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def fetch(url: str, timeout: float = 20.0):
    """A default Python-urllib user agent is 403'd by more CDNs than not, and
    this repo has paid for that once already on dev.to. A 403 would read here
    as 'the catalog moved'."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def entry_repo(plugin: dict) -> str:
    source = plugin.get("source")
    if isinstance(source, dict):
        return str(source.get("url") or "")
    return str(source or "")


def main() -> int:
    try:
        catalog = fetch(CATALOG)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            json.JSONDecodeError) as exc:
        print("UNREACHABLE")
        print(f"  {CATALOG}")
        print(f"  {type(exc).__name__}: {exc}")
        print("\n  This says nothing about whether we are listed. It is a fact")
        print("  about this machine's network, exactly as a 000 from a")
        print("  catalogue host is. Do not record it as 'not listed'.")
        print("\nCLAUDE_PLUGIN_LISTING=undetermined")
        return 0

    plugins = catalog.get("plugins") or []
    hits = [p for p in plugins
            if p.get("name") == OUR_NAME
            or any(r in entry_repo(p).lower() for r in OUR_REPOS)]

    print(f"directory : {len(plugins)} plugins")
    security = [p for p in plugins if p.get("category") == "security"]
    print(f"security  : {len(security)}")

    if hits:
        print("\nLISTED. FD-12 is live.")
        for p in hits:
            print(f"  name     : {p.get('name')}")
            print(f"  category : {p.get('category')}")
            print(f"  source   : {entry_repo(p) or p.get('source')}")
        print("\n  NEXT, and none of it is automatic:")
        print("  - FRONT_DOORS.md FD-12 row AND its section, both, or the")
        print("    record is half written.")
        print("  - Register nothing new: the install path in the listing is")
        print("    what the published blog post already tells readers to run.")
        print("  - The install command is the measurable surface. Anything")
        print("    pointing at the plugin carries ?source=claude-skill.")
        print("\nCLAUDE_PLUGIN_LISTING=listed")
        return 0

    print("\nNOT LISTED YET.")
    print("  Submitted 2026-09-06 via https://clau.de/plugin-directory-submission")
    print("  There is no ticket, no issue template and no PR route: their")
    print("  close-external-prs workflow auto-closes a non-member PR unless it")
    print("  adds an entry whose source repo already backs a live listing.")
    print("  So the only actions available are to wait, or to re-submit a")
    print("  STRONGER entry. The strongest available improvement is the org")
    print("  move -- their guide calls org ownership the single biggest thing")
    print("  that speeds up review, and our marketplace is a personal account")
    print("  for a plugin branded RelayShield.")
    print("\nCLAUDE_PLUGIN_LISTING=absent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
