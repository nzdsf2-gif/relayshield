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

## Question 2 — RelayShield angle on secrets in Origin: **yes, and it is time-sensitive**

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
