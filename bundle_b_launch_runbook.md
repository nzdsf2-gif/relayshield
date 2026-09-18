# Bundle B: from a written change set to a public listing

**Written 2026-09-17, after the drift read came back clean.** Everything here is one
ordered sequence. Each step names WHO does it and what its success looks like, because
three of the nine cannot be done from a container and two of those are irreversible.

## THE ANSWER TO "CAN YOU PUBLISH IT REMOTELY": NO, AND THE TWO REASONS ARE DIFFERENT

**1. The catalog grant has never been applied.** `relayshield-github-deploy` has
`MeterUsage` and `ResolveCustomer` and lacks `StartChangeSet`. The grant is
`tools/apply_marketplace_catalog_policy.sh`, which is operator-side and once, **because
a role cannot widen its own permissions.** That is IAM working correctly, not a gap, and
it means no amount of automation can bootstrap it.

**2. Workflow dispatch returns 403 for me.** Every workflow run in this repo is a click.

**So two of the steps below are yours by construction.** What was mine is the part that
did not exist at all, and it is done.

## WHAT I FOUND AND FIXED, BECAUSE IT CHANGES WHAT "READY" MEANT

**There was no route to submit this change set.** `bundle_b_create_entity.json` has been
written and guarded by six tests since 2026-09-15, and the only submitter in the repo,
`tools/marketplace_add_dimension.py`, is hardcoded to `BUNDLE_D_ENTITY_ID =
prod-kkvurtspreofy`. It reads that live entity and builds a dimension change set FROM the
capture, so it cannot send a `CreateProduct`, which by definition names no entity because
AWS assigns the id.

The artefact was real, every test passed, and the submission had no door. That is "a
route added to the handler's dispatch table is not a route", one layer out.

**Built this session:** `tools/marketplace_submit_changeset.py`,
`.github/workflows/marketplace_changeset.yml`, `aws_marketplace/bundle_b_test_offer.json`,
`aws_marketplace/bundle_b_go_public.json`, the Bundle B gating in `relayshield_api.py` and
`relayshield_bundle_fulfillment.py`, and 27 tests. Six defects were reintroduced to prove
the guards fire.

---

## WHO DOES WHAT. ONE TERMINAL COMMAND IS LEFT, AND THE REST ARE CLICKS.

**Rewritten 2026-09-18 after the founder asked why he was slogging through ten terminal
steps.** He was right and the answer was not "you have to". Everything that is an AWS
API call can run in Actions, which holds `relayshield-github-deploy` through OIDC; what
was left in his terminal was there because nobody had moved it.

| # | What | Who | How |
|---|---|---|---|
| 1 | Catalog grant | **ANDREW, TERMINAL** | the only one, and it cannot be automated |
| 4 | Dry run the change set | ANDREW CLICKS | Actions, Marketplace Change Set |
| 5 | Create the product | ANDREW CLICKS | same workflow, `apply` |
| 6 | Set `BUNDLE_B_PRODUCT_CODE` | ANDREW CLICKS | Actions, Set one Lambda env var |
| 7 | Create the test offer | ANDREW CLICKS | Marketplace Change Set, `product_id` filled |
| 8 | E2E subscription | **ANDREW, BROWSER** | a real subscription is the point of it |
| 9 | Go public | ANDREW CLICKS | Marketplace Change Set |

**STEP 1 IS OPERATOR-SIDE BY CONSTRUCTION AND NO TOOLING CHANGES THAT.** A role cannot
widen its own permissions, so the first catalog grant to `relayshield-github-deploy`
cannot be made by anything running as `relayshield-github-deploy`. That is IAM working
correctly. Workflow dispatch is separately 403 for me, so the clicks are his too -- but a
click with the fields filled in is not a command to check, paste and diagnose.

**Steps 2 and 3 are done.** The merge landed, run 156 deployed all three functions, and
the invoke grant is the outstanding half of that.

---

## WHERE YOU ARE NOW, 2026-09-18. STEPS 2 AND 3 ARE ALREADY DONE.

You ran the merge and the push on 2026-09-17/18. `origin/main` is at `622fa03` and
deploy_lambdas run **156 DEPLOYED BOTH FUNCTIONS** -- the red is the import probe being
refused `lambda:InvokeFunction`, which the run's own annotation says in those words.
**Nothing is broken and nothing needs rolling back.**

What is outstanding from the first three steps is the grant that should have run between
them, and it is one command now that your clone carries the ARN:

```zsh
cd ~/dev/relayshield
git --no-pager log --oneline -1
sh tools/apply_deploy_invoke_policy.sh
```
EXPECT: `622fa03` on the first line, then account `239677749008`, the
`relayshield-bundle-fulfillment` ARN added, and `allowed` from
`simulate-principal-policy`.
STOP IF: the first line is NOT `622fa03` -- the merge is not in your clone and the JSON
has no ARN to push. Run STEP 2 below first.
STOP IF: `REFUSING: expected 239677749008` -- re-run with `AWS_PROFILE=relayshield`.

**There is nothing to re-deploy after it.** The code is live; the next deploy that
touches either file probes cleanly. **Then go to STEP 1**, the catalog grant, which is
the one that actually blocks Bundle B.

### AND STEP 6 WAS RUN OUT OF ORDER ON 2026-09-18. READ THIS BEFORE ANYTHING ELSE.

`BUNDLE_B_PRODUCT_CODE` was set to `622fa036203fb4ea59ea180be6d4570757ec755e`, which is
**this session's git commit SHA, not a product code.** Steps 4 and 5 had not run, so no
Bundle B product exists and no code had been assigned. The value is wrong and the write
also REPLACED the whole environment block, so anything else that was in it is gone.

Do not write to that block again until STEP 6 below has been run and read. It is
read-only and it is the first thing to do.

---

## STEP 1 -- ANDREW RUNS THIS. The catalog grant, once.

```zsh
cd ~/dev/relayshield
sh tools/apply_marketplace_catalog_policy.sh
```
EXPECT: it creates or updates one customer-managed policy, attaches it to
`relayshield-github-deploy`, then proves it with `simulate-principal-policy` against the
ROLE. The last lines should show `allowed` for `StartChangeSet` and `DescribeEntity`.
STOP IF: `REFUSING: expected 239677749008` -- you are on the pre-audit profile. Re-run
with `AWS_PROFILE=relayshield`.

## STEP 2 -- ANDREW RUNS THIS. Merge, and grant the deploy role the invoke it needs.

**THE ORDER OF THESE TWO IS LOAD-BEARING AND THE FIRST VERSION OF THIS RUNBOOK HAD IT
BACKWARDS, WHICH COST A RED RUN ON 2026-09-18.** `apply_deploy_invoke_policy.sh` pushes
`iam_github_deploy_invoke.json` **out of your clone** to AWS, and that file gains the
`relayshield-bundle-fulfillment` ARN only through the merge. Applying it first sends AWS
a policy without the new ARN, so the deploy that follows goes red on the import probe --
run 134's shape, for the fourth time, guaranteed by the instruction rather than by luck.

So: merge, which puts the ARN in the file, and grant from the same block on the same
success. The push is STEP 3, deliberately, so the grant is live in AWS before any deploy
fires.

```zsh
cd ~/dev/relayshield
git checkout main
git --no-pager fetch origin main claude/tender-planck-cb2qrx
git --no-pager log --oneline origin/main..main
git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap
git stash push --include-untracked -m "pre-merge untracked"
git -c pull.rebase=false merge --no-edit origin/claude/tender-planck-cb2qrx && sh tools/apply_deploy_invoke_policy.sh
```
EXPECT: the log line prints nothing, then a fast-forward, then the grant script printing
account `239677749008`, the ARN added, and `simulate-principal-policy` showing `allowed`.
STOP IF: `CONFLICT`. The grant is skipped by design, because a conflicted tree has no
reliable copy of that JSON. CLAUDE.md alone is expected and is `git checkout --merge
CLAUDE.md`, keep both sides, `git commit --no-edit`, then re-run the grant on its own. A
`.py` or a workflow is two sessions in one file -- send me the filename.
STOP IF: `REFUSING: expected 239677749008` -- re-run with `AWS_PROFILE=relayshield`.

## STEP 3 -- ANDREW RUNS THIS. Push, which deploys the code.

The Bundle B code is INERT until `BUNDLE_B_PRODUCT_CODE` is set, by construction, so it
is safe to ship before the product exists. That is the whole reason it can go first.

```zsh
cd ~/dev/relayshield
git push origin main
```
EXPECT: a push, then a green `deploy_lambdas` run in Actions.
STOP IF: the run is RED on `WAS DEPLOYED. Only the probe was denied` -- the code IS live
and nothing needs rolling back. It means step 2's grant did not run or did not take. Run
`sh tools/apply_deploy_invoke_policy.sh` on its own; the next deploy probes cleanly and
there is nothing to re-deploy.

**This deploy ships `relayshield-api` AND `relayshield-bundle-fulfillment`.** The second
one has never had a deploy path before today; its drift read this morning came back
byte-identical to main, which is what made mapping it safe.

## STEP 4 -- ANDREW CLICKS THIS. Dry run the change set. Read it.

Actions, **Marketplace Change Set**, Run workflow:

| Field | Value |
|---|---|
| changeset | `aws_marketplace/bundle_b_create_entity.json` |
| mode | `dry-run` |
| confirm | leave empty |

EXPECT: five changes, `CreateProduct` first, then six dimensions --
`attack_surface_bundle_access` as `Entitled` and five `ExternallyMetered`. **Read those
six names.** They are the rate card; nothing after this step changes them cheaply.
STOP IF: `AccessDeniedException` -- step 1 did not take.

## STEP 5 -- ANDREW CLICKS THIS. Create the product. IRREVERSIBLE.

Same workflow, `mode: apply`, `confirm: CREATE-NEW-PRODUCT` typed by hand.

EXPECT: `SUBMITTED` plus a `ChangeSetId`. AWS reviews asynchronously, so the product does
not exist the moment this returns. Watch it:

```zsh
read -r "CSID?Paste the ChangeSetId, then press Enter: "
AWS_PROFILE=relayshield aws marketplace-catalog describe-change-set \
  --catalog AWSMarketplace --change-set-id "$CSID" --no-cli-pager
```
EXPECT: `Status` moves `PREPARING` -> `APPLYING` -> `SUCCEEDED`, and the entity id
appears. **That id is the product code.** Save it.
STOP IF: `FAILED` -- the `ErrorDetailList` names the field. Send it to me.

## STEP 6 -- ANDREW CLICKS THIS. Set the product code. No terminal, no paste.

**This step used to be a pasted `update-function-configuration` and that is what went
wrong on 2026-09-18.** `--environment` REPLACES the whole variables block rather than
merging, so one key set by hand left the function holding only that key, with a success
block on screen. The fix is not a more careful command.

`tools/lambda_env_merge.py` GETs the block, merges the one key, and **refuses to write a
result that drops a key**. It also refuses a 40-character hex value for anything ending
`_PRODUCT_CODE`, because that is a git commit SHA and it is exactly what got pasted.

Actions, **Set one Lambda env var (merge, never replace)**, Run workflow:

| Field | Value |
|---|---|
| function | `relayshield-bundle-fulfillment` |
| key | `BUNDLE_B_PRODUCT_CODE` |
| value | the product id from STEP 5, and nothing else |
| mode | `plan` first |

EXPECT: a `before:`, an `after:` and a `preserved:` line. Non-product values print as
`<redacted>` -- these blocks carry live secrets and a full dump would put them in a run
log anyone with repo read access can fetch.
**Read `preserved:`. Every key that was there must be listed.** Then re-run with
`mode: apply`.
STOP IF: `REFUSED: ... git commit SHA` -- the value is not a product code and STEP 5 has
not produced one yet.
STOP IF: `AccessDenied` on `UpdateFunctionConfiguration` -- the deploy role lacks that
action. Section 5 of `tools/diagnose_bundle_fulfillment_env.sh` says so in advance; tell
me and I will send the one-line grant.

**If the block is missing `BUNDLE_D_PRODUCT_CODE` or `BUNDLE_A_PRODUCT_CODE`**, set each
the same way, one run per key. The tool merges, so order does not matter and nothing is
lost between runs. Section 4 of the diagnostic reads those values off
`relayshield-api` and `relayshield-agentic-api`, which this incident never touched.

## STEP 7 -- ANDREW CLICKS THIS. Create the test offer.

Actions, **Marketplace Change Set**, Run workflow:

| Field | Value |
|---|---|
| changeset | `aws_marketplace/bundle_b_test_offer.json` |
| mode | `dry-run` first, then `apply` |
| confirm | `CREATE-NEW-PRODUCT`, for apply only |
| product_id | the Bundle B product id from STEP 5 |

EXPECT: `charge date : <today>` filled at send time, nine changes ending in
`ReleaseOffer`, then `SUBMITTED` on apply.
STOP IF: `unsubstituted placeholder` -- `product_id` was left empty.

**What this offer is.** A private offer targeted at buyer account `442429445748`, granting
the Entitled dimension once and pricing all five metered dimensions at `0.00000001` -- free
in practice and **non-zero on purpose**, so `BatchMeterUsage` is genuinely exercised rather
than skipped. It is Bundle A's accepted envelope with four fields changed.

---

## STEP 8 -- ANDREW DOES THIS. The E2E fulfillment test AWS requires.

**This is the step the auditors care about, and it is a real subscription, not a
simulation.** You subscribe to your own Limited product through the offer from step 7 and
prove the whole path works before asking for public visibility.

1. **Sign in to the AWS console as the BUYER account** (`442429445748`, not the seller
   account). The offer is targeted at it and invisible to anything else.
2. **Open the private offer and subscribe.** AWS redirects you to the product's
   fulfillment URL with an `x-amzn-marketplace-token` in a POST body.
3. **You should land on the RelayShield registration page** and receive the Bundle B
   key. That single redirect exercises `ResolveCustomer`, `GetEntitlements` and the
   `attack_surface_bundle_access` branch of `BUNDLE_CONFIGS`.
4. **Make one call against each of the five endpoints** with the key you were issued:
   `/v1/metered/supply-chain`, `/v1/metered/asset-intel`, `/v1/metered/secret-scan`,
   `/v1/metered/threat-actor`, `/v1/metered/session-risk`.

**Then confirm it, rather than assuming it.** Four things, and each has a different
failure:

```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield aws logs filter-log-events \
  --log-group-name /aws/lambda/relayshield-bundle-fulfillment \
  --start-time $(( ($(date +%s) - 3600) * 1000 )) \
  --filter-pattern "resolve_customer" --no-cli-pager \
  --query 'events[*].message' --output text
```
EXPECT: a `resolve_customer` line naming the Bundle B product code.
STOP IF: nothing -- the subscription never reached our handler, which is a fulfillment URL
problem and not a code problem.

```zsh
AWS_PROFILE=relayshield aws logs filter-log-events \
  --log-group-name /aws/lambda/relayshield-api \
  --start-time $(( ($(date +%s) - 3600) * 1000 )) \
  --filter-pattern "BatchMeterUsage" --no-cli-pager \
  --query 'events[*].message' --output text
```
EXPECT: five accepted meter records, one per endpoint.
STOP IF: `InvalidUsageDimension` -- the dimension key in the code and the one on the
product disagree. `test_bundle_b_gating.py` asserts they cannot, so this would mean the
deployed code is older than the change set: check `LastModified` on `relayshield-api`.
STOP IF: `402` in the API log instead -- the 402 gate does not recognise the key, which
means `bundle_b_access` was never written onto the key record in step 3 of the flow.

**Nothing about metered usage is billed at a meaningful amount here**: five calls at
`0.00000001` is a fraction of a cent, which is the point of the test offer's pricing.

## STEP 9 -- ANDREW CLICKS THIS. Go public, once STEP 8 passes.

Actions, **Marketplace Change Set**, Run workflow:

| Field | Value |
|---|---|
| changeset | `aws_marketplace/bundle_b_go_public.json` |
| mode | `dry-run` first, then `apply` |
| confirm | `CREATE-NEW-PRODUCT` |
| product_id | the Bundle B product id |

EXPECT: one `UpdateVisibility` change, then `SUBMITTED`. **AWS reviews this one with a
human in the loop**, so it is not instant and it can come back with comments.

**Do not run STEP 9 before STEP 8 passes.** Public visibility is the thing that is hard to
take back, and the fulfillment verification is exactly what the review asks about.

---
