<!-- Verbatim sections moved out of CLAUDE.md on 2026-10-18, original order. Not auto-loaded.
     Find one with: grep -n 'WORDS' docs/claude_memory/INDEX.md -->

## AN ENDPOINT IS NOT SHIPPED UNTIL THE PREFLIGHT ANSWERS. curl CANNOT TELL YOU THIS.

**Found 2026-09-09 while wiring the Mini App watchlist, before it could cost anything, and it is a
new instance of the quiet-alarm shape rather than a new lesson.**

`relayshield_watchlist.py` returned no CORS headers at all. `relayshield_api.py` has carried
`Access-Control-Allow-Origin: *` for months, and the new file simply did not, because it was written
against the handler dispatch pattern and nobody looked at who calls it.

**The Mini App is served from its own hostname and posts `content-type: application/json`, which is
not a CORS-safelisted value.** So a browser sends an OPTIONS PREFLIGHT first and will not send the
POST at all unless it succeeds. Two consequences, and the second is the nasty one:

- A response without `Access-Control-Allow-Origin` is discarded by the browser AFTER it arrives. The
  Lambda logs a successful call and the user sees nothing.
- **A failed preflight means the real request is never sent, so there is no log line at all.** The
  symptom is a button that does nothing, and the server-side evidence is an empty log, which reads
  like the click never happened.

**And curl ignores CORS entirely**, so every terminal test passes on an endpoint that is dead in the
only client that uses it. That is the exact shape of the alarm that goes quiet rather than red.

So: `_CORS` on every response including the 400s and 404s, an OPTIONS branch answered BEFORE the
route lookup (a preflight carries no body and arrives at a path the browser has not been allowed to
POST to yet), `tools/create_watchlist_routes.sh` creates an OPTIONS method alongside every POST and
checks the preflight SEPARATELY and FIRST, and `test_miniapp.py` executes the dispatcher with boto3
stubbed rather than grepping it.

`*` rather than the Mini App's origin, deliberately: these endpoints authenticate on Telegram's
signed `initData` in the body, never on a cookie or an Origin header, so there is no ambient
authority for an origin allowlist to protect, and locking it down would break the widget for no gain.

**THE SECOND HALF, and it is the same mistake at a different layer.** The same script had to wait for
the Lambda to leave `Pending`:

    ResourceConflictException ... The function is currently in the following state: Pending

`create-function` RETURNS before the function can be invoked. That is the IAM propagation retry
already in that script, one operation later -- **an AWS call that succeeds, followed immediately by
one that assumes it finished.** Both failures were caused by doing the next thing at machine speed.
`aws lambda wait function-active-v2` is one line and the documented answer.

**The general form: after any AWS create, ask what the NEXT call assumes about it.** Creation
returning is not creation finishing, in IAM, in Lambda, in DynamoDB, or in API Gateway, where the
change is invisible until the stage is redeployed.

**AND THE CHECK I WROTE TO ENFORCE THE STATUS-CODE RULE BROKE THE STATUS-CODE RULE.** Its first real
run, the same day, printed exactly this and nothing else:

    -> 404, access-control-allow-origin: NONE
    STOP: the preflight did not succeed with an allow-origin header.

Correct verdict, unactionable output. **An API Gateway 404 and our own handler's 404 are different
problems with different fixes, and the BODY is the only thing that separates them** -- API Gateway
answers `{"message": ...}`, a shape our handler never produces, while our handler names the path it
was given, which is how a stage prefix leaking into `event.path` announces itself. The probe captured
the status code with `-o /dev/null` and threw the body away, so a stop that should have been
self-diagnosing cost a round trip instead.

So: **every probe in this repo prints the body of what it got, not a summary of it.** `curl -sS -i`,
and print it. `tools/diagnose_watchlist_routes.sh` is the read-only script that separates the four
causes in one run, including invoking the function DIRECTLY with the gateway taken out of the path,
which is the move that made `diagnose_agent_bait_routes.sh` pay for itself.

**The general form, and it is now three sessions old: a check that says a thing is wrong owes the
reader the evidence that says WHICH thing.** "It failed" is a round trip. "It failed and here is who
answered" is a fix.

### AND THE ANSWER WAS THE THIRD INSTANCE OF THE SAME RACE, IN THE SAME SCRIPT

The diagnostic settled it in one run, and the finding is worse than a bug.

Read the timestamps together. The Lambda's `LastModified` was **11:31:01 UTC**, so the CORS code was
live. The stage deployment `d41p0d` was created at **07:32:52 -04:00, which is 11:32:52 UTC**, and
the probe that 404'd ran seconds later inside the same script. An hour on, with nothing changed in
between, the identical request returned **204 with `access-control-allow-origin: *`** and the POST
returned `{"ok": false, "error": "unverified: open this inside Telegram"}` with CORS headers on it.
Steps 4 to 6 had already ruled out every other cause: six methods correct, six integrations pointing
at the right function, the stage serving the newest deployment, the function Active and answering a
synthetic OPTIONS with 204.

**`create-deployment` returns a deployment id before the edge serves the new resource set.** So this
is the same class as the two failures already fixed inside `create_watchlist_lambda.sh`, in the same
session, by the same person:

    create-role       -> "the role cannot be assumed by Lambda"
    create-function   -> "the function is in state: Pending"
    create-deployment -> a 404 at the edge for a few seconds

**AND THE REPO ALREADY KNEW.** `tools/create_mpp_settlement_lambda.sh` hit this exact race on
2026-09-05 and carries an inline retry with the diagnosis written above it, including the sentence
*"a propagation race that reports as a hard failure is worse than a slow script: it sends someone
diagnosing a routing bug that does not exist."* A script written four days later probed once,
because that knowledge lived in a neighbouring file's comments and nothing carried it across.

**A LESSON RECORDED IN ONE FILE IS NOT A LESSON THE NEXT FILE LEARNS.** That is the real finding, and
the fix is structural rather than another comment: `tools/lib_await_route.sh` holds `await_http`
once, and `create_watchlist_routes.sh`, `create_link_check_endpoint.sh` and
`create_agent_bait_scan_routes.sh` all source it. The last two had the same single-probe bug and had
simply been getting away with it.

**The half that keeps it from becoming a new problem: only 403, 404 and a failed connection are
waited on.** Those are what an undeployed route returns. Every other status is a real answer from a
component that is listening, so it returns immediately. A loop that waits out a 500 turns a clear
fault into a slow one, which is the "a probe that cannot tell must not block" rule pointed the other
way. Verified in this container against a live host: it succeeds on the first try, returns instantly
on a real non-matching answer, and retries only the 404.

**One place it deliberately is NOT used**, because the helper cannot tell: the second agent-bait
probe EXPECTS 403, which is also a propagation code. Ordering does that work instead -- the first
probe returning 402 proves the stage reached the edge, and the second request goes to the same stage
moments later.

---

## PUBLISHING TO DEV.TO. ONE COMMAND. DO NOT RE-DERIVE THIS.

**Written 2026-09-07 after ONE post took FOUR ROUNDS, every one of them my fault and none of them
about the writing.** Andrew's words: *"I'm frustrated and wasting way too much time."* He was right,
and the cost was not any single bug. It was that each round fixed one symptom and the next round
found the same cause somewhere else in the same file.

**THE PROCEDURE. Two commands, and nothing else.**

    python3 tools/publish_devto.py <file>.md --dry-run     # sends nothing
    python3 tools/publish_devto.py <file>.md --publish     # needs DEVTO_API_KEY

The key is read from the environment, never an argument, and is prompted with
`read -rs "DEVTO_API_KEY?..."` so it never echoes and never enters shell history. Get one at
<https://dev.to/settings/extensions>, under "DEV Community API Keys".

**NEVER PASTE FRONT MATTER INTO THEIR WEB EDITOR AGAIN.** Two attempts failed on 2026-09-07 and
neither produced an error: the front matter simply rendered as visible text. Retyping a structured
document into a web form is a step that fails silently, and the API is a step that fails with an
HTTP status and a message. The syndication file is generated and committed, and the script sends it.

**The keys are not the problem, and checking them again is a wasted round.** Verified 2026-09-07:
`title`, `published`, `description`, `tags` (four maximum, comma separated) and `canonical_url` are
all supported by the markdown editor. If a paste fails it is the paste, not the schema.

### THE ONE CAUSE BEHIND THREE OF THE FOUR ROUNDS: dev.to is behind Cloudflare

**Cloudflare 403s urllib's default `Python-urllib/3.x` user agent before the request reaches
anything.** That single fact produced, in order:

1. The canonical liveness probe reporting **403** on a page that a browser and `curl` both load at
   200, which blocked a finished post from publishing.
2. My first diagnosis of it, *"the Worker does not answer HEAD"*, which was wrong: a grep of
   `cloudflare_worker_blog.js` shows it does not branch on `request.method` at all.
3. `GET /api/articles/me/all` returning **403**, one function further on, **because I fixed the
   probe and did not generalise the fix.**

**So: every outbound request in `tools/publish_devto.py` sends a browser user agent, and any new
one must too.** A 403 from dev.to is Cloudflare rejecting the client far more often than the API
rejecting the key; a bad key gives 401.

**The general rule, which is now its own CLAUDE.md section:** a status code is a fact about the
REQUEST you made, not about the resource you asked about. And when a fix turns out to be about the
CLIENT rather than the endpoint, apply it to every call in the file in the same commit, because the
next call will have the same problem and finding that out is another round trip.

### THE DESIGN RULE THAT COST THE MOST: no probe may block the publish

Two checks in this script are probes rather than facts, and **both warn and continue** now:

- **Is the canonical live?** Only **404 and 410** block, because only those unambiguously mean "not
  published". 403, 405, 429, any 5xx and a refused connection mean *this probe could not tell*.
- **Does this post already exist?** If listing the account's articles fails, it posts anyway and
  says so. Worst case is a duplicate, which is visible on the dashboard and deletable. Blocking a
  finished post is worse than a duplicate.

Both behaviours are tested by triggering them, the second with the network faked so the POST is
observed to still happen.

### THE ORDERING RULE THAT IS REAL, AND IS THE ONLY HARD ONE

**The canonical must be live before dev.to publishes.** dev.to is a LIVE copy carrying
`canonical_url`, unlike Medium which takes a snapshot. A canonical that 404s tells every crawler our
canonical does not exist and hands dev.to the canonical position for our own post. Syndication files
therefore ship `published: false`, and `--publish` flips it.

That is the ONE thing worth stopping for. Everything else warns.

### HUGGING FACE IS NOT A SYNDICATION TARGET. IT TAKES AN ORIGINAL.

Verified 2026-09-08 from the community article editor: it has Owner, Slug,
thumbnail and Coauthors, and **no canonical URL field**. Every other channel in
the house order either sets a canonical properly (dev.to) or snapshots with one
(Medium). HF can do neither, so a full copy there is a duplicate competing with
our own canonical instead of pointing at it.

**So HF gets a shorter ORIGINAL piece written for its audience, linking the
canonical for the long version.** `blog-agent-bait-scan-hf.md` is the pattern.
Publish at <https://huggingface.co/new-blog>, owner `relayshieldadmin`; the title
is the first `#` heading in the body, so the file pastes as-is.

**AND THE CHECK THAT MATTERS BEFORE ANY HF POST: name only tools the Space
actually has.** On 2026-09-08 a draft claimed the agent-bait check was "already a
tool on the Space". It is not: `hf-space-mcp-server/app.py` declares thirteen
tools and no agent-bait scan. That is the `_APIFY_BANNER` mistake in a new place,
and it was caught only because the plan carried an explicit instruction to verify
it. huggingface.co is egress-blocked from the container, so the repo copy is the
best evidence available and the DRIFT RULE applies: it is not proof of what is
deployed. Grep `app.py` before naming a tool, and never upgrade "the repo has it"
into "the Space has it" without opening the Space.

### The file, and how to make the next one

`blog-agent-bait-scan-devto.md` is the pattern: DEV front matter, then a short runnable lead-in
because their readers want the thing before the thesis, then the canonical post body with the API
link switched to that channel's own `?source=` key. Generate it from `blog_markdown/`, never by
hand, and register the `?source=` key BEFORE it ships.

**Tags: four maximum and they must already exist on DEV.** `ai`, `security`, `devops`, `opensource`
are the safe set. `mcp` and `aiagents` are worth trying first for anything agent-shaped; a tag that
does not exist comes back as a 422 naming it.

---

## A STATUS CODE DESCRIBES YOUR REQUEST, NOT THE RESOURCE. AND A PROBE THAT CANNOT TELL MUST NOT BLOCK.

**Added 2026-09-07, after a check I wrote stopped a finished post from publishing over a page that
was perfectly fine, and after I then misdiagnosed it twice in a row.**

`tools/publish_devto.py` refused to publish because the canonical returned **403**. The canonical
loads in a browser and returned **200** to Andrew's own `curl` minutes earlier.

**First wrong diagnosis: "the Worker does not answer HEAD."** Plausible, since the probe used HEAD.
`cloudflare_worker_blog.js` does not branch on `request.method` anywhere, so it was wrong. **Second
wrong diagnosis avoided only by grepping the Worker before asserting it.** The likelier cause is
Cloudflare refusing urllib's default `Python-urllib/3.x` user agent, which curl and a browser do not
send.

**The lesson is the 402-price lesson in a new costume.** That one: two components can return the
same shape of success, so verify the field that differs. This one: **a status code is a fact about
the REQUEST you made, not about the resource you asked about.** A 403 answered "is a scripted
request from this client allowed", which nobody asked. Probe with the method, headers and user agent
a real reader would send, or accept that you have not asked the question you think you asked.

**And the half that actually cost the time, which is a design rule rather than a diagnosis.** The
check was a GATE, so an inconclusive probe became a hard stop between a finished post and its
publication. That is a worse failure than the thing it was guarding against.

**Only an unambiguous answer may block. Everything else warns and continues.** For "is this page
published", 404 and 410 are unambiguous. 403, 405, 429, every 5xx and a refused connection all mean
*this probe could not tell*, and a probe that cannot tell has no standing to stop the work. The
warning says so in those words and names the URL to open.

Applies to every guard in this repo, not just this one: **before writing a check that blocks, ask
what its inconclusive answer looks like, and make sure that answer does not read as failure.** A
check that cries wolf gets disabled, and then it is not a check at all.

---

## TWO THINGS RESCUED FROM THE SUPERSEDED 2026-09-05 LIST

Kept because regenerating a list deletes the reasoning inside it, and both of these are decisions
rather than status.

**A REGISTRY RECORD IS IMMUTABLE ONCE PUBLISHED, AND ITS VERSION IS NOT THE PACKAGE'S VERSION.**
That is what closed FD-8 after two failed attempts. A metadata fix needs a NEW VERSION STRING,
because the existing record cannot be edited. And the server entry's version is independent of
`packages[].version`: **0.2.12 pointing at package 0.2.11 is legal**, and is exactly what shipped,
with no PyPI release needed. Worth reading twice, because on 2026-09-07 I saw that same 0.2.12
against PyPI's 0.2.11 and called it a live breakage before checking the field that decides. The
record's own version and the version it PINS are different fields.

**`crewai-relayshield` IS FAIL-CLOSED, AND DECLARES NO HARD DEPENDENCY ON CREWAI. Do not
re-litigate either.** The gate core is pure stdlib and `install()` imports the framework lazily;
pinning crewai would make the package uninstallable next to a different crewai version for no gain.
Only `no_known_finding` proceeds, because a gate that lets a call through when the check times out
is a gate anyone can remove by causing a timeout. `fail_open=True` releases `DEFER` only, a check
that could not be COMPLETED, while a completed `REVIEW` still blocks and a `FINDING` always blocks.
There is deliberately no setting that lets a known-bad target through, and a test asserts it.

---

## WHERE 2026-09-05 LEFT THINGS — read this first

## READING THE LIVE BUNDLE D ENTITY ANSWERED THREE QUESTIONS AND FOUND TWO OF MY DEFECTS

**2026-09-09. The DescribeEntity capture is the most informative artefact this programme has
produced, and it was available the whole time.**

### 1. agent-bait-scan is NOT in Bundle D. Six dimensions, and none of them is it.

    agentic_bundle_access      Entitled            the monthly minimum
    bulk_identity_risk         ExternallyMetered
    tech_stack_cve             ExternallyMetered
    mcp_registry_risk          ExternallyMetered
    prompt_injection_breach    ExternallyMetered
    llm_credential_exposure    ExternallyMetered

`LastModifiedDate 2026-08-06`, `ProductState Active`, `Visibility Public`. So the listing is healthy
and the dimension is simply absent, exactly as `AWS_DIMENSION_NAMES` says it should be.

### 2. MY GUARD KNEW TWO OF THOSE SIX, AND THAT WAS THE DANGEROUS HALF

`tools/marketplace_add_dimension.py` refused any capture missing `mcp_registry_risk` or
`prompt_injection_breach`, because I took the list from `AWS_DIMENSION_NAMES`. **That table maps the
endpoints we METER through the Marketplace rail. It is not the listing's rate card.** Four
dimensions are on the product and not in that table, including the **Entitled** one that carries the
monthly commitment.

So a capture holding only those two would have PASSED, and a change set built from it could have
dropped four live dimensions and the monthly minimum with them. That is the 2026-07-27 "prices
rolled back to placeholders" failure, with a guard in front of it that was looking at the wrong
list. All six are named now, and a two-dimension capture is refused by test.

**The general form: a guard is only as good as where it got its expectations.** Deriving them from a
neighbouring table in our own code felt rigorous and was not; the authoritative list was one
DescribeEntity away.

### 3. THERE ARE TWO HF SPACES, AND THE WATCHER WAS WATCHING THE LESS IMPORTANT ONE

The listing carries `ApiType: MCP_SERVER` and this endpoint:

    https://relayshieldadmin-relayshield-agentic-attack-surface-aws.hf.space/gradio_api/mcp/sse

Note the `-aws` suffix. `hf-space-mcp-server/app.py` says outright that the same file is deployed
twice: the public Space, and a second one with `AWS_MARKETPLACE_MODE=true` that scrubs every
reference to the self-serve signup page, because **AWS's Tier-1 audit treats a reachable link to an
external payment page as a violation and that failed Bundle D's visibility request twice.**

**The AWS Space is a PUBLISHED product's declared endpoint.** If it stops answering, buyers who
arrived through AWS Marketplace hit a dead URL. That is worse than the public Space going quiet, and
until today nothing watched it: `tools/check_hf_space.py` named only the public one. It now checks
both, reports them separately, and the worst verdict decides the run.

### 4. TWO THINGS THE ENTITY SHOWS THAT ARE NOT MINE TO FIX SILENTLY

**The public listing quotes corpus figures this repo has since corrected.** Three times, in
ShortDescription, LongDescription and Highlights: *"5.0M+ indicators of compromise, 3,750+ malware
families, and 85+ monitored criminal Telegram marketplaces."* The corrected figures recorded on
2026-09-03 are 494K distinct indicators, 5.8M sightings and 95 channels. MEASUREMENT DOCTRINE says
the headline is not quoted at all, and this is a PUBLIC page a competitor can read. Changing listing
copy is a change set, so it batches with the dimension rather than being a separate submission.

**The delivery option targets ONE account.** The product's `Targeting.PositiveTargeting` lists eight
buyer accounts, but the DeliveryOption inside `version-baq5najnqgsam` lists only `239677749008`,
which is ours. Whether that restricts who can actually subscribe is a question for the Marketplace
console rather than something to assert from a JSON field, but it is worth asking, because a public
listing nobody outside our own account can take up would explain a lot.

---

## THE MINI APP MERGE DID NOT DEPLOY IT, AND A DEPLOYED WORKER IS NOT A MINI APP

Found 2026-09-09, asked as "I ran the merge that deployed the Tg miniApp. How do I access it on Tg?"
Two separate blockers, either one enough on its own, and neither is a defect in the code.

**1. The merge never reached GitHub.** `origin/main` is at `556b4f1` and carries neither
`cloudflare_worker_miniapp.js` nor `wrangler.miniapp.toml` nor `.github/workflows/deploy_miniapp.yml`.
That is the LOCAL MERGE IS NOT A PUSH rule, and **it has a second edge nobody had written down: a
workflow file that is not on the default branch cannot be dispatched from the Actions UI either.**
So the usual fallback -- Claude cannot dispatch, Andrew clicks *Run workflow* -- was not available.
There was no route to deploying this that did not start with pushing `main`.

**2. A Cloudflare Worker at `app.relayshield.net` is a web page. Telegram does not serve an arbitrary
URL as a Mini App.** It exists only after `/newapp` in @BotFather, which is what mints
`t.me/relayshield_bot/<short_name>` and gives `?startapp=` something to attach to. **That step is not
in the repo and could not be** -- it is a conversation with a bot, not a file -- and its absence from
the Mini App v1 work was a real gap. `miniapp_launch_checklist.md` now carries it, with the short
name pinned to `app` because `miniapp_discovery_and_stripe_choice.md` and item 1 already assume
`t.me/<bot>/app` in every planned link. **SUPERSEDED 2026-09-10: the registered short name is
`idcheck`, and every planned link now reads `t.me/relayshield_bot/idcheck?startapp=<source>`.**

**The likely third failure, flagged before it fires:** `wrangler.miniapp.toml` uses the zone-route
form, like blog/badge/partners/pricing/support. **A zone route attaches to a hostname, it does not
create one.** If `app` has no proxied DNS record in the zone, wrangler reports a successful deploy
and the hostname does not resolve -- the deploy-succeeded-and-nothing-works shape again.

**Do not submit to any announcement channel before opening it on a phone.** Item 1 is explicit:
each channel gives one first impression, `@trendingapps` is 3.9M of them, and a submission landing
while the link 404s spends it.

## THE PRE-COMMIT HOOK'S DISCOVERY VALUE HAS NEVER BEEN MEASURED, AND IT HAS BEEN MEASURABLE SINCE 2026-09-03

Asked 2026-09-09 as "is there a similar benefit to an IDE widget". The question rests on rsscan
having been a good discovery surface, and **nothing in this repo could say whether that is true.**
`rsscan` and `rsscan-deps` are registered `_SOURCE_BANNERS` keys, so every arrival has been
attributed and logged in CloudWatch the whole time. Nobody counted them. FD-1 says **DONE**, and
"done" is a fact about shipping, not about reach.

`tools/source_arrivals.py` closes it, and it runs on the Mac:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/source_arrivals.py --days 90 --key rsscan

It reports the window it OBSERVED rather than the one asked for, prints `unmatched:` rows first
because each is a live link naming a key that does not exist, and separates ZERO ARRIVALS from
UNREGISTERED, which are different findings with different fixes.

**IT ALSO CAUGHT ITSELF, which is the part worth carrying.** The first `registered_keys()` walked
only `ast.Assign`, so it read `_SOURCE_ALIASES` and silently skipped `_SOURCE_BANNERS` -- declared as
`_SOURCE_BANNERS: dict[...] = {`, an `ast.AnnAssign`. It returned 117 keys, which looks exactly like
a working parse, with every real banner missing. The tool would have reported `rsscan`, `tg-widget`
and `tg-miniapp` as UNREGISTERED when all three are registered, and an unregistered key is a
completely different conclusion from a channel that produced nothing. Nothing errored. Found by
running it and grepping the handler to check -- rule 14 applied to my own tool rather than to a
command. It now asserts a floor: an empty table raises rather than reporting a false absence, and
`test_source_arrivals.py` pins it against an independent parse.

**The answer to the widget question is in `ide_widget_scope.md`**, and the short form is: three of
the four named categories are not ours (no SAST anywhere in this codebase, and "malware detection"
overstates an indicator match), one is completely ours and has no IDE incumbent, and **rsscan is the
wrong host for it because the direction is opposite** -- rsscan reads `git diff --cached`, your own
authored change, while agent-baiting is about files somebody else wrote that your agent is about to
read. Measure first, read the VS Code Marketplace rules second, build one narrow thing third.

## A DEPLOY PATH IS NOT DRIFT DETECTION, AND relayshield-oauth-watchlist-monitor HAD ONLY THE FIRST

Asked 2026-09-09 as "we also need to map the rs-watchlist.py in the deployer". **It is already
mapped**, and has been: `deploy_lambdas.yml` carries it in the `paths:` trigger, the manual-dispatch
list and `LAMBDA_MAP`, and `iam_github_deploy_invoke.json` carries its ARN. Nothing to do there.

**What it did not have was a drift check**, and that is the gap that was real. The telegram, whatsapp
and discord handlers are all mapped in the deployer AND watched in `lambda_drift_check.yml`,
deliberately, because "having a deploy path is not the same as never being hand-deployed again". The
watchlist monitor was in the deployer only, so the question "has anyone hand-deployed over it" had
never been asked of it. It is now watched.

**`relayshield_mpp_settlement.py` was added to the drift check at the same time, and deliberately NOT
to the deployer.** `tools/check_deploy_invoke_policy.py` prints "granted but not in LAMBDA_MAP" for
it on every run and Top-15 item 4 is to close that -- but nothing has ever compared its live package
against main, so mapping it now would be mapping a function whose drift is unmeasured. Watch, read
the first diff, then map. A clean diff makes item 4 one line; a dirty one makes it a recovery, and
learning that from a red check costs nothing while learning it from a deploy costs the live code.

## SMITHERY NOW POINTS AT THE HOSTED HF SPACE. CHANGED 2026-09-09, AND THE CLI SCHEMA IS NOT WHAT WE THOUGHT.

**This SUPERSEDES the section immediately below it, which is kept because its finding was correct on
the morning it was written and its process note is the reason this one exists.**

Two things changed, and the second was a surprise that would have cost a round if it had been
guessed at instead of read.

**1. The file points at the hosted Space, because that is the listing we actually want.**
`mcp_registry/smithery.yaml` now carries `target: remote` and

    https://relayshieldadmin-relayshield-agentic-attack-surface.hf.space/gradio_api/mcp/sse

the SAME URL the AWS Marketplace entity registers as Bundle D's `EndpointUrl`. The PUBLIC Space, not
the `-aws` one: they run the same code, but `AWS_MARKETPLACE_MODE=true` scrubs every reference to the
self-serve signup page for AWS's Tier-1 audit, and a Smithery visitor is not an AWS buyer and should
be able to find the way to buy. That is FD-15 answered: one hosted URL, everywhere.

**2. THE MODERN SMITHERY CLI READS EXACTLY TWO KEYS OUT OF THAT FILE.** Read from `@smithery/cli`
4.11.1 on the npm registry, not from a docs page -- smithery.ai is egress-blocked from the container
and npm is not, which is the BLOCKED SOURCE WAS REACHABLE ALL ALONG rule paying for itself a second
time. Its parser is literally:

    z.object({ name: z.string().optional(),
               target: z.enum(["local","remote"]).optional() }).loose()

`.loose()` keeps unknown keys, which is why the rest of that file is harmless documentation. **The
elaborate `startCommand` / `configSchema` / `commandFunction` block that two previous sessions argued
about, corrected, and argued about again is the LEGACY v1 schema** from when Smithery scanned a
GitHub repo and built the server itself. It is not read by the CLI that publishes today. We spent
three sessions perfecting a file the tool mostly ignores.

**And publishing a hosted server is ONE command, from the CLI's own README:**

    smithery auth login
    smithery mcp publish <url> -n <org/server>

The login is not optional and is not "you logged in earlier" -- that is the `mcp-publisher` 401 that
cost a round, and the rule is that a block driving an authenticated CLI carries its auth step every
time.

**FD-11 IS THEREFORE NOT BLOCKED AND NEVER NEEDED A BUILD.** It is one command against a URL that
already answers.

**THE URL IS WATCHED, AND THE WATCH WAS LOOKING AT THE WRONG THING UNTIL TODAY.**
`tools/check_hf_space.py` checked the Space's HTTP front door and the HF API's runtime stage. Neither
says anything about whether the MCP server is MOUNTED. `app.py` passes `mcp_server=True` to
`demo.launch()`, and its own comments record a previous Gradio upgrade changing how that route is
served -- so dropping that argument, or upgrading past a rename, would have left the watcher green
forever while every directory we are listed in resolved to a 404. It now probes
`/gradio_api/mcp/sse` itself on both Spaces, treats 404/405/410 there as DOWN, and reports
`/gradio_api/mcp/` (streamable HTTP) as information so "the route moved" and "the server is down"
are one line apart instead of an afternoon apart. `test_hosted_mcp_pointer.py` pins the URL in
`smithery.yaml` against the one the watcher probes, because advertising a URL that nothing watches is
the quiet alarm with an audience, and advertising one the watcher does NOT probe is worse: the alarm
is green and pointed at the wrong target.

---

## SMITHERY POINTS AT THE PyPI STDIO SERVER. SETTLED 2026-09-09, IT IS NOT THE HF SPACE.

Andrew asked me to double-check the recollection that Smithery had been pointed at the HF MCP
server. It has not, and the check is now on record from the copy that actually matters.

**`~/mcp-live/smithery.yaml`, grepped on the Mac**, which is the file Smithery reads:

    27:  type: stdio
    44:  commandFunction: |
    46:      command: 'uvx',

No `url`, no `hf.space`, nothing hosted. It is the stdio PyPI package, identical to the copy in
`mcp_registry/`. So both copies agree and neither points at HF. The 2026-09-05 change corrected this
file to describe the RIGHT server (PyPI, sixteen real tool names) after a previous version described
a Node server that does not exist; it never pointed it at the Space.

**Why this matters rather than being a filing detail.** stdio and hosted-HTTP are two different
listings with two different visitors. A stdio entry tells someone to install a Python package; a
hosted entry hands them a URL. FD-15 exists because Grok Bot connectors, Smithery and possibly
OpenAI all want the SAME hosted URL, and we have two candidates already serving MCP over HTTP (the
HF Space and the Apify Actor) with no decision recorded about which one a stranger gets.

**So FD-11 is not blocked and never was: the stdio listing can ship today.** What is undecided is
whether we ALSO want a hosted entry, and that is FD-15's question, not this file's.

**The process note worth keeping.** The right answer here came from one grep on the machine that
holds the file, after this container could only report what `origin/main` said. That is the
"IT IS NOT IN THE REPO IS A CLAIM ABOUT ORIGIN" rule working in the direction it was written for:
report what you checked, name the one command that settles the rest, and let it be run.

---

### WHAT 2026-09-09 SHIPPED, so the next session does not re-derive it

**All of it is on `claude/top-15-todos-summary-cgjupn` and pushed.** The lessons are written up in
their own sections above; this is only the state.

- **The Mini App watchlist is LIVE end to end.** `relayshield-watchlist` exists, is Active, and all
  three `/v1/watchlist/*` routes answer with CORS. Proven by the refusal an unsigned request gets:
  `{"ok": false, "error": "unverified: open this inside Telegram"}` with
  `access-control-allow-origin: *` on it. Three defects were fixed getting there and every one is
  written up above: no CORS at all, `create-function` returning before Active, and
  `create-deployment` returning before the edge serves the route.
- **`tools/lib_await_route.sh`** is the shared propagation wait, sourced by three route scripts.
- **`tools/diagnose_watchlist_routes.sh`** is read-only and separates four causes in one run.
- **Smithery now points at the hosted public Space** and `test_hosted_mcp_pointer.py` pins that URL
  against the one `check_hf_space.py` probes.
- **The HF watcher probes the MCP endpoint itself**, on BOTH Spaces, not just the front door.
- **The Bundle D change set is built and unsubmitted**: dimension AND listing copy in ONE change
  set, guarded against the stale corpus figures.

**Tests: `test_miniapp.py` 39, `test_hosted_mcp_pointer.py` 8, `test_workflows_parse.py` 16
workflows, all green. `test_agent_bait_scan.py`, `test_agent_bait_skill.py`,
`test_relayshield_widget.py`, `test_mpp_settlement.py`, `test_developer_signup_banners.py` all OK.**

### THE TOP 15, REGENERATED 2026-09-09

**Regenerated, not annotated.** Item 1 of the 2026-09-08 list (build the Mini App) is BUILT, and
items 2 and 3 (FD-15, the HF watcher) are closed, so the top of the list has moved.

**Closed since 2026-09-08:** FD-15 is decided and implemented (one hosted URL, watched). The HF
Space watcher is built and now checks the MCP endpoint rather than the front door. The Mini App and
its watchlist are built and live. The Bundle D tooling is finished and its guard defect is fixed.

---

1. **Map `relayshield_watchlist.py` in the deployer. THIS IS NOW UNBLOCKED AND IT IS THE TOP ITEM.**
   The function exists in AWS, the routes are wired, and it is in NEITHER `deploy_lambdas.yml`,
   `lambda_drift_check.yml` NOR `iam_github_deploy_invoke.json`. That is the exact combination --
   source in the repo, live traffic, no deploy path -- that this repo has now been bitten by SIX
   times, most expensively by `relayshield_developer_signup.py`, which grew a 700-line billing path
   nobody could see. **Do it before the file accumulates a single hand-deployed edit.**
   Three edits, in this order and no other:
   (a) `iam_github_deploy_invoke.json` FIRST, then `sh tools/apply_deploy_invoke_policy.sh`, or the
       first CI deploy repeats run 134's denied import probe;
   (b) the `paths:` trigger and `LAMBDA_MAP` in `deploy_lambdas.yml`, plus the drift check;
   (c) `python3 test_workflows_parse.py`.
   **The mapping commit MUST touch `relayshield_watchlist.py` itself** -- the deployer ships a
   function only when the push changed its source, so a commit touching only workflow files deploys
   nothing and the map looks applied while nothing has moved.

2. **FD-11: Smithery. Two commands, ten minutes, the cheapest open item on this list.**

       npx -y @smithery/cli@latest auth login
       npx -y @smithery/cli@latest mcp publish https://relayshieldadmin-relayshield-agentic-attack-surface.hf.space/gradio_api/mcp/sse -n relayshield/relayshield

   UNVERIFIED from the container: there is no Smithery credential here. Node 20+. If the namespace
   does not exist, run `namespace list` rather than guessing a name.

3. **Bundle D: submit the change set.** `ANDREW CLICKS`: Actions, Marketplace Dimension,
   mode `plan` first and READ the four `was:`/`now:` blocks, then mode `apply` with
   `confirm_entity: prod-kkvurtspreofy` and `include_listing_copy: true`. It carries the
   `agent_bait_scan` dimension AND the copy in one change set, which is one AWS review cycle.
   **Carry this with it:** `AWS_DIMENSION_NAMES` in `relayshield_agentic_api.py` still says
   agent-bait is held back pending a measured false-positive rate, which will contradict the live
   listing the moment this lands. One-line comment fix, same session as the submission.

4. **Run the six Mini App discovery routes, now that v1 exists.** The sequencing risk is spent
   otherwise: each announcement channel gives ONE first impression. The ranking, from
   `miniapp_discovery_and_stripe_choice.md` §2 and NOT to be re-litigated:
   (1) the Telegram blog channel, the only surface whose audience chose us;
   (2) Mini App announcement channels -- `@trendingapps` 3.9M, `@web3telegrambotx` 72,742,
       `@findminiapp` 56,380, `@onclicka_tma_en` 33,723, `@telegtapps` 9,671;
   (3) Mini App directories, tApps Center and family;
   (4) attributed deep links `t.me/relayshield_bot/idcheck?startapp=<source>`, keys registered FIRST;
   (5) the bot's menu button, cheap rather than high-reach;
   (6) TON catalogues, only if TON scans ship.

5. **Watch the first few HF watcher runs.** `.github/workflows/hf_space_watch.yml` runs every six
   hours and now probes `/gradio_api/mcp/sse` on both Spaces. A DOWN opens an issue; UNREACHABLE
   reddens the run without one. **The first runs are the ones that tell us whether the MCP probe is
   calibrated** -- if a sleeping Space reports UNCLEAR every time, the wake ordering needs work.

6. **Map `relayshield-mpp-settlement` in `deploy_lambdas.yml`.** Still in neither the `paths:`
   trigger nor `LAMBDA_MAP`; `tools/check_deploy_invoke_policy.py` prints it as
   "granted but not in LAMBDA_MAP" on every run of `test_workflows_parse.py`. Same rule as item 1:
   the commit must touch the `.py`.

7. **MPP settlement selftest, reads-only.**
   `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/mpp_settlement_selftest.py --reads-only`.
   Answers whether the account has crypto deposit addresses and a business profile. A 403 is the
   text to send `machine-payments@stripe.com`.

8. **FD-14: read OpenAI's plugin directory rules. Reading IS the task.** Largest audience of the
   three directories. **Do not scope the work before reading the rules** -- FD-2 cost a day on a
   destination whose own page said the PR would be closed unread. Three questions decide it: is a
   plain MCP server submittable or must it carry Apps SDK components, what is the stated bar, and is
   a paid pay-per-call tool eligible at all. The hosted URL FD-15 settled is ready if it needs one.

9. **Rewrite the MCP registry listing copy to lead with counterparty authorization.** The record
   still describes the server as a list of tools. Needs an `mcp-publisher` run, so batch it with
   anything else the record needs rather than spending a version on copy alone.

10. **Apify: the form is OPEN NOW, not November.** Saurav Jain in `#apify-writers`, 2026-09-07.
    Andrew has DM'd his username and asked for the form link. **The disqualifier is unchanged: the
    article must NOT appear on blog.relayshield.net first.** Submitting is not publishing.

11. **The Commerce Agents blog post.** `commerce_agents_integration.md` has the argument, resting on
    a primary source Anthropic published saying authorization is the deployment's problem.
    **Register `?source=commerce-agents` BEFORE it ships.** No PR to that repo; its README says it
    accepts nothing.

12. **ABS-1: the measured false-positive rate.** `tools/agent_bait_fp_rate.py --pull` runs inside
    the Marketplace workflow so the numbers and the change set come from the same run. This is the
    gate item 3's code comment names, and the agent-bait post is the thing most likely to produce
    the traffic that makes the measurement possible.

13. **Extend the Rain demo to the merchant-agent shape.** `tools/rain_demo.py` does the hard part.
    Audience order unchanged: Routavo, Rain, Stripe, Coinbase CDP, Aduna. Not Anthropic.

14. **Send the twelve** (`outreach_bot_prospects_curated.md`). Five real inboxes first, then the
    seven websites. Track replies per 100 by channel.

15. **INTEL-5.** `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/diagnose_stolen_sessions.py`.
    Until it runs, no count out of `relayshield_stolen_sessions` means anything about the criminal
    market, and the OpenRouter revocation webhook stays gated on it.

### THE PUBLISHED MCP PACKAGE IS BROKEN FOR EVERY NEW INSTALL. FOUND 2026-09-05.

**This is the most serious finding of the day and it was not on any list.** It came out of a
question about bundling the MCP server into the Claude Code plugin, which is the only reason anyone
looked.

`relayshield-mcp` declares its dependency as **`mcp>=1.0.0`, with no upper bound**, on 0.2.9 AND on
the 0.2.7 that the official registry still pins. A resolver picks the newest thing allowed, so a
fresh `pip install relayshield-mcp` today installs **mcp 2.1.1** and the server dies at import:

    AttributeError: 'Server' object has no attribute 'list_tools'

Reproduced end to end in a clean venv, not inferred from the metadata. **The wheel is fine. The
dependency range is not.**

**Why nothing caught it, and this is the part worth carrying.** Every check in this repo tests the
code we WROTE. Nothing tested the thing users INSTALL, and on this date those were different. A
developer's venv already holds a working `mcp` pinned months ago, so it passes forever; the resolver
would never choose that version for a new user. **The failure also needs no change on our side at
all** -- somebody else published a major version and our shipped package broke, silently, for new
installs only. That is the quiet-alarm rule applied to packaging.

`python3 tools/mcp_selftest.py --pypi` now builds a throwaway venv, installs the published package
the way a new user would, prints what the resolver actually chose, and handshakes it. Exit 1 on
DEAD. It reproduces this in about a minute.

**RESOLVED 2026-09-05. `relayshield-mcp` 0.2.11 is on PyPI and the check is green:**
`resolved: mcp 1.29.1, relayshield-mcp 0.2.11 -- ACTIVE, 16 tools`. The source in `~/mcp-live`
already carried `mcp>=1.0.0,<2.0.0`; it had simply never been released, so this was always "ship
the fix that exists" rather than "fix the pin".

**TWO WAYS THE VERIFICATION LOOKED LIKE A FAILURE WHEN IT WAS NOT, and both were mine.**

First, the check run minutes after the upload resolved **0.2.9**, because a just-published version
takes time to reach the index pip reads. Identical output to a genuinely broken release. The
checker now compares what the resolver took against PyPI's latest and says outright when they
differ, so "the new release is broken" and "the index has not served it yet" stop looking the same.

Second, and worse because it was a throwaway diagnostic presented as evidence: a one-off command
printed `all versions` using `sorted(releases)[-6:]`, and **`sorted()` on version STRINGS puts
"0.2.11" before "0.2.4"**, so the slice cut off the very version being checked. It read as "0.2.11
is not on PyPI" when 0.2.11 was there the whole time. Andrew stopped the session over it, correctly.

The lesson is rule 14 applied to my own output, not just to commands: **a number I print is evidence
the reader will act on, so a sloppy one-liner is as expensive as a wrong command.** Version strings
are never sorted lexically; compare them as tuples or do not print an ordering at all.

**Do not bundle the MCP server into the Claude Code plugin until this ships.** A plugin that
installs a server which dies at import would fail on first use for everyone, and it would fail that
way inside a submission to Anthropic's directory.

### "THE DEPLOY SUCCEEDED" IS NOT "THE ITEM IS CLOSED"

Recorded 2026-09-05 because it nearly cost the item. A status line reading *"Item 2: still open, and
confirmed from run 137's log — relayshield-agentic-api WAS DEPLOYED, only the probe was denied"* was
read as evidence the item could be closed.

It is the opposite, and the sentence contains both halves. "The deploy succeeded" is the reason the
failure is survivable; **"only the probe was denied" is the open item**, because the policy that
would authorise the probe has still never been pushed to AWS. Nothing about run 137 changed that,
and nothing will until `apply_deploy_invoke_policy.sh` runs.

The general form, and it is the counterpart to "a red run names a step, not an outcome": **reading a
red run correctly tells you what did NOT break. It does not close anything.** The diagnosis and the
fix are separate events, and only the second one is a state change.

### A SKILL IN OUR OWN REPO REACHES NOBODY

The honest answer to "this increases our discovery surface, right?", recorded because the optimistic
version is very easy to write.

**Building it does not increase discovery. Distributing it does.** A skill at
`.claude/skills/` in this repo is available to people who have cloned this repo, which is us. The
artefact is real and it is a prerequisite; it is not the channel.

What makes it a discovery surface is that it puts the check **at the moment of the decision** -- a
developer in Claude Code about to add an MCP server -- which is a far better moment than a blog post
read later by someone with no pending decision. That is why item 11 ranked above two posts. But the
moment is only reachable if the skill is somewhere they can install it from.

**Do not write submission instructions for any route before reading its rules.** That is the FD-2
lesson (a PR that would have been closed without comment, against a page whose own last section said
so) and the CrewAI lesson (PR #6550, opened against a live repo and still unreviewed months later:
open is not the same as responsive). Both cost real effort against destinations that never took it.

**CORRECTION, 2026-09-05.** An earlier draft of this line described CrewAI as "a repo whose README
says it is unmaintained and accepts nothing". That is `anthropics/commerce-agents`, not CrewAI, and
the two were conflated in a single sentence. **CrewAI is actively maintained** -- `crewai` 1.15.20
was published to PyPI on 2026-09-04, the day before this was written. The lesson from #6550 is about
an unreviewed PR, not a dead framework, and the difference decides whether item 7 is worth doing.

### A PLUGIN'S MCP SERVER GOES IN `.mcp.json`, NOT IN `plugin.json`

Measured 2026-09-05, and found only because the install was VERIFIED rather than
declared done.

An `mcpServers` block written into `plugins/relayshield/.claude-plugin/plugin.json`
is **silently ignored**. The plugin installs, `claude plugin validate` passes, and
`claude plugin details` reports:

    MCP servers (0)

Moving the identical block into `plugins/relayshield/.mcp.json` at the plugin
root registered it immediately:

    MCP servers (1)  relayshield

Nothing errors in the wrong configuration. A validator that passes and a field
that does nothing look exactly like a working plugin, which is the quiet-alarm
shape again -- and the first version of the test asserted the ignored key, so it
went green while the plugin shipped no server at all. **A test that reads the
same wrong file as the code proves nothing.** `test_agent_bait_skill.py` now
reads `.mcp.json` AND fails if `mcpServers` reappears in `plugin.json`.

The general form, for the third time this session: `claude plugin details` is the
check, not `claude plugin validate`. Validation says the file is well formed;
details says what the plugin actually contributes.

### THE FLOOR ON `relayshield-mcp` IS A SAFETY PROPERTY

`.mcp.json` pins `relayshield-mcp>=0.2.10`, and that is not tidiness. 0.2.9 and
earlier declare `mcp>=1.0.0` unbounded, resolve mcp 2.x, and die at import. The
floor makes it impossible for the plugin to install a version that cannot start.

Verified today that it fails CLOSED: `pip install 'relayshield-mcp>=0.2.10'`
returns `No matching distribution found`, because 0.2.10 is not published yet. A
loud failure at install time is much better than the alternative, which is a
server that installs, starts, dies, and presents to the user as "disconnected"
with a configuration that looks perfectly correct.

**So the plugin is complete and the MCP half is inert until the release ships.**
That is deliberate and it is the right way round.

### A LOCAL MERGE IS NOT A PUSH, AND `owner/repo` READS THE DEFAULT BRANCH

Found 2026-09-05 when `claude plugin marketplace add nzdsf2-gif/relayshield` failed with

    Marketplace file not found at
    ~/.claude/plugins/marketplaces/nzdsf2-gif-relayshield/.claude-plugin/marketplace.json

Nothing was wrong with the manifest. **`.claude-plugin/` was on the feature branch and not on
`origin/main`**, and the `owner/repo` source form clones GitHub's DEFAULT BRANCH. Confirmed with
`git ls-tree origin/main --name-only | grep claude-plugin`, which returned nothing.

This is the DRIFT RULE's mirror image and it is worth stating in both directions:

- A push from the container puts a file on GitHub and **not** on Andrew's Mac. That is why every
  command block starts with the merge.
- A merge on Andrew's Mac puts a file in his clone and **not** on GitHub. That is why anything
  fetched by `owner/repo` -- a plugin marketplace, a raw.githubusercontent URL, a CI checkout --
  keeps failing until `main` is actually pushed.

**Two routes, and the local one needs no push:**

    claude plugin marketplace add ~/dev/relayshield        # works right after the merge
    claude plugin install relayshield@relayshield

Verified end to end. Note `claude plugin marketplace add .` is REJECTED as an invalid source
format; use an absolute path or `./` with the trailing slash. The `nzdsf2-gif/relayshield` form
starts working the moment `main` carries `.claude-plugin/marketplace.json` on GitHub, and that is
the form to put in any published copy, because a reader has no local clone.

### THE ROUTE WAS CHECKED, 2026-09-05, AND IT IS OPEN

Unlike FD-2 and CrewAI. Read from the destination's own files rather than assumed:

**`anthropics/claude-plugins-official` accepts third-party submissions.** Its README says so in
those words -- *"Third-party partners can submit plugins for inclusion in the marketplace"* -- and
names a formal route, the plugin directory submission form at
<https://clau.de/plugin-directory-submission>. The bar it states is *"External plugins must meet
quality and security standards for approval"*, and it does not enumerate them. So this is a real
door, and the first one in this programme that did not turn out to be shut.

**The unit of distribution is a PLUGIN, not a skill**, which is why the skill alone was never
installable by anyone. A plugin is `.claude-plugin/plugin.json` plus a `skills/` directory; a
marketplace is `.claude-plugin/marketplace.json` at a repo root listing plugins by source. Both now
exist here, so this repo IS a marketplace and the skill is installable today:

    /plugin marketplace add nzdsf2-gif/relayshield
    /plugin install relayshield@relayshield

That is the prerequisite for the directory submission, not a substitute for it. **Our own
marketplace reaches people we tell; the directory is the part that reaches people we do not.**

`test_agent_bait_skill.py` pins both manifests, that they agree on the plugin name, that the source
path resolves, and that the declared `skills/` reaches the SKILL.md. Two files that must agree with
nothing checking that they do is the shape that produced run 134's red probe.

**The skill lives at `plugins/relayshield/skills/` and `.claude/skills/` is a SYMLINK to it.** One
file, two places it has to appear. A copy would drift, and this repo already carries four copies of
one pattern table.

### ITEM 10, APIFY SUBMISSION: the mechanics, so it is actionable

Recorded 2026-09-05 because "submit to Discord" left every real question unanswered, and an
instruction nobody can act on is how this item fell off the list in the first place.

**Where, corrected TWICE on 2026-09-05, and the second correction came from the channel itself.**

The programme page says to join the Discord, go to `#apify-writers`, check the quarterly theme, read
the guide and fill out the form. Andrew then looked at the actual channel and there was **no theme,
no guide and no form** -- because those only exist while a call is OPEN. A writer in the channel
that day stated it plainly: *"the July Typeform is closed and the next call opens in November."*

So the submission mechanism is a **Typeform that appears per call**, and today there is nothing to
fill in. **The next call is NOVEMBER.** That is the date this item waits on, and reading the
programme page alone would have had us hunting a form that does not currently exist.

**Posting in the channel while the call is closed is fine and is what other people do.** An observed
example from 2026-09-04: a developer introduced their Actor, described their finished Theme 2
article, noted the Typeform was closed, asked how to get dev.to publishing access, and linked the
draft. Nobody was penalised for it. So a pre-call introduction is available to us now if we want the
contact, and it is not a submission.

**The lesson, which is the FD-2 lesson with the label already read:** the programme page describes
the process in the abstract; the channel shows its current state. Both were needed, and only the
second one carried the date.

**SUBMITTING EARLY DOES NOT COST THE $500. PUBLISHING EARLY DOES.** Asked directly on 2026-09-05,
and the distinction is the whole risk. The rule is *"only original, previously unpublished
content"* -- it is about PRIOR PUBLICATION, and a submission is not a publication. So sending the
draft into `#apify-writers` or the form is the intended action and carries no downside. Putting the
same article on `blog.relayshield.net`, Medium or dev.to before Apify publishes it is what
disqualifies it. Their guidelines do not address republishing AFTER they publish, and the
programme's own $100 dev.to bonus is a post-publication republish under their organisation, so the
canonical-first channel order resumes once the article is live on their blog.

**Cadence, and it decides the date.** The programme is QUARTERLY. The July call closed 2026-08-16
and the next opens in NOVEMBER, per the channel. Use the wait for the three verifications below
rather than treating the wait as the blocker.

**The three facts to confirm with the Apify console open**, because the draft asserts them and no
session has verified them directly:

1. **The 154 runs figure**, and whether to quote it at all. It is small enough that a reviewer may
   read it as a toy. Consider dropping the number and keeping "in production since August".
2. **The exact Standby configuration** (memory, timeout), if we want to quote it. The draft
   deliberately does not.
3. **The dependency versions as they stand today.** The draft says `apify>=2,<3` crash-looped and
   `apify>=4,<5` fixed it, taken from a Dockerfile comment dated 2026-08-25. If the pin has moved,
   the article moves with it.

**What is actually at stake:** $500 on publication, plus $100 in Apify credits for a dev.to version
under their organisation. The money is not the point. It is a technical article on a platform
developers read, about a category we sell into, written from work we actually did, and both the
Actor and the API get a link carrying `?source=apify`, which is already a registered key.


### THE MOVE BROKE SOMETHING THE REPO COULD NOT SEE, AND THE LOG HAD BEEN SAYING SO FOR HOURS

The most instructive failure of the session, because the fix that was supposed to prevent it was
already in place and could never have worked.

Moving the clone to `~/dev/relayshield` was made safe INSIDE the repo by deriving paths from
`Path(__file__).resolve().parent`. It killed the RelayShield MCP server anyway, in both Claude
Desktop and Claude Code, because both configs launch it by absolute path into `~/Side SaaS Hustle`.
Those files live in `~/Library/Application Support` and `~/.claude.json` — **directories the repo
does not own and cannot enumerate**, so no amount of discipline inside the repo reaches them.

Two things made it invisible for hours:

- **The client says "disconnected", which describes the symptom and not the cause.** The actual
  cause was in the log, repeating every few minutes since 04:24 UTC: `can't open file
  '.../Side SaaS Hustle/relayshield_mcp_server.py': [Errno 2] No such file or directory`.
- **Nobody was reading the log**, because the config is the thing you look at when a server will not
  start, and the config looked fine. It WAS fine, for a machine layout that no longer existed.

`tools/mcp_inventory.sh` reads every client config path AND the client's own logs, redacting every
credential-looking value first. `tools/fix_mcp_config_paths.py` repoints them, rewriting dict KEYS as
well as strings because Claude Code files its MCP servers under the project's absolute path.

**The general form, and it is the second half of the move checklist: an absolute path to the clone
can exist anywhere on the machine.** After relocating it, fix what names it from outside — MCP client
configs, launchd plists, cron, shell aliases, IDE run configurations. And when a process "will not
start", read its log before re-reading its config: the config says what was attempted, the log says
what happened, and they are usually different problems.

### THE DEPLOY WENT RED AND THE DEPLOY SUCCEEDED. AGAIN.

Run 134's lesson, second occurrence, and this time the improved error message did its job:

    relayshield-agentic-api WAS DEPLOYED. Only the probe was denied — the deploy
    role has no lambda:InvokeFunction on it.

`iam_github_deploy_invoke.json` gained `relayshield-agentic-api` when that function was mapped, and
**the repo half does not push the policy to AWS**. `sh tools/apply_deploy_invoke_policy.sh` does, and
until it runs every deploy touching that function is red for a reason unrelated to the code.

Worth restating because it keeps costing time: **a red run names a step, not an outcome.** "The
deploy failed" and "the check after the deploy failed" are different facts with different fixes, and
the second one costs nothing if read correctly and a rollback if it is not.

### THERE ARE FIVE MCP SURFACES, NOT ONE

Asked as "I think I only have one MCP server, can you check". Inventoried 2026-09-05:

| Surface | What it is | State |
|---|---|---|
| `relayshield-mcp` on PyPI | stdio, the one that appears in a client | live, 0.2.9 |
| MCP registry entry | the canonical directory listing | active, pinned 0.2.7 |
| HuggingFace Space | hosted MCP over HTTP | egress-blocked from the container |
| Apify Actor | MCP over Streamable HTTP, Standby | egress-blocked from the container |
| `@relayshield/bankr-mcp` | a TypeScript stdio server built for Bankr | never published |

**Only the first can show "disconnected" in a client.** The hosted two would present as a failing
URL, and the Bankr one has never shipped. Knowing which surface is which is what turned an
open-ended "the MCP server is down" into one log line. Full detail in `mcp_surfaces_inventory.md`.


### THE DIAGNOSTIC PAID FOR ITSELF ON ITS FIRST RUN

Written the same day as the script it describes, because the result is the argument for the habit.

Two candidate causes with different fixes: the gateway resource wired to the wrong function, or the
route right and the deployed code stale. Guessing would have been a coin flip, and the wrong guess
means deleting and recreating gateway methods on a live API for no reason.

`diagnose_agent_bait_routes.sh` answered it in one run and left nothing to interpret:

- Step 3: **both** resources integrate with `relayshield-agentic-api`. The routes were never wrong.
- Step 5: that function, invoked DIRECTLY with the gateway taken out of the path, returns
  `x402Version: 2` and this endpoint's own description — so the handler is current.
- The `$0.25` was `relayshield-api`'s fallback for a path it does not know, reached only because the
  gateway had been sending it there before the deploy.

**Cause B, and the fix was a push rather than anything touching AWS.** A `/{proxy+}` at the API root
turned up in step 4 and is not a factor: an explicit resource beats a greedy proxy. Recorded so
nobody re-opens that question.

The habit worth keeping: **when two causes produce the same symptom, the cheap read-only script that
separates them is worth writing before the first guess, not after the third.**

### A 402 IS NOT PROOF THE RIGHT LAMBDA ANSWERED

The most useful mistake of the session, and it is run 134's lesson in a new costume.

`create_agent_bait_scan_routes.sh` printed **"LIVE. The x402 door challenges for payment at $0.50"**
over a response body that plainly said `"price": "$0.25 USDC"`. The script asserted the status code
and never looked at the body.

**`relayshield_api.py` answers `/v1/payg/*` too, and its unknown-path default is 250000 units.
`relayshield_agentic_api.py`'s is 350000.** So a route wired to the wrong function, or a stale
deployment, returns a perfectly well-formed 402 at the wrong price, and every structural check
passes. The price is the only discriminator, and nothing was checking it.

Both scripts now assert the price. **The general form: when two components can produce the same
shape of success, verify the field that differs between them, not the shape.**

### THE PYPI NUMBERS CAME BACK, AND THE HONEST READING IS MIXED

    langchain-relayshield       last_day 2   last_week 4    last_month 137
    openai-agents-relayshield   last_day 2   last_week 6    last_month 143
    relayshield-mcp             last_day 6   last_week 44   last_month 322

**`relayshield-mcp` is the real one.** 44 a week and 6 a day is a steady rate consistent with actual
use, and it is the package with the least marketing behind it.

**The two framework packages are a burst plus a trickle, and the monthly number flatters them.** 137
a month against 4 a week is not a rate — 4 a week annualises to about 17 a month, so most of that
137 landed at once. That shape is a mirror scrape or a CI matrix, not adoption.

**It still justifies `crewai-relayshield`**, because the marginal cost is half a day against code
that already exists, and because a trickle from a package nobody has promoted is a better base rate
than zero. It does NOT justify treating framework packages as a growth channel. Rank the work
accordingly, and quote none of these numbers externally — MEASUREMENT DOCTRINE applies to our own
download counts exactly as it does to the corpus.

### A MODULE-LEVEL SECRET CACHE WITH NO TTL WAS A SILENT BILLING RISK

Found while answering "can I delete the old Stripe key". Three handlers cached the Stripe secret for
the life of the execution environment with no expiry, while `relayshield_stripe_webhook.py` re-read
it every call. So the two halves disagreed for minutes to hours after any rotation.

That would be a harmless race except for what fails in it: `_record_stripe_meter_event` is
fire-and-forget and never raises, so a 401 from a revoked key is caught, logged at WARNING, and the
customer is served the paid response anyway. **Revoking early produced no outage and no red alarm.
It produced silent under-billing.**

`_get_secret` now carries `_SECRET_TTL = 300` in `relayshield_api.py`, `relayshield_agentic_api.py`
and `relayshield_mpp_settlement.py`, and falls back to the last known good value if a refresh fails.
Rotation is now: write the secret, wait six minutes, revoke. **It also removed an IAM dependency
rather than adding one** — the operator identity's implicitDeny on
`lambda:UpdateFunctionConfiguration` stopped mattering, because nothing needs to force a recycle any
more. Fixing the cause beat granting the permission.

### THE DEMO'S AUDIENCE, since it was asked

Ranked by whether the recipient has a DISTRIBUTION interest, not just interest:

1. **Routavo.** Their "Control" pillar is spend control on the buy side; we are the sell side and
   the counterparty question is the gap they do not cover. Already registered for early access, so
   it is a follow-up rather than a cold approach.
2. **Rain, `apa@rain.xyz`.** The first demo is what they responded to. A merchant-agent version is
   new information rather than a nudge, and the two open questions from that submission are still
   unanswered.
3. **Stripe, Jake Lamoine.** The MPP conversation is live and stuck on eligibility. A working demo
   is the concrete artefact, and it pairs with the carried question about early-adopter status.
4. **Coinbase CDP / the x402 Foundation.** We are in the Bazaar, we have filed on their repo, and
   they run a community show-and-tell — see `cdp_discord_show_and_tell_post.md` for the format that
   worked last time.
5. **Aduna, via Reggie Daniels.** Warm intro pending; `aduna_outreach.md` has the messaging.

**Not Anthropic.** `anthropics/commerce-agents` says in its own README that it is unmaintained and
does not accept contributions. There is no channel there, and sending a demo to a repo that says it
takes nothing is the CrewAI mistake with the label already read.

---

## WHERE 2026-09-04 LEFT THINGS — read this first

### THE BLOCKED SOURCE WAS REACHABLE ALL ALONG, AND IT MADE A DERIVED SHAPE WRONG

The single most useful thing this session found, and it generalises well past Stripe.

Two sessions recorded `docs.stripe.com` as egress-blocked and derived Stripe's wire shapes from
prose instead, labelling them "derived, not verified". Both statements were true. The conclusion
drawn from them was not: **that the shapes could not be verified from this container.**

They could. Nobody had tried the two obvious neighbours:

- **`registry.npmjs.org` is reachable**, and `mppx` — Stripe's OWN reference implementation of MPP —
  is published there with readable source. `npm view` needs no browser.
- **`raw.githubusercontent.com` is reachable**, and `github.com/tempoxyz/payment-auth-spec` is the
  IETF draft that mppx cites, co-authored by Tempo and Stripe.

Reading the implementation settled every open question in an hour, and **one of the two derived
shapes was wrong in three separate places** — a missing `mode` key, `transaction_verification`
where the real name is `transaction_verification_options`, and a missing
`payment_method_types: ["crypto"]`. The pinned API version was wrong too: `2026-05-27.preview`
where mppx pins `2026-07-29.preview`, which matters because **a probe on the wrong preview version
reports "not enabled" for an account that is enabled.**

**The general form, and it belongs next to "NO AWS IN THIS SANDBOX IS NEVER A REASON TO SKIP A
CHECK": a blocked documentation site is not a blocked FACT.** Before recording anything as
underived, try the package registry, the vendor's own SDK source, the spec repository, and
raw.githubusercontent.com. A vendor that documents a protocol almost always ships an
implementation of it somewhere fetchable, and the implementation is better evidence than the docs
anyway.

### MPP is an HTTP AUTHENTICATION SCHEME, not a JSON block in a response body

The invented `mpp` block this endpoint shipped with on 2026-09-04 was not merely unverified, it was
structurally wrong. MPP uses the `Payment` scheme under RFC 7235: the challenge rides
**`WWW-Authenticate`**, the credential comes back in `Authorization`, the receipt goes out in
`Payment-Receipt`. The challenge `id` is **HMAC-SHA256 bound to the challenge's own contents** over
seven fixed pipe-delimited slots, which is what stops a client altering the amount and presenting an
id we would still accept.

That is implemented and tested now. **The credential side is not**, and the challenge is therefore
switched OFF by default (`RELAYSHIELD_MPP_CHALLENGE=off`): redeeming a Shared Payment Token is a
Stripe call this module does not make, and SPTs are in private preview on top of the crypto gate.
**Advertising a payment method we would then reject is worse for the agent than never offering it**
— it spends the agent's authorisation on a route that cannot complete.

`npx mppx@latest validate <url>` is the objective compliance test and it runs on the Mac. It is the
acceptance criterion, not our own reading.

### relayshield_agentic_api.py IS RECONCILED. Item 8 is closed.

It was far smaller than four sessions of carrying it implied: **+22 / -1**, both hunks live-only,
fully readable in one screen.

- **The branded `API_BASE_URL`** (`https://api.relayshield.net`, not the execute-api host), with a
  five-line comment explaining that this URL is advertised as the resource in every 402 and is what
  x402 indexers persist.
- **The Bundle D "Door 2" branch**: a direct-Stripe bundle key must be metered ABOVE the
  `has_subscription` test, or it is classed "unlimited under an existing subscription" and billed
  nothing while the AWS door bills per call.

Main has been moved to the live bytes VERBATIM — a pure move, no edits — so live is byte-identical
to main, and `relayshield_agentic_api.py` is now in `deploy_lambdas.yml`: the `paths:` trigger, the
`LAMBDA_MAP`, and `iam_github_deploy_invoke.json`. Recover, read, reconcile, then map, in that
order and no other.

### RULE 12 FIRED AGAIN, THE DAY AFTER IT WAS WRITTEN

Stripe documentation was pasted into the session on 2026-09-04 with the account's **live
`sk_test_` secret key interpolated into the curl samples**, exactly as on 2026-09-03. Stripe
personalises examples for a signed-in reader; nobody typed a credential and one arrived anyway.

**Roll it in the Dashboard under Developers, API keys.** And read rule 12 as what it is: not a
one-off, a property of every vendor doc page read while signed in. Screenshots carry it too — the
key is rendered into the image, so "I only sent a picture" is not a mitigation.


### The MPP settlement endpoint is BUILT. Item 1 of the 2026-09-03 list, second half.

`relayshield_mpp_settlement.py`, one endpoint, `POST /v1/mpp/mcp-registry-risk` at $0.35 on Base,
settled through Stripe with a fallback to the rail that already collects. 30 offline tests. Full
write-up in `mpp_settlement_endpoint.md`.

**It is NOT live yet and needs two commands on the Mac**, in this order and no other. Note the
shapes below were CORRECTED on 2026-09-04 against Stripe's own reference implementation — see
"THE BLOCKED SOURCE WAS REACHABLE ALL ALONG" above:

1. `sh tools/create_mpp_settlement_lambda.sh` — creates the function, its own IAM role, both gateway
   routes, and proves the 402.
2. `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/mpp_settlement_selftest.py` — settles whether
   the Stripe parameter shapes are right.

**Three things in it worth carrying:**

- **It is a NEW FILE and not a branch in `relayshield_agentic_api.py`, on purpose.** That file still
  carries unreconciled live drift (item 8 below). Adding an endpoint there and giving it a deploy
  path is the 2026-08-17 mistake exactly. A new file has no live counterpart, so it cannot drift
  from one. The detector is IMPORTED from agentic_api rather than copied, because this repo already
  has four copies of one pattern table and does not need a fifth. The deployer's `resolve_deps` grep
  is `^[[:space:]]*(import|from) relayshield_`, so a function-level indented import is still
  packaged — checked against that grep, not assumed.
- **It is not in `deploy_lambdas.yml`, and must not be until the function exists in AWS.** The
  deployer calls `update-function-code` on whatever `LAMBDA_MAP` names, so mapping a function that
  does not exist turns the first push red with a `ResourceNotFoundException` that reads exactly like
  a broken deploy. Create first, map second. `relayshield-mpp-settlement` IS already in
  `iam_github_deploy_invoke.json`, so the first CI deploy will not repeat run 134's denied probe.
  **`sh tools/apply_deploy_invoke_policy.sh` still has to push that file to AWS** — the repo half
  does not do it on its own.
- **Two Stripe wire shapes in it are DERIVED, not verified**, because `docs.stripe.com` is blocked
  from the container. Both are isolated in single builder functions with no branching so a
  correction is one line, and `tools/mpp_settlement_selftest.py` exists to have Stripe name the
  wrong parameter rather than guessing again. The `mpp` block in the 402 body says
  `"version": "unverified"` in its own payload for the same reason. **Derived is not verified, and
  saying so in the artefact is cheaper than being wrong in production.**

### Andrew's merge failed, and BOTH halves of the failure came from one cause

    error: The following untracked working tree files would be overwritten by merge:
        agent_baiting_scope.md
        outreach_bot_prospects_curated.md

Both files are on `claude/top-10-todos-discord-lambda-vn4583` AND were saved by hand into
`~/Side SaaS Hustle` from a chat paste — the delivery process at the top of this file, working. Git
will not clobber an untracked file it did not write, so the copies collided and the merge aborted.
`tools/stripe_machine_payments_probe.py` and `tools/fd8_prepare_republish.py` were then "missing"
only because the merge that would have delivered them never completed.

**The general form, and it will recur:** the chat-paste delivery rule and `git merge` collide by
design. Anything pasted into chat AND committed blocks a later merge. The fix is to delete the
hand-saved copy immediately before merging — the branch copy is identical, so nothing is lost.

### The drift check RAN with the Discord bot in it, and the bot is clean

Run 25, scheduled 2026-09-03 16:56, executed and went red. It opened issue #23, naming
**relayshield-agentic-api and relayshield-developer-signup** — and NOT relayshield-discord-bot.
That is the positive evidence 2026-09-03 was waiting for: the bot deployed, and live matches main.
Closes the "the drift check has still never run with the Discord bot in it" item below.

Deploy runs 135 and 136 are both GREEN, so the invoke-policy fix took and run 134's red probe is
behind us.

**Do not close #23's developer-signup half without re-checking.** Run 25 fired at 16:56 and deploy
run 136 shipped at 17:57, an hour later, so the drift it names may already be gone. The next
scheduled drift run answers it; a stale issue is not a finding.

---
