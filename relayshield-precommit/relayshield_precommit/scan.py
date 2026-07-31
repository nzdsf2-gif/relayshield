"""RelayShield pre-commit hook: block commits that introduce secrets.

Runs before the commit enters git history, which is the whole point. A CI-side
check (a GitHub Action, a GitLab job) only sees the secret after a push, by
which time it is in history and has to be rotated even if the commit is deleted.

Sends `git diff --cached -U0` to RelayShield's secret-scan-text endpoint, which
returns findings located by file and line. The submitted diff is never logged or
persisted server-side, and matched values are never echoed back — findings carry
a byte offset and a truncated fingerprint instead.

Exit codes:
    0  no blocking findings (or non-blocking severities only)
    1  blocking findings; the commit is refused
    0  any transport/config failure, unless --strict is set (see _fail_open)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_ENDPOINT = "https://api.relayshield.net/v1/metered/secret-scan-text"
DEFAULT_TIMEOUT = 10
SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Keep in step with SECRET_SCAN_TEXT_MAX_BYTES server-side. Checked locally so an
# enormous staged diff fails with an actionable message instead of a 413.
MAX_BYTES = 1_048_576

_RED = "\033[31m"
_YELLOW = "\033[33m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _colour(text: str, code: str) -> str:
    if os.environ.get("NO_COLOR") or not sys.stderr.isatty():
        return text
    return f"{code}{text}{_RESET}"


def _staged_diff() -> str:
    """The staged changes, zero context lines.

    -U0 matters: with context lines the server would still only scan `+` lines,
    but the payload would be several times larger for no benefit.
    """
    return subprocess.run(
        ["git", "diff", "--cached", "-U0", "--no-color"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _load_allowlist(path: str) -> set[str]:
    """Fingerprints to ignore, one per line, `#` comments allowed.

    Fingerprints rather than raw values on purpose — an allowlist file that
    contains the actual secrets would be the same mistake this hook exists to
    prevent.
    """
    if not path or not os.path.exists(path):
        return set()
    out = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if line:
                out.add(line)
    return out


def _fail_open(message: str, strict: bool) -> int:
    """Network down, no key, endpoint 500 — do not wedge the user's commit.

    A secret scanner that blocks every commit when the network is flaky gets
    uninstalled, and then it catches nothing at all. Default is to warn loudly
    and allow; --strict flips it for CI or a regulated repo.
    """
    if strict:
        print(_colour(f"RelayShield: {message} (--strict, refusing commit)", _RED), file=sys.stderr)
        return 1
    print(_colour(f"RelayShield: {message} — skipping scan, commit allowed.", _YELLOW), file=sys.stderr)
    return 0


def _scan(diff: str, endpoint: str, api_key: str, timeout: int) -> dict:
    payload = json.dumps({"diff": diff}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-RS-API-KEY": api_key,
            "User-Agent": "relayshield-precommit/0.1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _report(findings: list[dict], blocking: list[dict]) -> None:
    print(file=sys.stderr)
    print(_colour("  RelayShield: secrets detected in staged changes", _BOLD + _RED), file=sys.stderr)
    print(file=sys.stderr)
    for f in findings:
        sev = f.get("severity", "?")
        colour = _RED if sev in ("CRITICAL", "HIGH") else _YELLOW
        loc = f.get("file") or "(unknown file)"
        line = f.get("line") or "?"
        print(
            f"  {_colour(sev.ljust(8), colour)} {f.get('description', f.get('type', '?'))}",
            file=sys.stderr,
        )
        print(f"           {loc}:{line}", file=sys.stderr)
        print(_colour(f"           fingerprint {f.get('fingerprint', '')}", _DIM), file=sys.stderr)
    print(file=sys.stderr)
    if blocking:
        print(_colour("  Commit refused.", _BOLD), file=sys.stderr)
        print(file=sys.stderr)
        print("  Remove the value and load it from a secrets manager or environment", file=sys.stderr)
        print("  variable instead. If it has already left this machine, rotate it.", file=sys.stderr)
        print(file=sys.stderr)
        print("  False positive? Add the fingerprint to .relayshield-allowlist:", file=sys.stderr)
        for f in blocking:
            print(f"      echo '{f.get('fingerprint', '')}' >> .relayshield-allowlist", file=sys.stderr)
        print(file=sys.stderr)
        print(_colour("  To bypass entirely: git commit --no-verify", _DIM), file=sys.stderr)
        print(file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="relayshield-secret-scan")
    parser.add_argument(
        "--fail-on",
        default="HIGH",
        choices=SEVERITY_ORDER,
        help="Lowest severity that blocks the commit (default: HIGH).",
    )
    parser.add_argument("--endpoint", default=os.environ.get("RELAYSHIELD_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--allowlist", default=".relayshield-allowlist")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Refuse the commit if the scan cannot run, instead of allowing it.",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("RELAYSHIELD_API_KEY", "").strip()
    if not api_key:
        return _fail_open("RELAYSHIELD_API_KEY is not set", args.strict)

    try:
        diff = _staged_diff()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return _fail_open(f"could not read staged diff ({exc})", args.strict)

    if not diff.strip():
        return 0

    size = len(diff.encode("utf-8"))
    if size > MAX_BYTES:
        return _fail_open(
            f"staged diff is {size} bytes, over the {MAX_BYTES} byte scan limit; commit in smaller pieces",
            args.strict,
        )

    try:
        body = _scan(diff, args.endpoint, api_key, args.timeout)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read()).get("error", "")
        except Exception:
            pass
        if exc.code in (401, 403):
            return _fail_open(f"API key rejected ({exc.code}) {detail}".strip(), args.strict)
        if exc.code == 402:
            return _fail_open("no credits or active subscription", args.strict)
        return _fail_open(f"scan failed with HTTP {exc.code} {detail}".strip(), args.strict)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return _fail_open(f"could not reach {args.endpoint} ({exc})", args.strict)

    if not body.get("ok"):
        return _fail_open(f"scan error: {body.get('error', 'unknown')}", args.strict)

    findings = body.get("data", {}).get("findings", [])
    allowed = _load_allowlist(args.allowlist)
    findings = [f for f in findings if f.get("fingerprint") not in allowed]

    if not findings:
        return 0

    threshold = SEVERITY_ORDER.index(args.fail_on)
    blocking = [
        f for f in findings
        if f.get("severity") in SEVERITY_ORDER and SEVERITY_ORDER.index(f["severity"]) >= threshold
    ]

    _report(findings, blocking)
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
