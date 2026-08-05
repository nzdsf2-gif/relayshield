# rsscan 0.1.3 — release runbook

**Internal. Not shipped in the sdist (excluded like PUBLISHING.md).**

Everything up to the upload is done. `dist/` is built and `twine check` passes on both artifacts.

---

## 1. The token: do not paste it into chat

**Do not give me the PyPI token, and do not paste it into a chat message.** Anything in the
conversation is in the transcript. I also should not be handling credentials directly at all.

You have three options, best first.

### Option A — Trusted Publishing (recommended, removes the token permanently)

PyPI can accept uploads from a GitHub Actions workflow with **no token at all**, using short-lived
OIDC credentials. This is the durable fix: nothing to store, nothing to rotate, nothing to leak.

1. On PyPI: **Your projects → rsscan → Publishing → Add a new pending publisher**
   - Owner: `RelayShield`
   - Repository: `rsscan`
   - Workflow name: `publish.yml`
   - Environment: `pypi`
2. Add `.github/workflows/publish.yml` to the public repo:

```yaml
name: publish
on:
  release:
    types: [published]
permissions:
  contents: read
jobs:
  pypi:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write        # the OIDC token that replaces the API token
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.x' }
      - run: python -m pip install --quiet build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

After that, publishing is "cut a GitHub release" and nothing else. **Do this once and item 1 never
comes up again.**

### Option B — publish from your machine (fastest for today)

The token stays in your shell and never reaches me or the transcript.

```bash
cd "/Users/andrewgibbs/Side SaaS Hustle/rsscan"
python3 -m pip install --quiet --upgrade twine
export TWINE_USERNAME=__token__
read -rs TWINE_PASSWORD && export TWINE_PASSWORD   # paste token, it stays hidden
python3 -m twine upload dist/rsscan-0.1.3*
unset TWINE_PASSWORD
```

`read -rs` keeps the token off screen and out of your shell history. A **project-scoped** token is
correct here — rsscan already exists, so the account-scoped token is only needed for a brand-new
project.

### Option C — `~/.pypirc`

Workable but least good: the token sits on disk in plaintext indefinitely. If you use it,
`chmod 600 ~/.pypirc`.

**Whichever you pick, do not put the token in the repo, in an env var committed to a file, or in a
message to me.**

---

## 2. Verify the upload actually worked

Do not trust "upload succeeded" — install it clean and run it:

```bash
curl -s https://pypi.org/pypi/rsscan/json | python3 -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"
# expect: 0.1.3

python3 -m venv /tmp/rsverify && /tmp/rsverify/bin/pip install --quiet rsscan==0.1.3
/tmp/rsverify/bin/rsscan --version          # expect: rsscan 0.1.3
/tmp/rsverify/bin/rsscan --help | grep -E "slack-webhook|--webhook|annotate"
```

---

## 3. The other three artifacts still point at old versions

PyPI is only one of four published surfaces. **Until each is re-released, its users stay on the
old scanner** — and the README already advertises `v0.1.3` for two of them.

| Surface | Current | Needs |
|---|---|---|
| PyPI `rsscan` | 0.1.2 | the upload above |
| GitHub tag `v0.1.3` | absent | tag + release on the public `RelayShield/rsscan` repo — this is what `pre-commit` `rev:` and `uses: RelayShield/rsscan@v0.1.3` resolve to, and **both are already written into the README** |
| Docker `relayshield/rsscan:0.1.3` | 0.1.2 | build + push |
| CircleCI orb `relayshield/rsscan` | 0.1.0 | `circleci orb publish` — **README deliberately still says `@0.1.0`**; bump it only after the orb is published, or CircleCI users get an orb that does not exist |

Remember the public repo is built from a **clean export**, not pushed from the parent repo
(`PUBLISHING.md` and this file excluded, `.relayshield-allowlist` included so the repo passes its
own hook).

---

## 4. What is in 0.1.3

- **Inline PR annotations** (BB-8). Findings land on the changed line in the PR's Files tab.
  Workflow commands, not the Checks API — no token, no GitHub App, no `permissions:` block.
- **Slack delivery** — `--slack-webhook`, opt-in, Block Kit summary.
- **Generic webhook** — `--webhook`, opt-in, JSON POST.
- **Fixed: the GitHub Action and CircleCI orb both pinned `rsscan==0.1.0`** while PyPI was at
  0.1.2, so every CI user was installing a two-version-stale scanner.

No payload on any channel ever contains a secret value — type, severity, file, line and
fingerprint only. Verified by scanning the delivered bytes for the planted test secrets.
