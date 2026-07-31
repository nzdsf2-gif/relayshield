# Publishing runbook — rsscan v0.1.0

Six catalogs. Publish in this order: each step depends on the one before it.

Everything below needs credentials held by the founder. Nothing here has been run.

---

## 0. Prerequisites

| Account | Needed for | Have it? |
|---|---|---|
| GitHub org `RelayShield` | Repo, Action, release tags | Yes — org exists |
| PyPI | `rsscan` package | Name verified available 2026-07-31 |
| Docker Hub org `relayshield` | Container image | Check availability |
| GitLab account/group `relayshield` | CI/CD Catalog component | Check availability |
| CircleCI account | Orb namespace `relayshield` | Check availability |
| Artifact Hub | Container listing | Sign in with GitHub |

Claim the three unverified namespaces **before** step 1 — the README hard-codes all of
them, and changing a name after publishing means a version bump everywhere.

---

## 1. GitHub repo (everything else references it)

```bash
cd "/Users/andrewgibbs/Side SaaS Hustle/rsscan"
git init && git add -A
git commit -m "rsscan 0.1.0"
gh repo create RelayShield/rsscan --public --source=. --push \
  --description "Block commits that introduce API keys, tokens and other machine credentials"
```

Set repo topics — these are the search surface on GitHub itself:

```bash
gh repo edit RelayShield/rsscan --add-topic secret-scanning,pre-commit,devsecops,security,git-hooks,secrets-detection,ci-cd
```

Add `LICENSE` (MIT — `pyproject.toml` already declares it, and PyPI will flag the mismatch if the file is absent).

Then tag, because the pre-commit config, the Action and the docs all pin `v0.1.0`:

```bash
git tag -a v0.1.0 -m "rsscan 0.1.0" && git push origin v0.1.0
gh release create v0.1.0 --title "rsscan 0.1.0" --notes "First release."
```

**Verify:** `.pre-commit-config.yaml` pointing at `https://github.com/RelayShield/rsscan` `rev: v0.1.0` installs and runs in a scratch repo. This is the primary client — test it before anything else ships.

---

## 2. PyPI

Every CI client `pip install rsscan==0.1.0`, so this must land before the Action, GitLab component or orb will work at all.

```bash
python3 -m pip install --upgrade build twine
python3 -m build
python3 -m twine check dist/*
python3 -m twine upload dist/*          # username: __token__, password: pypi-…
```

**Verify:** `pip install rsscan && rsscan --version` in a clean venv on a different machine.

Use a **scoped** PyPI token, and prefer Trusted Publishing (OIDC from GitHub Actions) over a long-lived token once the repo exists — a static PyPI token in CI is exactly the credential class this tool detects.

---

## 3. Docker Hub

```bash
docker login
docker buildx create --use --name rsscan-builder     # multi-arch; Colima default builder is single-arch
docker buildx build --platform linux/amd64,linux/arm64 \
  -t relayshield/rsscan:0.1.0 -t relayshield/rsscan:latest --push .
```

**arm64 alone is not enough.** Nearly all CI runners are amd64; an arm64-only image fails on
GitHub-hosted runners, GitLab shared runners and most Bitbucket Pipelines. The local Colima build
was arm64 (Apple Silicon), so this is the one step where the tested artifact differs from the
published one.

Fill in the Docker Hub description from `README.md`, and link back to the GitHub repo.

**Verify on an amd64 host:**
```bash
docker run --rm --platform linux/amd64 -v "$PWD:/workspace" \
  -e RELAYSHIELD_API_KEY -e RSSCAN_REV_RANGE=HEAD~1..HEAD relayshield/rsscan:0.1.0
```

---

## 4. GitHub Marketplace (Action)

The Action is already at the repo root as `action.yml`, which is what Marketplace requires.

1. Repo → **Releases** → edit the `v0.1.0` release.
2. Tick **Publish this Action to the GitHub Marketplace**.
3. Accept the developer agreement.
4. Primary category **Continuous integration**, secondary **Code quality** or **Security**.

Marketplace requires: a unique Action name, `action.yml` at the repo root, an OSI licence file,
and a README. All present except `LICENSE` — add it in step 1.

**Verify:** a workflow in a throwaway repo using `RelayShield/rsscan@v0.1.0` blocks a commit
containing a fake AWS key and passes on a clean diff.

---

## 5. GitLab CI/CD Catalog

The component must live in a **GitLab** repo — mirror from GitHub, don't move.

```bash
git remote add gitlab https://gitlab.com/relayshield/rsscan.git
git push gitlab main --tags
```

Then in the GitLab project:

1. **Settings → General → Visibility** → public.
2. **Settings → General → CI/CD Catalog resource** → toggle on.
3. Add `README.md` and a `LICENSE` (both required for catalog listing).
4. Create a release for the tag — the catalog indexes **releases**, not tags:

```yaml
# .gitlab-ci.yml in the component repo
create-release:
  stage: deploy
  image: registry.gitlab.com/gitlab-org/release-cli:latest
  rules:
    - if: $CI_COMMIT_TAG
  script: echo "Releasing $CI_COMMIT_TAG"
  release:
    tag_name: $CI_COMMIT_TAG
    description: "rsscan $CI_COMMIT_TAG"
```

Component path resolves as `$CI_SERVER_FQDN/relayshield/rsscan/secret-scan@0.1.0`, taken from
`templates/secret-scan.yml`. The filename **is** the component name — renaming the file changes
the public path.

**Verify:** include the component in a scratch GitLab project and confirm the job runs and fails
correctly. Confirm `GIT_DEPTH: 0` took effect — without it GitLab's shallow clone silently yields
an empty diff and the job passes while scanning nothing.

---

## 6. CircleCI Orb

```bash
circleci setup                                   # personal API token
circleci namespace create relayshield github RelayShield
circleci orb create relayshield/rsscan
circleci orb pack orb/ > orb.yml
circleci orb validate orb.yml
circleci orb publish orb.yml relayshield/rsscan@0.1.0
```

A namespace is **one per org and permanent** — check the name carefully before creating it.
Public orbs require accepting CircleCI's open-source terms; the source becomes public, which is
fine (it already is).

**Verify:** `circleci orb info relayshield/rsscan` lists it, then run it in a scratch project.

---

## 7. Artifact Hub

1. Sign in at [artifacthub.io](https://artifacthub.io) with GitHub.
2. **Control Panel → Repositories → Add**, kind **Container image**.
3. URL `https://hub.docker.com/r/relayshield/rsscan`.
4. Copy the generated repository ID into `artifacthub-repo.yml` and push.

Artifact Hub reads metadata from image **labels**, so add these to the `Dockerfile` before the
Docker Hub push in step 3 — retrofitting means republishing the image:

```dockerfile
LABEL io.artifacthub.package.readme-url="https://raw.githubusercontent.com/RelayShield/rsscan/main/README.md"
LABEL io.artifacthub.package.license="MIT"
LABEL org.opencontainers.image.source="https://github.com/RelayShield/rsscan"
LABEL org.opencontainers.image.description="Block commits that introduce API keys and machine credentials"
```

---

## 8. After publishing

- [ ] Add `secret-scan-text` to `/developers` and `/openapi.json` — it is live and billable but
      undocumented on our own site, which is where most traffic lands.
- [ ] Publish the RelayShield-side docs page the README links to.
- [ ] Add a `.pre-commit-config.yaml` using rsscan to **this** repo. Dogfooding is both a real
      control and the most credible thing to point at.
- [ ] Watch the first week of `relayshield_secret_scan_text_calls` meter events for unexpected
      volume — the hook fires on every commit and billing is per call.

## Not yet claimable

**pre-commit.com hooks index** requires >500 GitHub stars and excludes Docker-based hooks; PRs
below the bar are closed without comment. Revisit once the repo clears 500. The hook works today
without it — the index is discovery, not distribution.

**Bitbucket Pipes** is curated via Atlassian's `official-pipes` repo rather than self-serve. The
Docker image works as a `docker://` pipe today with no listing.

**JFrog / Anomali** are partner-gated. Per the prior decision, deals not flywheels. Note that
enterprises proxying PyPI through Artifactory get the package automatically once step 2 lands.
