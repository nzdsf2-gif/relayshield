"""
agent-bait-scan — read the INSTRUCTIONS an agent is given, not its code.

    POST /v1/payg/agent-bait-scan       $0.50 USDC, x402, no signup
    POST /v1/metered/agent-bait-scan    $0.50/call, API key

THE GAP THIS CLOSES
-------------------
A repository can be prepared to be found by an agent rather than by a person.
Its code is clean and every scanner passes it. What is hostile is the ENGLISH:
a README, an AGENTS.md, or an MCP tool description written so that an agent
reading it does something the user never asked for.

None of that is a code vulnerability, so nothing that looks for code
vulnerabilities sees it. "We scanned it and it was clean" is a true statement
about a malicious repository, and that is the whole finding.

`mcp-registry-risk` covers the name and the domain. Nothing of ours read the
instructions. This does.

Full scope, signals and reasoning: `agent_baiting_scope.md`.

WHY IT IS A SEPARATE MODULE AND A SEPARATE ENDPOINT
----------------------------------------------------
`mcp-registry-risk` answers from DynamoDB plus at most one RDAP call and is live
in Bundle D on AWS Marketplace. This makes several bounded fetches to GitHub and
package registries, with their own rate limits and partial failures. Folding
that into the earning path changes its latency profile and its failure modes.

Same Lambda, different endpoint: `relayshield_agentic_api.py` routes to this
module, which keeps Bundle D's endpoints together without letting a fetch-heavy
scan sit inside a lookup-only response.

SIGNAL 4 IS IMPORTED, NEVER COPIED
-----------------------------------
The typosquat distance check, the known-domain list and the IOC corpus lookup
already exist in `relayshield_agentic_api.py`. This repo already carries four
copies of one pattern table that must agree with nothing checking that they do.
It does not need a fifth, so signal 4 calls into that module rather than
reimplementing it. The dependency points one way only.

THREE RULES, AND THE THIRD IS SPECIFIC TO THIS SHAPE
-----------------------------------------------------
1. **It never throws.** Every failure is a partial result with `ok` true and the
   surface marked unreadable. This runs in front of somebody's deployment
   decision; a 500 there is worse than a thin answer.
2. **It never says safe.** An absence of hostile instructions in the files we
   could read is not proof of anything, least of all about the code.
3. **It never calls a repository or a person malicious.** It reports what the
   instructions would cause an agent to DO. "This README instructs an agent to
   fetch and execute a script from a second domain, and that domain was
   registered eleven days ago" is checkable and enough. "This repo is malware"
   is a libel risk aimed at a named maintainer on the basis of a heuristic, and
   we would be wrong often enough to deserve it.
"""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Bounded on purpose. A scan that can walk a repository is a scan that can be
# pointed at a large one to burn our Lambda budget.
FETCH_TIMEOUT   = 6
MAX_SURFACES    = 10
MAX_BYTES       = 256 * 1024
MAX_REFERENCES  = 25

# The files an agent actually reads before or while acting. Ordered by how
# commonly each is honoured, because the first MAX_SURFACES are what get fetched.
AGENT_SURFACES = [
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
    "mcp.json",
    "smithery.yaml",
    ".mcp.json",
    "package.json",
    "README.rst",
]

_UA = "RelayShield-agent-bait-scan/1.0 (+https://api.relayshield.net)"


# ---------------------------------------------------------------------------
# Signal 1 — execution instructions.
# ---------------------------------------------------------------------------
# Piping a downloaded script into a shell is the single most load-bearing
# pattern here, and it is deliberately matched loosely: the hostile variants
# differ by whitespace, flags and shell far more than by structure.

_EXEC_PATTERNS = [
    (r"\b(?:curl|wget)\b[^\n|]{0,200}\|\s*(?:sudo\s+)?(?:ba|z|k|)sh\b",
     "downloads a script and pipes it straight into a shell"),
    (r"\b(?:iwr|invoke-webrequest|irm|invoke-restmethod)\b[^\n|]{0,200}\|\s*iex\b",
     "downloads and executes via PowerShell iex"),
    (r"\bpython3?\s+-c\s+[\"'][^\"'\n]{0,200}urlopen",
     "fetches and executes Python from a URL"),
    (r"\beval\s*\(\s*(?:atob|base64|Buffer\.from)",
     "evaluates base64-decoded content"),
    (r"\"(?:post|pre)install\"\s*:\s*\"[^\"]{0,200}(?:curl|wget|node -e|python -c)",
     "runs a network fetch from an npm install hook"),
    (r"\bchmod\s+\+x\b[^\n]{0,80}&&[^\n]{0,80}\./",
     "makes a downloaded file executable and runs it"),
]

# ---------------------------------------------------------------------------
# Signal 2 — injection markers.
# ---------------------------------------------------------------------------
# Instructions addressed to the assistant rather than to the reader. The
# hiding places matter as much as the phrases: a directive a human never sees
# is strictly worse than one they might notice.

_INJECTION_PATTERNS = [
    (r"\bignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+instructions?\b",
     "tells the agent to ignore its previous instructions"),
    (r"\bdisregard\s+(?:all\s+)?(?:previous|prior|above|your)\b",
     "tells the agent to disregard prior context"),
    (r"\byou\s+are\s+now\s+(?:a|an|the)\b",
     "attempts to reassign the agent's role"),
    (r"^\s*system\s*:",
     "opens a fake system prelude"),
    (r"\b(?:do\s+not|don'?t|never)\s+(?:tell|inform|mention\s+to|show)\s+the\s+user\b",
     "instructs the agent to conceal an action from the user"),
    (r"\bwithout\s+(?:asking|confirming|telling)\s+the\s+user\b",
     "instructs the agent to act without confirmation"),
    (r"\bas\s+an\s+ai\s+(?:assistant|agent)[^.\n]{0,60}\byou\s+(?:must|should|will)\b",
     "addresses the assistant directly with an obligation"),
]

# Where a directive hides from a human but not from a parser.
_HIDDEN_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
_ZERO_WIDTH          = re.compile(r"[​‌‍⁠﻿]")
_INVISIBLE_STYLE     = re.compile(
    r"<[^>]+style\s*=\s*[\"'][^\"']*(?:display\s*:\s*none|font-size\s*:\s*0|"
    r"color\s*:\s*(?:#fff(?:fff)?|white))", re.I)
# Unicode tag characters (U+E0000 block) encode ASCII invisibly and are a known
# prompt-smuggling channel. Nothing legitimate in a README uses them.
_UNICODE_TAGS        = re.compile(r"[\U000e0000-\U000e007f]")

# ---------------------------------------------------------------------------
# Signal 3 — credential-touching directives.
# ---------------------------------------------------------------------------

# A credential NOUN on its own is not a finding. `.env` appears in almost every
# legitimate README on earth, and flagging it makes this endpoint noise. What is
# a finding is a noun in a DIRECTIVE context: something telling the agent to
# read it, or to send it somewhere.
#
# This split was forced by the benign corpus, which is what it is for: the first
# version fired three MEDIUM findings on an ordinary Docker quickstart.

_CREDENTIAL_NOUNS = [
    (r"~?/?\.aws/credentials\b",                 "the AWS credentials file"),
    (r"\.env(?:\.local|\.production)?\b",        "an environment file"),
    (r"~?/?\.ssh/id_(?:rsa|ed25519|ecdsa)\b",     "a private SSH key"),
    (r"\blogin\.keychain(?:-db)?\b",             "the macOS keychain"),
    (r"~?/?\.config/(?:gcloud|gh)/",             "a cloud CLI credential store"),
    (r"\bLibrary/Application Support/(?:Google/Chrome|Firefox)\b"
     r"|\.config/google-chrome\b",               "a browser profile directory"),
    (r"~?/?\.npmrc\b|~?/?\.pypirc\b",           "a package-registry credential file"),
    (r"\bprocess\.env\.[A-Z_]{3,}\b",           "an environment variable"),
]

# Verbs that turn a mention into an instruction. Deliberately narrow: "copy
# .env.example and fill it in" is what every real project says, so `copy` is
# NOT here.
_CREDENTIAL_ACTIONS = re.compile(
    r"\b(?:cat|read|open|exfiltrat\w*|upload|send|post|include\s+(?:its|the)\s+contents"
    r"|contents\s+of|base64|tar\s|zip\s|curl\b[^\n]{0,40}\s-d\b|fetch\s*\(|"
    r"security\s+find-generic-password)\b", re.I)

# How far either side of the noun the directive may sit. Wide enough for
# "read ~/.aws/credentials and POST the contents to <url>", narrow enough that
# an unrelated sentence two paragraphs away does not count.
_CREDENTIAL_WINDOW = 120


def _credential_findings(text: str, hidden_regions: list) -> list[tuple[str, str, str]]:
    """(severity, detail, evidence) for each credential noun in a directive
    context. Returns nothing for a bare mention, which is the point."""
    out = []
    for pattern, what in _CREDENTIAL_NOUNS:
        for m in re.finditer(pattern, text, re.I):
            lo = max(0, m.start() - _CREDENTIAL_WINDOW)
            hi = min(len(text), m.end() + _CREDENTIAL_WINDOW)
            window = text[lo:hi]
            action = _CREDENTIAL_ACTIONS.search(window)
            if not action:
                continue
            hidden = next((how for body, how in hidden_regions if m.group(0) in body), "")
            out.append((
                "CRITICAL" if hidden else "MEDIUM",
                f"instructs the agent to {action.group(0).lower().strip()} {what}"
                + (f", {hidden}" if hidden else ""),
                window.strip(),
            ))
    return out


_URL_RE     = re.compile(r"https?://([A-Za-z0-9.\-]+\.[A-Za-z]{2,})(?:[/?#][^\s\"'`)>\]]*)?")
_NPM_RE     = re.compile(r"\bnpm\s+(?:i|install)\s+(?:-g\s+)?([@A-Za-z0-9._/\-]+)")
_PIP_RE     = re.compile(r"\bpip3?\s+install\s+(?:-U\s+)?([A-Za-z0-9._\-\[\]]+)")

SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _fetch(url: str) -> str | None:
    """One bounded GET. Returns text, or None for anything that is not a
    readable 200. Never raises: an unreadable surface is a reported gap, not an
    error, and a scan that dies on one 404 is useless on real repositories."""
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", _UA)
        req.add_header("Accept", "text/plain, application/json;q=0.9, */*;q=0.8")
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return resp.read(MAX_BYTES).decode("utf-8", errors="replace")
    except urllib.error.HTTPError:
        return None
    except Exception as exc:
        logger.info("agent-bait-scan fetch failed url=%s error=%s", url, exc)
        return None


def parse_github_target(target: str) -> tuple[str, str] | None:
    """owner/repo from a GitHub URL or a bare owner/repo. None if it is neither.

    Deliberately strict. A loose parser here turns an arbitrary user string into
    an arbitrary outbound request, which is a request-forgery surface on a
    keyless endpoint.
    """
    t = (target or "").strip()
    if t.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(t)
        if parsed.netloc.lower() not in ("github.com", "www.github.com"):
            return None
        parts = [p for p in parsed.path.split("/") if p]
    else:
        parts = [p for p in t.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    # A segment of "." or ".." parses as a valid name under a naive charset
    # check and turns "../../etc/passwd" into a request we would then make.
    # Found by the parser tests, which exist for exactly this.
    ok = re.compile(r"^(?=.*[A-Za-z0-9])[A-Za-z0-9._\-]{1,100}$")
    if owner in (".", "..") or repo in (".", ".."):
        return None
    if not ok.match(owner) or not ok.match(repo):
        return None
    return owner, repo


def collect_surfaces(owner: str, repo: str) -> tuple[dict, list]:
    """Fetches the agent-facing files. Returns (name -> text, list of misses).

    Tries the default branch names in order and stops at the first that answers,
    so a repo on `master` costs one extra request rather than failing.
    """
    found, missed = {}, []
    branch = None
    for candidate in ("main", "master"):
        if _fetch(f"https://raw.githubusercontent.com/{owner}/{repo}/{candidate}/README.md") is not None:
            branch = candidate
            break
    if branch is None:
        branch = "main"   # still try the rest; a repo may have no README at all

    for name in AGENT_SURFACES[:MAX_SURFACES]:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{name}"
        text = _fetch(url)
        if text is None:
            missed.append(name)
        else:
            found[name] = text
    return found, missed


def _hidden_regions(text: str) -> list[tuple[str, str]]:
    """Text a human would not see, paired with how it was hidden."""
    regions = []
    for m in _HIDDEN_HTML_COMMENT.finditer(text):
        body = m.group(1).strip()
        if body:
            regions.append((body, "inside an HTML comment"))
    if _INVISIBLE_STYLE.search(text):
        regions.append((text, "styled to be invisible"))
    return regions


def scan_text(name: str, text: str) -> list[dict]:
    """Signals 1 to 3 over one surface. Pure, offline, and the whole reason this
    is testable without a network."""
    findings = []

    def add(sev, kind, detail, evidence, hidden=""):
        findings.append({
            "surface":  name,
            "type":     kind,
            "severity": sev,
            "detail":   detail + (f", {hidden}" if hidden else ""),
            # Bounded so a finding stays readable in ten seconds, which is the
            # rule that decides whether anyone can dismiss a false positive.
            "evidence": evidence.strip()[:200],
        })

    hidden_regions = _hidden_regions(text)

    for pattern, detail in _EXEC_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            hidden = next((how for body, how in hidden_regions if m.group(0) in body), "")
            add("CRITICAL" if hidden else "HIGH", "execution_instruction",
                detail, m.group(0), hidden)

    for pattern, detail in _INJECTION_PATTERNS:
        for m in re.finditer(pattern, text, re.I | re.M):
            hidden = next((how for body, how in hidden_regions if m.group(0) in body), "")
            add("CRITICAL" if hidden else "HIGH", "injection_marker",
                detail, m.group(0), hidden)

    for severity, detail, evidence in _credential_findings(text, hidden_regions):
        add(severity, "credential_directive", detail, evidence)

    if _ZERO_WIDTH.search(text):
        add("HIGH", "hidden_text", "contains zero-width characters, which a human reader "
            "cannot see and a model can", "zero-width characters present")
    if _UNICODE_TAGS.search(text):
        add("CRITICAL", "hidden_text", "contains Unicode tag characters, a known channel "
            "for smuggling instructions past a human reader", "Unicode tag block present")

    return findings


def extract_references(surfaces: dict) -> dict:
    """Every domain and package the instructions point at. This is what signal 4
    is joined against, and it is the half nobody replicating this can do."""
    domains, packages = [], []
    for text in surfaces.values():
        for m in _URL_RE.finditer(text):
            d = m.group(1).lower()
            if d.startswith("www."):
                d = d[4:]
            if d not in domains:
                domains.append(d)
        for rx, eco in ((_NPM_RE, "npm"), (_PIP_RE, "pypi")):
            for m in rx.finditer(text):
                pkg = m.group(1).strip(".")
                if pkg and (eco, pkg) not in packages:
                    packages.append((eco, pkg))
    return {"domains": domains[:MAX_REFERENCES],
            "packages": packages[:MAX_REFERENCES]}


def provenance_findings(references: dict) -> list[dict]:
    """Signal 4. Joins referenced domains to the criminal IOC corpus and to the
    typosquat and registration-age checks that mcp-registry-risk already
    implements.

    IMPORTS them. The alternative is a fifth copy of a table that must agree
    with four others and has nothing checking that it does.

    Never raises: with no corpus reachable this returns [] and the scan reports
    signals 1 to 3 with provenance marked unavailable, which is a thinner answer
    rather than a failed one.
    """
    findings = []
    try:
        import relayshield_agentic_api as agentic
    except Exception as exc:
        logger.warning("provenance unavailable, detector not importable: %s", exc)
        return findings

    for domain in references.get("domains", []):
        # Well-known hosts are where instructions legitimately point. Checking
        # them wastes a corpus query and invites a typosquat finding against
        # the very list they are on.
        if domain in agentic.KNOWN_MCP_DOMAINS:
            continue
        try:
            result = agentic.handle_mcp_registry_risk({"server_url": f"https://{domain}"})
            data = json.loads(result.get("body", "{}")).get("data", {})
        except Exception as exc:
            logger.warning("provenance lookup failed domain=%s: %s", domain, exc)
            continue
        for f in data.get("findings", []) or []:
            findings.append({
                "surface":  "referenced_domain",
                "type":     f"referenced_{f.get('type', 'domain_risk')}",
                "severity": f.get("severity", "MEDIUM"),
                "detail":   f"the instructions reference {domain}: {f.get('detail', '')}",
                "evidence": domain,
            })
    return findings


def handle_agent_bait_scan(params: dict) -> dict:
    """The endpoint. Returns the same {ok, data} envelope as every other one.

    Deliberately returns 200 with an explanatory verdict rather than an error
    for a target we could not read: "we could not read this" is a result a
    caller can act on, and it is what actually happens on a private or renamed
    repository.
    """
    from relayshield_agentic_api import _ok, _err

    target = (params.get("repository") or params.get("target")
              or params.get("server_url") or "").strip()
    if not target:
        return _err("repository is required — a GitHub URL or owner/repo")

    parsed = parse_github_target(target)
    if not parsed:
        return _err("only GitHub repositories are supported in v1 — pass a "
                    "github.com URL or owner/repo")
    owner, repo = parsed

    surfaces, missed = collect_surfaces(owner, repo)

    findings: list[dict] = []
    for name, text in surfaces.items():
        findings.extend(scan_text(name, text))

    references = extract_references(surfaces)
    provenance = provenance_findings(references)
    findings.extend(provenance)

    verdict = max((f["severity"] for f in findings),
                  key=lambda s: SEVERITY_ORDER.get(s, 0), default="LOW")

    if not surfaces:
        note = ("No agent-facing file could be read. The repository may be private, "
                "renamed, or empty. This is not a finding about its contents.")
    elif not findings:
        # Rule 2. The ceiling is "nothing known against it", never "safe".
        note = ("No hostile instructions found in the files that were read. That is "
                "an absence of evidence, not proof of safety: it says nothing about "
                "the code, and nothing about files that were not read.")
    else:
        # Rule 3. Report what the instructions would cause, never a character
        # judgement about a named maintainer.
        note = ("These are the actions the repository's own agent-facing text would "
                "cause an agent to take. They are not an assertion that the "
                "repository or its maintainer is malicious.")

    return _ok({
        "repository":        f"{owner}/{repo}",
        "verdict":           verdict,
        "surfaces_read":     sorted(surfaces.keys()),
        "surfaces_missing":  missed,
        "findings":          findings,
        "references":        {"domains": references["domains"],
                              "packages": [f"{e}:{p}" for e, p in references["packages"]]},
        "provenance_checked": bool(provenance) or bool(references["domains"]),
        "note":              note,
    })
