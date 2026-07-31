# relayshield-precommit

A [pre-commit](https://pre-commit.com) hook that blocks commits introducing API keys, tokens and other machine credentials.

It runs **before the commit enters git history**. That is the difference that matters: a CI check only sees the secret after a push, and by then it is in history and has to be rotated even if you delete the commit.

Detects 31 credential patterns — AWS IAM keys, GitHub PATs, Stripe secrets, Slack tokens, private keys, and LLM provider keys (OpenAI, Anthropic, Google, Groq, xAI, Replicate).

## Install

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/RelayShield/relayshield-precommit
    rev: v0.1.0
    hooks:
      - id: relayshield-secret-scan
```

```bash
pre-commit install
```

Set your API key — [get one here](https://api.relayshield.net/developers):

```bash
export RELAYSHIELD_API_KEY=rs_live_...
```

## How it works

The hook sends `git diff --cached -U0` to RelayShield's scan endpoint and blocks the commit on a finding at or above `--fail-on` (default `HIGH`).

**Only added lines are scanned.** Secrets already in your files are not re-flagged, so the hook does not become unbypassable noise on a repo with legacy findings.

**Your code is not stored.** The diff is never logged or persisted server-side, and matched values are never sent back — findings carry a file, a line, and a truncated fingerprint.

## Example

```
  RelayShield: secrets detected in staged changes

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

| Flag | Default | Meaning |
|---|---|---|
| `--fail-on` | `HIGH` | Lowest severity that blocks. One of `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. |
| `--allowlist` | `.relayshield-allowlist` | Fingerprints to ignore, one per line, `#` comments allowed. |
| `--strict` | off | Refuse the commit when the scan cannot run, instead of allowing it. |
| `--timeout` | `10` | Request timeout in seconds. |

```yaml
      - id: relayshield-secret-scan
        args: [--fail-on, MEDIUM, --strict]
```

### Allowlisting

The allowlist holds **fingerprints, not secrets** — a file containing the actual values would be the same mistake this hook exists to prevent.

```
# .relayshield-allowlist
sha256:1a5d44a2dca19669   # documented example key in docs/quickstart.md
```

### Failure behaviour

By default the hook **fails open**: no API key, no network, or a server error warns on stderr and lets the commit through. A scanner that wedges every commit on a flaky connection gets uninstalled, and then it catches nothing. Use `--strict` to invert that.

`git commit --no-verify` bypasses it, like any pre-commit hook.

## Beyond pre-commit

The same endpoint backs a GitHub Action, a GitLab CI component, and a plain `curl` for Jenkins, CircleCI, Azure DevOps and Bitbucket Pipelines:

```bash
curl -sX POST https://api.relayshield.net/v1/metered/secret-scan-text \
  -H "X-RS-API-KEY: $RELAYSHIELD_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @<(jq -Rs '{diff: .}' <<< "$(git diff --cached -U0)")
```

## Pricing

$0.05 per scan, billed per commit that runs the hook. Empty staged diffs are not sent and are not billed.

## Licence

MIT
