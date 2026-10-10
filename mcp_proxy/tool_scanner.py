"""RelayShield MCP tool-definition scanner: pre-deployment security check.

Fetches tool definitions from an MCP server (tools/list) and analyzes
each tool for poisoning indicators before you connect an agent to it.
This is the "scan before you connect" step: find poisoned tools here,
then deploy the MCP Proxy Firewall for runtime protection of every
tool call and result.

Usage:
    python3 -m mcp_proxy.tool_scanner --url https://server.example.com/mcp
    python3 -m mcp_proxy.tool_scanner --config /path/to/mcp.json
    python3 -m mcp_proxy.tool_scanner --url https://server.example.com/mcp --format json
    python3 -m mcp_proxy.tool_scanner --url https://server.example.com/mcp --ci

What it checks per tool:
    - Prompt-injection phrases in tool descriptions
    - Instruction-hijack phrasing ("you must now", "act as", ...)
    - Exfiltration instructions: descriptions telling the agent to send,
      post, or upload data to external URLs
    - Dangerous capabilities implied by the tool name (shell exec,
      file delete, broad write)
    - Credential parameters (password, api_key, token) in the input schema
    - Missing descriptions and unconstrained input schemas

Exit codes:
    0 - no CRITICAL or HIGH findings
    1 - one or more CRITICAL or HIGH findings
    2 - could not fetch tool definitions
"""

import argparse
import json
import re
import sys
import urllib.request
import urllib.error

try:
    from .screener import (
        _PROMPT_INJECTION_PATTERNS,
        _SYNTHETIC_INSTRUCTION_HINTS,
        extract_indicators,
    )
except ImportError:  # direct import (unit tests)
    from screener import (
        _PROMPT_INJECTION_PATTERNS,
        _SYNTHETIC_INSTRUCTION_HINTS,
        extract_indicators,
    )

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

_COLORS = {
    "CRITICAL": "\033[91m",
    "HIGH": "\033[33m",
    "MEDIUM": "\033[93m",
    "LOW": "\033[94m",
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
}

# Tool names that imply broad, dangerous capabilities. Flagged at MEDIUM:
# the capability may be legitimate, but the deployer should confirm the
# agent actually needs it before connecting.
_DANGEROUS_TOOL_PATTERNS = [
    (re.compile(r"(?i)\b(exec|execute|eval|shell|bash|sh|zsh|powershell|cmd|terminal|command)\b"),
     "shell or code execution"),
    (re.compile(r"(?i)\b(rm|delete|remove|unlink|drop|destroy|wipe)\b"),
     "destructive delete"),
    (re.compile(r"(?i)\b(write_file|save_file|overwrite|chmod|chown)\b"),
     "file write or permission change"),
    (re.compile(r"(?i)\b(http_request|fetch_url|curl|wget|download)\b"),
     "arbitrary network fetch"),
]

# Parameter names that suggest the tool wants credentials passed as
# arguments. Credentials in tool arguments end up in logs and traces.
_CREDENTIAL_PARAM_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|client[_-]?secret|"
    r"private[_-]?key|access[_-]?token|auth[_-]?token|bearer)\b"
)

# Verbs that, next to a URL in a description, suggest the tool tells
# the agent to send data somewhere.
_EXFIL_VERB_RE = re.compile(
    r"(?i)\b(send|post|upload|transmit|forward|submit|push|exfiltrate|"
    r"leak|dispatch)\b"
)

_MCP_CLIENT = {"name": "relayshield-tool-scanner", "version": "1.0.0"}


def _post_jsonrpc(url, payload, timeout=15.0, headers=None):
    """POST a JSON-RPC payload, return the parsed response dict."""
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

    Performs the initialize handshake then tools/list. Returns
    (tools_list, error_message). tools_list is a list of tool dicts
    with at least a "name" key.
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

    # Best effort: send the initialized notification. Some servers
    # require it before tools/list; failures here are non-fatal.
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


def _finding(severity, tool, check, detail, remediation):
    return {
        "severity": severity,
        "tool": tool,
        "check": check,
        "detail": detail,
        "remediation": remediation,
    }


def _check_prompt_injection(tool_name, description, findings):
    lowered = description.lower()
    for pattern in _PROMPT_INJECTION_PATTERNS:
        if pattern in lowered:
            findings.append(_finding(
                "CRITICAL", tool_name, "prompt_injection",
                "tool description contains prompt-injection phrase %r" % pattern,
                "Do not connect this server. A tool description that tries "
                "to override agent instructions is a poisoning attempt.",
            ))
            return True
    return False


def _check_instruction_hijack(tool_name, description, findings):
    lowered = description.lower()
    for hint in _SYNTHETIC_INSTRUCTION_HINTS:
        if hint in lowered:
            findings.append(_finding(
                "HIGH", tool_name, "instruction_hijack",
                "tool description contains instruction-like phrasing %r" % hint,
                "Review the full description. Tool descriptions should "
                "describe what the tool does, not give the agent new "
                "instructions.",
            ))
            return True
    return False


def _check_exfiltration(tool_name, description, findings):
    indicators = extract_indicators(description)
    urls = indicators["urls"]
    if not urls:
        return
    lowered = description.lower()
    has_verb = bool(_EXFIL_VERB_RE.search(lowered))
    for url in urls:
        if has_verb:
            findings.append(_finding(
                "HIGH", tool_name, "exfiltration_instruction",
                "tool description pairs an exfiltration verb with URL %s" % url,
                "Do not connect this server. The tool tells the agent to "
                "send data to an external address.",
            ))
        else:
            findings.append(_finding(
                "MEDIUM", tool_name, "url_in_description",
                "tool description contains URL %s" % url,
                "Confirm the URL is documentation, not an instruction to "
                "send data there.",
            ))


def _check_dangerous_name(tool_name, findings):
    for pattern, label in _DANGEROUS_TOOL_PATTERNS:
        if pattern.search(tool_name):
            findings.append(_finding(
                "MEDIUM", tool_name, "dangerous_capability",
                "tool name suggests %s" % label,
                "Confirm the agent needs this capability. If it does, "
                "put the RelayShield MCP Proxy Firewall in front of the "
                "server to screen every invocation at runtime.",
            ))
            return


def _check_credential_params(tool_name, schema, findings):
    if not isinstance(schema, dict):
        return
    props = schema.get("properties") or {}
    if not isinstance(props, dict):
        return
    for prop_name in props:
        if _CREDENTIAL_PARAM_RE.search(str(prop_name)):
            findings.append(_finding(
                "HIGH", tool_name, "credential_parameter",
                "input schema requests credential parameter %r" % prop_name,
                "Pass credentials via server configuration or environment, "
                "not as tool arguments. Arguments end up in logs and traces.",
            ))
            return


def _check_schema_shape(tool_name, description, schema, findings):
    if not description or not description.strip():
        findings.append(_finding(
            "LOW", tool_name, "missing_description",
            "tool has no description",
            "Undescribed tools are harder to audit. Ask the server author "
            "for a description, or document the tool's purpose before "
            "connecting.",
        ))
    if not isinstance(schema, dict) or not schema.get("properties"):
        findings.append(_finding(
            "LOW", tool_name, "unconstrained_schema",
            "tool input schema has no declared properties",
            "An unconstrained schema accepts anything. Prefer servers "
            "that declare typed parameters so calls can be validated.",
        ))


def scan_tools(tools, source=""):
    """Analyze a list of MCP tool definitions.

    Each tool is a dict with "name", optional "description", and
    optional "inputSchema". Returns a list of finding dicts sorted
    by severity.
    """
    findings = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", "<unnamed>"))
        description = str(tool.get("description") or "")
        schema = tool.get("inputSchema") or {}

        injected = _check_prompt_injection(name, description, findings)
        if not injected:
            _check_instruction_hijack(name, description, findings)
        _check_exfiltration(name, description, findings)
        _check_dangerous_name(name, findings)
        _check_credential_params(name, schema, findings)
        _check_schema_shape(name, description, schema, findings)

    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: order.get(f["severity"], 99))
    return findings


def _colorize(text, severity, use_color):
    if not use_color:
        return text
    return _COLORS.get(severity, "") + text + _COLORS["RESET"]


def print_report(findings, source, use_color=True, stream=None):
    out = stream or sys.stdout
    counts = {s: 0 for s in SEVERITIES}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    out.write("RelayShield MCP tool scan: %s\n\n" % source)
    if not findings:
        out.write("No issues found. The tool definitions look clean.\n")
        return
    for f in findings:
        sev = _colorize("[%s]" % f["severity"], f["severity"], use_color)
        out.write("%s %s (%s)\n" % (sev, f["tool"], f["check"]))
        out.write("  %s\n" % f["detail"])
        out.write("  Fix: %s\n\n" % f["remediation"])
    summary = ", ".join(
        "%s=%d" % (s, counts[s]) for s in SEVERITIES if counts[s]
    )
    out.write("Summary: %d finding(s): %s\n" % (len(findings), summary))
    out.write(
        "\nRuntime protection: the RelayShield MCP Proxy Firewall screens "
        "every tool call and result. Scanning finds poisoned definitions; "
        "the proxy catches what slips through at runtime.\n"
    )


def _servers_from_config(path):
    """Load a Claude-style MCP config. Returns (servers, error)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
    except FileNotFoundError:
        return None, "file not found: %s" % path
    except json.JSONDecodeError as exc:
        return None, "invalid JSON in %s: %s" % (path, exc)
    except OSError as exc:
        return None, "could not read %s: %s" % (path, exc)
    servers = config.get("mcpServers") or config.get("servers") or {}
    return servers, None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scan MCP server tool definitions for poisoning "
                    "indicators before connecting."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="MCP server JSON-RPC endpoint URL")
    src.add_argument("--config",
                     help="MCP client config JSON; URL-based servers are "
                          "scanned, stdio servers are reported as unscannable")
    parser.add_argument("--header", action="append", default=[],
                        help="extra HTTP header as 'Name: value' "
                             "(repeatable)")
    parser.add_argument("--timeout", type=float, default=15.0,
                        help="HTTP timeout in seconds (default 15)")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="output format")
    parser.add_argument("--ci", action="store_true",
                        help="exit 1 on HIGH or CRITICAL findings")
    parser.add_argument("--no-color", action="store_true",
                        help="disable color output")
    args = parser.parse_args(argv)

    headers = {}
    for h in args.header:
        if ":" in h:
            name, value = h.split(":", 1)
            headers[name.strip()] = value.strip()

    targets = []  # list of (label, url)
    skipped = []
    if args.url:
        targets.append((args.url, args.url))
    else:
        servers, error = _servers_from_config(args.config)
        if error:
            print("Error: %s" % error, file=sys.stderr)
            return 2
        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue
            url = cfg.get("url")
            if url:
                targets.append((name, url))
            else:
                skipped.append(name)
        if not targets:
            print("Error: no URL-based servers in %s" % args.config,
                  file=sys.stderr)
            return 2

    all_findings = []
    failed = []
    for label, url in targets:
        tools, error = fetch_tools(url, timeout=args.timeout,
                                   headers=headers or None)
        if error:
            failed.append((label, error))
            continue
        findings = scan_tools(tools, source=label)
        for f in findings:
            f["server"] = label
        all_findings.extend(findings)

    for label, error in failed:
        print("Error: %s" % error, file=sys.stderr)
    for name in skipped:
        print("Note: stdio server %r cannot be scanned without launching "
              "it; connect it through the proxy for runtime screening."
              % name, file=sys.stderr)

    if failed and not all_findings:
        return 2

    if args.format == "json":
        print(json.dumps({
            "targets": [t[0] for t in targets],
            "failed": [{"server": l, "error": e} for l, e in failed],
            "findings": all_findings,
        }, indent=2))
    else:
        use_color = not args.no_color and sys.stdout.isatty()
        for label, _ in targets:
            server_findings = [f for f in all_findings
                               if f.get("server") == label]
            print_report(server_findings, label, use_color=use_color)
            if len(targets) > 1:
                print()

    bad = any(f["severity"] in ("CRITICAL", "HIGH") for f in all_findings)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
