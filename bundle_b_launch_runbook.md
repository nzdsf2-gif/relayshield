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

---

## STEP 1 -- ANDREW RUNS THIS. ANDREW RUNS THIS. The catalog grant, once.

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
AWS_PROFILE=relayshield aws marketplace-catalog describe-change-set \
  --catalog AWSMarketplace --change-set-id PASTE_THE_ID_HERE --no-cli-pager
```
EXPECT: `Status` moves `PREPARING` -> `APPLYING` -> `SUCCEEDED`, and the entity id
appears. **That id is the product code.** Save it.
STOP IF: `FAILED` -- the `ErrorDetailList` names the field. Send it to me.

## STEP 6 -- ANDREW RUNS THIS. Set the product code on the Lambda.

Until this runs, every Bundle B branch in the code is inert and a subscriber would
resolve and be provisioned nothing.

```zsh
cd ~/dev/relayshield
read -r "BUNDLE_B_PRODUCT_CODE?Paste the Bundle B product code, then press Enter: "
AWS_PROFILE=relayshield aws lambda update-function-configuration \
  --function-name relayshield-bundle-fulfillment \
  --environment "Variables={BUNDLE_B_PRODUCT_CODE=$BUNDLE_B_PRODUCT_CODE}" \
  --no-cli-pager
```
**STOP. READ THIS BEFORE RUNNING IT.** `update-function-configuration` REPLACES the whole
environment block. If that function already carries `BUNDLE_D_PRODUCT_CODE` or
`BUNDLE_A_PRODUCT_CODE`, the command above **deletes them** and Bundles A and D stop
resolving. Read what is there first:

```zsh
AWS_PROFILE=relayshield aws lambda get-function-configuration \
  --function-name relayshield-bundle-fulfillment \
  --query 'Environment.Variables' --no-cli-pager
```
EXPECT: the existing variables. If there are any, send them to me and I will write the
full replacement block rather than you reconstructing it by hand. **This is the same
shape as a change set replacing a rate card: the API replaces, it does not merge.**

## STEP 7 -- ANDREW CLICKS THIS. Create the test offer.

Same workflow, `changeset: aws_marketplace/bundle_b_test_offer.json`, `mode: apply`,
`confirm: CREATE-NEW-PRODUCT`.

**It will refuse** unless the product id is supplied, which the workflow does not yet take
as an input -- so run this one locally instead:

```zsh
cd ~/dev/relayshield
read -r "PID?Paste the Bundle B product id, then press Enter: "
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/marketplace_submit_changeset.py \
  aws_marketplace/bundle_b_test_offer.json --product-id "$PID" \
  --apply --confirm CREATE-NEW-PRODUCT
```
EXPECT: `charge date : <today>` filled at send time, nine changes ending in
`ReleaseOffer`, then `SUBMITTED`.
STOP IF: `unsubstituted placeholder` -- the id did not reach it.

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

## STEP 9 -- ANDREW CLICKS THIS. Go public, once step 8 passes.

```zsh
cd ~/dev/relayshield
read -r "PID?Paste the Bundle B product id, then press Enter: "
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/marketplace_submit_changeset.py \
  aws_marketplace/bundle_b_go_public.json --product-id "$PID" \
  --apply --confirm CREATE-NEW-PRODUCT
```
EXPECT: one `UpdateVisibility` change, then `SUBMITTED`. **AWS reviews this one with a
human in the loop**, so it is not instant and it can come back with comments.

**Do not run step 9 before step 8 passes.** Public visibility is the thing that is hard to
take back, and the fulfillment verification is exactly what the review asks about.

---

## TWO THINGS THAT WILL BITE AND ARE WRITTEN DOWN RATHER THAN DISCOVERED

**`update-function-configuration` replaces the environment block.** Step 6 says so twice
because the failure is silent: Bundles A and D stop resolving and nothing errors until a
customer subscribes.

**AWS's own documentation could not be read from the container.**
`docs.aws.amazon.com` returned HTTP 000, which is the container's egress policy and not a
fact about AWS. **So the step-8 sequence is derived from `bundle_a_test_offer.json` --
our own artefact, which AWS accepted for Bundle A -- and not from their published
requirements.** That is strong evidence and it is not the same thing. If the visibility
review asks for something step 8 does not cover, that is the gap, and it is worth
reading their current SaaS validation page before step 9 rather than after.
