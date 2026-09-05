#!/usr/bin/env python3
"""Is the RelayShield MCP server ACTUALLY running? Launch it and ask it.

    python3 tools/mcp_selftest.py            # every server in every client config
    python3 tools/mcp_selftest.py --name relayshield
    python3 tools/mcp_selftest.py --script ./relayshield_mcp_server.py

Read-only. Exit status is 0 only if every server tested answered.

WHY THIS EXISTS, AND WHY THE INVENTORY WAS NOT ENOUGH
-----------------------------------------------------
`tools/mcp_inventory.sh` prints the configs and the last 25 log lines and asks a
human to decide. That is the same shape of check that let the 2026-09-05 outage
run for hours: the log HAD been saying `[Errno 2] No such file or directory`
every few minutes since 04:24 UTC and nobody was reading it, because the config
looked fine and the client only ever said "disconnected".

CLAUDE.md's own rule is that the alarm you must check hardest is the one that
goes quiet. A log tail you have to interpret is a quiet alarm. So this script
does not report evidence for a human to weigh -- it performs the client's own
job (spawn the command, speak MCP to it) and prints ACTIVE or DEAD.

WHAT "ACTIVE" MEANS HERE, PRECISELY
-----------------------------------
The server process started, completed an MCP `initialize` handshake, and
answered `tools/list`. That is exactly what a client does on connect, so a
server that passes here is a server that will not show "disconnected".

It does NOT mean the API key works. A tool CALL costs money and may charge the
account, so this stops at the handshake -- the same boundary
`mpp_settlement_selftest.py --reads-only` draws, and for the same reason.

THREE FAILURES IT SEPARATES, BECAUSE THEY HAVE DIFFERENT FIXES
--------------------------------------------------------------
  ENOENT on the script    the clone moved. tools/fix_mcp_config_paths.py --write
  ModuleNotFoundError     the interpreter in the config lacks `mcp` or `httpx`
  AttributeError on
    Server.list_tools     the `mcp` SDK went to 2.x under us. See below.

That last one is a live risk rather than a hypothetical. `relayshield_mcp_server.py`
registers its tools with the pre-2.x decorator API (`@app.list_tools()`), which
`mcp` 2.x removed. Verified 2026-09-05: on mcp 1.29.1 the server hands over all
8 tools; on mcp 2.1.1 it dies at IMPORT time with

    AttributeError: 'Server' object has no attribute 'list_tools'

An interpreter that upgrades `mcp` therefore breaks the server with no config
change and no code change -- and it presents to the user as "disconnected",
identical to the path bug. Pin `mcp<2` for whatever python the config names, or
port the registrations, but know which one you are looking at first.

NO CREDENTIAL IS PRINTED. Env values are shown as a prefix and a length, per
CLAUDE.md rule 12, because this output is going into a chat.
"""

import argparse
import glob
import json
import os
import selectors
import shutil
import subprocess
import sys

HOME = os.path.expanduser("~")

CANDIDATES = [
    ("Claude Desktop", f"{HOME}/Library/Application Support/Claude/claude_desktop_config.json"),
    ("Claude Code (user)", f"{HOME}/.claude.json"),
    ("Claude Code (settings)", f"{HOME}/.claude/settings.json"),
    ("Cursor", f"{HOME}/.cursor/mcp.json"),
    ("Windsurf", f"{HOME}/.codeium/windsurf/mcp_config.json"),
    ("VS Code", f"{HOME}/Library/Application Support/Code/User/mcp.json"),
]

SECRET_HINTS = ("key", "token", "secret", "password", "payment")


def redact(k, v):
    s = "" if v is None else str(v)
    if any(h in str(k).lower() for h in SECRET_HINTS):
        return f"{s[:4]}… ({len(s)} chars)" if s else "(empty)"
    return s


def servers_from(doc):
    """Client configs disagree about where the server map lives. Check every
    shape rather than assuming one -- guessing reports 'none configured' on a
    machine that has three."""
    out = {}
    if not isinstance(doc, dict):
        return out
    for key in ("mcpServers", "mcp_servers", "servers"):
        if isinstance(doc.get(key), dict):
            out.update(doc[key])
    if isinstance(doc.get("mcp"), dict) and isinstance(doc["mcp"].get("servers"), dict):
        out.update(doc["mcp"]["servers"])
    for proj, pdoc in (doc.get("projects") or {}).items():
        if isinstance(pdoc, dict):
            for name, spec in (pdoc.get("mcpServers") or {}).items():
                out[f"{name}  [project {proj}]"] = spec
    return out


def discover():
    """(client label, server name, spec) for every stdio server declared."""
    paths = list(CANDIDATES)
    for pat in (f"{HOME}/dev/relayshield/.mcp.json", f"{HOME}/dev/*/.mcp.json"):
        for p in glob.glob(pat):
            paths.append(("project .mcp.json", p))
    found = []
    for label, path in paths:
        if not os.path.exists(path):
            continue
        try:
            doc = json.load(open(path))
        except Exception as exc:
            # A config the client cannot parse is a config the client ignores,
            # which looks identical to "no servers configured".
            found.append((label, "(file unreadable)", {"_error": str(exc)}))
            continue
        for name, spec in servers_from(doc).items():
            found.append((label, name, spec if isinstance(spec, dict) else {}))
    return found


def readline_timeout(proc, sel, timeout):
    """One line from the child's stdout, or None. A hung server must fail the
    check rather than hang it -- an unattended run that never returns is the
    quiet alarm again."""
    events = sel.select(timeout)
    if not events:
        return None
    return proc.stdout.readline()


def handshake(command, args, env_extra, timeout=25.0):
    """Do what a client does on connect. Returns (ok, detail, tool_names)."""
    exe = shutil.which(command) or command
    if not os.path.exists(exe) and shutil.which(command) is None:
        return False, f"interpreter not found: {command}", []

    for a in args:
        # Only check things that look like a path we are being asked to run.
        if a.startswith("/") or a.startswith("~"):
            p = os.path.expanduser(a)
            if not os.path.exists(p) and not a.startswith("-"):
                # This is the 2026-09-05 outage exactly, caught before spawning.
                # The client renders it as "disconnected", which names the symptom
                # and not the cause, so name the cause here.
                hint = ""
                if "Side SaaS Hustle" in p or "relayshield_mcp_server.py" in p:
                    hint = ("\n        FIX: the clone moved to ~/dev/relayshield and this "
                            "config still names the old location.\n"
                            "        python3 tools/fix_mcp_config_paths.py --write, "
                            "then QUIT AND REOPEN the client.")
                return False, f"file named in args does not exist: {p}{hint}", []

    env = dict(os.environ)
    env.update({str(k): str(v) for k, v in (env_extra or {}).items()})

    try:
        proc = subprocess.Popen(
            [exe, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, env=env,
        )
    except Exception as exc:
        return False, f"could not spawn: {exc}", []

    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)

    def send(obj):
        try:
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()
            return True
        except Exception:
            return False

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "relayshield-selftest", "version": "1"}}})
        line = readline_timeout(proc, sel, timeout)
        if not line:
            proc.kill()
            err = (proc.stderr.read() or "").strip()
            if err:
                return False, first_cause(err), []
            return False, f"no response to initialize within {timeout:.0f}s", []
        try:
            init = json.loads(line)
        except Exception:
            proc.kill()
            return False, f"initialize returned non-JSON: {line.strip()[:200]}", []
        if "error" in init:
            proc.kill()
            return False, f"initialize error: {init['error']}", []

        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        line = readline_timeout(proc, sel, timeout)
        if not line:
            proc.kill()
            return False, "no response to tools/list", []
        try:
            tools = json.loads(line)["result"]["tools"]
        except Exception:
            proc.kill()
            return False, f"tools/list unreadable: {line.strip()[:200]}", []

        info = (init.get("result") or {}).get("serverInfo") or {}
        detail = f"{info.get('name', '?')} v{info.get('version', '?')}"
        return True, detail, [t.get("name", "?") for t in tools]
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        sel.close()


def first_cause(stderr_text):
    """A Python traceback's LAST line is the exception; the middle is noise.
    Report the exception plus the named fix where we know one, because
    'AttributeError' on its own sends you back to the config, which is fine."""
    lines = [l for l in stderr_text.strip().splitlines() if l.strip()]
    last = lines[-1] if lines else stderr_text.strip()[:200]
    if "list_tools" in stderr_text and "AttributeError" in stderr_text:
        return (last + "\n        FIX: the `mcp` SDK is 2.x and removed the decorator API "
                       "this server registers with. Pin `mcp<2` for the interpreter this "
                       "config names, or port the registrations.")
    if "No such file or directory" in stderr_text or "can't open file" in stderr_text:
        return (last + "\n        FIX: the clone moved. "
                       "python3 tools/fix_mcp_config_paths.py --write, then restart the client.")
    if "ModuleNotFoundError" in stderr_text:
        return (last + "\n        FIX: the interpreter this config names does not have that "
                       "package. Install it into THAT python, not the default one.")
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="", help="only servers whose name contains this")
    ap.add_argument("--script", default="", help="test a server script directly, ignoring configs")
    ap.add_argument("--python", default=sys.executable, help="interpreter for --script")
    ap.add_argument("--timeout", type=float, default=25.0)
    args = ap.parse_args()

    print("== MCP selftest — spawn each server and speak MCP to it")
    print()

    results = []

    if args.script:
        path = os.path.expanduser(args.script)
        print(f"  direct: {args.python} {path}")
        ok, detail, tools = handshake(args.python, [path], {}, args.timeout)
        if ok:
            print(f"      VERDICT : ACTIVE — {detail}, {len(tools)} tools")
            print(f"      tools   : {', '.join(tools)}")
        else:
            print(f"      VERDICT : DEAD — {detail}")
        print()
        results.append(("direct", os.path.basename(path), ok, detail, tools))
    else:
        entries = discover()
        if not entries:
            print("  No MCP client config found at any known path.")
            print("  Nothing is broken; there is no server declared to connect to.")
            return 0
        for label, name, spec in entries:
            if args.name and args.name.lower() not in name.lower():
                continue
            if spec.get("_error"):
                print(f"  {label} / {name}: config UNREADABLE ({spec['_error']})")
                results.append((label, name, False, "config unreadable", []))
                continue
            url = spec.get("url") or spec.get("serverUrl")
            if url:
                # The HF Space and the Apify Actor are HTTP surfaces. They cannot
                # show "disconnected" in a client the way a stdio server does, and
                # probing them is a network test, not this test.
                print(f"  {label} / {name}: remote transport ({url}) — SKIPPED, not stdio")
                continue
            if spec.get("disabled"):
                print(f"  {label} / {name}: DISABLED in this config — skipped")
                continue

            command = spec.get("command", "")
            sargs = spec.get("args") or []
            env_extra = spec.get("env") or {}
            print(f"  {label} / {name}")
            print(f"      command : {command} {' '.join(sargs)}".rstrip())
            for k, v in env_extra.items():
                print(f"      env     : {k} = {redact(k, v)}")
            if not command:
                print("      VERDICT : DEAD — no command and no url in this entry")
                results.append((label, name, False, "no command and no url", []))
                print()
                continue

            ok, detail, tools = handshake(command, sargs, env_extra, args.timeout)
            if ok:
                print(f"      VERDICT : ACTIVE — {detail}, {len(tools)} tools")
                print(f"      tools   : {', '.join(tools)}")
            else:
                print(f"      VERDICT : DEAD — {detail}")
            results.append((label, name, ok, detail, tools))
            print()

    print()
    tested = len(results)
    dead = [r for r in results if not r[2]]
    if not tested:
        print("Nothing matched the filter. Widen --name, or drop it.")
        return 0
    if not dead:
        print(f"ALL {tested} SERVER(S) ACTIVE. Each completed initialize and tools/list,")
        print("which is exactly what a client does on connect.")
        return 0
    print(f"{len(dead)} of {tested} DEAD:")
    for label, name, _ok, detail, _t in dead:
        print(f"  - {label} / {name}: {detail}")
    print()
    print("A config edit changes nothing until the client restarts, so after any fix:")
    print("QUIT AND REOPEN the client, then run this again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
