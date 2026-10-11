"""RelayShield MCP config scanner: free security check for MCP setups.

Scans MCP client config files (Claude Desktop format and compatible) for
security issues before runtime. This is the free first step: find the
problems here, then deploy the MCP Proxy Firewall for runtime protection.

Usage:
    python3 -m mcp_proxy.scanner                      # default config location
    python3 -m mcp_proxy.scanner /path/to/config.json
    python3 -m mcp_proxy.scanner --format json
    python3 -m mcp_proxy.scanner --ci                  # exit 1 on HIGH+

Exit codes:
    0 - no CRITICAL or HIGH findings
    1 - one or more CRITICAL or HIGH findings
    2 - config file not found or unreadable
"""

import argparse
import base64
import ipaddress
import json
import os
import re
import socket
import sys
import urllib.parse

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

# ANSI colors for terminal output. Disabled when not a TTY or --no-color.
_COLORS = {
    "CRITICAL": "\033[91m",  # bright red
    "HIGH": "\033[33m",      # orange/yellow
    "MEDIUM": "\033[93m",    # yellow
    "LOW": "\033[94m",       # blue
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
}

# Patterns that look like hardcoded secrets in env values or args.
_SECRET_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}"), "OpenAI-style API key"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{16,}"), "Anthropic API key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "GitHub personal access token"),
    (re.compile(r"\bgho_[A-Za-z0-9]{20,}"), "GitHub OAuth token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}"), "AWS access key ID"),
    (re.compile(r"\bxox[bap]-[A-Za-z0-9\-]+"), "Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key material"),
    (re.compile(r"(?i)\b(password|passwd|pwd)\b\s*[:=]\s*\S+"), "inline password"),
    (re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token)\b\s*[:=]\s*\S+"),
     "inline API key or secret"),
]

# Env var names that almost always hold secrets.
_SECRET_ENV_NAMES = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|private[_-]?key|credentials)"
)

# Filesystem paths that grant excessive access when used as server roots.
_DANGEROUS_ROOTS = {"/", "~", "$HOME", "${HOME}", "/root", "/etc", "/home"}

# Server packages known to expose dangerous tools (write, shell exec).
_DANGEROUS_TOOL_SERVERS = {
    "server-filesystem": "exposes file write and delete tools",
    "server-shell": "exposes shell command execution",
    "server-terminal": "exposes terminal command execution",
    "server-everything": "exposes a broad toolset including exec",
}

# Server packages whose tools fetch caller-supplied URLs at runtime.
# Their tool schemas accept URL-like parameters (url, uri, link,
# endpoint, path, webhook). Without validation, a caller-supplied
# internal URL is fetched by the server: protocol pivoting (SSRF),
# the flaw class disclosed across Google, JPMorgan, Weaviate, Rapid7,
# France's DINUM, and Tangerang City government in 2026.
_URL_FETCHING_SERVERS = {
    "server-fetch": "fetches caller-supplied URLs",
    "mcp-server-fetch": "fetches caller-supplied URLs",
    "fetch-mcp": "fetches caller-supplied URLs",
    "server-curl": "issues caller-supplied HTTP requests",
    "curl-mcp": "issues caller-supplied HTTP requests",
    "http-request": "issues caller-supplied HTTP requests",
    "webhook": "delivers caller-supplied payloads to URLs",
}

# IPv4 networks that are never public infrastructure. A hardcoded
# config URL aimed at one of these is a static SSRF indicator.
_STATIC_INTERNAL_V4 = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
]
_STATIC_INTERNAL_SUFFIXES = (
    ".localhost", ".local", ".internal", ".intranet",
    ".lan", ".corp", ".home", ".private",
)
_CONFIG_URL_RE = re.compile(r"https?://[^\s\"'<>`]+", re.IGNORECASE)

# Built-in advisory list: (package_substring, fixed_version, cve_or_ref, summary)
# Versions are compared as dot-separated integers.
_ADVISORIES = [
    (
        "mcp-server-git",
        (2025, 12, 8),
        "prompt injection via README/issues/web content (Cyata, Dec 2025)",
        "mcp-server-git before the 2025-12-08 fix is vulnerable to prompt "
        "injection through untrusted content it reads",
    ),
]

# Default config locations, checked in order.
_DEFAULT_PATHS = [
    os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json"),
    os.path.expanduser("~/.config/Claude/claude_desktop_config.json"),
    os.path.expanduser("~/.cursor/mcp.json"),
    os.path.expanduser("~/.config/mcp.json"),
]


def _version_tuple(version_str):
    """Parse a version string into a comparable tuple of ints."""
    parts = []
    for piece in re.split(r"[.\-+_]", str(version_str)):
        m = re.match(r"(\d+)", piece)
        if m:
            parts.append(int(m.group(1)))
        elif parts:
            break
    return tuple(parts)


def _check_secrets(server_name, server_cfg, findings):
    """Flag hardcoded secrets in env values and command args."""
    env = server_cfg.get("env") or {}
    for key, value in env.items():
        value = str(value)
        matched = False
        for pattern, label in _SECRET_PATTERNS:
            if pattern.search(value):
                findings.append({
                    "severity": "CRITICAL",
                    "server": server_name,
                    "check": "hardcoded_secret",
                    "detail": "env var %r contains %s" % (key, label),
                    "remediation": "Remove the secret from the config file. Use a "
                                   "secrets manager or environment injection at "
                                   "launch time.",
                })
                matched = True
                break
        if matched:
            continue
        if _SECRET_ENV_NAMES.search(key):
            findings.append({
                "severity": "HIGH",
                "server": server_name,
                "check": "hardcoded_secret",
                "detail": "env var %r looks like a secret stored in plain text" % key,
                "remediation": "Move the value to a secrets manager or OS keychain "
                               "and reference it at runtime instead of storing it "
                               "in the config file.",
            })
            continue
        for pattern, label in _SECRET_PATTERNS:
            if pattern.search(value):
                findings.append({
                    "severity": "CRITICAL",
                    "server": server_name,
                    "check": "hardcoded_secret",
                    "detail": "env var %r contains %s" % (key, label),
                    "remediation": "Remove the secret from the config file. Use a "
                                   "secrets manager or environment injection at "
                                   "launch time.",
                })
                break
    for arg in server_cfg.get("args") or []:
        arg = str(arg)
        for pattern, label in _SECRET_PATTERNS:
            if pattern.search(arg):
                findings.append({
                    "severity": "CRITICAL",
                    "server": server_name,
                    "check": "hardcoded_secret",
                    "detail": "command argument contains %s" % label,
                    "remediation": "Never pass secrets as command-line arguments. "
                                   "They are visible in process listings. Use env "
                                   "injection or a secrets manager.",
                })
                break


def _check_filesystem(server_name, server_cfg, findings):
    """Flag filesystem servers rooted at dangerous paths."""
    command = str(server_cfg.get("command", ""))
    args = [str(a) for a in (server_cfg.get("args") or [])]
    blob = (command + " " + " ".join(args)).lower()
    if "filesystem" not in blob and "server-filesystem" not in blob:
        return
    for arg in args:
        expanded = os.path.expanduser(os.path.expandvars(arg))
        if arg in _DANGEROUS_ROOTS or expanded in ("/", os.path.expanduser("~")):
            findings.append({
                "severity": "HIGH",
                "server": server_name,
                "check": "overprivileged_filesystem",
                "detail": "filesystem server rooted at %r gives the agent broad "
                           "disk access" % arg,
                "remediation": "Restrict the server to the smallest directory the "
                               "agent needs, e.g. a project folder instead of / "
                               "or the home directory.",
            })


def _check_advisories(server_name, server_cfg, findings):
    """Check server packages against the built-in advisory list."""
    command = str(server_cfg.get("command", ""))
    args = " ".join(str(a) for a in (server_cfg.get("args") or []))
    blob = (command + " " + args).lower()
    for pkg, fixed_tuple, ref, summary in _ADVISORIES:
        if pkg not in blob:
            continue
        # Try to find a version string nearby.
        m = re.search(r"@(\d[\w.\-]*)", blob)
        version = m.group(1) if m else None
        if version and _version_tuple(version) >= fixed_tuple:
            continue
        findings.append({
            "severity": "HIGH" if version else "MEDIUM",
            "server": server_name,
            "check": "known_vulnerable_server",
            "detail": "%s: %s%s" % (
                pkg, summary,
                (" (found version %s)" % version) if version else
                " (could not determine installed version, assuming vulnerable)",
            ),
            "remediation": "Upgrade %s to a version with the fix. See: %s" % (pkg, ref),
        })


def _check_remote_auth(server_name, server_cfg, findings):
    """Flag remote (URL-based) servers with no authentication configured."""
    url = server_cfg.get("url")
    if not url:
        return
    headers = server_cfg.get("headers") or {}
    has_auth = any(
        re.search(r"(?i)(authorization|api[_-]?key|token|bearer)", str(k))
        for k in headers
    ) or bool(server_cfg.get("auth"))
    if not has_auth and str(url).startswith("https://"):
        findings.append({
            "severity": "MEDIUM",
            "server": server_name,
            "check": "unauthenticated_remote",
            "detail": "remote server at %s has no authentication headers "
                       "configured" % url,
            "remediation": "Add an Authorization header or API key. Anyone with "
                           "the URL can invoke tools on an unauthenticated "
                           "remote server.",
        })


def _check_dangerous_tools(server_name, server_cfg, findings):
    """Flag servers known to expose dangerous tools without a note."""
    command = str(server_cfg.get("command", ""))
    args = " ".join(str(a) for a in (server_cfg.get("args") or []))
    blob = (command + " " + args).lower()
    for pkg, reason in _DANGEROUS_TOOL_SERVERS.items():
        if pkg in blob:
            findings.append({
                "severity": "MEDIUM",
                "server": server_name,
                "check": "dangerous_tools",
                "detail": "%s %s" % (pkg, reason),
                "remediation": "Confirm the agent needs these tools. Consider "
                               "the RelayShield MCP Proxy Firewall to screen "
                               "every invocation at runtime.",
            })
            break


def _static_host_is_internal(url):
    """True when a config URL points at internal infrastructure.

    No DNS is performed: this is a static pre-deployment check, so
    only IP literals (including decimal/octal/hex bypass forms),
    localhost, and private-intranet suffixes are evaluated.
    """
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except Exception:
        return False, ""
    host = host.rstrip(".")
    if not host:
        return False, ""
    if host == "localhost" or host.endswith(_STATIC_INTERNAL_SUFFIXES):
        return True, host
    ip = None
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        try:
            ip = ipaddress.IPv4Address(socket.inet_aton(host))
        except (OSError, ValueError):
            return False, ""
    if isinstance(ip, ipaddress.IPv4Address):
        internal = any(ip in net for net in _STATIC_INTERNAL_V4)
    else:
        internal = ip.is_loopback or ip.is_link_local or ip.is_private
    return internal, host


def _check_potential_ssrf(server_name, server_cfg, findings):
    """Flag URL-fetching servers whose tools accept unvalidated URLs.

    A static config cannot show the tool schema, so this flags servers
    whose package identity means their tools take URL-like parameters
    (url, uri, link, endpoint, path, webhook). Only runtime screening
    can confirm whether caller input is validated, hence MEDIUM.
    """
    command = str(server_cfg.get("command", ""))
    args = " ".join(str(a) for a in (server_cfg.get("args") or []))
    blob = (command + " " + args).lower()
    for pkg, reason in _URL_FETCHING_SERVERS.items():
        if pkg in blob:
            findings.append({
                "severity": "MEDIUM",
                "server": server_name,
                "check": "potential_ssrf",
                "detail": "%s %s. Its tools accept URL-like parameters "
                           "(url, uri, link, endpoint, path, webhook); a "
                           "caller-supplied internal URL would be fetched "
                           "by the server (protocol pivoting / SSRF)."
                           % (pkg, reason),
                "remediation": "Validate caller-supplied URLs against an "
                               "allowlist of public hosts and block private, "
                               "link-local, and localhost targets. Deploy the "
                               "RelayShield MCP Proxy Firewall to screen "
                               "every tool call for internal URLs at runtime.",
            })
            break


def _check_internal_config_urls(server_name, server_cfg, findings):
    """Flag hardcoded internal URLs in server config values."""
    candidates = []
    if server_cfg.get("url"):
        candidates.append(("url", str(server_cfg["url"])))
    for i, arg in enumerate(server_cfg.get("args") or []):
        candidates.append(("args[%d]" % i, str(arg)))
    for key, value in (server_cfg.get("env") or {}).items():
        candidates.append(("env:%s" % key, str(value)))
    seen = set()
    for where, value in candidates:
        for m in _CONFIG_URL_RE.finditer(value):
            url = m.group(0).rstrip(".,;:!?)")
            internal, host = _static_host_is_internal(url)
            if internal and host not in seen:
                seen.add(host)
                metadata = host.startswith("169.254.")
                findings.append({
                    "severity": "HIGH" if metadata else "MEDIUM",
                    "server": server_name,
                    "check": "internal_config_url",
                    "detail": "%s contains a hardcoded URL aimed at internal "
                               "infrastructure (host: %s)" % (where, host),
                    "remediation": "Confirm this server must reach internal "
                                   "infrastructure. A hardcoded cloud metadata "
                                   "or intranet URL in config is a static "
                                   "SSRF indicator; restrict the server to "
                                   "the hosts it needs.",
                })


_CHECKS = [
    _check_secrets,
    _check_filesystem,
    _check_advisories,
    _check_remote_auth,
    _check_dangerous_tools,
    _check_potential_ssrf,
    _check_internal_config_urls,
]


def scan_config(config):
    """Scan a parsed MCP config dict. Returns a list of finding dicts."""
    findings = []
    servers = config.get("mcpServers") or config.get("servers") or {}
    for server_name, server_cfg in servers.items():
        if not isinstance(server_cfg, dict):
            continue
        for check in _CHECKS:
            check(server_name, server_cfg, findings)
    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: order.get(f["severity"], 99))
    return findings


def load_config(path):
    """Load a config file. Returns (config_dict, error_message)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, "file not found: %s" % path
    except json.JSONDecodeError as exc:
        return None, "invalid JSON in %s: %s" % (path, exc)
    except OSError as exc:
        return None, "could not read %s: %s" % (path, exc)


def find_default_config():
    """Return the first default config path that exists, or None."""
    for path in _DEFAULT_PATHS:
        if os.path.isfile(path):
            return path
    return None


def _colorize(text, severity, use_color):
    if not use_color:
        return text
    return _COLORS.get(severity, "") + text + _COLORS["RESET"]


def print_report(findings, path, use_color=True, stream=None):
    """Print a human-readable report to the stream."""
    out = stream or sys.stdout
    counts = {s: 0 for s in SEVERITIES}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    out.write("RelayShield MCP config scan: %s\n\n" % path)
    if not findings:
        out.write("No issues found. Your config looks clean.\n")
        return
    for f in findings:
        sev = _colorize("[%s]" % f["severity"], f["severity"], use_color)
        out.write("%s %s (%s)\n" % (sev, f["server"], f["check"]))
        out.write("  %s\n" % f["detail"])
        out.write("  Fix: %s\n\n" % f["remediation"])
    summary = ", ".join(
        "%s=%d" % (s, counts[s]) for s in SEVERITIES if counts[s]
    )
    out.write("Summary: %d finding(s): %s\n" % (len(findings), summary))
    out.write(
        "\nRuntime protection: the RelayShield MCP Proxy Firewall screens "
        "every tool call and response. See the README to deploy it.\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scan MCP client configs for security issues."
    )
    parser.add_argument("config", nargs="?",
                        help="path to config JSON (default: auto-detect)")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="output format")
    parser.add_argument("--ci", action="store_true",
                        help="exit 1 on HIGH or CRITICAL findings")
    parser.add_argument("--no-color", action="store_true",
                        help="disable color output")
    args = parser.parse_args(argv)

    path = args.config or find_default_config()
    if not path:
        print("No config file found. Checked:", file=sys.stderr)
        for p in _DEFAULT_PATHS:
            print("  %s" % p, file=sys.stderr)
        print("Pass a path explicitly: python3 -m mcp_proxy.scanner <path>",
              file=sys.stderr)
        return 2

    config, error = load_config(path)
    if error:
        print("Error: %s" % error, file=sys.stderr)
        return 2

    findings = scan_config(config)

    if args.format == "json":
        print(json.dumps({"config": path, "findings": findings}, indent=2))
    else:
        use_color = not args.no_color and sys.stdout.isatty()
        print_report(findings, path, use_color=use_color)

    bad = any(f["severity"] in ("CRITICAL", "HIGH") for f in findings)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
