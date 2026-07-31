"""rsscan — block commits and builds that introduce secrets.

Two modes, one code path:

  --staged (default)   `git diff --cached -U0`. The pre-commit hook. Runs before
                       the commit enters git history, which is the whole point:
                       once a secret is committed and pushed it must be rotated
                       even if the commit is later deleted.
  --rev-range A..B     `git diff A..B -U0`. The CI mode used by the GitHub
                       Action, the GitLab CI component and the CircleCI orb.
                       Strictly a backstop — by the time CI runs, the secret is
                       already in history.

Either way only ADDED lines are scanned, so a repo with pre-existing findings
does not get an unbypassable gate.

The diff is sent to RelayShield's secret-scan-text endpoint. It is never logged
or persisted server-side, and matched values are never echoed back — findings
carry a file, a line and a truncated fingerprint instead.

Exit codes:
    0  no blocking findings (or non-blocking severities only)
    1  blocking findings
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

from . import __version__ as _VERSION

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


def _git_diff(rev_range: str = "") -> str:
    """The diff to scan, zero context lines.

    -U0 matters: with context the server would still only scan `+` lines, but
    the payload would be several times larger for no benefit.
    """
    args = ["git", "diff", "-U0", "--no-color"]
    args += [rev_range] if rev_range else ["--cached"]
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


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
        print(_colour(f"rsscan: {message} (--strict, failing)", _RED), file=sys.stderr)
        return 1
    print(_colour(f"rsscan: {message} — skipping scan, continuing.", _YELLOW), file=sys.stderr)
    return 0


def _scan(diff: str, endpoint: str, api_key: str, timeout: int) -> dict:
    payload = json.dumps({"diff": diff}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-RS-API-KEY": api_key,
            "User-Agent": f"rsscan/{_VERSION}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _report(findings: list[dict], blocking: list[dict], where: str, staged: bool) -> None:
    print(file=sys.stderr)
    print(_colour(f"  rsscan: secrets detected in {where}", _BOLD + _RED), file=sys.stderr)
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
        print(_colour("  Commit refused." if staged else "  Build failed.", _BOLD), file=sys.stderr)
        print(file=sys.stderr)
        if staged:
            print("  Remove the value and load it from a secrets manager or environment", file=sys.stderr)
            print("  variable instead. If it has already left this machine, rotate it.", file=sys.stderr)
        else:
            # CI is a backstop, not prevention. Saying "remove it" here would be
            # misleading advice: the secret is already in pushed history.
            print("  These secrets are already in git history. Deleting the commit is not", file=sys.stderr)
            print("  enough — rotate every credential listed above, then purge from history.", file=sys.stderr)
        print(file=sys.stderr)
        print("  False positive? Add the fingerprint to .relayshield-allowlist:", file=sys.stderr)
        for f in blocking:
            print(f"      echo '{f.get('fingerprint', '')}' >> .relayshield-allowlist", file=sys.stderr)
        if staged:
            print(file=sys.stderr)
            print(_colour("  To bypass entirely: git commit --no-verify", _DIM), file=sys.stderr)
        print(file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rsscan",
        description="Block commits and builds that introduce secrets.",
    )
    parser.add_argument(
        "--fail-on",
        default=os.environ.get("RSSCAN_FAIL_ON") or "HIGH",
        choices=SEVERITY_ORDER,
        help="Lowest severity that blocks (default: HIGH).",
    )
    parser.add_argument(
        "--rev-range",
        default=os.environ.get("RSSCAN_REV_RANGE", ""),
        help="Scan a commit range (e.g. origin/main...HEAD) instead of staged changes. CI mode.",
    )
    parser.add_argument("--endpoint", default=os.environ.get("RELAYSHIELD_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--allowlist", default=os.environ.get("RSSCAN_ALLOWLIST", ".relayshield-allowlist"))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("RSSCAN_TIMEOUT") or DEFAULT_TIMEOUT))
    # Tri-state on purpose: None means "not specified", which lets the default
    # differ between the pre-commit path and CI (see below).
    parser.add_argument(
        "--strict",
        dest="strict",
        action="store_const",
        const=True,
        default=None,
        help="Fail if the scan cannot run, instead of allowing it through. Default in CI mode.",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_const",
        const=False,
        help="Allow the run to continue when the scan cannot run. Default in pre-commit mode.",
    )
    parser.add_argument("--version", action="version", version=f"rsscan {_VERSION}")
    args = parser.parse_args(argv)
    staged = not args.rev_range

    if args.strict is None:
        env = os.environ.get("RSSCAN_STRICT", "").strip().lower()
        if env in ("1", "true", "yes"):
            args.strict = True
        elif env in ("0", "false", "no"):
            args.strict = False
        else:
            # Default differs by mode, and the asymmetry is deliberate.
            #
            # Pre-commit runs on a developer's machine many times a day. A hook
            # that wedges every commit on a flaky network gets uninstalled, and
            # then it catches nothing at all -- so fail open there.
            #
            # CI runs once, unattended, and its whole job is to be a gate. A
            # gate that silently reports success when it could not actually run
            # is worse than no gate: it manufactures false assurance. Verified
            # the hard way 2026-07-31 -- a container with an unmounted repo
            # printed a warning and exited 0, which would have passed every
            # build in a misconfigured pipeline.
            args.strict = not staged

    api_key = os.environ.get("RELAYSHIELD_API_KEY", "").strip()
    if not api_key:
        return _fail_open("RELAYSHIELD_API_KEY is not set", args.strict)

    where = "staged changes" if staged else args.rev_range
    try:
        diff = _git_diff(args.rev_range)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return _fail_open(f"could not read diff for {where} ({exc})", args.strict)

    # Nothing added means nothing to scan, and no billed call.
    if not diff.strip():
        return 0

    size = len(diff.encode("utf-8"))
    if size > MAX_BYTES:
        return _fail_open(
            f"diff is {size} bytes, over the {MAX_BYTES} byte scan limit; "
            + ("commit in smaller pieces" if staged else "narrow the commit range"),
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

    _report(findings, blocking, where, staged)

    # GitHub Actions step output, ignored everywhere else.
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        try:
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(f"findings={len(findings)}\n")
                fh.write(f"blocking={len(blocking)}\n")
                fh.write(f"highest={findings[0].get('severity', '')}\n")
        except OSError:
            pass

    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
