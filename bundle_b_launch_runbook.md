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

**Added 2026-09-18, after "Running GH Action in Step 5 doesn't make it obvious" what to
type into step 6:** STEP 5b. Turning a step into a click without giving the reader a way
to read its RESULT back is half a step. `tools/marketplace_read_product.py` and
`.github/workflows/marketplace_read_product.yml` are that read -- and writing them found
that this runbook, `tools/marketplace_submit_changeset.py` and CLAUDE.md all said the
entity id IS the product code. It is not. See STEP 5b.

**Built 2026-09-17:** `tools/marketplace_submit_changeset.py`,
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
| 5b | **Read the product code back** | ANDREW CLICKS | Actions, Read a Marketplace product **(needs the merge first)** |
| 6 | Set `BUNDLE_B_PRODUCT_CODE` | ANDREW CLICKS | Actions, Set one Lambda env var |
| 7 | Create the test offer | ANDREW CLICKS | Marketplace Change Set, `product_id` filled |
| 8 | E2E subscription | **ANDREW, BROWSER** | a real subscription is the point of it |
| 9 | Go public | ANDREW CLICKS | Marketplace Change Set |

**A CLICK ON A NEW WORKFLOW IS NOT A CLICK UNTIL main CARRIES THE FILE.** Every entry above
except 5b is already on `origin/main` and appears in the Actions sidebar today. **Read a
Marketplace product** was written this session and is the one exception: GitHub dispatches a
workflow only from the DEFAULT BRANCH, so it is invisible until the merge. Checked rather than
assumed -- `git ls-tree origin/main .github/workflows/` names nineteen files and that is the
twentieth.

No test guards this, deliberately. A check demanding every named workflow be on main would fail
on every workflow the day it is written, which is the check that gets worked around rather than
obeyed. The note above is the guard.

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

## STEP 3b -- ANDREW RUNS THIS. Merge and push, BEFORE any click below.

**THIS STEP EXISTS BECAUSE ITS ABSENCE COST FOUR CHANGE SETS.** A workflow dispatch runs
the DEFAULT BRANCH's copy of **every file it reads** -- the workflow, the tool, and the
change set JSON. A fix sitting on `claude/...` is not in the run. Change set
`dldmvatisooxdj8b7zll8q4a1` failed on 2026-09-19 with the SAME error as the one before
it, because the corrected document was on a branch and `main` still carried the five-change
version.

    cd ~/dev/relayshield
    git checkout main
    git --no-pager fetch origin claude/tender-planck-cb2qrx
    git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap
    git stash push --include-untracked -m "pre-merge untracked"
    git -c pull.rebase=false merge --no-edit FETCH_HEAD
    git push origin main
    python3 -c "import json;print(len(json.load(open('aws_marketplace/bundle_b_create_entity.json'))['ChangeSet']),'changes')"

EXPECT: the last line prints `13 changes`.
STOP IF: `Automatic merge failed` **in CLAUDE.md alone** -- expected, two sessions append
to it. `git checkout --merge CLAUDE.md`, delete the three marker lines keeping BOTH sides,
`git add CLAUDE.md`, `git commit --no-edit`, then push. A conflict in a `.py`, a `.json` or
a workflow is NOT that case: stop and send it to me.
STOP IF: it prints `5 changes` -- the merge did not bring the fix; do not click anything.

## STEP 4 -- ANDREW CLICKS THIS. Dry run the change set. Read it.

Actions, **Marketplace Change Set**, Run workflow:

| Field | Value |
|---|---|
| changeset | `aws_marketplace/bundle_b_create_entity.json` |
| mode | `dry-run` |
| confirm | leave empty |

**READ THE FIRST STEP OF THE RUN, `Which commit and which document`.** It prints the commit
the run is using and every `ChangeType` in the file. That is the only place a stale `main`
becomes visible before money and a review cycle are spent.

EXPECT, in this order:
- `changes : 13`. **Thirteen, not five.** A SaaS product is created by ONE change set
  carrying the product AND its offer; five was the document AWS refused twice.
- six dimensions -- `attack_surface_bundle_access` as `Entitled`, five `ExternallyMetered`.
  **Read those six names.** They are the rate card and nothing after this changes them cheaply.
- `pricing preflight:` with `OK` against all six.
- `media preflight:` `OK  HTTP 200`.
- `field sizes, against the change set AWS accepted` -- a table of every field in the
  document beside the longest value AWS has ever taken from us in that same field.
  Three lines read `OVER`, all of them by one or two characters on a dimension KEY or a
  search keyword, and all three are deliberate: a key cannot be shortened without
  changing what the API meters. Nothing else may be OVER.

STOP IF: `changes : 5` -- STEP 3b did not land. Do not run the apply.
STOP IF: any `UNPRICED` line -- send me the block; the apply would fail the same way again.
STOP IF: `REFUSED: field values over a limit AWS enforces` -- the run stops itself; send
me the block. It is reproducing AWS's own refusal in one second instead of fifteen.
STOP IF: an `OVER` line naming anything that is not a Key or a SearchKeyword -- send it.
STOP IF: `AccessDeniedException` -- step 1 did not take.

## STEP 5 -- ANDREW CLICKS THIS. Create the product. IRREVERSIBLE.

Same workflow, `mode: apply`, `confirm: CREATE-NEW-PRODUCT` typed by hand.
**Only after STEP 4 printed `changes : 13` and both preflights OK.**

EXPECT: `SUBMITTED` plus a `ChangeSetId`, 25 lowercase alphanumerics, printed by the Apply
step itself. The 40-hex string in the run page HEADER is the git commit, not the id.
AWS reviews asynchronously, so the product does not exist the moment this returns. Take
that id to STEP 5b.
STOP IF: `AccessDeniedException` -- step 1 did not take.

## STEP 5 HAS FAILED FIVE TIMES. FOUR DEFECTS, AND EACH ONE NOW HAS A PREFLIGHT.

Change set `de0zvpnvpcq3olta3y7kpx4p2` came back **FAILED**, so **no Bundle B product exists, no
product code exists, and the Marketplace Management Portal correctly lists three SaaS products.**

    INVALID_MEDIA_LOCATION Media location not accessible:
    .../bundle_b/relayshield_logo_bundle_b.png

**That object was never uploaded.** `bundle_a/relayshield_logo_bundle_a.png` returns 200 and the
`bundle_b` path returns 403, which on a public S3 bucket means absent rather than forbidden. The
change set now points at Bundle A's object -- the generic RelayShield shield mark, no
bundle-specific text in it, checked by downloading it.

**`tools/marketplace_submit_changeset.py` now HEADs every media URL before submitting**, so a dry
run catches this in one second instead of AWS catching it in fifteen. **Re-run STEP 4 first**: the
dry run prints a `media preflight:` block and `OK HTTP 200` is the line to look for. Then STEP 5
again, which produces a NEW ChangeSetId for STEP 5b.

**Nothing was created, so nothing needs undoing.** A failed change set leaves no entity.

**SECOND FAILURE, `17or75a96xofiu7gic33wjrm6`, read from the STEP 5b run rather than
reported.** The logo was fixed and the media preflight passed; the change set failed on a
different field:

    Status : FAILED
    Error  : INVALID_INPUT When adding dimensions for SaaS products, you must also
             set pricing for usage dimensions.

**The document carried FIVE changes. Bundle A's accepted one carries THIRTEEN.** I built
Bundle B by reusing Bundle A's envelope and stopped reading at `AddDimensions`, so the
whole offer half -- `ReleaseProduct`, `CreateOffer`, the offer's information, **pricing**,
legal, support and renewal terms, and `ReleaseOffer` -- was simply absent. Six guards were
green because every one of them read the document that existed rather than asking what a
complete one looks like.

**Fixed, and the prices are read out of the code rather than typed:** the per-call rate
card is derived from `BUNDLE_B_DIMENSION_NAMES` and `METERED_CREDIT_COSTS` in
`relayshield_api.py` (supply-chain $0.10, asset-intel $0.15, secret-scan $0.35,
threat-actor $0.30, session-risk $0.30) and the monthly minimum is the $100 that file's own
Bundle B comment records. A test fails if the listing and the biller ever disagree.

**And the submitter now reproduces AWS's refusal locally, in the dry run, in one second.**
The STEP 4 dry run prints a `pricing preflight:` block; every dimension must read `OK`.

**THE EARLIER RE-RUN, for the record**, 2026-09-18 19:06 and 19:09 UTC, both green and
read from the run logs rather than reported:

    run #5  19:06:54Z   Dry run: success    Apply: skipped
    run #6  19:08:52Z   Dry run: skipped    Apply: success

Both printed the new preflight block, which is the guard doing its job on the real document:

    media preflight:
      OK       HTTP 200   ChangeSet[1].DetailsDocument.LogoUrl = .../bundle_a/relayshield_logo_bundle_a.png

**The apply submitted `17or75a96xofiu7gic33wjrm6`, which FAILED on pricing.**

**AND `dldmvatisooxdj8b7zll8q4a1`, the fourth, failed with the IDENTICAL error** -- because
the pricing fix was on a branch and the workflow checks out `main`. Nothing was wrong with
the fix and nothing was wrong with the click. **STEP 3b above is the missing step**, and the
dry run now prints the commit and the change count so a stale `main` is visible in one line
rather than fifteen seconds later in an AWS refusal. Do not read either of those two ids
again; the next apply produces a new one.

**THE 40-HEX STRING ON THE RUN PAGE IS THE GIT COMMIT, NOT THE CHANGE SET.** GitHub prints
`a7067bd2c5e70b0318c9b7f327ddeb13568b778c` in the run header because that is the commit the
workflow ran; the ChangeSetId is 25 lowercase alphanumerics and is only in the job's output.
Offered as a marketplace identifier twice now, once for the product code and once for this, and
both times because the value the reader actually needed was buried in a log while a
plausible-looking one was on screen.

## THE FIFTH FAILURE, `em3sw5gs00lifcmy42mxe95t9`, AND WHAT ENDED THE PATTERN

    INVALID_INPUT Remove invalid key 'supply_chain_calls' with types
    '[Metered, ExternallyMetered]'. Valid descriptions cannot exceed more
    than 90 characters.

Four of six dimension descriptions were over: 93, 109, 92, 93. The run listed all thirteen
changes and both preflights passed, so STEP 3b and the pricing fix had both landed -- this
was a fourth, separate validation.

**The defect was not any of the four. It was fixing one constraint per round.** Every check
we had read the document that existed. None asked whether it was within the range of the
one document AWS has actually accepted from us.

**Bundle A's create set is now the reference, for every field rather than for its envelope.**
The dry run prints each field beside the longest value AWS took in that same field, and the
90-character ceiling -- the only one we have MEASURED -- blocks. The four descriptions were
shortened to 78, 75, 86, 82 and 86; nothing else in the document is now longer than the
accepted example except three keys that cannot change without changing what the API meters.

**Measured while doing it, and worth knowing before anyone edits this file:** Bundle B's
change set and Bundle A's accepted one have the IDENTICAL field structure -- same changes,
same keys, all the way down. A test fails if that stops being true in either direction.

## THE PRODUCT EXISTS. `prod-szi2wdww3obry`, CREATED 2026-09-19 BY `27vgy6fh2q7uke1ddtxa0w1l3`.

    Status : SUCCEEDED
    CreateProduct : prod-szi2wdww3obry@1
    CreateOffer   : offer-tphmeebmexqp2@1      all thirteen changes applied

**The red run was MY TOOL, one line after the product was created**, and the two halves of
that output say opposite things while both being true -- a GREEN step and a RED step in one
job, which is "a red run names a step, not an outcome" in the direction that matters here.

    ValidationException: [Requested entity id 'prod-szi2wdww3obry@1' is invalid.
    It should match with ^[a-zA-Z0-9][.a-zA-Z0-9/-]+[a-zA-Z0-9$.]

**DescribeChangeSet reports the entity REVISION (`@1`). DescribeEntity refuses it.** One
product, two identifiers, one character apart, and the message reads as "the product is
invalid" when the product is fine and the REQUEST was malformed. Stripped now, with the
call site asserted by `ast` rather than the helper's existence.

### THE PRODUCT CODE IS NOT A BLOCKER, AND STEP 6 MOVES AFTER STEP 8

Read from `relayshield_bundle_fulfillment.py` rather than assumed, and it changes the order
of the rest of this runbook:

* **`BUNDLE_CONFIGS` is keyed on the entitlement DIMENSION** (`attack_surface_bundle_access`),
  not on the product code. `_resolve_bundle` looks up that dimension and nothing else.
* **`ResolveCustomer` RETURNS the product code** at fulfillment time, and `_get_entitlement`
  is called with that value, so `GetEntitlements` queries the right product whatever the
  env var says.
* **The mismatch guard requires BOTH sides non-empty** -- `if product_code and
  config.get("product_code") and ...` -- so an empty `BUNDLE_B_PRODUCT_CODE` SKIPS it rather
  than tripping it.

So the E2E subscription works with the variable unset, and **the subscription is what tells
us the code**, in one CloudWatch line:

    Product code not recognised: got <THE CODE>, known ['<bundle D>', '<bundle A>']

**Set the env var from that line, AFTER the test.** Hunting for it first is a round spent on
a value the next step hands over, and it was the step that produced a git SHA in a product
code field two days ago.

## STEP 5b -- ANDREW CLICKS THIS. Read the result. This is the step that tells you what to type next.

**THE MERGE IS A PREREQUISITE FOR THIS STEP AND I SHIPPED IT WITHOUT SAYING SO.** Reported as
*"Step 5b says 'read a marketplace product' which doesn't literally exist"* -- correct, it was
not in the sidebar, because **a workflow file that is not on the DEFAULT BRANCH cannot be
dispatched from the Actions UI.** This file already records that edge from the Mini App deploy
and I wrote a click against a workflow living on a branch anyway. Merge and push main first;
the entry appears immediately after.

Actions, **Read a Marketplace product (read only)**, Run workflow, `change_set_id` = the
id the STEP 5 apply printed. **`17or75a96xofiu7gic33wjrm6` is spent** -- it is the change
set that failed on pricing, and reading it again just reprints that failure.

No apply mode, no confirmation phrase, so re-run it as often as you like while AWS is still
working. **The workflow is on `origin/main` as of `a7067bd` and is in the sidebar now**, checked
with `git ls-tree origin/main .github/workflows/` rather than assumed.

**BOTH EARLIER CHANGE SETS FAILED**, `de0zvpnvpcq3olta3y7kpx4p2` on the logo and
`17or75a96xofiu7gic33wjrm6` on pricing -- see the section above. Both still proved STEP 1
took, because `StartChangeSet` returned rather than refusing. Read the id from the newest
apply, never one of those two.

**A GREEN `read` JOB DOES NOT MEAN A SUCCEEDED CHANGE SET.** The workflow succeeds whenever the
read completes; the change set's own `Status` line is the answer. Read that line, not the job's
tick.

**AND DISREGARD THE LAST THREE LINES OF THAT RUN'S OUTPUT.** They say *"That id is the product
code"*. It is not, and that text was corrected after the run executed. See the table below.

EXPECT: `Status : SUCCEEDED`, a `CreateProduct: prod-...` line, and a
**PRODUCT CODE CANDIDATES** section.
STOP IF: `Status : PREPARING` or `APPLYING` -- AWS is still working. Wait a few minutes and
re-run. The product does not exist until SUCCEEDED, so there is nothing to read yet.
STOP IF: `Status : FAILED` -- the error lines name the field. Send them to me.

**THE ENTITY ID IS NOT THE PRODUCT CODE, AND UNTIL 2026-09-18 THIS RUNBOOK SAID IT WAS.**
That was mine and it was wrong. They are different namespaces, and the evidence is in this
repo rather than in a doc I remembered:

| | Example | What takes it |
|---|---|---|
| entity id | `prod-kkvurtspreofy` | Catalog API. STEP 7 and STEP 9's `product_id` |
| product code | `46y72j0d99w7lyqkiqrakpc5k` | `ResolveCustomer`, `GetEntitlements`, `BatchMeterUsage`. **`BUNDLE_B_PRODUCT_CODE`** |

(`TODO.md:1707` and `relayshield_aws_marketplace.py:22` each record a real product code.
Note a change set id is the same 25-character shape, so read the label, never the shape.)

**If the candidates section says NONE**, that is a fact about `DescribeEntity` and not about
the product -- whether it carries the code is UNVERIFIED, because `docs.aws.amazon.com` is
egress-blocked from my container and the only capture in this repo is of an Offer. The
authoritative read is then one browser page:

**ANDREW CLICKS THIS:** <https://aws.amazon.com/marketplace/management/products/>, open the
Bundle B product, and read the product code off its page. It also appears at the end of the
SNS topic ARN AWS creates for the listing.

## STEP 6 IS NOW STEP 8b. IT MOVED, AND RUNNING IT HERE IS REFUSED BY DESIGN.

**2026-09-19: it was run here with the entity id, and `lambda_env_merge.py` refused it.**
The guard did its job -- an entity id in that field matches no key row, raises nothing, and
makes revocation scans over a live listing find nothing and report success. But the step
should not have been reachable yet, and leaving it numbered 6 in a numbered list is an
instruction to run it sixth, whatever the prose beside it says.

**THE VALUE DOES NOT EXIST UNTIL THE E2E SUBSCRIPTION RUNS**, and the subscription does not
need it. Read from `relayshield_bundle_fulfillment.py` rather than assumed:

* `BUNDLE_CONFIGS` is keyed on the entitlement DIMENSION (`attack_surface_bundle_access`),
  never on the product code, and `_resolve_bundle` looks up that dimension alone.
* `ResolveCustomer` RETURNS the product code at fulfillment, and `_get_entitlement` queries
  `GetEntitlements` with THAT value whatever the environment says.
* The mismatch guard needs BOTH sides non-empty (`if product_code and
  config.get("product_code")`), so an empty `BUNDLE_B_PRODUCT_CODE` SKIPS it.

So the order is **STEP 7, then STEP 8, then STEP 8b**. The subscription is what prints the
code, and it prints it in its own warning line. Skip to STEP 7.

## STEP 6b -- SETTLED 2026-09-19. NOTHING TO DO. The buyer account is yours.

**`442429445748` is `TestUser`, and the founder signed into it on 2026-09-19.** Confirmed by
looking at the AWS Marketplace console in that account, which is the only read that could settle
it. The number came across into Bundle B by reuse from Bundle A's accepted test offer and nothing
in this repo said whose account it was; that gap is closed here so no session spends a round on it
again.

**Its Private offers list reading `Available private offers (0)` is CORRECT and is not a fault.**
A private offer exists only after STEP 7 applies. Zero offers before STEP 7 is the expected state,
and reading it as a missing offer sends the reader to diagnose a change set that was never
submitted.

---

## STEP 7 -- ANDREW CLICKS THIS. Create the test offer.

Actions, **Marketplace Change Set**, Run workflow:

| Field | Value |
|---|---|
| changeset | `aws_marketplace/bundle_b_test_offer.json` |
| mode | `dry-run` first, then `apply` |
| confirm | `CREATE-NEW-PRODUCT`, for apply only |
| product_id | `prod-szi2wdww3obry` -- the entity id STEP 5 created |

EXPECT: `charge date : <today>` and `availability : ends <today + 90 days>`, both filled
at send time, nine changes ending in `ReleaseOffer`, then `SUBMITTED` on apply. Then two
`date : ok` lines; a `date : PAST` line is a refusal, not a warning.
STOP IF: `MISSING_AVAILABILITY_END_DATE` -- the `UpdateAvailability` change was dropped. A
private offer needs it or `ReleaseOffer` fails, which cost Bundle A a submission
(commit `e72cc31`). The change set carries it and a test asserts the sequence matches
Bundle A's accepted one.
STOP IF: `unsubstituted placeholder` -- `product_id` was left empty.
STOP IF: `REFUSED: ... targets a LIVE listing` -- a `prod-` id was typed that
belongs to Bundle A or Bundle D. Bundle B's is `prod-szi2wdww3obry`.

**What this offer is.** A private offer targeted at buyer account `442429445748`, granting
the Entitled dimension once and pricing all five metered dimensions at `0.00000001` -- free
in practice and **non-zero on purpose**, so `BatchMeterUsage` is genuinely exercised rather
than skipped. It is Bundle A's accepted envelope with four fields changed.

---

## STEP 8 -- DONE 2026-09-19 20:40 UTC. The offer was accepted and an agreement exists.

    Product   RelayShield - Attack Surface & Supply Chain API   prod-szi2wdww3obry
    Offer     442429445748 - TestUser - Bundle B Fulfillment Verification
              offer-a4jhoh7wgdz5g
    Agreement agmt-29l852u6kqzmjh2me0pglvj9q
    Buyer     442429445748 (TestUser)
    Term      2026-09-19 to 2026-10-19, purchase amount 0.01 USD

Confirmed by AWS Marketplace's own "Customer accepted an AWS Marketplace offer" email and by the
buyer account's Purchased offers list showing 1 of 1. **This is the evidence AWS's visibility
review asks for**, and it is a real subscription rather than a simulation.

**The one thing an acceptance does NOT prove is the fulfillment REDIRECT.** Accepting creates the
agreement; clicking through to the product's fulfillment URL is what posts
`x-amzn-marketplace-token` to `relayshield-bundle-fulfillment`, where `ResolveCustomer` runs and a
key is provisioned. If you did not land on a RelayShield registration page, that half has not run
and STEP 8b's log route has nothing to read -- use the portal route instead, which does not depend
on it.

---

## STEP 8b -- ANDREW CLICKS THIS. Set the product code. NOTHING TO MERGE FIRST.

**THERE IS NOTHING TO TYPE IN A TERMINAL IN THIS STEP.** It is a GitHub Actions form,
like steps 4, 5, 5b, 7 and 9. `tools/lambda_env_merge.py` is named below only because it
is what that workflow runs on the runner; **you never invoke it**, and an earlier version
of this step read as though you might.

**THE VALUE COMES OUT OF STEP 8, AND NOWHERE ELSE IS CHEAPER.** The subscription's own
CloudWatch line names it:

    Product code not recognised: got <THE CODE>, known ['<bundle D>', '<bundle A>']

That line is `relayshield_bundle_fulfillment.py` reporting a code it resolved and does not
recognise, which is exactly correct while this key is unset, and it is the authoritative
read: it is what `ResolveCustomer` returned for this product, not a value anybody typed.
It is a 20-30 character lowercase alphanumeric string with no `prod-` prefix.

**THAT LINE EXISTS ONLY IF THE FULFILLMENT REDIRECT RAN.** Accepting the offer creates the
agreement; it does not by itself POST a token to our handler. So if you accepted the offer and
never landed on a RelayShield registration page, there is no log line to read and the log route
is a dead end rather than a slow one.

**THE ROUTE THAT DOES NOT DEPEND ON IT: the AWS Marketplace Management Portal, SELLER side.**
Open the product page for `RelayShield - Attack Surface & Supply Chain API` and read the
**Product code** field. It is a distinct field from the Product ID -- the ID is
`prod-szi2wdww3obry` and the CODE is the 25-character string this step wants. The two real ones
already in this repo, for shape only, are `46y72j0d99w7lyqkiqrakpc5k` and
`5s4a96a1ui1a5efrom6udnm2g`. **Do not paste either of those**; they belong to other products.

Actions, **Set one Lambda env var (merge, never replace)**, Run workflow:

| Field | Value |
|---|---|
| function | `relayshield-bundle-fulfillment` |
| key | `BUNDLE_B_PRODUCT_CODE` |
| value | the **product code** from STEP 8's log line. Not the `prod-...` entity id |
| mode | `plan` first |

EXPECT: a `before:`, an `after:` and a `preserved:` line. Non-product values print as
`<redacted>` -- these blocks carry live secrets and a full dump would put them in a run
log anyone with repo read access can fetch.
**Read `preserved:`. Every key that was there must be listed.** Then re-run with
`mode: apply`.
STOP IF: `REFUSED: ... git commit SHA` -- that is the commit in the Actions page HEADER,
which is the most copyable 40-hex string on the screen and is never a product code.
STOP IF: `REFUSED: ... Catalog API ENTITY ID` -- that is `prod-szi2wdww3obry`, which STEP 7
and STEP 9 take and this field does not. The product code is in STEP 8's log, above.
**Why a workflow rather than a command, recorded so it is not undone:**
`aws lambda update-function-configuration --environment` REPLACES the whole variables
block rather than merging, so one key set by hand on 2026-09-18 left the function holding
only that key, with a success block on screen. The workflow GETs the block, merges the one
key, and **refuses to write a result that drops a key**. It also refuses a 40-character
hex value for anything ending `_PRODUCT_CODE` (that is a git commit SHA, and it is exactly
what got pasted) and a `prod-...` entity id (that is the Catalog API identifier, which
steps 7 and 9 want and this field does not).

STOP IF: `AccessDenied` on `UpdateFunctionConfiguration`. **THIS FIRED ON 2026-09-19.**
`plan` succeeded and `apply` failed, because `GetFunctionConfiguration` is granted to
`relayshield-github-deploy` and `UpdateFunctionConfiguration` is not. There are two routes
and they are not equivalent in cost:

**ROUTE A, the AWS console, and it needs no IAM change at all.** Lambda, function
`relayshield-bundle-fulfillment`, Configuration, Environment variables, Edit. **That page
is a merge by construction** -- it shows every existing row and you add one. The hazard
this whole step exists to avoid is a property of the `--environment` API parameter, not of
the console, and you are acting as yourself rather than as the deploy role, so no grant is
involved. Use this when the point is to be finished.

**ROUTE B, grant the role, so the workflow is not dead for the next key.**

    ANDREW RUNS THIS:
    cd ~/dev/relayshield
    sh tools/apply_lambda_env_policy.sh

EXPECT: both decisions in the table read `allowed`.
STOP IF: `REFUSING: expected 239677749008` -- the profile resolved to the pre-audit
account and nothing was written.
Then re-run the workflow's `apply`. Route B is worth doing whichever route sets this key,
because it is the difference between a workflow that works and one that fails every time.

### THE BLOCK LOST `BUNDLE_A_PRODUCT_CODE` AND `BUNDLE_D_PRODUCT_CODE` ON 2026-09-18

The plan run on 2026-09-19 printed `preserved: (none -- the block held only this key)`,
which is the measurement that settles it: **the hand-typed `--environment` write of
2026-09-18 did land, and it deleted both.**

**That is a live defect on two PUBLIC listings and it outranks Bundle B.** With those keys
unset, `PRODUCT_CODES` loses their entries, `_product_code_filter()` matches no existing
key row, and `_deactivate_api_key` finds nothing on an unsubscribe -- so **a cancelled
Bundle A or Bundle D customer keeps a working key**, silently, because a scan that matches
nothing and a customer with no keys are the same output.

Restore all three, one run per key (or all three rows at once in the console). The tool
merges, so order does not matter and nothing is lost between runs.

**READ THE VALUES, DO NOT TYPE THEM FROM MEMORY OR FROM THIS REPO.** Two product-code-shaped
strings in this repo (`46y72j0d99w7lyqkiqrakpc5k`, `5s4a96a1ui1a5efrom6udnm2g`) sit in
contexts that do not establish which product they belong to, and one of them is the TI
product rather than a bundle. A value pasted into this field wrongly produces no error and
breaks deactivation exactly as an empty one does.

    ANDREW RUNS THIS:
    cd ~/dev/relayshield
    AWS_PROFILE=relayshield sh tools/diagnose_bundle_fulfillment_env.sh

EXPECT: section 1 prints the block as it stands; **section 4 prints
`BUNDLE_D_PRODUCT_CODE` off `relayshield-api` and `relayshield-agentic-api`**, which this
incident never wrote to, so that value is recovered rather than guessed. Section 2 prints
any published version whose configuration is frozen -- if one exists it carries the whole
old block including Bundle A's.
STOP IF: section 4 shows `(not set)` on both functions and section 2 shows no versions.
Then the only remaining authoritative read is the Marketplace Management Portal product
page for each bundle, seller side, **Product code** field.

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
