# rsscan

Block commits and builds that introduce API keys, tokens and other machine credentials.

Detects 31 credential patterns — AWS IAM keys, GitHub PATs, Stripe secrets, Slack tokens, private keys, and LLM provider keys (OpenAI, Anthropic, Google, Groq, xAI, Replicate).

**The pre-commit hook is the point.** It runs *before* the commit enters git history. A CI check only sees the secret after a push, and by then it is in history and has to be rotated even if you delete the commit. The CI integrations below are a backstop, not a substitute.

## Install

Get an API key at [api.relayshield.net/developers](https://api.relayshield.net/developers), then pick your client.

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
export RELAYSHIELD_API_KEY=rs_live_...
```

### GitHub Actions

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0        # required — the range needs history
- uses: RelayShield/rsscan@v0.1.0
  with:
    api-key: ${{ secrets.RELAYSHIELD_API_KEY }}
    fail-on: HIGH
```

### GitLab CI/CD

```yaml
include:
  - component: $CI_SERVER_FQDN/relayshield/rsscan/secret-scan@0.1.0
    inputs:
      fail_on: HIGH
```

Set `RELAYSHIELD_API_KEY` as a masked CI/CD variable.

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
  -e RELAYSHIELD_API_KEY \
  -e RSSCAN_REV_RANGE=origin/main...HEAD \
  relayshield/rsscan:0.1.0
```

Bitbucket Pipelines:

```yaml
- step:
    script:
      - pipe: docker://relayshield/rsscan:0.1.0
        variables:
          RELAYSHIELD_API_KEY: $RELAYSHIELD_API_KEY
          RSSCAN_REV_RANGE: "origin/main...HEAD"
```

### Jenkins, Azure DevOps, or any shell

```bash
pip install rsscan
RSSCAN_REV_RANGE="origin/main...HEAD" rsscan
```

Or call the API directly, no client at all:

```bash
git diff --cached -U0 | jq -Rs '{diff: .}' | \
curl -sX POST https://api.relayshield.net/v1/metered/secret-scan-text \
  -H "X-RS-API-KEY: $RELAYSHIELD_API_KEY" \
  -H 'Content-Type: application/json' --data-binary @-
```

## How it works

Sends the diff to RelayShield's scan endpoint and fails on a finding at or above `--fail-on` (default `HIGH`).

**Only added lines are scanned.** Secrets already in your files are not re-flagged, so the tool does not become unbypassable noise on a repo with legacy findings.

**Your code is not stored.** The diff is never logged or persisted server-side, and matched values are never sent back — findings carry a file, a line and a truncated fingerprint.

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
| `--strict` / `--no-strict` | `RSSCAN_STRICT` | *see below* | Fail when the scan cannot run. |
| `--timeout` | `RSSCAN_TIMEOUT` | `10` | Request timeout, seconds. |
| | `RELAYSHIELD_API_KEY` | *(required)* | Your API key. |

### Failure behaviour differs by mode, on purpose

**Pre-commit fails open.** No key, no network, or a server error warns on stderr and lets the commit through. A hook that wedges every commit on a flaky connection gets uninstalled, and then it catches nothing.

**CI fails closed.** A gate that silently reports success when it could not actually run is worse than no gate — it manufactures false assurance. Override either way with `--strict` / `--no-strict` or `RSSCAN_STRICT`.

### Allowlisting

The allowlist holds **fingerprints, not secrets** — a file containing the actual values would be the same mistake this tool exists to prevent.

```
# .relayshield-allowlist
sha256:1a5d44a2dca19669   # documented example key in docs/quickstart.md
```

## Pricing

$0.05 per scan. Empty diffs are not sent and are not billed.

## Licence

MIT
