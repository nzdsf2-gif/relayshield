<!-- Verbatim sections moved out of CLAUDE.md on 2026-10-18, original order. Not auto-loaded.
     Find one with: grep -n 'WORDS' docs/claude_memory/INDEX.md -->

## RUN 134'S SHAPE FOR THE FIFTH TIME, AND THIS ONE MY OWN RUNBOOK GUARANTEED

**2026-09-18, reported as "Bundle B deploy lambda in step 4 failed".** Read from the run
rather than from the screenshot, which is the half that settles it:

    ✅ relayshield-agentic-api deployed          imports cleanly
    ✅ relayshield-api deployed                  imports cleanly
    ✅ relayshield-bundle-fulfillment deployed   probe DENIED

    AccessDeniedException ... assumed-role/relayshield-github-deploy/GitHubActions
    is not authorized to perform: lambda:InvokeFunction on
    function:relayshield-bundle-fulfillment

**All three functions are live. Nothing needed rolling back.** The error message written
into the deployer after run 134 said so in those words, unprompted, which is that
message earning its place for the fourth time.

**THE NEW PART, AND IT IS WORSE THAN THE DEFECT: MY RUNBOOK ORDERED THE REMEDY SO IT
COULD NOT WORK.** `bundle_b_launch_runbook.md` shipped with

    STEP 2  sh tools/apply_deploy_invoke_policy.sh
    STEP 3  merge and push

and **that script pushes `iam_github_deploy_invoke.json` out of the CLONE**, which gains
the `relayshield-bundle-fulfillment` ARN only through the merge in step 3. So step 2 sends
AWS a policy without the new ARN and step 3 then deploys into a role that still cannot
invoke it. **The red run was not bad luck, it was arithmetic**, exactly like the
`git add -A` loop: the instruction re-created the condition that makes the next step fail.

And step 2 said in its own text *"without this the first deploy goes RED on the import
probe -- run 134's shape, for the fourth time"*. **I named the failure, wrote the remedy,
and ordered the two so the remedy could not reach it**, which is rule B ("predicting a
failure and shipping it anyway is worse than not predicting it") in its most expensive
form so far.

**THE ORDER, AND IT IS THREE PHASES RATHER THAN TWO.** The merge is what puts the ARN in
the file, the grant is what puts it in AWS, and the push is what fires the deploy:

    merge locally   -> the JSON now carries the ARN
    apply the grant -> AWS now carries it
    push            -> the deploy probes cleanly

The runbook now chains the first two on one `&&` so a CONFLICT skips the grant rather
than applying a half-merged file, and the push is its own step. **A grant that reads a
repo file is downstream of the merge, always** -- this is the repo-half/AWS-half split
that `apply_deploy_invoke_policy.sh` was written for, with the third term nobody had
written down: the repo half is not in the clone until the merge lands.

**Nothing here is testable from the container and pretending otherwise would be worse
than saying so.** `check_deploy_invoke_policy.py` already keeps `LAMBDA_MAP` and the JSON
honest and runs inside `test_workflows_parse.py`; whether AWS has the policy is
unknowable from here by construction. **The guard is the ordering in the runbook and this
section, and that is the honest scope.**

## I PUT A DESTRUCTIVE WRITE ABOVE ITS OWN WARNING, AND IT FIRED WITHIN THE HOUR

**2026-09-18, asked as "Step 6: Does this output look ok?"** No, twice over, and the
second one is mine.

    read -r "BUNDLE_B_PRODUCT_CODE?Paste the Bundle B product code..."
    Paste the Bundle B product code: 622fa036203fb4ea59ea180be6d4570757ec755e

**That is this session's git commit SHA.** No Bundle B product existed -- steps 4 and 5
had not run, and `StartChangeSet` is what makes AWS assign a code. The prompt asked for a
value that did not yet exist anywhere, so the most recent 40-hex string in the terminal
was the reasonable thing to reach for. **A prompt for a value the reader cannot possibly
have is rule 11's placeholder wearing a question mark**, exactly like the Cloudflare
account id answered with an email address two days earlier.

**AND THE COMMAND REPLACED THE WHOLE ENVIRONMENT BLOCK.** `update-function-configuration
--environment` does not merge. `relayshield_bundle_fulfillment.py` reads THREE product
codes, and the block now holds one. An emptied `BUNDLE_D_PRODUCT_CODE` raises nothing:
`PRODUCT_CODES` loses the entry, `_product_code_filter()` stops matching any existing key
row, and `_get_entitlement` queries `GetEntitlements` with the wrong set -- so revocation
and suspension scans over a LIVE PUBLIC listing find nothing and report success.

**MY RUNBOOK PUT THE WRITE FIRST AND THE WARNING UNDER IT**, opening
*"STOP. READ THIS BEFORE RUNNING IT"* -- below the fenced block it was warning about, with
the read-the-existing-block command below that. Rule C says in its own words that an
instruction writing to a live shared surface is PRECEDED by the one that reads it, two
blocks and never one. **I wrote the hazard down, correctly, underneath the thing that
causes it.** That is rule B again and it is the second ordering defect in this same
document in two turns: yesterday the grant was ordered before the merge that feeds it.

**THE RULE, and it is narrower than "read first" because that was already written down and
did not work: a block that writes is never in the same reply as the reasoning about
whether it is safe to write.** The read is its own step with its own EXPECT. The write
comes back in a later reply, built from what the read returned. Prose cannot enforce an
order inside a reply, because a fenced block under a heading is the thing a reader runs.

**AND `--environment` IS NOT ALONE.** The same replace-not-merge shape is a change set
against a rate card (which rolled Bundle D's prices to placeholders once), `put-role-policy`
against an inline policy, and `setMyCommands`. **Before any call whose argument is a whole
collection, ask what is in that collection now** -- and get the answer from the API, not
from the diff.

`tools/diagnose_bundle_fulfillment_env.sh` is the read, and it exists because Lambda keeps
no previous configuration for `$LATEST`: the old block survives only in a PUBLISHED VERSION
or in CLOUDTRAIL's `requestParameters.environment`, 90-day retention. It checks both, names
a refusal as a fact about the identity rather than about the function, and says outright
when neither can answer instead of printing nothing. All five branches were exercised
against a stand-in `aws`, because a diagnostic that has only been read is the defect it is
meant to catch.

## HE ASKED WHY HE WAS RUNNING TEN TERMINAL STEPS. THE ANSWER WAS NOT "YOU HAVE TO".

**2026-09-18: *"Rather than my wrestling with your runbook, why can't you deploy the bulk
of the remaining terminal commands in my place."*** He is right, and the honest count was
one terminal command, not ten.

**EVERY STEP IN THAT RUNBOOK THAT IS AN AWS API CALL CAN RUN IN ACTIONS**, which holds
`relayshield-github-deploy` through OIDC and has since `lambda_drift_check.yml` was
written. What was sitting in his terminal was there because nobody had moved it, which is
this file's own "I CANNOT REACH AWS IS A CLAIM ABOUT THIS CONTAINER" rule pointed at a
runbook instead of at a task: **the container's limits are not the reader's limits either.**

    STEP 1  catalog grant          TERMINAL, and genuinely cannot be automated
    STEP 4  dry run                click
    STEP 5  create the product     click
    STEP 6  set the env var        click  <- was the pasted command that broke things
    STEP 7  test offer             click  <- was terminal because MY workflow lacked an input
    STEP 8  E2E subscription       browser, and a real subscription is the point
    STEP 9  go public              click

**Only STEP 1 is structural.** A role cannot widen its own permissions, so the first
catalog grant to `relayshield-github-deploy` cannot be made by anything running as it.

**STEPS 7 AND 9 WERE TERMINAL FOR NO REASON AT ALL.** `marketplace_changeset.yml` had no
`product_id` input, so the runbook fell back to a pasted command carrying a `read -r`
prompt. One input added, and both became clicks. **A missing workflow input is a reason a
step is in someone's terminal, and it reads exactly like a step that has to be.**

### THE ENV WRITE IS A MERGE NOW, SO THE HAZARD IS GONE RATHER THAN DOCUMENTED

`tools/lambda_env_merge.py` GETs the variables block, merges one key, and **refuses to
write a result that drops a key**. It refuses a 40-character hex value for anything ending
`_PRODUCT_CODE`, which is the git SHA that was pasted, and it prints every non-product
value as `<redacted>` -- `deploy_lambdas.yml` learned that one expensively, its default
output having printed live secrets into a log anyone with repo read access can fetch.

**The general form, and it is the better version of "read before you write": when a write
is dangerous because it replaces a collection, the fix is a tool that reads and merges,
not a warning above the command.** A warning depends on the reader; a refusal does not.
Every branch was exercised against a stand-in `aws`.

### CLOUDTRAIL CANNOT ANSWER WHAT WAS IN A LAMBDA ENV BLOCK, AND `{}` IS NOT "EMPTY"

The diagnostic's CloudTrail section returned `{}` for both config writes. **AWS
deliberately omits Lambda environment variables from `requestParameters`, because they
routinely carry secrets.** So that section proves a write happened and when, and can never
carry values -- and my own reading guide had no row for `{}`, only for "empty", which is a
different answer with a different meaning.

**The route that does work was sitting one function over.** `relayshield_api.py` and
`relayshield_agentic_api.py` both read `BUNDLE_D_PRODUCT_CODE` from their OWN environment
blocks, which this incident never touched. Section 4 reads exactly those keys, by name
rather than dumping the block. **When a value is gone from one place, ask which other
component was configured with the same value** -- that is cheaper than any forensic route
and it was available before CloudTrail was ever queried.


## AN ENTITY ID IS NOT A PRODUCT CODE, AND MY OWN TOOL PRINTED THAT IT WAS

**2026-09-18, asked as "You need to tell me what Product Code to enter. Running GH Action in
Step 5 doesn't make it obvious."** He is right twice: the value was not obvious, and the
answer the repo had written down for it was WRONG.

`tools/marketplace_submit_changeset.py` printed, on every successful submission:

    WHEN IT SUCCEEDS it returns the new entity id. That id is the product
    code the fulfillment Lambda needs as BUNDLE_B_PRODUCT_CODE

`bundle_b_launch_runbook.md` STEP 5 said the same in four words -- *"That id is the product
code."* -- and CLAUDE.md called `marketplace_dimension.yml`'s `confirm_entity` input "the
product code typed by hand" when that input takes `prod-kkvurtspreofy`.

**THEY ARE DIFFERENT NAMESPACES, AND THE EVIDENCE WAS IN THIS REPO THE WHOLE TIME.**
`docs.aws.amazon.com` returns 000 from the container, so this was settled by grepping our
own artefacts rather than by recalling a docs page:

    entity id     prod-kkvurtspreofy          Catalog API identifier
    product code  46y72j0d99w7lyqkiqrakpc5k   TODO.md:1707, "set aws_product_code"
    product code  5s4a96a1ui1a5efrom6udnm2g   relayshield_aws_marketplace.py:22

The entity id is what `StartChangeSet` returns and what the test-offer and go-public change
sets take as `product_id`. **The PRODUCT CODE is what `ResolveCustomer` returns and what
`GetEntitlements(ProductCode=...)` and `BatchMeterUsage` take**, and it is the value
`BUNDLE_B_PRODUCT_CODE` needs.

**SO THE ENTITY ID IN THAT FIELD IS STRICTLY WORSE THAN THE GIT SHA THAT WAS ACTUALLY
PASTED.** `_product_code_filter()` would match no key row, `_get_entitlement` would query
the wrong product, nothing raises, and the fulfillment path reports success -- the exact
silent-wrong-answer shape the diagnostic was built to catch. A git SHA at least looks wrong.

### THE SHAPES COLLIDE, WHICH IS WHY "IT LOOKS LIKE A PRODUCT CODE" PROVES NOTHING

`9hxvi0lkd62on8uhb1iv3yfbc` is a CHANGE SET id, from `TODO.md`. Same 25 lowercase
alphanumerics as both real product codes. **Three different identifiers, two of them
indistinguishable by shape**, so anything reporting a candidate labels it with the key path
it came from rather than the pattern it matched.

### THE FIX IS A READ, BECAUSE THE MISSING STEP WAS A READ

Turning "create the product" into a click without giving the reader a way to read its RESULT
back is half a step, and that is precisely what he reported. `tools/marketplace_read_product.py`
plus `.github/workflows/marketplace_read_product.yml` are STEP 5b: `DescribeChangeSet`, then
`DescribeEntity` on the id it returns, then any product-code-shaped value with its key path.
**Read only, no apply mode and no confirmation phrase, deliberately** -- it is the thing you
re-run every few minutes while AWS is still APPLYING, and a workflow that cannot be talked
into writing is one nobody hesitates to re-run.

**Whether `DescribeEntity` carries the product code at all is UNVERIFIED and is labelled that
way in the tool.** The only DescribeEntity capture in this repo is of an Offer, not a
SaaSProduct. So the tool REPORTS what came back and, when nothing matches, says that is a
finding about the API rather than about the product, and names the authoritative read:
the Marketplace Management Portal product page. The code is also the suffix of the SNS topic
ARN AWS creates for a listing, which `relayshield_aws_marketplace.py:23` records.

`tools/lambda_env_merge.py` now refuses a `prod-` value for any `*_PRODUCT_CODE` key, next to
the git-SHA refusal, and the refusal names the read that produces the right value rather than
just saying no.

### TWO THINGS THE PROOF RUNS FOUND THAT READING WOULD NOT HAVE

**A guard I wrote could never fire.** `candidates()` excluded `prod-` ids with its own rule;
deleting that rule changed nothing, because an entity id is hyphenated and the shape pattern
allows no hyphen. **Decoration reads as protection.** It is gone, and the test asserts the
exclusion as a property of the shape pattern, which is where it actually lives.

**And the FAILED branch told the reader to wait.** A `FAILED` change set printed *"NOT
SUCCEEDED YET ... re-run this in a few minutes"*, which is correct for `PREPARING` and
`APPLYING` and is advice to wait forever for a change set that is finished and dead. Two
statuses, one message, and only running it shows that. `FAILED` now says nothing was created
and points at the error lines.

**THE RULE, and it is the measurement-tool rule pointed at advice rather than at numbers: a
value a tool tells you to go and paste somewhere is as consequential as a number it prints.**
Both get acted on without re-derivation. Read it out of the code or the artefact that defines
it -- `grep` found both real product codes in this repo in one command -- and never out of a
sentence a previous session wrote.

## A CLICK ON A WORKFLOW WRITTEN THIS SESSION IS NOT A CLICK. IT IS NOT IN HIS SIDEBAR.

**2026-09-18, reported as *"Your runbook Step 5b says 'read a marketplace product' which doesn't
literally exist. Do you mean Marketplace Change Set?"*** No -- the workflow is real, it is on the
branch, and **GitHub dispatches a workflow only from the DEFAULT BRANCH**, so it does not appear in
the Actions sidebar until main carries the file.

**THIS FILE ALREADY RECORDS THAT EDGE, FROM THE MINI APP DEPLOY**: *"a workflow file that is not on
the default branch cannot be dispatched from the Actions UI either"*. I wrote a `ANDREW CLICKS THIS`
step against a workflow living on a feature branch anyway, one turn after writing the workflow.

**It is the LOCAL MERGE IS NOT A PUSH rule in its third direction.** A push reaches GitHub, a merge
reaches his clone -- and **a push to a BRANCH does not reach the Actions dispatch menu**, which reads
main and nothing else. Checked rather than recalled: `git ls-tree origin/main .github/workflows/`
lists nineteen files and `marketplace_read_product.yml` is not among them, while the other five
workflows the runbook names all are.

**THE RULE: a click step naming a workflow written in the same session carries the merge as its
prerequisite, in the step, not in a preamble.** The cheap check is one command and it distinguishes
the two states a reader cannot:

    git --no-pager ls-tree origin/main --name-only .github/workflows/ | grep <file>

**And no test guards this, deliberately.** A check requiring every named workflow to be on main
would fail on every workflow the day it is written -- the CSM-SIMSWAP-1 shape, where passing means
deleting something true. The note in the step is the guard.

### THE OTHER HALF OF THAT QUESTION WAS ANSWERABLE FROM HERE, AND I HAD NOT TRIED

He also asked what the ChangeSetId from step 5 was. **It is in the run log, and the GitHub MCP tools
in this session can read a job log.** `actions_list` then `get_job_logs` returned it in two calls:
`de0zvpnvpcq3olta3y7kpx4p2`, with run #4's step list showing `Dry run: skipped` and `Apply: success`,
which ALSO proves STEP 1's catalog grant took -- `StartChangeSet` returned instead of refusing.

**Asking him to go and read a value that is in a log I can read is a round trip I chose.** The same
class as writing the procedure for reading two numbers off an Apify screen he could just screenshot,
inverted: there, the container could not see it and I wrote a procedure; here, the container COULD
see it and I asked anyway. **Before asking for a value, ask which of this session's tools already
reaches it.**

**And the run log still carries the wrong sentence**, because it executed `403a63c`, before the
entity-id correction. A log is a record of the code that ran, not of the code that is correct now --
so a fix shipped after a run does not retroactively fix that run's output, and the reader has to be
told which lines to disregard.

## THE CHANGE SET FAILED ON A LOGO THAT WAS NEVER UPLOADED. SIX GUARDS ON THE DOCUMENT SAW NOTHING.

**2026-09-18. Asked as "show me where to find the Bundle B product code" in the Marketplace
Management Portal. It is not there, and the portal is right:** that page lists three SaaS products,
all Public, and Bundle B is not among them because **the change set FAILED.**

    Status : FAILED
    Error  : INVALID_MEDIA_LOCATION Media location not accessible:
             .../bundle_b/relayshield_logo_bundle_b.png

**AND MY FIRST SENTENCE BACK TO HIM WAS WRONG IN A WAY WORTH RECORDING.** He said step 5b succeeded;
I said the portal contradicts that. **It does not.** The `read` job WAS green -- reading is all it
does -- and what it read was a failed change set. Both are true at once. That is this file's own
"a red run names a step, not an outcome" pointed the other way: **a GREEN run names a step too.** He
corrected it in one line and he was right.

### THE DEFECT: A FIELD WHOSE VALUE IS AN EXTERNAL RESOURCE IS NOT VALIDATED BY VALIDATING THE STRING

`bundle_b_create_entity.json` was built by reading Bundle A's ACCEPTED change set and reusing its
envelope, which is the right method and is recorded above as such. The `LogoUrl` came across with
`bundle_a` substituted to `bundle_b` in the path -- **and that object had never been uploaded.**
`curl -I` settles it in one second, from this container:

    bundle_a/relayshield_logo_bundle_a.png   200
    bundle_b/relayshield_logo_bundle_b.png   403

**A public S3 bucket with no ListBucket answers 403 for an object that is not there rather than 404**,
so those two codes are ONE finding and a guard that only knows 404 misses the real case.

`test_bundle_b_changeset.py`'s six guards were all green and always would have been: every one of
them reads the DOCUMENT. **Six checks on a document say nothing about a URL inside it**, which is the
"a guard is only as good as where it got its expectations" shape landing on a field rather than on a
table -- and the expectation here lives on somebody else's server.

### THE FIX IS A PREFLIGHT, NOT A NOTE, AND THE DRY RUN RUNS IT

`check_media()` in `tools/marketplace_submit_changeset.py` HEADs every `*Url` field AWS actually
dereferences and refuses before spending a change set. It reproduces AWS's exact failure locally in
one second against the fifteen a real submission takes, and **it runs BEFORE the dry-run return**, so
a dry run checks the same document an apply would send.

**Only 403 and 404 block. A timeout, a refused connection, a 5xx or a blocked egress policy prints
UNKNOWN and continues**, because a probe that cannot tell has no standing to stop the work -- the
rule `publish_devto.py` already carries, applied to a submission instead of a post. An S3 blip that
refuses to submit finished work is worse than the defect it guards.

**It deliberately ignores every URL AWS never fetches.** The usage instructions carry
`api.relayshield.net` and a docs link; probing those turns an unrelated outage into a refusal.

**THE LOGO NOW POINTS AT BUNDLE A'S OBJECT**, checked rather than assumed: it is downloaded and
looked at, and it is the generic RelayShield shield mark with **no bundle-specific text in it**, so
reuse is correct rather than a shortcut. A separate `bundle_b` object buys nothing a reader can see
and needs an upload nobody has done.

### AND MY FIRST ORDERING GUARD PASSED ON THE DEFECT, FOR THE SECOND TIME THIS WEEK

It compared `body.index("check_media(doc)")` against `body.index("DRY RUN")`. Moving the call INSIDE
the `if not args.apply` branch **preserves textual order** while making it run on the dry run and NOT
on the apply -- the dangerous half, and the guard stayed green. **A substring the defect also
satisfies is not a guard**, which this file recorded four days ago about `is not None` containing
`not `.

It reads `main()` with `ast` now and asserts the property that matters: `check_media` is called
exactly ONCE, at the top level of the function, before any branch that can return. **"Not nested in
a branch" is the rule; "earlier in the file" was a proxy for it**, and a proxy is what fails on
correct code or passes on broken code, eventually both.

Three defects proven by reintroducing them: the call moved into the branch, 403 narrowed to 404
alone, and the call deleted. The 403 mapping is pinned without a network, because the narrowing
changed the live verdict on the real URL from MISSING to UNKNOWN and nothing noticed.

### THE GENERAL FORM

**Before submitting anything to a system that will FETCH what you hand it, fetch it yourself.** A
change set, a webhook registration, an OG image, a marketplace listing, an MCP server URL in a
directory record. The remote system's failure is slow, asynchronous and arrives as an error code;
yours is one HEAD request. This repo already watches the HF Space's own MCP URL for exactly that
reason -- **advertising a URL that nothing checks is the quiet alarm** -- and a change set is the
same thing with a review cycle attached.

## THE VALUE THE READER NEEDS WAS IN A LOG. THE ONE ON SCREEN WAS A GIT SHA, TWICE.

**2026-09-18, asked as "Is this the new ChangeSetid from Step 5 which i just reran:
a7067bd2c5e70b0318c9b7f327ddeb13568b778c".** No -- that is this session's own runbook
commit. A ChangeSetId is 25 lowercase alphanumerics.

**SECOND TIME IN TWO DAYS, AND THE MECHANISM IS THE SAME BOTH TIMES.** A git SHA was
pasted into `BUNDLE_B_PRODUCT_CODE` on 2026-09-18 morning, and now offered as a
ChangeSetId. **GitHub prints the commit SHA in the Actions run page HEADER**, large and
copyable; the ChangeSetId is inside the job's output, behind an expandable step. So the
plausible-looking value is the one on screen and the correct one is buried. **That is not a
reader error, it is a layout, and a procedure that says "copy the ChangeSetId" without
saying where it is loses to the layout every time.**

**THE FIX IS THE REFUSAL, NOT THE INSTRUCTION.** `marketplace_read_product.py` now blocks a
40-hex value and its message says WHERE the real one is -- open the run, expand the Apply
step, the line reading `ChangeSetId  : ...`. `lambda_env_merge.py` already carried the
same refusal for the product code. Anything else unexpected WARNS and continues: a
read-only tool has no standing to block on a shape it merely does not recognise.

**And the value was readable from here the whole time.** `actions_list` plus
`get_job_logs` returned it in two calls, along with which of the two runs was the dry run
and which the apply. **Before asking for a value, ask which of this session's tools already
reaches it** -- written down one turn earlier and then not applied, which is why the
refusal is code rather than another sentence.

### THE RE-RUN WORKED, AND THE PREFLIGHT PROVED ITSELF ON THE REAL DOCUMENT

    run #5  19:06:54Z   dry run   media preflight: OK HTTP 200
    run #6  19:08:52Z   apply     SUBMITTED  ChangeSetId 17or75a96xofiu7gic33wjrm6

The logo check that FAILED the first change set now passes in one second, in the dry run,
before anything is spent. A guard written after a failure is worth having only if the next
run exercises it, and this one did.

## THE CHANGE SET FAILED A SECOND TIME. I HAD READ BUNDLE A'S ENVELOPE AS FAR AS ITS DIMENSIONS.

**2026-09-19, read from the STEP 5b run rather than reported.** The logo fix took and the
media preflight printed `OK HTTP 200`, and `17or75a96xofiu7gic33wjrm6` failed anyway:

    INVALID_INPUT When adding dimensions for SaaS products, you must also set
    pricing for usage dimensions.

**FIVE CHANGES WHERE BUNDLE A'S ACCEPTED SET HAS THIRTEEN.** This file records, approvingly,
that Bundle B was "built by READING Bundle A's change set and reusing its envelope rather
than retyping it, so the shape AWS already accepted is preserved". That was the right
method and I applied it to the first five changes. Everything after `AddDimensions` --
`ReleaseProduct`, `CreateOffer`, the offer's `UpdateInformation`, **`UpdatePricingTerms`**,
`UpdateLegalTerms`, `UpdateSupportTerms`, `UpdateRenewalTerms`, `ReleaseOffer` -- was never
read and therefore never copied. **A SaaS product is created by ONE change set carrying the
product AND its offer**, and a product with dimensions and no rate card is not a smaller
version of that, it is invalid.

**SECOND FAILURE IN TWO DAYS ON THE SAME DOCUMENT, AND THE SECOND ONE IS THE SAME SHAPE AS
THE FIRST.** The logo was a field copied across with its value substituted and not checked;
this was a section not copied across at all. Both are "I reused an accepted artefact" doing
less work than the sentence implies. **When the method is reuse, the check is a diff against
the thing being reused, not a reading of the result.**

**AND EVERY GUARD WAS GREEN, INCLUDING THE ONE I ADDED HOURS EARLIER.** Six document guards
plus the new media preflight, all passing on a document missing eight of its thirteen parts.
**A check that reads the document cannot see what the document does not contain.** The new
guard is therefore not another document check: `test_bundle_b_changeset.py` asserts Bundle
B's ChangeType sequence EQUALS Bundle A's, because Bundle A's file is the only accepted
example in the repo and a difference there is a missing step rather than a style choice.

### THE PREFLIGHT REPRODUCES AWS'S REFUSAL IN ONE SECOND

`check_pricing()` in `tools/marketplace_submit_changeset.py` runs beside `check_media()`,
at the top level of `main()` before any branch that returns, and refuses a change set whose
`AddDimensions` keys are not all priced -- and, in the other direction, a rate card naming a
key no dimension declares, which is a price nothing can ever bill. Run against the exact
document AWS rejected it prints six `UNPRICED` lines and exits 1.

**The general form, third instance this week: when a remote system will VALIDATE what you
hand it, reproduce its validation locally.** `check_media` fetches what AWS would fetch;
`check_pricing` asserts what AWS would assert. The remote answer costs fifteen seconds, a
review cycle and a round trip; the local one costs nothing and names the field.

### THE RATE CARD IS DERIVED FROM THE BILLING TABLES, NOT TYPED

The five per-call prices are read out of `BUNDLE_B_DIMENSION_NAMES` and
`METERED_CREDIT_COSTS` in `relayshield_api.py`, and the $100 monthly minimum out of that
file's own Bundle B comment. **A price in a public listing is a number in a public artefact**,
so the rule that a command list is extracted rather than remembered applies with money on it:
a listing price above what we meter is a price we do not honour, and one below it bills AWS
buyers less than everyone else with nothing raising. `test_bundle_b_changeset.py` fails if
the two ever disagree, proven by moving `secret_scan_calls` to $0.45.

### AND ONE OF MY OWN GUARDS FAILED ON THE CORRECT DOCUMENT

`test_it_creates_its_own_entity` required every change to target
`$CreateProductChange.Entity.Identifier`. The offer half correctly targets
`$CreateOfferChange.Entity.Identifier`, so the complete change set failed a test written
against the incomplete one. **A guard derived from a broken artefact encodes the breakage**,
which is the CSM-SIMSWAP-1 shape arriving from a new direction: there, passing meant deleting
a true sentence; here, passing meant keeping the document invalid. It accepts either chain now
and still refuses a literal `prod-...`, which would point the offer at a LIVE product.

## STEP 6 WAS A CLICK AND READ LIKE A COMMAND. THE TOOL'S NAME WAS THE WHOLE PROBLEM.

Reported as: *"your Step 6 instruction is poorly worded... Am I submitting a terminal command
`tools/lambda_env_merge.py`? If so you violated your rule where you are supposed to list as
Andrew runs this."*

**The step was labelled `ANDREW CLICKS THIS` and its body then spent a paragraph on the
script's behaviour before naming the workflow.** Rule 9 says the LABEL governs the block that
follows it; it does not say the prose in between cannot contradict the label. A reader who
sees a repo-relative path to a `.py` file has been handed something that looks runnable,
whatever the heading says -- and this repo's own rules exist because a fenced block, a slash
command and a placeholder all look identical to somebody reading quickly.

**THE RULE: when a step is a click, the workflow name is the first thing in it, and any tool
it runs on the runner is named only after the form, explicitly as something the reader never
invokes.** Mechanism belongs under the instruction, never above it -- the same ordering that
put a destructive write above its own warning two days ago.

## THE FOURTH FAILURE WAS MY FIX SITTING ON A BRANCH. A CLICK RUNS `main`, NOT MY WORK.

**2026-09-19, and the founder's words are the measurement: *"This is the 4th time the Step
5b changeset has failed. Its not only your fault but its cost me too many unnecessary turns
and token."*** Change set `dldmvatisooxdj8b7zll8q4a1` came back with the IDENTICAL error as
the one before it:

    INVALID_INPUT When adding dimensions for SaaS products, you must also set
    pricing for usage dimensions.
    CreateProduct / UpdateInformation / AddDeliveryOptions / AddDimensions / UpdateTargeting

**Five changes. The document I had fixed carries thirteen.** `origin/main` was at `a7067bd`
and my fix was `b01ce51` on `claude/tender-planck-cb2qrx`, so the workflow checked out the
OLD document, submitted it, and AWS refused it for the same reason a second time. **Nothing
was wrong with the fix and nothing was wrong with his click.** My reply said "Two clicks
first" and never said merge.

**I WROTE THIS RULE YESTERDAY AND APPLIED IT TO THE WRONG NOUN.** The section above says a
click step naming a workflow written this session carries the merge as its prerequisite,
because a dispatch reads the default branch. **A dispatch reads the default branch's copy of
EVERY FILE THE JOB TOUCHES** -- the workflow, the tool it runs, and the DATA it is pointed
at. I fixed the sentence for workflow files and left the same hole open for the JSON, one
turn later, on the same runbook.

**THE RULE, and it is the noun that was wrong rather than the idea: before any click step,
ask which files that job READS, and whether every one of them is on `main`.** Not "is the
workflow there". The cheap check names the thing rather than the branch:

    git --no-pager show origin/main:<path> | <the one-line assertion>

**AND THE OTHER HALF IS WORSE, BECAUSE IT TAUGHT HIM THE DEFECT.** Runbook STEP 4 said
`EXPECT: five changes`. I wrote that line by reading our own document rather than from what
AWS requires, so the dry run printed the correct number for a broken file and the reader had
no way to know. **An EXPECT written from the artefact confirms the artefact.** It has to come
from the requirement, or from the accepted example -- Bundle A's thirteen -- and when those
two disagree the EXPECT is the thing that is wrong.

### THE GUARD IS IN THE RUN OUTPUT, BECAUSE THE READER CANNOT SEE MY BRANCH

`marketplace_changeset.yml` now opens every run with **the commit it checked out and every
`ChangeType` in the file it is about to send**. A stale `main` was previously invisible until
AWS answered fifteen seconds later with a validation error, and the run log named neither.
`marketplace_read_product.yml` prints the commit too. Both were exercised by running the step
body exactly as the YAML stores it: it prints `changes : 13` here and `changes : 5` against
`origin/main`'s copy, which is precisely the distinction nobody could make.

**And the runbook gained STEP 3b, a merge-and-push with `13 changes` as its EXPECT**, in
front of the two click steps rather than in a preamble -- the same placement rule as the
destructive write two days ago: a prerequisite stated after the thing it governs is not a
prerequisite.

**One thing the guards caught on the way, worth one line:** `run: echo "commit : $(...)"`
is not valid YAML, because a plain scalar cannot contain `": "`. `test_workflows_parse.py`
failed it immediately, which is that check earning its place again -- GitHub's own response
to an unparseable workflow is "No jobs were run", quieter than a failure.

## FIVE REFUSED CHANGE SETS, FIVE DIFFERENT VALIDATIONS, ONE DEFECT: I FIXED THEM ONE AT A TIME

**2026-09-19, and the founder's words are the measurement: *"You messed up Step 5b a fifth
time... It feels like trial-and-error where you are being very careless. I want Bundle B
released and I don't want to burn tons more turns to do it."*** He is right, and the thing
worth recording is not the fifth defect.

    de0zvpnvpcq3olta3y7kpx4p2   INVALID_MEDIA_LOCATION      a logo never uploaded
    17or75a96xofiu7gic33wjrm6   INVALID_INPUT ... pricing   5 changes, not 13
    dldmvatisooxdj8b7zll8q4a1   INVALID_INPUT ... pricing   the fix was on a branch
    em3sw5gs00lifcmy42mxe95t9   INVALID_INPUT ... 90 chars  four descriptions over

**EACH ROUND I ADDED A GUARD FOR THE THING THAT HAD JUST FAILED, AND EVERY ONE OF THOSE
GUARDS READ THE DOCUMENT THAT EXISTED.** Six document guards were green on a document
missing eight of its thirteen changes. Eleven were green on one with four over-length
fields. **A check that reads the artefact can only find what the artefact contains; it can
never tell you what a VALID one looks like.** That question has one answer available in
this repo and it was used for the envelope and then put down: `bundle_a_create_entity.json`
is the only change set AWS has ever accepted from us.

**SO THE REFERENCE IS THE WHOLE ACCEPTED DOCUMENT, FIELD BY FIELD, NOT ITS SHAPE.**
`check_field_limits()` prints every field in the change set beside the longest value AWS
took in that SAME field, with list indices collapsed -- a class path, so all six dimension
Descriptions are one field rather than six. Comparing by INDEX pairs "Breach Exposure
Check" with "Supply Chain Exposure Check" and reports the difference as a finding, which is
a guard nobody can act on.

**The measurement that would have caught the fifth failure before the first:** Bundle A's
dimension descriptions are 80/76/88/78/71/71/83 and **every one is under 90.** The
constraint was derivable from the accepted example all along, without a docs page --
`docs.aws.amazon.com` returns 000 from this container, which is exactly why the accepted
artefact is the authority.

**TWO MECHANISMS, DELIBERATELY DIFFERENT IN FORCE, and the split is the repo's own rule.**
`CEILINGS` holds limits we have MEASURED and it BLOCKS, each entry naming where the number
came from -- a limit nobody can source is one the next session deletes. Everything else
merely REPORTS `OVER`, because "longer than one accepted example" is not a known constraint
and a probe that cannot tell has no standing to stop finished work.

**AND THE COMPARISON FOUND SOMETHING BETTER THAN A LENGTH: THE TWO DOCUMENTS HAVE THE
IDENTICAL FIELD STRUCTURE.** Same changes, same keys, all the way down. A test now fails in
BOTH directions -- a field Bundle A carries that we do not is a missing step, and a field we
carry that no accepted set has may be fine but nothing in this repo has evidence that it is.

**THE GENERAL FORM, and it outranks adding another guard: when a remote system has refused
you more than once, stop fixing the thing it named. Diff your artefact against one it
accepted.** The refusal names a symptom; the accepted example is the specification. Three
sessions of this programme have now reached for the second one and stopped halfway --
Bundle A's envelope was read as far as `AddDimensions`, its dimension lengths were never
read at all, and both were one `json.load` away.

## FD-12 WAS SUBMITTED THIRTEEN DAYS AGO AND THE ROW SAID OTHERWISE. IT IS WATCHED NOW.

**2026-09-19.** `FRONT_DOORS.md`'s FD-12 row read **ROUTE OPEN, ARTEFACT BUILT**; two hundred
lines below it, in the same file, sat the sentence **"FD-12's form was submitted 2026-09-06."**
Nobody was wrong on purpose. The submission form returns no ticket and no email, so the only way
to know the state was to remember to look -- and **a status nothing measures drifts.** That is
the XSOAR gate word for word, and it gets the same fix:
`.github/workflows/claude_plugin_directory_watch.yml`, weekly, issue on the day it lands.

**MEASURED, because the directory is one public JSON file:** `anthropics/claude-plugins-official`
carries **310 plugins**, 39 first-party, 14 vendored, **258 sourced REMOTELY** (97 `git-subdir`,
161 `url`). We are in none of them.

**THERE IS NO FOLLOW-UP ROUTE, AND IT WAS READ RATHER THAN ASSUMED.** No issue template, no
CONTRIBUTING, and `.github/workflows/close-external-prs.yml` **auto-closes any non-member PR**
unless `external-pr-scope.js` finds it adds an entry whose source repo ALREADY backs a live
listing. Ours does not. **Do not open a PR there** -- that is FD-2's failure with the evidence
available in advance for once, and it took one clone to establish.

**THE COMPETITIVE FINDING IS THE BEST ARGUMENT FOR A RE-SUBMISSION.** Eighteen entries carry
`category: security` -- 42crunch, auth0, crowdsec, two CrowdStrike, jfrog, semgrep, sonarqube,
sonatype, two StackHawk, two Vanta, workos, zscaler and three Anthropic ones. **Every one is
app-sec, identity, or posture and compliance. Not one screens the thing an agent is about to
install.** The directory has no entry making agent-bait's argument.

**AND THE ORG MOVE IS HALF APPLIED, WHICH IS WORSE THAN NEITHER STATE.**
`plugins/relayshield/.claude-plugin/plugin.json` names `RelayShield/relayshield-plugin` as its
repository while `.claude-plugin/marketplace.json` still sources the personal account. Their guide
calls org ownership *"the single biggest thing that speeds up review"*. **It cannot be finished
from a `nzdsf2-gif/*` session** -- repo sources are one owner, fixed before the prompt is typed.

## THE CATALOGUE TABLES HOLD MORE READY ROUTES THAN HAVE BEEN SUBMITTED

Asked as "we need to add RS to more catalogs", and the honest ranking is worth stating before the
rows: **`miniapp_routes.json` held 14 destinations and `bot_directories.json` held 8, and four
Mini App submissions and one unconfirmed bot submission have gone out.** The binding constraint is
submissions, not candidates. Adding rows is cheap and does not move anything on its own.

Five added anyway, typed and ranked rather than listed: **dappradar** (the one catalogue whose
audience HOLDS TON, which is the single audience for whom a TON-only Check tab is the headline
rather than a limitation), **producthunt** (recorded as a DIFFERENT KIND of destination and ranked
last -- a listing is a standing shelf, a launch is ONE DAY, which makes it a channel post with a
bigger audience and the largest first impression left unspent), and **botostore, tgstat, tlgrm**
on the bot side, all `route_type: unverified`.

**Both Mini App keys are registered in all three lists BEFORE either is submitted.** A bot key
needs no registration and a Mini App key does; getting that backwards costs a round in one
direction and four months of `unmatched:` in the other.

**AND A REACHABILITY PROBE WAS RUN AND PROVED NOTHING, WHICH IS THE POINT OF RECORDING IT.**
Eleven candidate hosts, all **HTTP 000** from the container -- including `findmini.app` and
`storebot.me`, both of which have accepted a submission from us in the last week. **A probe whose
negative result is indistinguishable from its blocked result has no standing to report a
negative**, so every new row says UNVERIFIED and names the one-minute browser read that settles it.

## A STEP NUMBERED 6 IS AN INSTRUCTION TO RUN IT SIXTH. PROSE CANNOT REORDER A LIST.

**2026-09-19.** I wrote *"step 6 moves after step 8"* in a reply, handed over
`prod-szi2wdww3obry` in the same reply, and **left STEP 6 sitting at position 6 in the
runbook.** He ran it sixth with the value I had just given him, and
`tools/lambda_env_merge.py` refused it:

    REFUSED: BUNDLE_B_PRODUCT_CODE was given 'prod-szi2wdww3obry', which is a
    Catalog API ENTITY ID, not a product code.

**The guard was right and the ORDER was mine.** An entity id in that field matches no key
row, raises nothing, and makes a revocation scan over a live public listing find nothing
and report success -- strictly worse than the git SHA that was pasted two days earlier,
because a SHA at least looks wrong.

**THIS IS THE DESTRUCTIVE-WRITE-ABOVE-ITS-OWN-WARNING DEFECT, THIRD INSTANCE IN THREE
DAYS, AND THE LESSON HAS NOW BEEN WRITTEN DOWN TWICE WITHOUT BEING APPLIED.** The grant
was ordered before the merge that feeds it; the env write was placed above the warning
about it; and now a step was left in a position its own text disclaims. All three are the
same thing: **I put the ordering in prose and the artefact carried a different order.**

**THE RULE, and it is the only version of this that has any force: reorder the ARTEFACT.**
A numbered list is read by its numbers. A heading is a position. A fenced block under a
label is the thing that gets run. Prose beside any of them loses, every time, and the
reader is not at fault for following the structure. STEP 6 is now STEP 8b, physically
after STEP 8, with a stub at position 6 saying where it went and why -- and
`test_product_code_is_not_entity_id.py` fails if the two ever swap back, proven by
swapping them.

### AND THE PRODUCT CODE WAS NEVER A BLOCKER, WHICH IS WHY THE STEP COULD MOVE

Read from `relayshield_bundle_fulfillment.py` rather than assumed:

* **`BUNDLE_CONFIGS` is keyed on the entitlement DIMENSION** (`attack_surface_bundle_access`),
  never on the product code. `_resolve_bundle` looks up that dimension alone.
* **`ResolveCustomer` RETURNS the product code** at fulfillment, and `_get_entitlement`
  queries `GetEntitlements` with that value whatever the environment holds.
* **The mismatch guard needs BOTH sides non-empty**, so an unset `BUNDLE_B_PRODUCT_CODE`
  SKIPS it rather than tripping it.

So the E2E subscription works with the key unset, **and the subscription is what assigns
and prints the code** -- `Product code not recognised: got <CODE>, known [...]`, which is
the handler correctly reporting a code it resolved and does not recognise. Set it from
that line, afterwards.

**A PRODUCT CODE IS ASSIGNED TO A SUBSCRIPTION, NOT TO A PRODUCT, AND BOTH OF MY REFUSAL
MESSAGES SAID OTHERWISE.** The git-SHA one said the code "is assigned by StartChangeSet",
which is the entity id; the entity-id one sent the reader to
`marketplace_read_product.py`, which may legitimately report NONE. **Two guards firing
correctly and then giving wrong directions is worse than one guard**, because the reader
trusts a refusal that names a next step. Both name ResolveCustomer now, and a test asserts
they do.

### AND TWO OF MY OWN GUARDS DEFENDED THE WRONG ANSWER

`test_the_refusal_says_which_namespace_it_got` REQUIRED the string
`marketplace_read_product.py`, and `test_the_runbook_step_6_asks_for_the_product_code`
required `from STEP 5b`. **Both pinned a ROUTE and a POSITION rather than the property**,
so the day the route turned out to be wrong and the step moved, the guards failed on the
correction and defended the defect. That is the CSM-SIMSWAP-1 shape and the
`is not None`-contains-`not` shape in one: **a guard that encodes today's answer instead
of what the answer must ACHIEVE eventually fails on correct code, and the temptation then
is to loosen it.** They assert the properties now -- a refusal names SOME route to the
right value, and the `| value |` row rules out the `prod-` id -- and the new ordering
guard asserts position rather than any wording at all.

### THE `@1` THAT MADE A SUCCESSFUL CREATE LOOK LIKE A FAILURE

Change set `27vgy6fh2q7uke1ddtxa0w1l3` SUCCEEDED, applied all thirteen changes, and
created **`prod-szi2wdww3obry`** with offer `offer-tphmeebmexqp2`. The run went red one
line later, in my own tool:

    ValidationException: [Requested entity id 'prod-szi2wdww3obry@1' is invalid.
    It should match with ^[a-zA-Z0-9][.a-zA-Z0-9/-]+[a-zA-Z0-9$.]

**DescribeChangeSet reports the entity REVISION. DescribeEntity refuses it.** One product,
two identifiers, one character apart, and the message reads as *your product is invalid*
when the product is fine and the REQUEST was malformed -- a status code describing the
request rather than the resource, for the fourth time in this programme. `bare_entity_id()`
strips it, asserted at the CALL SITE with `ast` because a helper nothing calls is
decoration.

**And it is a GREEN-run version of "a red run names a step, not an outcome":** the founder
reported 5b as succeeded and I said the portal contradicted that. It did not. The read job
was green, reading is all it does, and what it read was a failed change set. Both halves
true at once, and he corrected me in one line.

## THE SIXTH FAILURE WAS CAUGHT BEFORE THE CLICK, BY THE CHECKLIST, ON THE OTHER HALF OF A FIX I ALREADY MADE

**2026-09-19.** `bundle_b_test_offer.json` carried `AvailabilityEndDate: "2026-09-06"` --
a literal date copied from Bundle A's accepted offer, **thirteen days in the past**.

**THE SAME FILE ALREADY RECORDS ME FIXING THIS EXACT DEFECT IN THE FIELD NEXT TO IT.**
The 2026-09-17 section says *"its ChargeDate is a placeholder and Bundle A's is not: that
file carries 2026-08-08, correct on the day and a date in the PAST for anyone since"*. I
turned `ChargeDate` into `__CHARGE_DATE__`, wrote down why, and **left the availability
date literal two changes further down the same document.** Half the fix, which is the
shape of every Bundle B failure so far.

**AN END DATE IN THE PAST IS WORSE THAN A CHARGE DATE IN THE PAST.** A stale charge date
is rejected. A stale availability date **releases an offer that has already expired**, so
the buyer account is told to go and accept something it cannot see -- and STEP 8's failure
would have read as a fulfillment-URL problem, which is a different bug with a different
fix.

**IT WAS FOUND BY THE PRE-HANDOVER CHECKLIST'S OWN QUESTION 3 -- what will the remote
system VALIDATE -- asked while reading commit `e72cc31` for something else entirely.** That
commit message is also where the requirement is recorded: *"Private offers additionally
require UpdateAvailability with an AvailabilityEndDate, or ReleaseOffer fails
MISSING_AVAILABILITY_END_DATE ... That is absent from the create-product flow and cost one
submission."* **The knowledge was in a commit message and nothing carried it into the
artefact**, which is a lesson recorded in one file not being a lesson the next file learns,
for the fourth time.

**THE GUARD IS GENERAL RATHER THAN ANOTHER FIELD-SPECIFIC ONE.** `check_dates()` walks
every ISO date under a key ending in `Date`, **after substitution, on the document that is
actually sent**, and REFUSES any that is before today. It blocks rather than warning, and
that is the same distinction `check_media` draws from the other side: a timeout means the
probe could not tell, while **a date before today cannot become valid by waiting.**

It is deliberately narrow: the standard EULA term carries `Version: "2022-07-14"`, which
is a document version that happens to look like a date and is correct as it stands. A
guard that forces you to change a true value to go green is one that gets loosened.

Seven tests, three proven by reintroducing the defect -- the literal date back in the
file, the call deleted from `main()`, and **the call moved inside the dry-run branch**,
where it would check the one document that is never sent.

**THE RULE, and it is narrower than "diff against the accepted example" because that was
already written down and still let this through: a value copied from an accepted artefact
is correct on ONE DAY if it is a date, for ONE PRODUCT if it is an id, and at ONE MOMENT
if it is a URL.** When reuse is the method, every field carried across is a candidate for
a placeholder, and the question is not "did I copy it correctly" but "what makes this
value true, and is that still true today".

### AND THE BUYER ACCOUNT IN THAT OFFER IS A FACT THE REPO NEVER RECORDED

`442429445748` appears in exactly four places -- the `PositiveTargeting.BuyerAccounts` of
Bundle A's and Bundle B's create sets and test offers -- and **nothing anywhere says whose
account it is.** It came across in the same reuse that carried the stale date. STEP 8 then
told the founder to sign in as it, and he could not, reasonably.

**The inference is strong and it is still an inference:** Bundle A and Bundle D are both
live and public, AWS grants public visibility only after the fulfillment test passes, and
`e72cc31` says Bundle A's offer *"mirrors Bundle D's proven test-offer shape"* -- so that
account was almost certainly used successfully twice. **An absence needs the same evidence
a presence does**, so the runbook now carries STEP 6b: one `organizations describe-account`
read from the seller side, and the decision made BEFORE the offer exists, when the target
is one line in a committed file rather than an offer in AWS.

**The general form: when a step names an identifier the reader has to BE rather than
type, the artefact says where that identity came from.** An account id, a root email, a
seller role -- these are not values to paste and a runbook that treats them as if they
were has not delivered the step.

### THE BUYER ACCOUNT IS OURS. SETTLED 2026-09-19 BY ONE SCREENSHOT.

`442429445748` is **`TestUser`**, and the founder signed into it and opened AWS Marketplace ->
Private offers. **The inference two sections above was right and it is now a measurement.** The
gap was never access; it was that no session had recorded whose account it is, so the runbook
told him to BE an identity the repo could not explain.

**AND THE LIST READ `Available private offers (0)`, WHICH IS THE CORRECT ANSWER.** STEP 7 has
never applied, so no Bundle B offer exists. **An empty list before the offer is created is the
expected state and reads exactly like a failure**, which is the same shape as a measurement tool
printing a zero: the reader acts on it. The runbook now orders that diagnosis so the free check
comes first -- has STEP 7 run at all -- before anything about the change set or the account.

**THE ONE THING THAT WOULD HAVE MADE IT A REAL FAILURE WAS CAUGHT BY THE DATE GUARD HOURS
EARLIER.** `origin/main` still carried `AvailabilityEndDate: "2026-09-06"`. Clicking STEP 7
against it would have released an offer that EXPIRED THIRTEEN DAYS AGO, which renders as **the
same empty list** -- an offer that was created, succeeded, and is invisible. That is the
worst diagnostic shape this programme produces: success everywhere and nothing on screen.

**The general form, and it is the empty-set rule arriving from a new side: before diagnosing an
empty list, establish whether the thing that fills it has ever run.** Absence of a record and
absence of the process that writes records are the same output and different problems, which is
what `_store_observed_session` already says about the stolen-sessions table.

## THE E2E SUBSCRIPTION COMPLETED. BUNDLE B HAS A REAL AGREEMENT.

**2026-09-19 20:40 UTC.** `442429445748` (TestUser) accepted `offer-a4jhoh7wgdz5g` on
`prod-szi2wdww3obry` and AWS created **`agmt-29l852u6kqzmjh2me0pglvj9q`**, 0.01 USD, term
2026-09-19 to 2026-10-19. Confirmed by AWS's own "Customer accepted an AWS Marketplace offer"
email and by the buyer account's Purchased offers list reading 1 of 1.

**STEP 8b AND STEP 9 NEEDED NO MERGE, AND CHECKING THAT WAS THE WHOLE ANSWER TO "CAN I MOVE
ON".** `lambda_env_set.yml`, `tools/lambda_env_merge.py` and `bundle_b_go_public.json` are all
on `origin/main` already. **The pre-handover checklist's question 2 -- what does the job READ,
every file -- answers "go straight to the click" as often as it answers "merge first"**, and
running it costs one command either way. Three of the seven Bundle B failures were a file on a
branch, so the check that has been catching problems also clears the path.

### ACCEPTING AN OFFER IS NOT THE SAME EVENT AS FULFILLMENT, AND STEP 8b DEPENDED ON THE SECOND

The agreement is what AWS's review asks for. **The fulfillment REDIRECT is a separate click**:
it is what POSTs `x-amzn-marketplace-token` to `relayshield-bundle-fulfillment`, where
`ResolveCustomer` runs, a key is provisioned, and the `Product code not recognised: got <CODE>`
line is written. STEP 8b read that line as its only source for the value.

**So a step's input can depend on a sub-event of the step before it that the step before it does
not guarantee.** The runbook now names a second route that does not -- the Management Portal's
own Product code field, seller side -- because a value with one source is a step that stalls
whenever that source did not fire, and the reader cannot tell a missing log line from a missing
permission.

### AND `BUNDLE_B_PRODUCT_CODE` IS NOT COSMETIC. IT DECIDES WHETHER A CANCELLED CUSTOMER KEEPS A KEY.

Read from `relayshield_bundle_fulfillment.py` rather than assumed, because "the E2E works with it
unset" (true, and recorded above) reads as "it does not matter" (false). `_product_code_filter()`
builds a DynamoDB filter from `PRODUCT_CODES`, and three functions use it:

    _deactivate_api_key             unsubscribe / entitlement lapse
    _find_api_key_for_customer      lookup outside the pending placeholder
    _find_provisioned_key_for_customer   the confirmation page

With the key unset, a Bundle B row carrying that `aws_product_code` matches none of them. **The
expensive one is the first: a cancelled Bundle B customer's key is never deactivated**, silently,
because a scan that matches nothing and a customer with no keys are the same output. That is the
quiet-alarm shape with revenue on it, and it is the reason 8b is a prerequisite for a real buyer
rather than tidying after go-public.


## SEVEN REJECTIONS ON BUNDLE B, AND THE VISIBILITY REQUEST WAS AGAINST A PRODUCT NOBODY HAD NAMED

**2026-09-21, written at Andrew's instruction after he said "I literally did everything you
said, got an HTTP 200 and still get rejected. I've wasted too much time on this."** He is
right, every round of it was mine, and the finding is in a screenshot I was sent and read
past.

    Failed to update product information for prod-v5nr5gjtdnofi@3
    Request changes: Update visibility, Update pricing terms
    Entities: RelayShield - Attack Surface & Supply Chain API,
              RelayShield Attack Surface & Supply Chain - offer

**`prod-v5nr5gjtdnofi` APPEARS NOWHERE IN THIS REPOSITORY.** Every artefact, every runbook
step, every diagnostic and the accepted agreement all name **`prod-szi2wdww3obry`**. Grep
settles it in one command.

**SO THERE ARE TWO BUNDLE B PRODUCTS WITH THE SAME DISPLAY NAME, AND WE HAVE BEEN WORKING ON
ONE AND SUBMITTING THE OTHER.** The audit's "no successful metering records" was CORRECT the
whole time: we metered `cmh79gzztkdtp0dlzbdepa643` (which is `prod-szi2wdww3obry`, the entity
the agreement is against) and asked AWS to publish `prod-v5nr5gjtdnofi`, which has never been
subscribed, never been fulfilled and never been metered. **Every fix I shipped was correct and
none of them could ever have cleared that request.**

### THE EVIDENCE WAS IN FRONT OF ME TWICE AND I DEPRIORITISED IT

`7ws2zmbdyk70tq34pr0pea0s2` turned up three times as a product code `ResolveCustomer` returned
for customer `fHL5zV6grGn`, and an unfiltered `GetEntitlements` showed it has **no
entitlements at all, for any customer**. I wrote, in this session:

> there's very likely a second, orphaned Bundle B product entity. That's not what's blocking
> you now, and I'm not going to chase it this turn.

**It was exactly what was blocking him.** A product code that AWS hands out and that holds no
entitlements is not an orphan to tidy up later, it is a SECOND LIVE PRODUCT, and the moment
two exist every instruction that says "the product" is ambiguous.

### THE RULE I BROKE IS ONE I WROTE IN THIS FILE SIX DAYS EARLIER

The section THERE ARE THREE AWS PRODUCT ENTITIES, NOT ONE says, in its own words:

> **When a repo holds more than one product entity, any claim about a product names the
> entity id it was read from.** Naming the id is what makes the claim checkable, and it is
> what stops the next session reading a neighbour's capture as this one's.

I applied that to Bundle A and Bundle D and never once applied it to **the visibility request
itself**. Seven rejections, and not one of my instructions said which entity to submit
against. `bundle_b_finish_2026-09-21.md` STEP 8 reads *"Management Portal, SaaS products,
RelayShield - Attack Surface & Supply Chain API, Update visibility"* -- **selected by DISPLAY
NAME, in a portal that evidently lists two products with that name.**

**THE RULE, TIGHTENED: a click step that selects a thing by its NAME is unfinished. It selects
by ID, and it says how to confirm the ID before clicking.** A name is a label a human chose
and can be duplicated; an id is the thing the API acts on. This applies to every portal,
console and dashboard, not to AWS Marketplace alone.

### THE OTHER FOUR THINGS THAT COST ROUNDS, EACH ONE MINE

**1. I TOLD HIM A LOG LINE WAS PROOF WHEN THE CODE DISCARDED THE RESPONSE.**
`BatchMeterUsage` returns 200 for a record it REJECTED -- the outcome is in `Results[].Status`
and `UnprocessedRecords`, and neither raises. `_report_marketplace_usage` threw the response
away and logged "Marketplace usage reported" on any call that did not throw. So our log and
AWS's audit were both true and described different things: the log described the REQUEST, the
audit described the RESULT. **This repo's own rule -- every probe prints the body of what it
got, not a summary of it -- broken in the billing path, where a customer's call is served once
and cannot be re-run to find out what happened.** Fixed, with 8 tests executed against a
stubbed client.

**2. I DIAGNOSED THREE TIMES FROM OUTPUT I COULD SEE WAS TRUNCATED.**
`tools/diagnose_bundle_b_audit.sh` prints five sections and the decisive one is LAST, so a
pasted terminal cut it off three runs in a row and each round ended with me asking for it
again. **A diagnostic's most important section goes FIRST, or it prints a one-line verdict at
the end that survives truncation.** Ordering output by narrative is a choice that costs the
reader a round every time their scrollback is shorter than the script.

**3. I FIXED WHATEVER THE ERROR NAMED INSTEAD OF ASKING WHAT IT WAS ABOUT.**
A logo, then pricing terms, then thirteen change types, then field lengths, then a stale date,
then the env var, then the SNS subscription, then the metering response. **Every one was a
real defect and every one was found by reading the error's TEXT.** Not once did I read the
error's SUBJECT -- the entity id printed beside it. The subject was wrong from the first
submission.

**4. THE PRE-HANDOVER CHECKLIST DID NOT HAVE A QUESTION FOR THIS, AND NOW IT DOES.**
Its four questions ask what the reader types, what the job reads, what the remote system
validates, and whether the artefact carries the order. **A fifth: WHICH OBJECT DOES THIS ACT
ON, AND IS ITS IDENTIFIER IN THE INSTRUCTION?** If the step says "the product", "the
function", "the listing" or "the subscription" rather than an id, it is not finished.

### WHAT TO DO ABOUT BUNDLE B, AND IT IS ONE READ THEN ONE CLICK

    AWS_PROFILE=relayshield aws marketplace-catalog list-entities \
      --catalog AWSMarketplace --entity-type SaaSProduct --no-cli-pager \
      --query 'EntitySummaryList[].[EntityId,Name,Visibility]' --output table

Every SaaS product this account owns, with its id. **Two rows will carry the Attack Surface &
Supply Chain name.** The one to publish is **`prod-szi2wdww3obry`**: it is the entity the
accepted agreement names as its resource, it is the one whose product code
`cmh79gzztkdtp0dlzbdepa643` holds the live entitlement, and it is the one that has been
metered. **`prod-v5nr5gjtdnofi` is the one that has been refused seven times, and it has never
had a subscriber.**

Then submit visibility against that id specifically -- through
`.github/workflows/marketplace_changeset.yml` with `product_id: prod-szi2wdww3obry`, which
takes the id as an input and cannot be pointed at the wrong row by a portal listing two
products with one name. **The portal's Update visibility button is what got us here.**

**AND DECIDE WHAT HAPPENS TO THE SECOND ONE BEFORE PUBLISHING EITHER.** Two public products
with the same name is worse than one unpublished: a buyer lands on whichever the search
returns, and only one of them can fulfil. It stays private, or it is withdrawn.

### THERE ARE THREE, NOT TWO, AND THE GUARD IS IN THE TOOL NOW

**Measured 2026-09-22.** `list-entities` returned **three** SaaS products named
*RelayShield - Attack Surface & Supply Chain API*, all `Limited`:

    prod-szi2wdww3obry   the real one -- agmt-29l852u6kqzmjh2me0pglvj9q,
                         product code cmh79gzztkdtp0dlzbdepa643, metered
    prod-v5nr5gjtdnofi   duplicate, never subscribed -- the seven refusals
    prod-p3ei5nmgufnnq   duplicate, never subscribed

**I predicted two rows and there are three**, which is the same defect one layer
down: I reasoned about how many duplicates there must be instead of reading the
list. One command answered it.

**AND THE SECTION ABOVE WOULD HAVE BEEN WORTHLESS ON ITS OWN**, by this file's
own closing rule: *if a turn produces a CLAUDE.md section and no change that
makes the failure impossible, it has written down an apology and billed a round
for it.* So the artefact changed in the same commit:

* `tools/marketplace_submit_changeset.py` REFUSES `UpdateVisibility` to `Public`
  against either duplicate, and the refusal names `prod-szi2wdww3obry`.
* **The refusal is narrow: only `Public`.** `Restricted` is allowed, because
  withdrawing a duplicate is the legitimate cleanup and a guard that blocks it is
  the CSM-SIMSWAP-1 shape -- one that gets loosened rather than obeyed.
* `bundle_b_finish_2026-09-21.md` STEP 8 is a workflow dispatch taking the id as
  an input, **not** the Management Portal button that selects by display name.
* Three tests in `test_bundle_b_changeset.py`, proven by deleting the guard (two
  failures) and restoring it.

**A portal that lists three identically-named rows is not a thing a reader can
get right, however carefully the step is worded.** The fix is the id in the
input and the refusal in the tool.

## BUNDLE B IS PUBLIC. prod-szi2wdww3obry, 2026-09-21.

    Product ID    prod-szi2wdww3obry          Status: Public
    Product code  cmh79gzztkdtp0dlzbdepa643
    Product ARN   arn:aws:aws-marketplace:us-east-1:239677749008:AWSMarketplace/
                  SaaSProduct/prod-szi2wdww3obry
    bundle_b_go_public   Succeeded  Sep 21 2026 8:48 PM EDT -> 9:51 PM EDT

Eight submissions: one create, one failed go-public (Sep 19), one succeeded
(Sep 21). **The entity that went public is the one the accepted agreement names**
-- `agmt-29l852u6kqzmjh2me0pglvj9q` -- so submitting by ID through
`marketplace_changeset.yml` rather than by display name in the portal is what
closed it, exactly as the seven-rejections section predicted.

**`prod-v5nr5gjtdnofi` AND `prod-p3ei5nmgufnnq` ARE STILL LIMITED AND STILL
CARRY THE SAME DISPLAY NAME.** Now that one of the three is Public that is no
longer cosmetic: a buyer searching the Marketplace sees one listing, and the
other two are duplicates that cannot fulfil. `marketplace_submit_changeset.py`
refuses to publish either and allows `Restricted`, which is the withdrawal.

### I BUILT A VERIFIER FOR A QUESTION THE PORTAL HAD ALREADY ANSWERED

Asked as "verify whether the metered call landed before I burn another rejected
submission". I read that as the question and built
`tools/verify_bundle_b_metering.py` for it. **The submission had already
succeeded three hours earlier**, and the Requests log on the product page says
so in one line.

**THE ORDERING RULE, and it is the cheap half of every diagnosis: before
building a check for whether something is READY to be attempted, check whether
it has already been ATTEMPTED and what happened.** The Requests log is one
glance and it is the authoritative record of every change set this programme
has submitted. It costs nothing and it is the first thing to look at, not the
last. This is the same shape as asking the founder to read a value out of a log
I could read myself -- a round spent on something a state read settles.

The tool was not wasted (it found the metering-response gap, three missing
patterns in the audit script's section 5, and that the log line cannot name the
product at all), but it answered a question nobody needed answered that hour.

### ARCHITECTURE DETAILS: "NONE OF THE ABOVE", AND IT IS NOT A JUDGEMENT CALL

The listing's Architecture details tab wants an AWS hosting pattern. Read from
the code rather than guessed:

* **Option 1, "runs entirely on AWS", is FALSE.** It requires that *any 3rd
  party dependencies* run on AWS. `/v1/metered/secret-scan` alone reaches
  GitHub, npm, PyPI, Docker Hub, Hugging Face and Postman -- its own price
  comment names all six -- and the other Bundle B endpoints add gopluslabs,
  DexScreener, tonapi, RDAP, Helius, Hudson Rock and HIBP. None of those runs
  in 239677749008.
* **Option 2, replicate or migrate data to AWS**, is a different product shape.
* **Option 3, "only the application plane runs on AWS", is ALSO FALSE**, and
  picking it to look better would be a different false claim: it asserts the
  CONTROL plane runs outside AWS, and ours does not. Key issuance, entitlement
  resolution, metering and DynamoDB are all in 239677749008.
* **Option 4 is what is left and it is accurate.** Its own text says the listing
  continues to publish; the only cost is a designation we are not entitled to.

**A public listing carries only claims that stay true without maintenance**, and
"all third-party dependencies run on AWS" would stop being true the next time an
endpoint adds a vendor. The conservative option is also the durable one.

**UNVERIFIED: AWS's own Architecture guidelines page is egress-blocked from the
container**, so whether they count an outbound SaaS API as a "3rd party
dependency" is read from the option text itself rather than from their
definition. The link is on that form. If it says they mean deployed components
rather than called APIs, option 1 becomes arguable -- and the form is
re-submittable ("if not approved, you can submit again"), so this is a cheap
thing to get wrong and an expensive thing to overclaim.

## THE DANGEROUS DIRECTION INVERTED THE DAY BUNDLE B WENT PUBLIC

**2026-09-22.** `bundle_b_withdraw.json` exists now (one `UpdateVisibility` to
`Restricted`, id from `--product-id`) so the two duplicates can be taken off the
board. Writing it opened a hole the same hour.

**`prod-szi2wdww3obry` WAS NOT IN `LIVE_ENTITIES`**, because that dict was
written the day before go-public succeeded. So the withdraw change set plus one
mistyped id would have taken the listing eight submissions bought straight off
the marketplace, past every guard, silently. **The three ids differ only by a
random suffix**, which is the shape that already cost seven rounds.

**The guard that was correct on Monday was the wrong guard on Tuesday.** It
refused `UpdateVisibility` to `Public` against a duplicate -- narrow on purpose,
so the withdrawal still worked. Nothing refused `Restricted` against the real
one, because on Monday the real one was not public and there was nothing to
protect. **A state change inverts which direction is dangerous, and a guard
pinned to the old direction reads as protection while covering nothing.**

`test_publishing_the_real_entity_is_allowed` had to be rewritten for the same
reason: it REQUIRED that publishing `prod-szi2wdww3obry` succeeds, which was
right on the day it was written and became wrong the moment it did. **A guard
that encodes today's answer rather than what the answer must ACHIEVE eventually
fails on correct code, and the temptation then is to loosen it.**

**Two smaller things found by RUNNING it rather than reading it:**

* **The field-size check reported `Restricted` (10) as OVER against the accepted
  `Public` (6).** An enum is not a length constraint, and a warning nobody can
  act on is how a check gets ignored. `ENUM_CLASS_PATHS` skips it.
* **The `LIVE_ENTITIES` refusal sent every case to
  `marketplace_add_dimension.py`, which cannot do `UpdateVisibility` at all** --
  a second tool that would also refuse them. It names the duplicate ids now,
  which is what the reader almost certainly meant. This file already recorded
  that misdirection once, in a comment forty lines above the code that did it.

All four proven by reintroducing the defect. **`Restricted` on a `Limited`
product is UNVERIFIED**: `docs.aws.amazon.com` returns 000 from the container and
no accepted change set in this repo uses that transition, so AWS's own
validation is the first thing that can answer it. It is an immediate refusal
rather than a review cycle, so getting it wrong costs seconds.

## THE MUSE BLOCKER WAS OVER-SCOPED BY HALF A DAY, BY ME, IN THE SCOPE DOCUMENT

`muse_connector_scope_2026-09-21.md` called the partner key *"a small build ...
Half a day."* **There is no build.** `relayshield_api.py:13073` already skips
`_check_keyless_ip_quota` on any valid `X-RS-API-KEY` and falls through to
`return handler(params)` with no free-tier decrement, no metering and no counter
inside `_verify_rs_api_key`. The cap's own comment names it as the intended
answer: *"The durable fix is per-install free-tier keys."*

**So it gates the LAUNCH, not the submission**, and the two run in parallel.
**Over-scoping a blocker is how a finished thing sits untouched**: half a day
gets scheduled behind other work, one existing operation gets done. The cost is
the same shape as claiming something is missing when it is merely unfetched.

`?source=muse` is registered in `_SOURCE_BANNERS` BEFORE anything is submitted,
with **no referer hosts** deliberately -- a connector platform's pages are not
where a click originates, and claiming `muse.ai` would attribute unrelated
arrivals to this listing. Verified by EXECUTING `_resolve_source`, not reading
it: `muse` logs `muse` and banners, an unregistered key logs `unmatched:` and
renders nothing.

## AWS MARKETPLACE ARRIVALS ARE ATTRIBUTED. THE BANNER WAS NAMING ONE BUNDLE OF TWO.

A note carried into this session said an AWS Marketplace arrival was
unattributable. **It is not**, and one grep settles it: the `aws` key in
`_SOURCE_BANNERS` has carried `aws.amazon.com` and `console.aws.amazon.com` as
referer hosts all along. **An absence needs the same evidence a presence does**,
and I nearly recommended work against one I had not checked.

**What WAS wrong is smaller and was caused by yesterday:** that banner named only
Bundle D's contents, so a buyer arriving from the Bundle B listing published on
2026-09-21 read a paragraph about a different product. Both are named now, in
capabilities rather than counts, because it is a page we cannot cheaply edit.

## NO ANNOUNCEMENT POST FOR BUNDLE B. THE PUBLISHABLE STORY IS THE TRAP, NOT THE SHIP.

Asked as whether Bundle B going public is worth a blog post. **Not as an
announcement.** The XSOAR rule already decides it: the angle is never "we
shipped an integration", it is what the thing DOES that a reader cannot do
today. A change set succeeding on the eighth attempt is a fact about our
paperwork and reaches nobody.

**There IS a real post in it and it is the failure rather than the success:**
three SaaS products carrying one display name, a Management Portal that selects
by name, seven refusals, and the one-command read (`list-entities`) that
separates them. Other AWS sellers hit this and nothing on the internet describes
it. The material is already written and it costs an afternoon.

**Gated on withdrawing the duplicates first**, which is also the post's ending:
here is the trap, here is how to detect it, here is how to fix it, here is the
guard now in our own tooling. Publishing it while two duplicates are still
listed is a claim anyone can check and find only half true. **Omit the entity
ids**; they are ours and they add nothing to the argument.

## THE CONSUMER-COMPELLING CHECKS ALL HAVE A VENDOR BILL. THAT IS WHY THE FREE SET IS THIN.

**2026-09-22, asked as "why not also add email checking to the Muse connector ... link and
wallet checking dont seem compelling enough."** The critique is right and the reason is
structural rather than a gap in the scope.

**FOURTEEN endpoints are in `KEYLESS_SCAN_ENDPOINTS`, not two, and TWELVE are crypto.** Only
`/v1/link-check` is universal. So the honest free set for a general consumer is one endpoint,
and reading the table rather than the scope document is what shows it.

**THERE IS NO EMAIL-CHECK ENDPOINT TO ADD.** `checkemail@` is a Cloudflare Worker: the whole
verdict model, and the 78 tests that pin it, are JavaScript in
`cloudflare_worker_checkemail.js`. Its only API calls are `/v1/scan-url` and `/v1/result`, and
`/v1/scan-url` is VirusTotal at $0.05 and has never been keyless. **A scoring model living in
a Worker is not an API surface**, and "add email checking" is a build, not a connector field.

**AND `/v1/breach` IS THE ONE THAT WOULD ACTUALLY HURT, FOR A REASON THAT IS NOT COST.**
`handle_breach` calls HIBP with ONE subscription key, has **no cache anywhere**, and handles
429 explicitly. **The $0.10 on the rate card is our RESALE price**, and I nearly recorded it as
our cost. HIBP bills a subscription with a rate limit, so the shared key is the scarce thing --
and the Telegram bot, the WhatsApp bot, the OAuth watchlist and every paying API customer are
on it. **A consumer platform pointed at breach does not run up a bill, it runs us into the
limit, and the 429 lands on the paying customers.** Invisible until it happens, which is the
quiet-alarm shape with revenue behind it.

**THE FIX IS POSITIONING, NOT AN ENDPOINT.** `/v1/link-check` is thin as "check a link" and
strong as **"check every link in my inbox"**, and Muse reads the inbox. Same endpoint, zero
vendor cost at any volume once a partner key lifts the per-IP cap. Breach is the right v2 and
needs a cache on `handle_breach` plus a partner rate budget first -- about a day, worth doing
regardless, and **until both exist, adding breach is a decision to degrade a live product.**

**The general form: before adding a capability to a free surface, ask what its UPSTREAM bills
and whether that upstream is SHARED.** A per-call bill is a cost question. A shared
rate-limited key is a blast-radius question, and the second one reaches customers who never
touched the new surface.

**Payments on the connector: NO**, and it is not a judgement call. Nothing is sold inside the
host, so claiming a payment surface invites review of billing we cannot show, and it is FD-14's
restriction shape with a different host's name on it.

## THE THREE MUSE FEATURES, AND THE TWO DEFECTS THAT ONLY EXECUTION FOUND

**Built 2026-09-22.** Batch link-check, a breach cache, and a partner budget on a
shared upstream. All three are runtime-shaped, which is why
`test_muse_connector_features.py` EXECUTES the handlers with boto3 and urllib
stubbed rather than reading them: an ordering, a fail-open and a partial result
rendering as a clean one are all invisible to a reader of the source.

**1. `/v1/link-check` TAKES `urls[]`.** Safe Browsing's `threatMatches:find`
already accepted a list and this file had been sending exactly two entries
(http and https for one domain) since it was written, so the batch is the
existing request shape used for what it could already do. **Deduplication by
DOMAIN is what makes it cheap** -- an inbox is fifty links across a dozen hosts
-- not concurrency. `_assess_domain` is shared by the single and batch paths so
they cannot drift.

**THE GUARD THAT MATTERS IS THE QUOTA, AND IT IS NOT OBVIOUS.** A batch is one
HTTP call and N domains of upstream work, so charging it as one call would have
**multiplied `KEYLESS_IP_DAILY_CAP` by 25** and turned link-check into precisely
the unmetered upstream proxy the cap's own comment says it exists to prevent.
`_check_keyless_ip_quota` counts UNITS now. A batch of 25 costs 25.

**2. `handle_breach` CACHES, keyed on `_sha256(email)` and never the address.**
Every failure path in that function returns 4xx/5xx before the cache write, so a
200 is a real verdict by construction -- which is the property that makes
caching safe and would not hold if any failure fell through to an empty list.
**Caching a 429 as "no breaches" serves an outage as good news for a day.**

**3. `_check_partner_upstream_budget` FAILS CLOSED, and that is a deliberate
divergence** from `_check_keyless_ip_quota` and `_check_demo_quota` two hundred
lines up, which both fail open. Those are cost guardrails and failing them open
costs us money. This one protects **other customers' access to a shared rate
limit**, so failing it open hands a partner the ability to starve paying
customers during exactly the blip that made the check unavailable. A comment in
the function says do not "fix" it to match its neighbours.

**THE ORDERING IS THE DESIGN: cache read, THEN budget charge.** A cache hit
costs a partner nothing, which is what makes the cache the thing that keeps a
partner inside its budget rather than a separate optimisation. Charging first
spends the budget on answers we already had. Proven by moving the call.

### THE SPEC LISTED ONLY THE PAID ENDPOINTS, AND THAT WOULD HAVE BLOCKED THE CONNECTOR

`relayshield_openapi_spec.py` carried 62 paths and **every one was
`/v1/metered/*`**. Neither `/v1/link-check` nor `/v1/wallet-risk` -- both live
and keyless for months -- was in it. **Muse generates its integration from the
spec**, so the connector would have pointed at a document describing only the
metered surface and none of what it is built on, which is also the FD-14
compliance trap pointed at the wrong endpoints.

That is **"a route added to the dispatch table is not a route", landing on the
SPEC rather than on the gateway.** Both routes exist at the edge already; only
the contract was missing, and the spec's own docstring says *"a spec that drifts
is worse than no spec"*. Verified by BUILDING it: 64 paths, both present, and
`urls` in link-check's request properties.

**The batch deliberately shares `/v1/link-check` rather than taking a new path.**
A new path needs an API Gateway resource, and this repo has paid for that
mistake more than once. The existing route carries it with no AWS change at all.

### AND MY OWN TEST STUB MADE EVERY VERDICT "high"

A bare `MagicMock` for `dynamodb` means `resp.get("Items")` returns a truthy
MagicMock, so **every domain scored an IOC-corpus hit** and the whole
link-check class passed with verdicts it had not earned. Only the one test
asserting a domain should NOT be flagged caught it.

**A stub that answers every question affirmatively is not a stub, it is a second
implementation that always says yes.** `_empty_ddb()` returns real empty
results. Worth remembering before writing `MagicMock()` for anything whose
return value a branch reads.

**Six defects reintroduced to prove the guards**: units dropped from the
dispatcher call, budget failing open, budget charged before the cache read, a
429 falling through to the cache, an unchecked URL presented as checked, and GSB
truncating past one chunk instead of chunking. Each fired on exactly its own
test.

**`relayshield_breach_cache` does not exist in AWS yet and the code SHIPS INERT
without it** -- `_breach_cache_get` fails soft to a live call, which is today's
behaviour exactly. `sh tools/setup_breach_cache.sh` creates it, **enables TTL**
(DynamoDB ignores a `ttl` attribute unless TTL is switched on, so skipping that
step means the cache never expires and serves a months-old verdict forever), and
asks the cheap question -- whether the role can already write to it -- before
proposing a grant the shared role has no inline budget left to make.

## ON DECK FOR THE NEXT SESSION: CREATE `relayshield_breach_cache` IN AWS

**Recorded 2026-09-22 at Andrew's request, in his words: "Add AWS rs_breach_cache as
ondeck ToDo for next session."** The table name is `relayshield_breach_cache`.

**ANDREW RUNS THIS, after the merge:**

    AWS_PROFILE=relayshield sh tools/setup_breach_cache.sh

**EXPECT**, and this is read out of the script's own `echo` lines rather than written from
memory, because an EXPECT invented by the writer is how a correct run reads as a failure:
section 1 prints `   239677749008  (correct)`; section 2 prints either `already exists --
leaving it alone` or `not present -- creating` then `created`; section 3 prints
`current: <status>` and then either `already on -- nothing to do` or `enabling on attribute
'ttl'` followed by `ENABLING`; section 4 prints the role name and **exactly two** decision
lines, `dynamodb:GetItem` and `dynamodb:PutItem`, each reading `allowed`.

**STOP IF** it prints `implicitDeny` on either write: the shared role
`relayshield-breach-check-role-1sapnwdl` is at 26 inline policies of a 10,240-byte budget
and 11 attached managed policies of 10 allowed, so the grant is not a one-liner and the
script deliberately does not attempt it. That is the IAM SPLIT runbook, not a quick fix.

**NOTHING IS BROKEN UNTIL THIS RUNS, AND THAT IS THE DESIGN.** `_breach_cache_get` fails
soft to `None`, so every call falls through to a live HIBP request, which is today's
behaviour exactly. The cache starts working the moment the table exists, **with no deploy**
-- so this is a state change in AWS and not a release.

**THE TTL STEP IS THE ONE THAT CANNOT BE SKIPPED.** DynamoDB IGNORES a `ttl` attribute
unless time-to-live is switched on for that attribute name. A table created without it
caches forever and serves a months-old breach verdict as current, which is worse than no
cache: a stale "no breaches" is a wrong answer rather than a slow one, and nothing raises.

**WHY IT MATTERS MORE THAN A CACHE USUALLY DOES.** HIBP is a **subscription with a rate
limit**, not a per-call bill, and the $0.10 on our rate card is a RESALE price, not a cost.
One key is shared by the Telegram bot, the WhatsApp bot, the OAuth watchlist and every
paying API customer, so **a 429 earned by one caller is served to all of them.** That is a
blast-radius question rather than a cost question, and it is invisible until it happens.

**And the cache is what keeps a partner inside its budget**, which is why the ordering in
`handle_breach` is cache read THEN budget charge: a cache hit costs a partner nothing.
Charging first spends the budget on answers we already had. A test pins that order.
