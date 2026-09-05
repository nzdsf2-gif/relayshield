#!/bin/sh
# Which MCP servers does this Mac actually have configured, and why is one down?
#
#   sh tools/mcp_inventory.sh
#
# Read-only. It finds every MCP client config on the machine, lists the servers
# each declares, REDACTS every environment value before printing, and then reads
# the client's own logs for the reason a server disconnected.
#
# WHY THE REDACTION IS NOT OPTIONAL
# ---------------------------------
# An MCP server config holds RELAYSHIELD_API_KEY and RELAYSHIELD_X_PAYMENT in
# plain text, and this output is going to be pasted into a chat. CLAUDE.md rule
# 12 is about a credential arriving somewhere nobody typed it. Values are shown
# as their first four characters and a length, which is enough to tell "the key
# is set" from "the key is empty" and not enough to use.
#
# THE LOG IS THE ANSWER, NOT THE CONFIG
# -------------------------------------
# "Disconnected" in a client almost always means the server process exited. The
# config tells you what it tried to run; the log tells you why it stopped, and
# they are usually different problems. Section 3 is the one to read first.

set -eu

echo "== 1. MCP client configs on this machine"
python3 - <<'PY'
import json, os, glob

HOME = os.path.expanduser("~")
CANDIDATES = [
    ("Claude Desktop", f"{HOME}/Library/Application Support/Claude/claude_desktop_config.json"),
    ("Claude Code (user)", f"{HOME}/.claude.json"),
    ("Claude Code (settings)", f"{HOME}/.claude/settings.json"),
    ("Cursor", f"{HOME}/.cursor/mcp.json"),
    ("Windsurf", f"{HOME}/.codeium/windsurf/mcp_config.json"),
    ("VS Code", f"{HOME}/Library/Application Support/Code/User/mcp.json"),
]
# Project-scoped configs in the repo and the documents folder
for pat in (f"{HOME}/dev/relayshield/.mcp.json", f"{HOME}/dev/*/.mcp.json"):
    for p in glob.glob(pat):
        CANDIDATES.append(("project .mcp.json", p))


def redact(v):
    s = str(v)
    if not s:
        return "(empty)"
    return f"{s[:4]}… ({len(s)} chars)"


def servers_from(doc):
    """Client configs disagree about where the map lives. Check the shapes
    rather than assuming one, because guessing here reports 'none configured'
    on a machine that has three."""
    out = {}
    if not isinstance(doc, dict):
        return out
    for key in ("mcpServers", "mcp_servers", "servers"):
        if isinstance(doc.get(key), dict):
            out.update(doc[key])
    if isinstance(doc.get("mcp"), dict) and isinstance(doc["mcp"].get("servers"), dict):
        out.update(doc["mcp"]["servers"])
    # Claude Code nests per-project maps under "projects"
    for proj, pdoc in (doc.get("projects") or {}).items():
        if isinstance(pdoc, dict):
            for name, spec in (pdoc.get("mcpServers") or {}).items():
                out[f"{name}  [project {proj}]"] = spec
    return out


found_any = False
total = 0
for label, path in CANDIDATES:
    if not os.path.exists(path):
        continue
    found_any = True
    print(f"\n  {label}")
    print(f"    {path}")
    try:
        doc = json.load(open(path))
    except Exception as exc:
        print(f"    UNREADABLE: {exc}")
        print("    A config the client cannot parse is a config the client ignores,")
        print("    which looks identical to 'no servers configured'.")
        continue
    srv = servers_from(doc)
    if not srv:
        print("    (no MCP servers declared in this file)")
        continue
    for name, spec in srv.items():
        total += 1
        spec = spec if isinstance(spec, dict) else {}
        cmd = spec.get("command", "")
        args = " ".join(spec.get("args", []) or [])
        url = spec.get("url") or spec.get("serverUrl") or ""
        print(f"    - {name}")
        if url:
            print(f"        transport : remote  {url}")
        else:
            print(f"        command   : {cmd} {args}".rstrip())
        env = spec.get("env") or {}
        if env:
            for k, v in env.items():
                print(f"        env       : {k} = {redact(v)}")
        if spec.get("disabled"):
            print("        DISABLED in this config")

if not found_any:
    print("\n  No MCP client config found at any known path.")
    print("  That is itself the answer if you expected one: the client is reading")
    print("  a file that does not exist, so it has no servers to connect to.")
else:
    print(f"\n  {total} MCP server declaration(s) found in total.")
PY
echo

echo "== 2. Is the RelayShield MCP server installed, and at what version?"
INSTALLED=$(python3 -c "
try:
    from importlib.metadata import version
    print(version('relayshield-mcp'))
except Exception:
    print('not installed for this python3')
" 2>/dev/null || echo "not installed for this python3")
echo "   python3 sees: $INSTALLED"
if [ -x "$HOME/.rsvenv/bin/python" ]; then
  RSV=$("$HOME/.rsvenv/bin/python" -c "
try:
    from importlib.metadata import version
    print(version('relayshield-mcp'))
except Exception:
    print('not installed in ~/.rsvenv')
" 2>/dev/null || echo "not installed in ~/.rsvenv")
  echo "   ~/.rsvenv sees: $RSV"
fi
LATEST=$(curl -sS --max-time 15 https://pypi.org/pypi/relayshield-mcp/json 2>/dev/null \
          | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])" 2>/dev/null \
          || echo "unknown")
echo "   PyPI latest  : $LATEST"
echo "   A config pointing at a python that does not have the package installed is"
echo "   the single most common cause of a server that will not start."
echo

echo "== 3. WHY it disconnected — the client's own logs"
# This is the section that actually answers the question. The config says what
# was attempted; the log says what happened.
LOGDIR="$HOME/Library/Logs/Claude"
if [ -d "$LOGDIR" ]; then
  echo "   $LOGDIR"
  # shellcheck disable=SC2044
  for f in "$LOGDIR"/mcp*.log; do
    [ -f "$f" ] || continue
    echo
    echo "   --- $(basename "$f") (last 25 lines) ---"
    tail -n 25 "$f" | sed 's/^/     /'
  done
else
  echo "   No Claude log directory at $LOGDIR."
  echo "   If the disconnect was in a different client, look for its logs instead:"
  echo "     Cursor    ~/Library/Application Support/Cursor/logs"
  echo "     VS Code   ~/Library/Application Support/Code/logs"
fi
echo

echo "HOW TO READ THIS"
echo "  Section 1 empty            -> nothing is configured. Nothing is broken;"
echo "                                there is no server to reconnect."
echo "  Section 1 lists a server,  -> the command cannot start. Section 2 usually"
echo "  section 3 shows ENOENT or     says why: wrong python, package not installed"
echo "  ModuleNotFoundError           in the python the config names."
echo "  Section 3 shows a 401/403  -> it starts and the API rejects it. The env key"
echo "                                is wrong or expired, not the server."
echo "  Section 3 is empty and the -> it is running. The client was showing a"
echo "  config looks right            transient reconnect, which is normal."
