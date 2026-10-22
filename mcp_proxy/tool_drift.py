"""RelayShield MCP tool-description drift check: pin tools, catch rug pulls.

The tool scanner (mcp_proxy.tool_scanner) answers "is this server's tool
set poisoned right now?" This module answers the follow-up question:
"is this the same tool set I approved?" It records a stable pin
(SHA-256 over the canonical form of each tool's name, description, and
input schema) and later compares a fresh tools/list snapshot against
the pins. Any drift, a description quietly rewritten, a schema quietly
widened, a tool added or removed, is reported as a finding.

That is the rug-pull pattern: a server ships a benign tool, gets
connected everywhere, then mutates the description to add an
exfiltration instruction or widens the schema to accept new data.
Static scanning alone cannot see it, because the first scan was clean.
Pins make the mutation itself the finding.

Usage:
    python3 tool_drift.py pin   --pins pins.json --file snapshot.json
    python3 tool_drift.py pin   --pins pins.json --url https://server.example.com/mcp
    python3 tool_drift.py check --pins pins.json --file snapshot.json
    python3 tool_drift.py check --pins pins.json --url https://server.example.com/mcp --ci
    python3 tool_drift.py check --pins pins.json --file snapshot.json --format json

Snapshot files may be a bare list of tool dicts, an object with a
"tools" key, or a full JSON-RPC tools/list response.

Exit codes:
    0 - pinned successfully, or no CRITICAL or HIGH drift findings
    1 - one or more CRITICAL or HIGH drift findings (check mode)
    2 - could not load pins, snapshot, or reach the server
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

PINS_VERSION = 1

_MCP_CLIENT = {"name": "relayshield-tool-drift", "version": "1.0.0"}

_URL_RE = re.compile(r"https?://[^\s)\]\"'<>]+")

# Phrases that, when they APPEAR in a changed description, suggest the
# new text is instructing the agent rather than describing the tool.
# Used only to escalate a description change from MEDIUM to HIGH; the
# base finding fires on any description change at all.
_SUSPICIOUS_PHRASES = (
    "ignore previous",
    "ignore all previous",
    "do not tell",
    "don't tell",
    "without telling",
    "without asking",
    "without the user's knowledge",
    "secretly",
    "exfiltrate",
    "send the contents",
    "send all",
    "post the contents",
    "upload all",
    "forward all",
)


# ---------------------------------------------------------------- pins

def canonical_tool(tool):
    """The canonical form of a tool definition that gets pinned.

    Only the fields an agent actually sees and reasons over: name,
    description, inputSchema. Server-side extras (annotations, output
    schemas, titles) are deliberately excluded: they do not change
    what the tool asks the agent to do.
    """
    if not isinstance(tool, dict):
        tool = {}
    return {
        "name": str(tool.get("name", "")),
        "description": tool.get("description") or "",
        "inputSchema": tool.get("inputSchema") or {},
    }


def tool_pin(tool):
    """Stable SHA-256 pin for one tool definition.

    Canonical JSON (sorted keys, tight separators) makes the pin
    insensitive to key ordering in the server's response.
    """
    blob = json.dumps(
        canonical_tool(tool),
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def build_pins(tools, source=""):
    """Build a pins document from a list of tool definitions."""
    pinned = {}
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        canon = canonical_tool(tool)
        name = canon["name"] or "<unnamed>"
        if name in pinned:
            continue  # first definition wins; duplicates are a server bug
        pinned[name] = {
            "pin": tool_pin(tool),
            "description": canon["description"],
            "inputSchema": canon["inputSchema"],
        }
    return {
        "version": PINS_VERSION,
        "source": source,
        "pinned_at": datetime.now(timezone.utc).isoformat(),
        "tools": pinned,
    }


def save_pins(path, pins_doc):
    """Write a pins document. Returns an error message or None."""
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(pins_doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except OSError as exc:
        return "could not write pins file %s: %s" % (path, exc)
    return None


def load_pins(path):
    """Load a pins document. Returns (pins_doc, error_message)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return None, "pins file not found: %s" % path
    except json.JSONDecodeError as exc:
        return None, "invalid JSON in pins file %s: %s" % (path, exc)
    except OSError as exc:
        return None, "could not read pins file %s: %s" % (path, exc)
    if not isinstance(doc, dict) or not isinstance(doc.get("tools"), dict):
        return None, "pins file %s has no 'tools' object" % path
    return doc, None


# ------------------------------------------------------------ snapshots

def _extract_tools(data):
    """Pull the tool list out of a parsed snapshot document."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("tools"), list):
            return data["tools"]
        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            return result["tools"]
    return None


def load_snapshot_file(path):
    """Load a tools/list snapshot from a JSON file.

    Returns (tools_list, error_message).
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None, "file not found: %s" % path
    except json.JSONDecodeError as exc:
        return None, "invalid JSON in %s: %s" % (path, exc)
    except OSError as exc:
        return None, "could not read %s: %s" % (path, exc)
    tools = _extract_tools(data)
    if tools is None:
        return None, ("no tool list in %s (expected a list, a 'tools' "
                      "key, or a JSON-RPC tools/list response)" % path)
    return tools, None


def _post_jsonrpc(url, payload, timeout=15.0, headers=None):
    """POST a JSON-RPC payload, return the parsed response dict.

    Mirrors mcp_proxy.tool_scanner._post_jsonrpc so this module stays
    runnable standalone; when it lands in mcp_proxy it can import
    fetch_tools from tool_scanner instead.
    """
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers,
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    raw = raw.strip()
    if not raw:
        raise ValueError("empty response from server")
    # Streamable HTTP servers may wrap the response in SSE framing.
    if raw.startswith("event:"):
        for line in raw.splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                break
    return json.loads(raw)


def fetch_tools(url, timeout=15.0, headers=None):
    """Fetch tool definitions from an MCP server.

    Performs the initialize handshake then tools/list, same as
    mcp_proxy.tool_scanner.fetch_tools. Returns
    (tools_list, error_message).
    """
    try:
        init_resp = _post_jsonrpc(url, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": _MCP_CLIENT,
            },
        }, timeout=timeout, headers=headers)
    except Exception as exc:
        return None, "initialize failed for %s: %s" % (url, exc)
    if isinstance(init_resp, dict) and init_resp.get("error"):
        return None, "initialize error from %s: %s" % (
            url, init_resp["error"].get("message", init_resp["error"]))

    # Best effort: some servers require the initialized notification
    # before tools/list; failures here are non-fatal.
    try:
        _post_jsonrpc(url, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        }, timeout=timeout, headers=headers)
    except Exception:
        pass

    try:
        list_resp = _post_jsonrpc(url, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
            "params": {},
        }, timeout=timeout, headers=headers)
    except Exception as exc:
        return None, "tools/list failed for %s: %s" % (url, exc)
    if isinstance(list_resp, dict) and list_resp.get("error"):
        return None, "tools/list error from %s: %s" % (
            url, list_resp["error"].get("message", list_resp["error"]))
    result = (list_resp or {}).get("result") or {}
    tools = result.get("tools") or []
    if not isinstance(tools, list):
        return None, "unexpected tools/list shape from %s" % url
    return tools, None


# ------------------------------------------------------------- checking

def _finding(severity, tool, check, detail, remediation):
    return {
        "severity": severity,
        "tool": tool,
        "check": check,
        "detail": detail,
        "remediation": remediation,
    }


def _description_assessment(old, new):
    """Severity and note for a description change.

    Any change is at least MEDIUM: the description is the text the
    agent reasons over, so silent edits are exactly the rug-pull
    signal. Escalate to HIGH when the new text introduces an external
    URL the pinned text did not have, or instruction-style phrasing
    the pinned text did not contain.
    """
    notes = []
    old_urls = set(_URL_RE.findall(old or ""))
    new_urls = set(_URL_RE.findall(new or "")) - old_urls
    if new_urls:
        notes.append("new text adds external URL(s): %s"
                     % ", ".join(sorted(new_urls)))
    lowered_new = (new or "").lower()
    lowered_old = (old or "").lower()
    for phrase in _SUSPICIOUS_PHRASES:
        if phrase in lowered_new and phrase not in lowered_old:
            notes.append("new text adds instruction-style phrase %r" % phrase)
            break
    if notes:
        return "HIGH", "; ".join(notes)
    return "MEDIUM", ""


def _type_set(fragment):
    """The set of JSON types a schema fragment allows, or None."""
    if not isinstance(fragment, dict):
        return None
    t = fragment.get("type")
    if t is None:
        return None
    if isinstance(t, list):
        return set(str(x) for x in t)
    return {str(t)}


def _schema_changes(old, new):
    """Describe input-schema drift as (severity, detail) pairs.

    Widening changes are HIGH: new parameters, widened types, enum
    values added or dropped constraints, parameters no longer
    required, additionalProperties relaxed. The tool now accepts input
    it did not accept when approved, which is how a benign tool grows
    an exfiltration channel. Narrowing and other changes are MEDIUM:
    they break or alter the approved contract but do not widen what
    the tool can be handed.
    """
    changes = []
    old = old if isinstance(old, dict) else {}
    new = new if isinstance(new, dict) else {}
    old_props = old.get("properties")
    new_props = new.get("properties")
    old_props = old_props if isinstance(old_props, dict) else {}
    new_props = new_props if isinstance(new_props, dict) else {}

    added = sorted(set(new_props) - set(old_props))
    removed = sorted(set(old_props) - set(new_props))
    if added:
        changes.append(("HIGH", "adds new parameter(s): %s"
                        % ", ".join(added)))
    if removed:
        changes.append(("MEDIUM", "removes parameter(s): %s"
                        % ", ".join(removed)))

    for name in sorted(set(old_props) & set(new_props)):
        o, n = old_props[name], new_props[name]
        if o == n:
            continue
        ot, nt = _type_set(o), _type_set(n)
        if ot != nt:
            if ot is None:
                changes.append(("MEDIUM",
                                "parameter %r type narrowed from "
                                "unconstrained to %s"
                                % (name, "/".join(sorted(nt)))))
            elif nt is None:
                changes.append(("HIGH",
                                "parameter %r type widened from %s to "
                                "unconstrained"
                                % (name, "/".join(sorted(ot)))))
            elif nt > ot:
                changes.append(("HIGH",
                                "parameter %r type widened from %s to %s"
                                % (name, "/".join(sorted(ot)),
                                   "/".join(sorted(nt)))))
            elif nt < ot:
                changes.append(("MEDIUM",
                                "parameter %r type narrowed from %s to %s"
                                % (name, "/".join(sorted(ot)),
                                   "/".join(sorted(nt)))))
            else:
                changes.append(("HIGH",
                                "parameter %r type changed from %s to %s"
                                % (name, "/".join(sorted(ot)),
                                   "/".join(sorted(nt)))))
            continue
        oe = o.get("enum") if isinstance(o, dict) else None
        ne = n.get("enum") if isinstance(n, dict) else None
        if oe != ne:
            if oe is not None and ne is None:
                changes.append(("HIGH", "parameter %r enum constraint "
                                "removed" % name))
            elif oe is None and ne is not None:
                changes.append(("MEDIUM", "parameter %r enum constraint "
                                "added" % name))
            else:
                added_vals = [v for v in ne if v not in oe]
                removed_vals = [v for v in oe if v not in ne]
                if added_vals:
                    changes.append(("HIGH",
                                    "parameter %r enum widened with new "
                                    "value(s): %s"
                                    % (name, ", ".join(repr(v)
                                                       for v in added_vals))))
                if removed_vals:
                    changes.append(("MEDIUM",
                                    "parameter %r enum value(s) removed: %s"
                                    % (name, ", ".join(repr(v)
                                                        for v in removed_vals))))
            continue
        changes.append(("MEDIUM", "parameter %r definition changed" % name))

    old_req = set(old.get("required") or [])
    new_req = set(new.get("required") or [])
    if new_req - old_req:
        changes.append(("MEDIUM", "newly required parameter(s): %s"
                        % ", ".join(sorted(new_req - old_req))))
    if old_req - new_req:
        changes.append(("HIGH", "parameter(s) no longer required: %s"
                        % ", ".join(sorted(old_req - new_req))))

    oap, nap = old.get("additionalProperties"), new.get("additionalProperties")
    if oap is False and nap is not False:
        changes.append(("HIGH", "additionalProperties relaxed from false"))
    elif nap is False and oap is not False:
        changes.append(("MEDIUM", "additionalProperties tightened to false"))

    if not changes and old != new:
        changes.append(("MEDIUM", "input schema changed (nested or other "
                        "constraint detail)"))
    return changes


def _worst(severities):
    order = {s: i for i, s in enumerate(SEVERITIES)}
    return min(severities, key=lambda s: order.get(s, 99))


def compare_tools(pinned_tools, tools):
    """Compare a current tool list against pinned tool records.

    pinned_tools is the "tools" object from a pins document (name ->
    {"pin", "description", "inputSchema"}). Returns finding dicts
    sorted by severity, same shape as the scanner family.
    """
    findings = []
    current = {}
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "<unnamed>"))
        if name not in current:
            current[name] = tool

    for name in sorted(pinned_tools):
        if name not in current:
            findings.append(_finding(
                "LOW", name, "tool_removed",
                "tool was pinned but is no longer offered by the server",
                "Confirm the removal is expected. A removed tool breaks "
                "agents that depended on it, but it is not by itself a "
                "poisoning signal.",
            ))

    for name in sorted(current):
        tool = current[name]
        record = pinned_tools.get(name)
        if record is None:
            findings.append(_finding(
                "MEDIUM", name, "tool_added",
                "tool is offered now but was not present when the pins "
                "were recorded",
                "Scan the new tool with the RelayShield tool scanner "
                "before letting agents use it, then re-pin if it is "
                "legitimate.",
            ))
            continue
        if tool_pin(tool) == record.get("pin"):
            continue
        canon = canonical_tool(tool)
        if "description" not in record or "inputSchema" not in record:
            findings.append(_finding(
                "MEDIUM", name, "tool_changed",
                "tool definition changed since pinning (pins file does "
                "not carry the stored definition, so the change cannot "
                "be classified further)",
                "Re-pin from a snapshot you trust so future drift can "
                "be classified.",
            ))
            continue
        old_desc = record.get("description") or ""
        if canon["description"] != old_desc:
            severity, note = _description_assessment(old_desc,
                                                      canon["description"])
            detail = "tool description changed since pinning"
            if note:
                detail += "; " + note
            findings.append(_finding(
                severity, name, "description_changed", detail,
                "Treat an unexplained description change as a possible "
                "rug pull. Diff the full text, re-scan the server with "
                "the RelayShield tool scanner, and re-pin only if the "
                "change is legitimate.",
            ))
        old_schema = record.get("inputSchema") or {}
        if canon["inputSchema"] != old_schema:
            changes = _schema_changes(old_schema, canon["inputSchema"])
            severity = _worst([sev for sev, _ in changes])
            detail = ("input schema changed since pinning: "
                      + "; ".join(text for _, text in changes))
            findings.append(_finding(
                severity, name, "schema_changed", detail,
                "Review the new schema before agents call this tool "
                "again. Widened schemas are how a benign tool grows an "
                "exfiltration channel. Re-pin only if the change is "
                "legitimate.",
            ))

    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: order.get(f["severity"], 99))
    return findings


# ----------------------------------------------------------------- CLI

def print_report(findings, source, pins_doc=None, stream=None):
    """Print a human-readable report to the stream (no color codes:
    drift output is meant to be logged and diffed in CI)."""
    out = stream or sys.stdout
    out.write("RelayShield MCP tool drift check: %s\n" % source)
    if pins_doc:
        out.write("Pins: recorded %s, %d tool(s)\n" % (
            pins_doc.get("pinned_at", "unknown"),
            len(pins_doc.get("tools") or {})))
    out.write("\n")
    if not findings:
        out.write("No drift. Every pinned tool matches the current "
                  "snapshot.\n")
        return
    counts = {s: 0 for s in SEVERITIES}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    for f in findings:
        out.write("[%s] %s (%s)\n" % (f["severity"], f["tool"], f["check"]))
        out.write("  %s\n" % f["detail"])
        out.write("  Fix: %s\n\n" % f["remediation"])
    summary = ", ".join(
        "%s=%d" % (s, counts[s]) for s in SEVERITIES if counts[s]
    )
    out.write("Summary: %d finding(s): %s\n" % (len(findings), summary))
    out.write(
        "\nPins record what a server's tools looked like when you "
        "approved them. Drift means the server you connected is no "
        "longer the server you scanned. Re-scan with the RelayShield "
        "tool scanner, and put the MCP Proxy Firewall in front of the "
        "server for runtime screening.\n"
    )


def _acquire_snapshot(args):
    """Resolve the snapshot source. Returns (tools, source, error)."""
    if args.file:
        tools, error = load_snapshot_file(args.file)
        return tools, args.file, error
    tools, error = fetch_tools(args.url, timeout=args.timeout)
    return tools, args.url, error


def _add_source_args(parser):
    parser.add_argument("--pins", required=True,
                        help="path to the pins JSON file")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="path to a tools/list snapshot JSON file")
    src.add_argument("--url", help="MCP server URL to fetch tools/list from")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="output format")
    parser.add_argument("--timeout", type=float, default=15.0,
                        help="fetch timeout in seconds for --url")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Pin MCP tool definitions and check for drift "
                    "(tool rug pulls)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pin_parser = sub.add_parser(
        "pin", help="record pins from the current snapshot")
    _add_source_args(pin_parser)

    check_parser = sub.add_parser(
        "check", help="compare the current snapshot against the pins")
    _add_source_args(check_parser)
    check_parser.add_argument("--ci", action="store_true",
                              help="exit 1 on HIGH or CRITICAL findings")

    args = parser.parse_args(argv)

    tools, source, error = _acquire_snapshot(args)
    if error:
        print("Error: %s" % error, file=sys.stderr)
        return 2

    if args.command == "pin":
        pins_doc = build_pins(tools, source=source)
        error = save_pins(args.pins, pins_doc)
        if error:
            print("Error: %s" % error, file=sys.stderr)
            return 2
        if args.format == "json":
            print(json.dumps({"pins_file": args.pins,
                              "source": source,
                              "pinned": pins_doc}, indent=2))
        else:
            print("Pinned %d tool(s) from %s to %s"
                  % (len(pins_doc["tools"]), source, args.pins))
            for name in sorted(pins_doc["tools"]):
                print("  %s  %s"
                      % (name, pins_doc["tools"][name]["pin"][:12]))
        return 0

    pins_doc, error = load_pins(args.pins)
    if error:
        print("Error: %s" % error, file=sys.stderr)
        return 2
    findings = compare_tools(pins_doc["tools"], tools)

    if args.format == "json":
        print(json.dumps({"source": source, "pins_file": args.pins,
                          "findings": findings}, indent=2))
    else:
        print_report(findings, source, pins_doc=pins_doc)

    bad = any(f["severity"] in ("CRITICAL", "HIGH") for f in findings)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
