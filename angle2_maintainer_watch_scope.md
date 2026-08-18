# Angle 2: dependency maintainer watch. Scope.

**Written 2026-08-11.** Follows the passed feasibility gate in task #9 and
`agentic_supply_chain_product_angle.md`.

**The one-line product:** every package security vendor analyses the artefact. None can tell you
whether the human who can publish that artefact is compromised right now. We can, because that is
what Bundle A already does, pointed at a different input.

---

## Answering the pricing question directly

**Yes, flat rate. No, not a new subscription.**

Fold it into **Bundle D** ($299/mo, `prod-kkvurtspreofy`, `agentic_bundle_access`) as included
capability, not as SKU ten.

Three reasons, in order of weight:

1. **The #19 audit is the binding constraint.** Nine ways to pay and zero paying customers. Another
   SKU makes the catalogue worse, not the revenue better. Bundle D is already the developer and
   agentic-surface bundle, and supply chain is squarely inside that story.
2. **It raises Bundle D's win rate.** Bundle D today is CVE, bulk identity, LLM credential exposure,
   MCP registry risk. It is a good bundle with no single reason to buy. "Nobody else can tell you
   whether your dependencies' maintainers are compromised" is a reason to buy.
3. **Flat rate matches the cost curve.** HIBP is a flat subscription and the stealer-log corpus is
   ours, so screening 400 maintainers costs the same as screening 4. This is the same correction the
   founder forced on Verdict Watch: marginal cost is approximately zero, so metering per call
   invents friction that recovers nothing. Perceived value scales with dependency count while cost
   does not, which is the good side of that trade.

**Break it out as its own SKU only if inbound demand appears for it alone.** Not before.

---

## What it does

**Input:** a dependency manifest, or a list of package names.
Start with `package-lock.json` and `package.json`. npm only for v1.

**Pipeline:**

1. Parse the manifest to a package list.
2. Resolve each package to its maintainers via `registry.npmjs.org/<pkg>` (`maintainers[].email`).
3. Screen those emails against the exposure sources Bundle A already uses: breach corpora,
   infostealer logs, session risk.
4. Re-screen on a schedule and alert on **change**, not on state.

**Output, and this is a hard design constraint:** findings are reported at the **dependency** level
and never name the human.

> 3 of your 412 dependencies are maintained by an account whose credentials appear in an
> infostealer log dated within the last 90 days.
> `left-pad`, `some-parser`, `another-lib`.

The customer's action is to pin the version, scrutinise updates, and add review. None of that needs
the person's identity. Naming a third party who never opted in carries GDPR and defamation exposure
for zero product benefit. **Do not build a version that names people, even internally, because
internal fields leak into support conversations.**

---

## Why a watch and not a scan

A one-time scan is worth almost nothing. The dependency tree is clean today and a maintainer is
phished in March. **The compromise happens at a random future moment, which means the product is
continuous or it is decorative.**

That is Verdict Watch's exact shape, and Verdict Watch already exists: `watch_access`, the watcher
Lambda, the flat-rate licence, and `_verdict_fingerprint` change detection that compares the finding
rather than the envelope.

**Add `dependency` as a fourth watch subject type** alongside `address`, `email`, `domain`, `phone`.

---

## What already exists versus what is new

| | Status |
|---|---|
| Breach, infostealer and session-risk screening of an email | **exists**, Bundle A |
| Watch registration, scheduling, change detection, alert delivery | **exists**, Verdict Watch |
| Flat-rate licence mechanism (`watch_access`) | **exists** |
| Free local tool that produces a forwardable artefact | **exists**, `rsscan` |
| npm package to maintainer email resolution | **new**, small, proven working at 91% |
| Manifest parsing | **new**, small |
| Dependency-level report format | **new**, small |
| Fan-out and caching for a 400-package manifest | **new**, the only real engineering |

The honest summary: this is mostly assembly, not invention. The screening engine, the watch engine
and the funnel all exist. What is new is a resolver and a report.

---

## Phases

**Phase 1, the wedge, free.** `rsscan --deps` reads the local manifest, resolves maintainers, and
reports counts only, with no screening: *"412 dependencies, term 1,140 maintainer accounts, 96 of
them personal webmail addresses."* Costs nothing, runs locally, needs no account, and closes on what
it cannot see: whether any of those accounts are exposed. That is the same construction as
`rsscan --report` and it is the founder-approved funnel unchanged.

**Phase 2, the paid capability.** `dependency` watch subject inside Bundle D. Weekly re-screen,
alert on change.

**Phase 3, only if Phase 2 gets used.** GitHub Action, MCP tool so an agent can ask before
installing, PyPI support.

**PyPI is deliberately Phase 3.** The gate measured only 69% individual-human emails on PyPI against
91% on npm, because PyPI returns a lot of `numpy-discussion@python.org` and
`contact@palletsprojects.com`. Screening a mailing list tells you nothing about whether a laptop is
compromised. npm is both the better join and where the self-replicating worms actually are.

---

## Open decisions for the founder

1. **Bundle D inclusion versus separate SKU.** Recommendation above is inclusion. This is the only
   decision that has to be made before building.
2. **Manifest upload versus package list.** Uploading `package-lock.json` is easier for the customer
   and means we hold their full dependency graph, which is commercially sensitive data we then have
   to defend. A hashed package-name list is more privacy-preserving and slightly more work for them.
   Leaning toward accepting both, defaulting to the list.
3. **Alert threshold.** Every exposed maintainer, or only stealer-log hits within N days? Breach
   corpora go back years and a 2013 LinkedIn breach on a maintainer's address is noise. Recommend
   stealer-log recency as the default signal, breach as context only.

## What could kill it, watch for these

- **False positives on shared or role addresses.** `dev@`, `contact@`, `oss-bot@`. The gate found
  9% of npm emails are role addresses. Filter them out of alerting, not just out of display.
- **Maintainer email churn.** Registry metadata is not always current. A stale address screens clean
  while the real one is compromised, which is a false clean, which is the defect family this project
  has fixed three times this month.
- **Volume.** A 400-package manifest fans out to roughly 1,100 maintainer lookups. Cache hard on
  package name and on email, and never re-resolve inside a single run.

---

## What this is not

It is not a package malware scanner. Socket, Snyk, Aikido and Endor own that and we would arrive
tenth. This is deliberately the one question they structurally cannot answer, because they analyse
code and we screen identities.

Related: `agentic_supply_chain_product_angle.md`, task #9 (gate, passed),
`project_developer_funnel_strategy` in memory.
