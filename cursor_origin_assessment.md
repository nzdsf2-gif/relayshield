# Cursor Origin — CI/CD value, and the secret-scanning angle

*Assessed 2026-08-21. Two separate questions with opposite answers.*

## What Origin actually is

Cursor (Anysphere, now SpaceX-owned) launched **Origin** on **17 August 2026** — four days ago — as
an early-beta Git host and code review platform. Real repositories, pull requests with inline
review, branch protections, a CLI, code browsing and search, and **GitHub mirroring**: connect a
GitHub org, pick repos, and they appear alongside Origin-native ones.

The differentiator is that Cursor's coding agents are first-class actors, with an automated pull
request pipeline that pulls a human in when judgement is needed. Beta integrations at launch:
**Vercel, Depot, Buildkite**.

---

## Question 1 — CI/CD value for the RelayShield repo: **no, not now**

Recommend against moving or dual-homing RelayShield's CI. Three concrete reasons, in order of
weight:

1. **The integration list does not include what this repo runs on.** Deployment here is GitHub
   Actions with **AWS OIDC** into `arn:aws:iam::239677749008:role/relayshield-github-deploy` —
   `deploy_lambdas.yml`, `lambda_drift_check.yml`, `intel_channel_classify.yml`, the intel feed
   workflows. Vercel, Depot and Buildkite do not cover that. Rebuilding it means new credentials
   and a second OIDC trust relationship on a four-day-old beta.
2. **The CI here is load-bearing for correctness, not just convenience.** `lambda_drift_check.yml`
   caught real drift on `relayshield-api` on its first run — code live in production that was never
   committed. That check, and the deploy preflight, are the controls standing between this repo and
   a repeat of the destroyed Telegram command merges. **Do not rehost the safety net on a beta.**
3. **There is no problem being solved.** Nothing about the current pipeline is failing. Migration
   cost is real; the benefit is speculative.

**What is worth doing, and it is cheap:** use Origin's **GitHub mirroring** in the direction that
costs nothing — GitHub stays authoritative, Origin gets a read-only mirror — purely to evaluate
whether the agent-assisted PR review is useful on a repo this size. `relayshield_api.py` is
11,000+ lines and this codebase has repeatedly shipped the same class of defect (an extractor
producing values a `type_map` never persisted, three times). An automated reviewer that catches
that is worth an evaluation. **Revisit properly once Origin supports OIDC to AWS**, which is the
actual gate.

⚠️ **One thing to settle before mirroring anything.** This repo carries commercial strategy,
customer material and partner correspondence. Mirroring puts all of it on a four-day-old platform
under new ownership. Read Origin's data handling terms first, and if there is any doubt, mirror
**`rsscan/` only** — it is already MIT-licensed and public, so it carries no exposure and is a
perfectly good test subject.

---

## Question 2 (RESTATED 2026-08-21) — can Origin become a source in `/v1/metered/secret-scan`?

The question was whether Origin can be added to the existing endpoint that searches *their* repos
for exposed secrets, the way GitHub, npm, PyPI, Docker Hub, Hugging Face and Postman already are.
My first pass answered a different question — outreach and CI — so this section answers the one
actually asked.

### Short answer: not as a seventh public source. There is nothing public to search.

**Origin's August 2026 beta has no public repositories.** Reporting is explicit that public repos
are not supported in the current beta, which is why it is a poor fit for open source. That is the
whole gate.

`/v1/metered/secret-scan` is built on one premise, visible in every one of its six sources: **search
a public surface for artifacts belonging to a domain, unauthenticated.** `_github_secret_scan`
searches public code; `_pypi_secret_scan` streams the public index; `_postman_secret_scan` hits
public search. Origin has no such surface, so the existing `(label, fn)` dispatch has nothing to
call. Adding it would produce a source that always returns zero findings and a `coverage` entry
saying it ran — **a false all-clear, which the endpoint's own code comments name as the worst
possible failure for this product.**

### The shape that does work: an authorised scan, which is a different product

Origin does have a REST API at `https://api.cursor.com/v1/origin`, with installation tokens and a
`GET /installation/repos` call to enumerate the repositories an installation can see. That is a
GitHub-App-style authorisation model: the customer installs and grants, then we read their repos.

That is genuinely buildable, and arguably more valuable — but it is **not the same product**:

| | `/v1/metered/secret-scan` today | An Origin authorised scan |
|---|---|---|
| Question answered | "What is leaking about us in public?" | "What is in our own repos?" |
| Access | None. Unauthenticated OSINT | Customer grants an installation token |
| Consent | Not needed — it is all public | Required, per customer |
| Competitor | GitGuardian public monitoring | GitHub secret scanning, TruffleHog |

**Recommendation: build it as a new endpoint, not a seventh source.** Something like
`POST /v1/metered/repo-scan`, taking a customer-supplied installation token and scanning what it can
reach, reusing `_findings_from_text()` and the existing 31 detectors — which is where the real value
already sits. Folding an authorised, consent-bearing scan into an endpoint whose whole contract is
"public exposure" would muddle both, and the `coverage` field could no longer be read honestly.

### ⚠️ I could not verify the API contract, and did not guess it

**`cursor.com` is blocked by this sandbox's egress proxy** (403 on CONNECT), so the official Origin
API documentation could not be read. Everything above about `api.cursor.com/v1/origin`,
installation tokens and `GET /installation/repos` comes from **secondary reporting, not the docs.**

That is not good enough to write HTTP calls against, and writing them anyway is the same mistake as
the Ansible Galaxy claim. **Before any implementation, read `cursor.com/docs/api/origin` from an
unblocked machine and confirm:** the auth header format, how an installation token is obtained and
refreshed, the exact repo-enumeration path and its pagination, whether file contents or a tree can
be read, and whether any code-search primitive exists (its absence would mean fetching and scanning
blobs, which changes the cost model completely).

### Still worth doing regardless — `rsscan` in an Origin pipeline

Independent of the API question, and unblocked today: `rsscan` already runs anywhere a container
runs, with Bitbucket Pipelines, Tekton, Drone, Woodpecker and Harness documented. Getting it into an
Origin pipeline and writing that up is low effort and lands while nobody else covers Origin. Detail
below.

## The outreach and tooling angle (original question 2)

This is the interesting half.

**A new code host is a new place credentials leak, and on day five nobody scans it.** Every existing
secret-scanning product — GitHub's own, GitGuardian, TruffleHog's SaaS — is built around GitHub,
GitLab and Bitbucket. Origin repositories are outside all of them. The gap will close, but it is
open now.

RelayShield already has both halves of the answer built:

* **`rsscan`** — MIT-licensed CLI, 31 credential patterns (AWS IAM, GitHub PATs, Stripe, Slack,
  private keys, and LLM provider keys for OpenAI, Anthropic, Google, Groq, xAI, Replicate), with a
  Docker image already documented for **Bitbucket Pipelines, Tekton, Drone, Woodpecker and Harness**
  — i.e. it was deliberately built not to depend on GitHub Actions.
* **`/v1/metered/secret-scan`** — the paid 6-source public-artifact scan (GitHub, npm, PyPI, Docker
  Hub, Hugging Face, Postman).

### Ranked by effort against value

| | Move | Effort | Why |
|---|---|---|---|
| 1 | **Get `rsscan` running in an Origin pipeline and document it** | Low | The Docker path already works anywhere a container runs. Mostly a README section and one verification run. Publishing "how to scan for secrets on Origin" in the first weeks is a genuine first-mover position on a search term with no incumbent |
| 2 | **Add Origin as a 7th source to `/v1/metered/secret-scan`** | Medium | Only worth it **if Origin exposes public repositories and an enumeration API**. That is unverified and is the gate — check before scoping. The other six sources are all public-artifact registries, so this only fits if Origin has a public surface |
| 3 | **Add Origin host/token patterns to `rsscan`'s 31 detectors** | Low, but blocked | Origin will issue its own PATs or CLI tokens with a recognisable prefix. Nobody detects them yet. **Cannot be done from here** — needs a real token's shape observed from an actual account. Get an Origin account and look at one |

### The angle that is genuinely differentiated

Agent-written code is the thing Origin is *for*. An agent that hardcodes a key while iterating is a
well-documented failure mode, and Origin's pipeline is explicitly built to let agents open PRs with
a human pulled in only when judgement is needed — which is precisely the workflow where a
hardcoded credential slips past. **"Secret scanning for agent-authored pull requests" is a sharper
product claim than "secret scanning", it is true, and it is aimed exactly at Origin's own thesis.**

That is also a better blog than a feature. `blog-secret-scanning-false-positives.md` already
establishes credibility on this topic — the follow-up writes itself.

### Do not overreach

The honest scope today is **item 1**: one documented pipeline and a post. Items 2 and 3 are both
blocked on facts that require an actual Origin account, and neither should be scoped until someone
has one. Announcing Origin support before that is the same mistake as claiming an Ansible
collection that had not shipped.
