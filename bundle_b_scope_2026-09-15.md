# AWS Bundle B — scoped 2026-09-15

**This file replaces an earlier version of itself that was wrong.** That version said
Bundle A's dimensions had never been added to AWS. They had. Bundle A and Bundle D are
both live, on **two separate product entities**, which is the fact everything below rests
on. The correction and how I got it wrong are in section 5.

---

## 1. Bundle B is packaging, not a build

*Attack Surface & Supply Chain*, $100/mo minimum, five endpoints, all live and all
metered today:

| Endpoint | `/v1/metered/` | `/v1/payg/` | Price, read from the live tables |
|---|---|---|---|
| `supply-chain` | yes | yes | $0.10 |
| `asset-intel` | yes | — | $0.15 |
| `secret-scan` | yes | yes | $0.35 |
| `threat-actor` | yes | — | $0.30 |
| `session-risk` | yes | yes | $0.30 |

No endpoint needs writing. What is missing is an AWS product and four lines of gating.

## 2. Bundle B gets its OWN entity, and that makes it cheaper than it looked

    Bundle D   prod-kkvurtspreofy    Agentic Attack Surface
    Bundle A   prod-f5qkfsxlxs4qg    Core Identity Exposure
    Bundle B   a third entity, created by the change set below

`aws_marketplace/bundle_a_*.json` is the exact template, in four artefacts:
`create_entity` (CreateProduct, UpdateInformation, UpdateTargeting, AddDeliveryOptions,
AddDimensions), `test_offer` (pricing terms), `go_public` (UpdateVisibility), and a
stale `add_dimensions` that targets Bundle D's entity from the abandoned
shared-entity plan.

**Two things I previously flagged as hazards do not apply, because the entity is new.**
There is no rate card to replace, so the 2026-07-27 placeholder failure is not reachable
here; and the one-change-set-in-flight limit is per entity, so Bundle B does not queue
behind anything on Bundle A or D.

**CLAUDE ALREADY DID THIS: `aws_marketplace/bundle_b_create_entity.json` is written.**
Built by reading Bundle A's change set rather than retyping its envelope, so the shape
AWS already accepted is preserved. Six dimensions (one Entitled monthly minimum plus five
ExternallyMetered), full usage instructions for all five endpoints, listing copy that
names its sources and quotes no corpus count.

`test_bundle_b_changeset.py`, six guards, all green:

- no corpus count, matched as a SHAPE rather than as today's stale figures;
- the sources ARE named, so the doctrine reads as a differentiator and not an omission;
- no external payment route anywhere in the copy, and the usage instructions say outright
  that AWS handles billing -- the Tier-1 clause that failed Bundle D's visibility request
  twice;
- every endpoint has a dimension and every dimension has an endpoint;
- exactly one Entitled dimension, because dropping it drops the monthly minimum;
- every change targets the product this change set CREATES, never an existing entity.

## 3. What is still to do, in order

1. **Read the fulfillment drift diff.** Section 4. Read-only, one command.
2. **Grant the catalog permissions.** Section 4.
3. **Submit `bundle_b_create_entity.json`**, then build `bundle_b_test_offer.json` from
   Bundle A's, with the five prices in section 1 and a $100/mo minimum.
4. **The code**, three small edits mirroring Bundle A exactly:
   - `BUNDLE_B_DIMENSION_NAMES` and `is_bundle_b_call` in `relayshield_api.py` (mapped in
     both the deployer and the drift check, so this one is safe to write today);
   - `BUNDLE_B_PRODUCT_CODE`, its entry in `PRODUCT_CODES`, and an
     `attack_surface_bundle_access` entry in `BUNDLE_CONFIGS` with a `bundle_b_access`
     flag -- all in `relayshield_bundle_fulfillment.py`, which is what step 1 gates.
5. **`bundle_b_go_public.json`**, with the entity id typed by hand after creation.

## 4. The two real blockers, both verified rather than recalled

**The fulfillment Lambda is in NO deploy map and NO drift check.**
`relayshield_bundle_fulfillment.py` holds `BUNDLE_CONFIGS` and `PRODUCT_CODES`, so two of
step 4's edits land there. It is in neither `deploy_lambdas.yml` nor
`lambda_drift_check.yml`: source in the repo, live traffic from every bundle subscriber,
no deploy path, no drift detection. **Seventh instance of that combination**, and the last
one had grown 700 lines including two Stripe revenue doors that a repo-sourced deploy
would have deleted with no error anywhere.

**CLAUDE ALREADY DID THIS:** added it to the drift check, watch only, deliberately not to
the deployer. The function name in the map is a guess from the filename convention and is
labelled UNVERIFIED; UNREADABLE means the name is wrong, not the entry.

**ANDREW RUNS THIS.** Read-only: it lists functions, downloads a package and diffs.

```zsh
cd ~/dev/relayshield
git checkout main
git --no-pager fetch origin claude/great-ritchie-6b8adu
git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap
git stash push --include-untracked -m "pre-merge untracked"
git -c pull.rebase=false merge --no-edit FETCH_HEAD
sh tools/handler_drift.sh relayshield_bundle_fulfillment.py
```
EXPECT: the resolved function name, then either *live is byte-identical to commit X* --
the stale case, safe, map it in the deployer -- or a list of live-only content, which is
recovered with `recover_live_handler.yml` first, exactly as developer-signup was.
STOP IF: the merge conflicts in **only CLAUDE.md** -- expected, keep both sides. A
conflict in a `.py` or a workflow is different; send me the filename.

**The role has no catalog permissions.** Read out of
`iam/snapshots/relayshield-breach-check-role-1sapnwdl.json` directly: `MeterUsage` and
`ResolveCustomer` are present, `DescribeEntity`, `ListEntities` and `StartChangeSet` are
all absent. So `StartChangeSet` fails before it reaches AWS's validator. That grant is an
IAM change on a role carrying 26 inline policies at 10,127 of 10,240 bytes with 11 of 10
managed slots used, so it is a customer-managed policy on a role already over the cap.

## 5. THE CORRECTION, and what produced it

I wrote that Bundle A had never had its dimensions added, and offered a recommendation to
do Bundle A before Bundle B on that basis. Andrew corrected it. Two mistakes, both
recorded shapes in this repo:

**I read the wrong entity.** The DescribeEntity capture in CLAUDE.md is of
`prod-kkvurtspreofy`, which is Bundle D's product. Bundle A lives on
`prod-f5qkfsxlxs4qg`. Its six dimensions were never going to appear in a capture of a
different product, and I read their absence as evidence. That is "a guard is only as good
as where it got its expectations", one directory over.

**And I read a July plan as current status.** `TODO.md` item 33 describes Bundle A as
dimensions on Bundle D's entity, which is what `bundle_a_add_dimensions.json` still
targets. That plan was abandoned in favour of a separate product.
`bundle_a_go_public.json` names the new entity id on its own first lines, and I did not
open it. This file's own rule is that a doc recording an open item is a LEAD, not a fact,
and the one file that would have settled it was sitting in the same directory as the one
I did read.

**The check that costs nothing and would have caught it: when a repo holds more than one
product entity, any claim about a product names the entity id it was read from.** There
are two live entities and there is about to be a third.
