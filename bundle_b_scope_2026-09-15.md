# AWS Bundle B — scoped 2026-09-15, and the order is not the obvious one

**Bundle B is not a build. Every endpoint in it already exists and is metered.** What is
missing is packaging, and the packaging is blocked on three things, two of which also block
Bundle A — which is further along than Bundle B and **has been one change set from
sellable since 17 July**.

---

## 1. What is actually built, checked in the code rather than recalled

Bundle B is *Attack Surface & Supply Chain*, $100/mo minimum, five dimensions
(`RelayShield_Strategy.md:5374`, approved 2026-07-06). All five endpoints are live:

| Endpoint | `/v1/metered/` | `/v1/payg/` |
|---|---|---|
| `supply-chain` | yes | yes |
| `asset-intel` | yes | — |
| `secret-scan` | yes | yes |
| `threat-actor` | yes | — |
| `session-risk` | yes | yes |

So the marginal work is a dimension table, a gate, a fulfillment config and an AWS change
set. Not five endpoints.

## 2. THE FINDING THAT DECIDES THE ORDER: Bundle A's dimensions were never added to AWS

`BUNDLE_A_DIMENSION_NAMES` and `is_bundle_a_call` are in `relayshield_api.py`. The
fulfillment Lambda carries a full `core_identity_bundle_access` config. The code shipped
**2026-07-13**.

**And the live product entity does not carry a single Bundle A dimension.** The
DescribeEntity capture shows six, and all six are Bundle D's:

    agentic_bundle_access      Entitled
    bulk_identity_risk         ExternallyMetered
    tech_stack_cve             ExternallyMetered
    mcp_registry_risk          ExternallyMetered
    prompt_injection_breach    ExternallyMetered
    llm_credential_exposure    ExternallyMetered

TODO.md item 33 records why: the `AddDimensions` change set failed with
`ResourceInUseException` in July because another change set was in flight, and the entity
was **re-checked live on 2026-07-17 and found clear**. Nobody resubmitted. So Bundle A is
sold in code, gated in code, fulfilled in code, and cannot be bought.

**My recommendation, and it is mine to be overruled: do Bundle A's AddDimensions before
Bundle B.** Bundle A is one submission away from revenue against code that has been live
for two months; Bundle B is that same submission plus a code change in a file with no
deploy path (section 3). Doing B first means two bundles with code and no rate card
instead of one, and both change sets touch the same entity, which allows only one in
flight at a time.

## 3. THE FILE BUNDLE B HAS TO BE WRITTEN INTO IS IN NO DEPLOY MAP AND NO DRIFT CHECK

`relayshield_bundle_fulfillment.py` holds `BUNDLE_CONFIGS`, which maps an entitlement's
`Dimension` to its bundle. A Bundle B entry goes there and nowhere else.

**It is in neither `deploy_lambdas.yml` nor `lambda_drift_check.yml`.** Source in the repo,
live traffic from every bundle subscriber, no deploy path, no drift detection — the
**seventh** instance of that exact combination, and the last one
(`relayshield_developer_signup.py`) had quietly grown 700 lines including two Stripe
revenue doors that a repo-sourced deploy would have deleted with no error anywhere.

**So writing Bundle B into it blind is the 2026-08-17 mistake, on the file that decides
who gets entitled to what.**

**CLAUDE ALREADY DID THIS:** added it to `lambda_drift_check.yml`, watch only, deliberately
not to the deployer. The function name in the map is a guess from the filename convention
and is UNVERIFIED; if the run reports UNREADABLE, the name is wrong, not the entry.

**ANDREW RUNS THIS** to settle it without waiting for the nightly check. It is read-only —
it lists functions, downloads a package and diffs:

```zsh
cd ~/dev/relayshield
git checkout main
git --no-pager fetch origin claude/great-ritchie-6b8adu
git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap
git stash push --include-untracked -m "pre-merge untracked"
git -c pull.rebase=false merge --no-edit FETCH_HEAD
sh tools/handler_drift.sh relayshield_bundle_fulfillment.py
```

EXPECT: the resolved function name, then either *live is byte-identical to commit X* (the
stale case — safe, map it in the deployer) or a list of live-only content (recover first
with `recover_live_handler.yml`, exactly as developer-signup was).
STOP IF: the merge conflicts in **only CLAUDE.md** — expected, keep both sides. A conflict
in a `.py` or a workflow is different; send me the filename.

## 4. The third blocker, and it is IAM

The IAM snapshot carries `aws-marketplace:MeterUsage`, `BatchMeterUsage` and
`ResolveCustomer` — **metering only**. `DescribeEntity`, `ListEntities` and `StartChangeSet`
are all absent, so `tools/marketplace_add_dimension.py` fails even on `--describe`.

That grant is itself an IAM change, and the shared role's inline budget is full (26
policies, 10,127 of 10,240 bytes) with 11 of 10 managed slots used. **So it is a
customer-managed policy on a role that is already over the cap**, which is the IAM split
runbook arriving whether we wanted it or not.

## 5. And the danger that is specific to this, worth restating before anyone submits

**A change set does not add a dimension. It replaces the whole rate card with whatever you
hand it, and an empty card is a valid document.** That rolled Bundle D's prices back to
placeholders once already, on 2026-07-27.

`tools/marketplace_add_dimension.py` guards it: the capture must be a `SaaSProduct`, must
be under 24 hours old, and must already contain all six live dimensions. **Those guards
were written for Bundle D and they are exactly what Bundle A and B need too** — a
submission that adds Bundle B while dropping Bundle D's monthly minimum is the same
failure with more money on it.

## 6. The order, then

1. **Read the fulfillment drift diff** (section 3). Read-only, one command, and it decides
   whether the next step is a map or a recovery.
2. **Grant the catalog permissions** as a customer-managed policy on the deploy role.
3. **Bundle A `AddDimensions` + pricing terms.** The code is live and tested; this is the
   cheapest revenue on the list.
4. **Then Bundle B**: `BUNDLE_B_DIMENSION_NAMES` and `is_bundle_b_call` mirroring Bundle A,
   a `BUNDLE_CONFIGS` entry with a `bundle_b_access` flag, and its own change set.

Steps 1 and 2 are prerequisites for both bundles, which is the argument for doing them now
rather than for doing Bundle B now.
