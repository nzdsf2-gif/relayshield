# rsscan

Block commits and builds that introduce API keys, tokens and other machine credentials.

Detects 31 credential patterns — AWS IAM keys, GitHub PATs, Stripe secrets, Slack tokens, private keys, and LLM provider keys (OpenAI, Anthropic, Google, Groq, xAI, Replicate).

**Free, and it runs entirely on your machine.** No account, no API key, no network call. Your source code never leaves the host — matching happens locally against patterns shipped inside the package.

**The pre-commit hook is the point.** It runs *before* the commit enters git history. A CI check only sees the secret after a push, and by then it is in history and has to be rotated even if you delete the commit. The CI integrations below are a backstop, not a substitute.

## Install

### pre-commit hook (recommended)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/RelayShield/rsscan
    rev: v0.1.0
    hooks:
      - id: rsscan
```

```bash
pre-commit install
```

That is the whole setup. Nothing to configure, nothing to sign up for.

### GitHub Actions

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0        # required — the range needs history
- uses: RelayShield/rsscan@v0.1.0
  with:
    fail-on: HIGH
```

### GitLab CI/CD

```yaml
include:
  - component: $CI_SERVER_FQDN/relayshield/rsscan/secret-scan@0.1.0
    inputs:
      fail_on: HIGH
```

### CircleCI

```yaml
orbs:
  rsscan: relayshield/rsscan@0.1.0
workflows:
  main:
    jobs:
      - rsscan/scan
```

### Docker — Bitbucket Pipelines, Tekton, Drone, Woodpecker, Harness, anything else

```bash
docker run --rm -v "$PWD:/workspace" \
  -e RSSCAN_REV_RANGE=origin/main...HEAD \
  relayshield/rsscan:0.1.0
```

Bitbucket Pipelines:

```yaml
- step:
    script:
      - pipe: docker://relayshield/rsscan:0.1.0
        variables:
          RSSCAN_REV_RANGE: "origin/main...HEAD"
```

### Jenkins, Azure DevOps, or any shell

```bash
pip install rsscan
RSSCAN_REV_RANGE="origin/main...HEAD" rsscan
```

## How it works

Scans the diff locally and fails on a finding at or above `--fail-on` (default `HIGH`).

**Only added lines are scanned.** Secrets already in your files are not re-flagged, so the tool does not become unbypassable noise on a repo with legacy findings.

**Nothing is transmitted and nothing is printed.** There is no scan endpoint to send code to. Matched values never appear in output either — findings carry a file, a line and a non-reversible fingerprint, so a scan is safe to run in CI without leaking the secret into build logs.

```
  rsscan: secrets detected in staged changes

  CRITICAL AWS IAM Access Key
           src/config.py:14
           fingerprint sha256:1a5d44a2dca19669

  Commit refused.

  Remove the value and load it from a secrets manager or environment
  variable instead. If it has already left this machine, rotate it.

  False positive? Add the fingerprint to .relayshield-allowlist:
      echo 'sha256:1a5d44a2dca19669' >> .relayshield-allowlist

  To bypass entirely: git commit --no-verify
```

## Configuration

Every flag has an environment variable equivalent, which is how the CI clients drive it.

| Flag | Env var | Default | Meaning |
|---|---|---|---|
| `--fail-on` | `RSSCAN_FAIL_ON` | `HIGH` | Lowest severity that fails. `LOW`/`MEDIUM`/`HIGH`/`CRITICAL`. |
| `--rev-range` | `RSSCAN_REV_RANGE` | *(staged)* | Scan a commit range instead of staged changes. |
| `--allowlist` | `RSSCAN_ALLOWLIST` | `.relayshield-allowlist` | Fingerprints to ignore. |
| `--report` | `RSSCAN_REPORT` | *(off)* | Write a shareable exposure report to this path. |
| `--org` | `RSSCAN_ORG` | *(off)* | Opt in to reporting adoption for your org domain. |
| `--strict` / `--no-strict` | `RSSCAN_STRICT` | *see below* | Fail when the scan cannot run. |

### Failure behaviour differs by mode, on purpose

**Pre-commit fails open.** If the scan genuinely cannot run — an unreadable diff, a broken git invocation — it warns on stderr and lets the commit through. A hook that wedges every commit gets uninstalled, and then it catches nothing.

**CI fails closed.** A gate that silently reports success when it could not actually run is worse than no gate — it manufactures false assurance. Override either way with `--strict` / `--no-strict` or `RSSCAN_STRICT`.

### Allowlisting

The allowlist holds **fingerprints, not secrets** — a file containing the actual values would be the same mistake this tool exists to prevent.

```
# .relayshield-allowlist
sha256:1a5d44a2dca19669   # documented example key in docs/quickstart.md
```

## Sharing a finding with your security team

```bash
rsscan --report exposure.md
```

Writes a Markdown report you can attach to a ticket or forward by email. It contains **no secret values** — only fingerprints — so it is safe to share.

## Optional: telling us your org uses rsscan

```bash
rsscan --org yourcompany.com
```

**Off by default and entirely optional.** When enabled it sends only your org domain, an anonymous per-machine id, the tool version, and how many findings there were by severity.

It never sends file paths, fingerprints, repository names, source code, or the secrets themselves. There is no mechanism in the tool to do so.

## What this tool cannot tell you

rsscan stops credentials *before* they enter git history. It cannot see credentials that have already left — a key committed last year, or one leaked through a dependency, a published package or a container image, may already be indexed and scraped.

Answering that needs a view of what is public, plus the identity layer secret scanners do not cover at all: workforce credentials surfacing in infostealer logs and breach dumps, SIM-swap risk on staff accounts, and session/token exposure. That is what [RelayShield](https://api.relayshield.net/developers?source=rsscan) does.

## Pricing

rsscan is free. There is no paid tier of this tool, no scan quota, and no account.

## Licence

MIT
