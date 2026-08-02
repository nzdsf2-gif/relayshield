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

**Everything matches locally.** All 31 credential patterns run on this machine.
No source code, no diff and no matched value is ever transmitted. There is no
API key, no account and no network call on the scanning path — which is what
makes the free tier genuinely free (zero server cost per commit) and removes the
"why does our pre-commit hook POST source code to a third party" objection that
kills adoption for a security tool. Matched values are never printed either;
findings carry a file, a line and a truncated fingerprint.

Two optional, explicitly opt-in network features exist, both off by default:

  --report PATH   Writes an escalation report the developer can forward. Local
                  file write only, still no network.
  --org DOMAIN    Sends ONLY {org domain, tool version, anonymous install id,
                  per-severity counts} so RelayShield can see that N engineers
                  at one company are using it. Never file paths, never
                  fingerprints, never code, never the secrets themselves.

Exit codes:
    0  no blocking findings (or non-blocking severities only)
    1  blocking findings
    0  any config failure, unless --strict is set (see _fail_open)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

from . import __version__ as _VERSION
from .patterns import _COMPILED, PATTERN_COUNT, fingerprint

# Org-signal endpoint. Only ever receives aggregate counts — see --org above.
DEFAULT_ORG_ENDPOINT = "https://api.relayshield.net/v1/telemetry/rsscan-install"
DEFAULT_TIMEOUT = 10
SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Where a developer is sent to check what is ALREADY public. The local hook can
# only prevent the next leak; it cannot see what has already been scraped.
EXPOSURE_URL = "https://api.relayshield.net/developers?source=rsscan"

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


def _scan_text(text: str, filename: str = "") -> list[dict]:
    """Run every credential pattern over `text`. Mirrors the server's scanner.

    Deliberately never returns the matched value — only a fingerprint. A local
    tool printing secrets to a terminal (and therefore into CI logs and shell
    history) would recreate the exposure it exists to prevent.
    """
    findings: list[dict] = []
    seen: set[tuple[str, int]] = set()
    attributed: set[str] = set()

    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    def line_of(offset: int) -> int:
        lo, hi = 0, len(line_starts)
        while lo < hi:
            mid = (lo + hi) // 2
            if line_starts[mid] <= offset:
                lo = mid + 1
            else:
                hi = mid
        return lo

    for name, pattern, severity, description, llm_provider in _COMPILED:
        for match in pattern.finditer(text):
            # Context-anchored patterns keep the secret in group 1, so the vendor
            # name that anchored the match is not fingerprinted with it.
            val = match.group(1) if pattern.groups else match.group(0)
            start = match.start(1) if pattern.groups else match.start(0)

            # A provider-attributed key must not also be reported by the
            # unattributed sk- catch-all. Same rule as the server.
            if llm_provider == "unknown_openai_compatible":
                if val in attributed:
                    continue
            elif llm_provider:
                attributed.add(val)

            key = (val, start)
            if key in seen:
                continue
            seen.add(key)

            findings.append({
                "type":        name,
                "description": description,
                "severity":    severity,
                "line":        line_of(start),
                "fingerprint": fingerprint(val),
                "file":        filename,
            })
    return findings


def _scan_unified_diff(diff: str) -> list[dict]:
    """Scan only the ADDED lines of a unified diff.

    Secrets already in a file are already in history; blocking on them would
    make the hook unbypassable on any repo with legacy findings. Added lines are
    reassembled per file so a pattern is not missed at a line boundary, with a
    side table mapping back to real line numbers.
    """
    findings: list[dict] = []
    current_file = ""
    new_lineno = 0
    buf: list[str] = []
    line_map: list[int] = []

    def flush() -> None:
        nonlocal buf, line_map
        if buf:
            block = "\n".join(buf)
            for f in _scan_text(block, current_file):
                idx = f["line"] - 1
                f["line"] = line_map[idx] if 0 <= idx < len(line_map) else 0
                findings.append(f)
        buf, line_map = [], []

    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            flush()
            path = raw[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            current_file = "" if path == "/dev/null" else path
        elif raw.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", raw)
            new_lineno = int(m.group(1)) if m else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            buf.append(raw[1:])
            line_map.append(new_lineno)
            new_lineno += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            pass                      # removed line: not in the new file
        elif raw.startswith("\\"):
            pass                      # "\ No newline at end of file"
        else:
            new_lineno += 1           # context line

    flush()
    return findings


def _install_id() -> str:
    """Stable per-machine id that identifies no person.

    Hostname + user, hashed and truncated. Enough to tell six developers at one
    company apart from one developer running it six times; useless for
    identifying anybody, and never reversible.
    """
    raw = f"{platform.node()}|{os.environ.get('USER') or os.environ.get('USERNAME') or ''}"
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _send_org_signal(org: str, counts: dict, endpoint: str, timeout: int) -> None:
    """Report that this org uses rsscan. Aggregate counts only, opt-in only.

    This is the bridge from an individual developer to the security lead who
    holds budget: N distinct install ids at one org domain is a qualified
    account, which PyPI download totals can never show. Deliberately carries no
    file paths, no fingerprints, no repo names, no code and no secrets — if it
    ever needs to, the answer is no.

    Failures are swallowed. Telemetry must never break somebody's commit.
    """
    payload = json.dumps({
        "org":         org,
        "install_id":  _install_id(),
        "version":     _VERSION,
        "counts":      counts,
        "reported_at": datetime.now(timezone.utc).isoformat(),
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": f"rsscan/{_VERSION}"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=timeout).read()
    except Exception:
        pass


def _write_report(path: str, findings: list[dict], where: str, org: str | None) -> bool:
    """Write the escalation artifact a developer forwards to their security lead.

    This is the actual conversion mechanic. A developer is not the buyer; the
    person they forward this to is. So the report answers the question the local
    scan cannot: this hook stopped the NEXT leak, but what is already public?
    """
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    summary = ", ".join(f"{n} {sev}" for sev, n in sorted(counts.items())) or "none"

    lines = [
        "# Credential exposure report",
        "",
        f"Generated by rsscan {_VERSION} on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Scope: {where}",
        f"Findings: {summary}",
        "",
        "## What was found",
        "",
        "| Severity | Credential type | File | Line | Fingerprint |",
        "| --- | --- | --- | --- | --- |",
    ]
    for f in findings:
        lines.append(
            f"| {f.get('severity','?')} | {f.get('description', f.get('type','?'))} "
            f"| `{f.get('file') or '(unknown)'}` | {f.get('line','?')} "
            f"| `{f.get('fingerprint','')}` |"
        )
    lines += [
        "",
        "No secret values appear in this report — only non-reversible fingerprints,",
        "so it is safe to forward, paste into a ticket, or attach to an email.",
        "",
        "## Why this matters beyond this commit",
        "",
        "rsscan runs locally and blocks credentials *before* they enter git history.",
        "It cannot see credentials that already left — a key committed last year, or",
        "leaked through a dependency, a published package or a container image, may",
        "already be indexed and scraped. Rotating what is listed above does not answer",
        "that question.",
        "",
        "## Recommended next step for whoever owns security here",
        "",
        "Check what is already public for this organisation — leaked credentials in",
        "public repos, packages and images, plus the identity-layer exposure that",
        "secret scanners do not cover at all: workforce credentials appearing in",
        "infostealer logs and breach dumps, SIM-swap risk on staff accounts, and",
        "session/token exposure.",
        "",
        f"  {EXPOSURE_URL}",
        "",
    ]
    if org:
        lines += [f"Organisation: {org}", ""]

    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        return True
    except OSError as exc:
        print(_colour(f"rsscan: could not write report to {path} ({exc})", _YELLOW), file=sys.stderr)
        return False


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
    parser.add_argument("--allowlist", default=os.environ.get("RSSCAN_ALLOWLIST", ".relayshield-allowlist"))
    parser.add_argument(
        "--report",
        default=os.environ.get("RSSCAN_REPORT", ""),
        metavar="PATH",
        help="Write a forwardable exposure report (Markdown). Local file only, no network.",
    )
    parser.add_argument(
        "--org",
        default=os.environ.get("RSSCAN_ORG", ""),
        metavar="DOMAIN",
        help=(
            "Opt-in. Report your org domain with per-severity counts only "
            "(no code, no file paths, no fingerprints, no secrets)."
        ),
    )
    parser.add_argument("--org-endpoint", default=os.environ.get("RSSCAN_ORG_ENDPOINT", DEFAULT_ORG_ENDPOINT))
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

    # No API key check. Scanning is entirely local and always free -- requiring a
    # key here was the single biggest install-friction item and bought nothing.
    where = "staged changes" if staged else args.rev_range
    try:
        diff = _git_diff(args.rev_range)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return _fail_open(f"could not read diff for {where} ({exc})", args.strict)

    # Nothing added means nothing to scan, and no billed call.
    if not diff.strip():
        return 0

    # No size cap. The old 1 MiB limit existed to protect an HTTP payload; a
    # local regex pass over a large diff is cheap, and refusing to scan a big
    # commit is exactly when a scanner is most needed.
    try:
        findings = _scan_unified_diff(diff)
    except re.error as exc:
        return _fail_open(f"pattern engine error ({exc})", args.strict)

    allowed = _load_allowlist(args.allowlist)
    findings = [f for f in findings if f.get("fingerprint") not in allowed]

    severity_counts: dict[str, int] = {}
    for f in findings:
        severity_counts[f["severity"]] = severity_counts.get(f["severity"], 0) + 1

    # Opt-in org signal. Fires on clean runs too -- adoption is the signal we
    # want, and only reporting on failures would bias it toward messy repos.
    if args.org:
        _send_org_signal(args.org.strip().lower(), severity_counts, args.org_endpoint, args.timeout)

    if not findings:
        return 0

    findings.sort(
        key=lambda f: (
            -SEVERITY_ORDER.index(f["severity"]) if f.get("severity") in SEVERITY_ORDER else 0,
            f.get("line", 0),
        )
    )

    threshold = SEVERITY_ORDER.index(args.fail_on)
    blocking = [
        f for f in findings
        if f.get("severity") in SEVERITY_ORDER and SEVERITY_ORDER.index(f["severity"]) >= threshold
    ]

    _report(findings, blocking, where, staged)

    if args.report and _write_report(args.report, findings, where, args.org or None):
        print(_colour(f"  Report written to {args.report}", _BOLD), file=sys.stderr)
        print("  It contains no secret values — safe to forward to whoever owns security.", file=sys.stderr)
        print(file=sys.stderr)

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
