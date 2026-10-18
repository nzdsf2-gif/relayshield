<!-- Verbatim sections moved out of CLAUDE.md on 2026-10-18, original order. Not auto-loaded.
     Find one with: grep -n 'WORDS' docs/claude_memory/INDEX.md -->

## THE PAGE IS INSIDE A TEMPLATE LITERAL, SO EVERY BACKSLASH IS EATEN ONCE. THIS SHIPPED A DEAD APP.

**2026-09-11, and it is the most expensive defect of the week because every check in the repo passed
while the app was dead.** The watchdog added hours earlier reported it on its first load:

    This app's code did not start. SyntaxError: Invalid regular expression: missing )

**THE MECHANISM.** `cloudflare_worker_miniapp.js` holds the whole page in a template literal, so the
Worker evaluates its escape sequences ONCE before a browser ever sees it. Two regexes I added were
written with single backslashes:

    source                                  served to the browser
    /^(?:-?\d+:[0-9a-fA-F]{64}...         /^(?:-?d+:[0-9a-fA-F]{64}...
    /^(?:https?:\/\/|...                 /^(?:https?://|...

The first is SILENTLY WRONG: it matches the letter `d` instead of a digit. **The second is fatal.**
`//` ends the regex literal at the second slash, so the browser parses `/^(?:https?:/` and throws
while reading the module. **A module that throws while parsing never runs**, so no handler is ever
registered: the static HTML renders perfectly and the tabs, the buttons and the example are all
dead. On a phone, with no console, that is indistinguishable from a CSS bug or a stale cache.

**EVERY OTHER REGEX IN THAT FILE WAS ALREADY DOUBLED.** The convention existed. I broke it, and
nothing in the repo could tell.

### THE REASON NOTHING CAUGHT IT: EVERY CHECK READ THE SOURCE

`node --check` parses the Worker, where the page is a STRING. `test_miniapp.py` greps the source.
And the harness I wrote the same day to "execute the page" read the source and stripped two escapes
by hand -- which produces text **nobody ever runs**. It passed. It was always going to pass.

**A detector whose extractor does not match what is deployed cannot detect anything.** That is the
third time this suite has learned it and the first time it cost a live outage rather than a green
test. The two earlier instances were cheap: an extractor that stopped at the first backtick, and a
guard that matched its own comment.

**`tools/miniapp_render.mjs` is the extractor that matches: it RUNS THE WORKER** and prints the page,
or the module, that a browser actually receives. Everything in `test_miniapp_routes.py` that looks at
page code now goes through it.

**`tools/miniapp_smoke.mjs` is the check that would have caught this.** It renders, evaluates the
served module against a minimal DOM, and fires every control a user presses -- the tabs, the example
button, Check, Watch, Share. Run it before any Mini App change:

    node tools/miniapp_smoke.mjs

Five guards now fail on the real defect, all proven by reintroducing it: the smoke test, a served-
text assertion on both escapes, a general "no bare `//` inside a served regex literal", and a direct
assertion that `TON_ADDR` RECOGNISES a raw TON address.

**That last one exists because the gate test had a blind spot that this defect walked straight
through.** `offChainReason` returns `""` for a TON address AND for anything it does not recognise at
all, so a table of cases cannot distinguish them: with the digit class eaten, a raw TON address
matched nothing, fell through every branch, returned `""`, and the table read it as a pass. **When a
function's "correct" answer and its "I have no idea" answer are the same value, a case table proves
nothing.** Assert the thing itself.

### AND THE FIFTH TIME PROSE FOOLED A GUARD, IN THE GUARD FOR THIS

The first version of the served-text assertion **passed on the real defect**, because the comment I
wrote directly above those two regexes documents the correct form and therefore contains it.
`strip_js_comments()` was already a shared helper in that file for exactly this reason, and I did not
use it. The natural way to write a guard is to search the file; the natural way to write good code is
to explain the rule beside it. They collide every single time.

### THE RULE, AND IT OUTRANKS EVERY SYNTAX CHECK IN THIS REPO

**`node --check` answers "does this parse". It never answers "does this run".** For a deployed
artefact, execute it. And execute the ARTEFACT -- the bytes the client receives -- never the source
it was generated from.

**A trailing backslash in that template literal is a line continuation too**, which silently welded
three lines of a comment into one. Harmless here, and the same class: the source and the served text
are different documents.

## THE MINI APP HAS NO CONSOLE, SO EVERY JS FAILURE LOOKS IDENTICAL. IT REPORTS ITSELF NOW.

2026-09-11. Reported as: the Check tab shows the new TON-only text, but "Try a link that gets
flagged" does nothing, the Watching tab will not open, and neither will Spot the fake.

**Every one of those is the same symptom: the static HTML rendered and no JavaScript ran.** On a
phone there is no console, so that is indistinguishable from a CSS bug, a stale cache, a broken
handler, or a failed deploy -- four causes with four different fixes and no way to tell them apart.

**I could not reproduce it, and everything checkable from the container passes**, which is worth
recording precisely so the next session does not repeat the search: the page HTML is tag-balanced,
the stylesheet is brace-balanced and `.hidden` survives, the page module parses as a real ES module,
it EXECUTES against a stubbed DOM, and all four handlers register and fire without throwing. Deploy
run 7 succeeded. So the honest report was "I cannot reproduce this", not a fifth guess.

**THE FIX IS THE INSTRUMENT, NOT A GUESS.** A classic (non-module) script now runs ABOVE the module,
records anything the page throws, and after three seconds writes onto the page itself if the module
never checked in. It has to be classic and it has to be above: **a module that fails to parse, fails
to IMPORT, or throws on its first line never runs its own error handler**, so a watchdog inside it
reports nothing in exactly the cases that matter. The module sets `window.__rsBoot = true` directly
after the import, which is the heartbeat.

**And a visible BUILD id in the footer**, computed from the page plus the embedded widget. "I cannot
see your changes" has three causes that look identical from a phone -- the deploy did not run,
Telegram served a cached page, or the change is live and something else is wrong -- and nothing on
the page could separate them, so every report started with a round trip to establish which.

## THE THIRD RUNTIME-DEAD DEFECT IN TWO DAYS, AND IT WAS IN THE FIX FOR THE SECOND

Writing the build id, I declared it as an IIFE that ran at module load and read `WIDGET_JS`, which is
declared **fifty lines further down**. `const` is not initialised until its own line is reached, so
that is a temporal-dead-zone `ReferenceError` at Worker startup and **every request 500s**.

`node --check` passes it. The syntax is perfect.

That is three in one family in two days, all syntactically valid and all runtime dead:

1. a stray backtick inside the `PAGE` template literal,
2. a constant declared in the WORKER scope and read from the PAGE,
3. a constant read before the one it depends on is initialised.

**No parser sees any of them. Executing the module sees all three.**
`test_miniapp_routes.py` now imports the Worker and serves a request: it checks the module loads,
that it returns a page with every `__PLACEHOLDER__` substituted, that `/relayshield-widget.js` is
served with a JavaScript content-type and still exports `check` (a module whose import fails runs
NOTHING while the static HTML renders, which is this whole section's symptom), and that the build id
appears. Proven by reintroducing all three defects plus a broken widget route.

**The general form, and it now outranks every syntax check in this repo: `node --check` answers
"does this parse". It never answers "does this run". For anything that is a deployed artefact rather
than a library, execute it.**

## THE WATCHLIST READ A SECRET THAT DOES NOT EXIST, AND EVERY PROBE PASSED

**2026-09-12. The worst defect of the week, found by the log the previous fix made readable.**
`tools/diagnose_stars_invoice.sh` step 4, sixteen times over:

    ResourceNotFoundException ... Secrets Manager can't find the specified secret
      relayshield_watchlist.py line 170, in verified_user_id
      token = _get_secret(BOT_TOKEN_SECRET)

**One character, in two places, plus a wrong key inside the secret.**

    relayshield_watchlist.py  relayshield/telegram-bot-token   key "bot_token"
    the secret that EXISTS    relayshield/telegram_bot_token   key "telegram_bot_token"

`TG_SECRET_NAME` and `TG_SECRET_KEY` in `relayshield_telegram_webhook.py` have been reading it
correctly for months. **So this was never about Stars.** `verified_user_id` is the first line of
`add_watch`, `list_watches`, `remove_watch` AND `stars_invoice`, so **every verified watchlist call
raised from 2026-09-09 to 2026-09-12.** The tracebacks name `list_watches` far more often than
`stars_invoice`: people were trying to use the watchlist and getting a 502.

**THE THIRD DEFECT IS THE ONE THAT WOULD HAVE SURVIVED FIXING THE NAME.** The IAM policy in
`tools/create_watchlist_lambda.sh` grants the ARN, so it named the hyphenated secret too -- a
corrected name would have moved the failure from ResourceNotFound to AccessDenied. And inside the
secret, `parsed.get("bot_token") or parsed.get("token") or token` **falls through to the RAW JSON
STRING as the token**, which fails the HMAC for every user and raises nothing at all. A wrong answer
rather than an exception, which is strictly worse.

### WHY EVERY CHECK PASSED, AND THIS IS THE GENERAL LESSON

`verified_user_id` returns None for empty `init_data` **BEFORE** it reads the secret. So an unsigned
request never touches Secrets Manager.

`create_watchlist_routes.sh` and `diagnose_watchlist_routes.sh` both prove the route by asserting
exactly one thing: that an unsigned POST is refused with
`{"ok": false, "error": "unverified: open this inside Telegram"}`. **That refusal is the one path
that does not need the secret.** Both scripts printed LIVE over a function that could not serve a
single real user.

**A PROBE THAT TAKES A ROUTE THE REAL CLIENT DOES NOT TAKE PROVES NOTHING ABOUT THE REAL CLIENT.**
This is the `/v1/ton-address` instrumentation lesson in a new place -- "the endpoint that does X"
and "the endpoint this client calls" are different questions -- and the CORS lesson too: curl
ignores CORS, and curl also cannot mint initData. **The cheapest path is the one a probe reaches
for, and it is systematically the path that skips the dependencies.**

The guard is four tests in `test_miniapp.py`, reading both constants out of both files plus the ARN
out of the shell script, all proven by reintroducing the defect. Two files that must agree with
nothing checking that they do, for the fourth time: the pattern tables, `LAMBDA_MAP` against the
invoke policy, the three route lists, and now this.

**AND THE NEW GUARD WAS FOOLED BY ITS OWN COMMENT ON ITS FIRST RUN, FOR THE SIXTH TIME.** The
key-order test searched for `BOT_TOKEN_KEY` and matched the comment saying "BOT_TOKEN_KEY first",
so it passed with the order reversed. It strips comments now. Six occurrences, four files, one
cause: the natural way to write a guard is to search the file, and the natural way to write good
code is to explain the rule beside it. **Strip comments in the FIRST version of any new guard, not
the second.**

## TWILIO SIM SWAP IS APPROVED FOR THE US, AND THERE IS NOTHING TO RE-ADD

**2026-09-12. Twilio approved the Lookup SIM Swap configuration for the United States**, ticket
28883049. Asked as: do we need to re-add SIM swap to Stripe, AWS or the bots?

**The account SID is deliberately NOT recorded here, and the reason is worth more than the SID.**
The first version of this section quoted it out of the approval email, and **GitHub's push
protection refused the push**: an `AC`-prefixed Twilio Account SID is a scanned pattern. So a
credential-shaped string arrived in a pasted vendor email, went into a commit without anyone typing
it, and only a server-side rule stopped it -- which is rule 12 in a new costume. Rule 12 says a
vendor DOC page read while signed in may carry your key; this says **a vendor SUPPORT email carries
your account identifiers too**, and pasting it into a session puts them one commit from a public
repo. The SID is in the Twilio console when anyone needs it.

**No, to all of it, and the reason is that nothing was ever removed.** Checked in the code rather
than recalled:

- `/v1/metered/sim-swap` is in the dispatcher, `KEYLESS`/PAYG tables at **$0.25**, the metering
  table, `_TTL` freshness at 86,400s, and the AWS rate-card comment. `/v1/payg/sim-swap` is a live
  x402 endpoint at 250000 units.
- `/simswap` in `relayshield_telegram_webhook.py` is complete: consent enrolment, `/simswap`
  withdrawal, `handle_sim_status`. `relayshield_whatsapp_webhook.py` imports the same consent
  module and defaults `sim_swap_monitoring` to False until the number's OWN owner consents.

**THE CODE WAS SELF-GATING THE WHOLE TIME, AND THAT IS WHY THERE IS NO WORK.** `handle_sim_swap`
reads `sim_swap.error_code` off a Twilio **200** and returns a **503** rather than a verdict,
because Twilio answers 200 with `error_code=60606` when carrier registration is not approved. Its
own comment names that code. And the metered dispatcher only bills a 2xx, **so a non-answer was
never charged.** Approval does not enable a feature; it stops that branch firing.

**So the only thing that changes is that real verdicts now flow, and the check is a call rather
than a code change.** The one thing worth confirming is the SCOPE: Twilio approved the **United
States**. A non-US number still returns 60606 and still 503s, which is correct behaviour and must
not be read as a regression.

## THE STARS INVOICE FAILED AND THE ONE LINE THAT NAMED WHY WAS THROWN AWAY

**2026-09-12, reported as "I pressed the Stars button but it fails with could not start the
purchase", after `create_watchlist_routes.sh` created `/v1/watchlist/invoice` (`0lm0as`, POST and
OPTIONS, stage deployment `dpot17`) and proved the gateway reaches our handler.**

So the route was no longer the problem. `stars_invoice()` was, and it had TWO defects that between
them guaranteed an unactionable failure.

**1. THE BRANCH THAT LOGS TELEGRAM'S REASON COULD NEVER RUN.** The code was:

    except Exception as exc:
        logger.error("createInvoiceLink failed: %s", exc)   # "HTTP Error 400: Bad Request"
    if not body.get("ok"):
        logger.error("createInvoiceLink rejected: %s", body.get("description"))

**Telegram answers a rejected `createInvoiceLink` with a non-2xx status and the reason in the
BODY.** `urllib` raises `HTTPError` on any non-2xx, so every Telegram-side refusal landed in the
`except`, where `exc` stringifies to "HTTP Error 400: Bad Request" and names no cause at all. The
`if not body.get("ok")` branch was reachable only for a 200 carrying `ok: false`, which Telegram
does not send. **Circular by construction, exactly like the stray-backtick detector whose extractor
stopped at the backtick.** It reads `exc.read()` now and logs the body.

**The rule this repo already had, applied one layer in: every probe prints the body of what it got
rather than a summary of it.** That was written for diagnostics. It applies to our own error paths,
where the cost is higher, because a diagnostic can be re-run and a user's failed purchase cannot.

**2. `provider_token` WAS OMITTED WHERE THE BOT API DOCUMENTS AN EMPTY STRING.** Its own parameter
description is *"Pass an empty string for payments in Telegram Stars"*, and it was required outright
before Stars existed. **Read from `@grammyjs/types` 5.0.0 on npm, not guessed** -- core.telegram.org
is egress-blocked from the container and `registry.npmjs.org` is not, which is the BLOCKED SOURCE
WAS REACHABLE ALL ALONG rule paying for itself a third time. A vendor's typed client is better
evidence than a docs page anyway.

**AND THE TWO FAILURE MESSAGES WERE ONE CAPITAL LETTER APART.** Our handler returns "could not
start the purchase, try again"; the Worker's fallback for a request that never arrived said "Could
not start the purchase." **A Telegram refusal and an unreachable endpoint read identically on a
phone**, so the screen could not say which side to look at. The fallback names the side now.

**`tools/diagnose_stars_invoice.sh` is read-only and answers the question curl cannot**: it prints
the deployed `LastModified` first, because a fix that has not shipped cannot log anything, then
every `createInvoiceLink` line in the last 24 hours, then any traceback or AccessDenied separately,
because a raise BEFORE the try block (`_get_secret`, say) is a different cause with a different fix.

**One hypothesis was checked and DISPROVED rather than shipped as a warning:** that
`relayshield-watchlist-role` lacked `secretsmanager:GetSecretValue` on the bot token. `git log -S`
shows that ARN has been in `tools/create_watchlist_lambda.sh` since its first commit (`982e9bb`,
2026-09-09), so the role got it when the script ran. Naming a cause I had not checked is what rule
C exists to stop.

## A GREEDY PROXY MAKES A MISSING ROUTE ANSWER IN OUR OWN ENVELOPE

**2026-09-12. The invoice probe I added yesterday was right about the conclusion and wrong about
the evidence, on its first real run.** It predicted that a missing route answers
`{"message": ...}` from API Gateway. What came back was:

    HTTP/2 404
    {"ok": false, "error": "unknown endpoint: /v1/watchlist/invoice"}

**That is OUR envelope, so by my own reading guide the route existed. It does not.** Step 2 of the
same run lists four watchlist resources and no `invoice` among them.

**THE MECHANISM IS THE `/{proxy+}` THE DIAGNOSTIC ITSELF PRINTS IN STEP 3.** With no explicit
resource, the request falls through to the greedy proxy at the API root, which is wired to
`relayshield-api`, whose unknown-path branch is `_err(f"unknown endpoint: {path}", 404)`.
`relayshield_watchlist.py`'s own 404 says `unknown path {path}`. **Three components can 404 at that
URL and I had written the guide as though there were two.**

**THE DISCRIMINATOR IS THE CORS HEADERS, NOT THE ENVELOPE.** `relayshield_watchlist.py` puts
`access-control-allow-origin` on EVERY response including its 404s, deliberately, because a
preflight that fails means the real request is never sent. `relayshield-api` does not. In the run
above, `/list`'s 400 carried the CORS headers and `/invoice`'s 404 carried none, which settles it
in one line. **This is the 402-at-the-wrong-price lesson exactly: when two components produce the
same SHAPE of answer, verify the field that differs between them.**

**AND THE MISSING ROUTE IS WORSE THAN A PLAIN 404 BECAUSE OF THAT MISSING HEADER.** A browser
discards a cross-origin response with no `access-control-allow-origin` after it arrives, so inside
the Mini App the buy button does not show an error: **it does nothing at all.** The terminal sees a
404 with a body; the user sees a dead button. That is the CORS quiet-alarm shape with money on the
end of it.

**The fix needs no change to the proxy.** An explicit resource beats a greedy `/{proxy+}` -- already
recorded from the agent-bait diagnosis -- so creating `/v1/watchlist/invoice` takes precedence and
the proxy keeps serving everything else.

**The general form, and it is the sixth costume this week: a guard is only as good as where it got
its expectations.** I wrote that reading guide from what API Gateway does to an unrouted path, in a
repo whose own diagnostic prints, three steps earlier, the exact reason that does not apply here.
The evidence I needed was in the output of the tool I was editing.

## THE PRICE WAS VISIBLE AND UNPRESSABLE, AND THE GATEWAY ROUTE FOR IT MAY NOT EXIST

**Founder, 2026-09-11: *"I do see Build 3c2e1188 and also see the '50 stars raises it to 25
addresses for 90 days' but you've not wired the actual payment rails in there. Why not?"***

**The rails ARE built, end to end, and every piece is on `origin/main`:** the Worker posts
`/v1/watchlist/invoice`, `stars_invoice()` calls `createInvoiceLink` in `XTR` with no provider
token, `tg.openInvoice` opens it, `handle_pre_checkout` answers inside Telegram's ten seconds,
`handle_stars_payment` reads the user id from the signed `from` field, and `grant_slots()` is
idempotent on `telegram_payment_charge_id`. So his conclusion was right and the mechanism was
not one he could see.

**MY HALF: THE TIER LINE I SHIPPED AN HOUR EARLIER HAD NO TAP TARGET.** It named a price in
prose, and the only buy control in the app was rendered from the `/v1/watchlist/list` response
beside the slot meter. So the fix for "the price is invisible" produced "the price is visible
and unbuyable" -- the same defect one layer down, in the patch for it. **Buying depends on the
signed initData and nothing else; the list adds better numbers, not capability.** The button is
static markup now, wired at module load, with the live response refining its numbers and hiding
it for somebody who has already paid. A test fails if the wiring moves back inside `loadWatches`,
proven by moving it.

**THE OTHER HALF, AND IT IS THE ONE THAT ACTUALLY BLOCKS A PAYMENT: the `invoice` route probably
does not exist at the API Gateway edge.** `tools/create_watchlist_routes.sh` gained `invoice` in
`PARTS` in commit `63e769f`, THIS session. The script last ran on 2026-09-09, when there were
three routes. The Lambda's `ROUTES` table carries `/v1/watchlist/invoice`, main carries the
handler, and **the edge has never been told the path exists**, so the Worker's POST gets an API
Gateway 404 and the app says the invoice could not be opened. Re-running the script is the fix
and it is idempotent: it adds the one missing resource and leaves the other three alone.

**UNVERIFIED from the container, and it must stay labelled that way** -- there are no AWS
credentials here, so this is read off the script's own `PARTS` line and the date it changed,
which is evidence about the repo and not about the edge. `tools/diagnose_watchlist_routes.sh`
answers it for real in one read-only run.

**THE GENERAL FORM, and it is the third costume this week: a route added to the handler's
dispatch table is not a route.** A path lives in three places -- the client that calls it, the
Lambda that answers it, and the gateway resource that connects them -- and only the first two are
in the repo. Adding the first two and pushing looks complete, tests green, and 404s at the edge.
Same family as "a registered attribution key is not a live integration" and "three lists must
agree": **the half that cannot be checked from here is the half that is missing.**

## THE PRICING WAS BEHIND A NETWORK CALL, SO A FAILED CALL DELETED THE PAID TIER

**Founder, 2026-09-11: *"why don't i see any copy on Paying stars for watching more addresses or
is our approach to remind the user just before they deplete their free watches"*** Both halves
are worth answering, and the second one was already fixed while the first was still broken.

**No, it is NOT a reminder at the wall, and that changed earlier the same day.** The offer was
gated on `used >= limit - 1`; it is now beside the slot meter at EVERY count, with the full card
only when the slots are actually full. That section is directly below this one.

**So why could he not see it? EVERY WORD OF THE PRICING WAS RENDERED FROM
`/v1/watchlist/list`.** The slot meter, the inline Stars link and the tier line were all built
from that response, and all three are gated on `data.limit`. So:

- an unverified user (`uid` falsy) got one sentence and an early return,
- and a FAILED list collapsed to `data = {}`, which prints "Nothing watched yet" and **nothing
  about a paid tier at all.**

**A product with a paid tier and a product with no paid tier rendered identically**, and the
second is what you get whenever the call does not come back. **What we charge is a fact about our
own product. It must not depend on a network call succeeding.** The tier line is STATIC markup in
the watch tab now, on screen before any request is made; the live response refines it and drops
the upsell entirely for somebody who has already paid.

**AND A FAILED LIST WAS RENDERING AS AN EMPTY ONE**, which is worse than the missing price:
"Nothing watched yet" over a watchlist that might be full reads as *my watches are gone*. The
failure path now names the cause -- the server's own error, or an unreachable endpoint -- and
returns before the empty state. Same rule as the CORS preflight and the 404 probe: **a check that
says something is wrong owes the reader the evidence that says WHICH thing.**

**THE COST OF STATIC COPY IS A SECOND COPY OF FOUR NUMBERS, AND IT IS PINNED.** The Worker now
holds 3 / 25 / 50 / 90, whose authority is `FREE_WATCH_SLOTS`, `PAID_WATCH_SLOTS`,
`SLOTS_PRICE_STARS` and `SLOTS_DURATION_DAYS` in `relayshield_watchlist.py`. Two files that must
agree with nothing checking that they do is run 134's shape, and here it is worse than a wrong
banner: **copy shown to a buyer that disagrees with what the server grants is a price we do not
honour.** `test_miniapp_routes.py` reads the SERVED page and fails if the numbers drift, and
fails on any number in that line the server does not recognise. Substituted as `__TOKEN__`s
rather than page-scope constants, because the page and the Worker share nothing else -- the
`INLINE_TEXT` defect recorded below.

**AND THE GUARD I ALREADY HAD ASSERTED THE WRONG THING.** `test_a_paying_user_is_never_shown_the
_upgrade` required every condition naming `slots_expire_at` to be NEGATED -- a proxy for the rule
rather than the rule -- so it failed on a correct positive branch that renders the PAID state. It
walks the branch BODY now and forbids selling inside it. **A test that pins the shape of a
condition instead of what the branch does will eventually fail on correct code, and the temptation
then is to loosen it rather than fix it.**

## THE STARS OFFER WAS ONLY VISIBLE AT THE WALL, AND MY OWN COMMENT SAID OTHERWISE

Founder, 2026-09-11: *"Shouldn't the watch tab include the Stars payment workflow? Users pay us to
watch interesting addresses that are tied to their money, so we should prompt them to pay."*

He is right, and the code contained its own indictment. The offer was gated on
`data.used >= data.limit - 1` -- two of three slots -- with a comment directly above it reading
*"Offered BEFORE the slots are full, not only at the wall."* **The comment and the code disagreed,
and the code won.** A user with zero or one watch never learned the paid tier existed.

**That is the inline-mode defect in a third place: built, live, and pointed at by nothing.** A paid
tier nobody can see is a paid tier nobody buys, and the people watching addresses their money is
actually in are precisely the ones for whom 50 Stars is obviously worth it.

**QUIET AT LOW COUNTS, PROMINENT AT THE WALL**, which is the distinction worth keeping. An inline
link beside the slot meter is information; a card that dominates the screen before somebody has
watched anything is an advertisement, and it converts worse because they have not felt the value
yet. The full card still fires from `add_watch`'s `slots_full` branch.

**And the empty state now sells watching rather than apologising for being empty.** It said "Nothing
watched yet" and returned, so the tab carrying the only paid product in the app said nothing about
what it does or what it costs to anybody who had not already used it.

**THE ONE LINE OF COPY THAT IS NOT NEGOTIABLE: the free slots are alerted immediately and in full.**
The only thing Stars buy is MORE SLOTS, because a slot is the only thing with a marginal cost -- a
recurring TON Center call, a DexScreener call and a corpus query, forever. Copy hinting that paid
alerts are faster, prioritised or more complete would be taxing the free tier while claiming not to,
which is the single principle this design exists to hold. A test forbids "faster", "priority",
"real-time", "sooner" and "delayed" in the watch tab's user-visible strings, and separately requires
a sentence that positively tells a free user their alerts are unchanged.

## A DETECTOR WHOSE EXTRACTOR STOPS AT THE THING BEING DETECTED CANNOT DETECT IT

The most interesting bug of the session, and it passed green for as long as nobody triggered it.

`page_script()` extracted the Mini App's client code by walking forward from `` const PAGE = ` `` to
the first UNESCAPED backtick. Two things followed, and both were wrong:

- **The page ends at line 994, not 981.** The quiz builds NESTED template literals with escaped
  backticks, and the walk stopped near them, so the scope test was silently checking about two
  thirds of the page.
- **The stray-backtick test could never fire.** A stray backtick ENDS the extraction, so the
  offending character always falls outside the range being scanned. Circular by construction.

Both are fixed by finding the template's real CLOSING DELIMITER (`</html>` plus backtick-semicolon)
rather than scanning for the next backtick. Proven three ways: a stray backtick near the top is
caught, one PAST the nested templates is caught, and the legitimate escaped ones are not flagged.

**`node --check` IS IN THE SUITE NOW, and was not.** `test_miniapp.py` says "no node" in its own
docstring, so the authoritative parse check had never been part of any test run -- the stray backtick
has broken this file three times and was caught by somebody happening to run node by hand each time.
That is the quiet-alarm shape guarding the one defect this file reliably produces. The targeted
backtick test sits alongside it because `node --check` reports the error at whatever token follows
the backtick, which reads as a problem with that token rather than with a quoted word in a comment
forty characters earlier.

## STRIPPING COMMENTS BEFORE GREPPING IS NOW A SHARED HELPER, AFTER THE FOURTH TIME

Every guard written in `test_miniapp_routes.py` has, on its first run, matched prose describing the
defect rather than the defect itself:

1. a comment naming `BOT` failed the Worker-scope test,
2. a docstring naming `invoice_payload` failed the signed-identity test,
3. a comment quoting `/v1/link-check` failed the never-metered test,
4. a comment reading *"better, faster or more complete"* failed the test forbidding exactly those
   words in user copy.

**It keeps recurring because the two habits collide by construction:** the natural way to write a
guard is to search the file, and the natural way to write good code is to explain the rule beside
the code that follows it. `strip_js_comments()` is module-level now rather than something each test
rediscovers, and `code_only()` does the same job for Python via `ast`.

**And the matching half of the same lesson:** copy in this file wraps across concatenations, so
`"alerted immediately and in " + "full."` matches neither half of a contiguous search. The first
version of that assertion failed on copy that was entirely correct. String literals are joined
before matching.

## THE EXAMPLE IS A REAL CHECK AGAINST A URL THAT IS FLAGGED BY CONSTRUCTION

An empty box is the worst possible first screen for a product whose most common honest answer is
"nothing known": a first-time user who pastes something clean learns nothing about what the app is
for.

**It is not a canned card.** It fills the box and runs the same code path the user runs, so whatever
comes back is true at the moment they press it. A verdict we rendered ourselves is a claim about our
own product that nobody can check and that goes stale silently.

**And the URL is `testsafebrowsing.appspot.com/s/malware.html`, which is GOOGLE'S OWN test host**,
published so anyone integrating Safe Browsing can prove their integration fires. `/v1/link-check`
consults Safe Browsing, so the flag is earned rather than asserted -- and it is not a real criminal's
domain, which matters because the alternative is shipping a live malicious link inside our own app
and inviting people to tap it.

**No TON address ships as an example, deliberately.** Naming one is a claim about a live address that
cannot be verified from this container, and an address that stops being flagged turns the example
into a false negative on the app's own front screen. A test forbids one appearing there.

## INLINE MODE HAS BEEN BUILT THE WHOLE TIME AND NOTHING TOLD ANYONE

Found 2026-09-11 while answering "is the Mini App compelling enough to return to". The honest answer
turned on a surface that already existed.

`handle_inline_query` in `relayshield_telegram_webhook.py` is complete, rate-limited and live: type
the bot's username then a link, **in any chat**, and the verdict posts into that conversation.
**Nothing mentioned it.** Not the Mini App, not the share card, not the bot's welcome. A finished
feature with no route to it, which is the same shape as a watchlist that could not alert.

**That matters more than any new feature, because it is the only surface that reaches the moment of
need.** A scam arrives in a group chat while the user is thinking about something else. An app they
have to remember, find and open has already lost; a check that works inside the conversation where
the scam was posted has not.

`switchInlineQuery` is the one-tap version and is **FEATURE-DETECTED, not assumed**: Telegram
documents it as available only to Mini Apps launched from a keyboard or inline button, and ours is
launched from a direct link, so it may simply be absent. UNVERIFIED from the container. The text
fallback is therefore the path that must work and is written to be useful on its own.

## THE BUG `node --check` CANNOT SEE: WORKER SCOPE IS NOT PAGE SCOPE

Shipped and caught within the same session, 2026-09-11.

`INLINE_TEXT` was declared in the Worker's own scope, forty lines above the `const PAGE = ...`
template literal, and read from inside the page. **`node --check` passed. `build_miniapp.py --check`
passed.** The file parses; the string is a valid string. The browser would have thrown
`ReferenceError` on load and the tip would simply have been blank, with no error anywhere we look.

Same family as the stray backtick that shipped on 2026-09-10: **syntactically valid, runtime dead.**
Everything outside the template literal runs in a Cloudflare Worker, in a different process on a
different machine, and the two scopes share nothing but the `__TOKEN__` substitutions done at
request time.

`test_miniapp_routes.py` now extracts the page template and fails if any SCREAMING_CASE constant the
page reads is declared only in the Worker. Proven by moving the constant back and watching it fail.

**And the guard's own first run was a false positive, for the third time in this file's history:** it
flagged `BOT` because a COMMENT two lines above says "sat in the Worker's own scope alongside BOT".
Prose describing a defect is not the defect. It strips comments now, the same correction
`test_telegram_markdown_escapes.py` and `code_only()` already carry -- and it keeps arriving in new
costumes because the natural way to write a guard is to search the file.

## ONE ATTRIBUTION KEY PER DESTINATION, NOT PER CATEGORY. AND THE FIX WENT TO THE WRONG ENDPOINT.

Built 2026-09-11, asked for as *"Build the measured bot funnel for all 6 discovery routes and run
tools/miniapp_funnel.py before and after each one."*

**THE DEFECT THAT MADE THE MEASUREMENT WORTHLESS BEFORE IT RAN.** All five Mini App announcement
channels shared one key, `tg-miniapp-channel`. So `@trendingapps` at 3.9M subscribers and
`@telegtapps` at 9,671 were **indistinguishable in the logs** -- and which of those works is the
entire question the funnel exists to answer. If the big channel produces nothing and the small one
produces returning users, that is the most valuable thing we could learn about distribution, and a
shared key throws it away. `miniapp_routes.json` is now the source of truth, nine routes, one key
per DESTINATION.

**AND THE `source=` FIX I SHIPPED THE DAY BEFORE WENT TO AN ENDPOINT THE MINI APP DOES NOT CALL.**
`/v1/ton-address` gained a source on 2026-09-10. Both the Mini App and the widget reach the API
through `check()`, which routes URLs to `/v1/link-check` and **every address, TON included, to
`/v1/wallet-risk`**. `/v1/ton-address` is never reached from the app. So the fix was real, correct
for direct API callers, and measured nothing for the client it was written for -- while looking
done.

Found by tracing the call rather than by reading the endpoint list, which is the only way it could
have been found: both endpoints exist, both accept a TON address, and only one is ever reached.
**The general form: "the endpoint that does X" and "the endpoint this client calls" are different
questions, and instrumentation must answer the second.**

### THREE LISTS MUST AGREE, AND THE TEST CAUGHT A LIVE REGRESSION ON ITS FIRST RUN

A route key must appear in `miniapp_routes.json`, in `ALLOWED_SOURCES` (the Worker's edge gate) and
in `_SOURCE_ALIASES` (the landing page). **A gap in either mirror produces attribution that looks
like it worked:** the Worker silently downgrades an unknown key to the generic `tg-miniapp`, and the
landing page logs `unmatched:` and renders no banner. That second one is FD-8, four months of it.

`test_miniapp_routes.py` fails if the three disagree, and it earned its place immediately:
rebuilding the Worker's list from the route table **dropped `tg-miniapp-bot`**, which is not a route
but a loop key, and would have cost the `/app` command its attribution. My edit, caught by my test,
before it shipped.

**The property that makes any of this possible is one line in `_resolve_source`,** and it is easy to
destroy by tidying: it returns the RAW parameter as the logged key rather than the alias it maps to.
That is why every route renders one banner and stays separable in CloudWatch, exactly as
`n8n-offboarding` and `n8n-onboarding` already did.

### BEFORE-AND-AFTER IS A MECHANISM NOW, NOT A DISCIPLINE

`--snapshot before-<id>` writes a committed JSON baseline; `--compare before-<id>` prints the delta.
A baseline held in a terminal that has scrolled away is not a baseline, and a comparison done from
memory is not a comparison.

**It REFUSES to overwrite a baseline**, and that refusal is the most important line in the tool.
Overwriting it after the submission has run turns the before-and-after into a comparison of a number
with itself, which reads as "the channel did nothing" -- a false negative on the one measurement the
whole exercise exists for.

**And every comparison prints the sliding-window caveat.** Both runs count a rolling `--days` window
back from now, so a delta is only the submission's effect if the two runs are close together
relative to that window. A 30-day baseline compared five weeks later measures the window sliding.
Reporting that silently as a channel result is the confident-wrong-number failure this repo has paid
for twice.

### TWO THINGS THE ROUTE TABLE RECORDS AS DECISIONS RATHER THAN GAPS

**The menu button is rank 10 and has NO KEY, on purpose.** A registered key would make it look
approved. `/setmenubutton` REPLACES the button that belongs to the TI monitoring product, and
shipping it means adding the key first -- which is the check firing correctly rather than a gap.

**TON catalogues are UNBLOCKED.** That route was gated on "only if TON scans ship" and they now do:
`/v1/ton-address` plus `relayshield_watchlist_monitor.py`, which watches TON and only TON. A TON
catalogue is the one audience for whom that is the headline rather than a detail.

**And `@trendingapps` does not go second in practice despite ranking second.** It is the largest
single first impression we will ever spend, so `@telegtapps` at 9,671 runs first: the cheapest place
to discover the listing copy is wrong. The rank column is priority; the running order in
`miniapp_discovery_funnel.md` is the sequence, and the two differ deliberately.

### RUN 142 IS RUN 134'S SHAPE FOR THE THIRD TIME

    relayshield-watchlist WAS DEPLOYED. Only the probe was denied — the deploy
    role has no lambda:InvokeFunction on it.

`iam_github_deploy_invoke.json` gained the ARN in the mapping commit, and **the repo half does not
push the policy to AWS.** `sh tools/apply_deploy_invoke_policy.sh` does. Third occurrence, and the
error message did its job again: the code is live, only the verification was refused.

**THE STARS GRANT IS CLOSED. MEASURED 2026-09-12, AND THIS SECTION USED TO SAY THE OPPOSITE.**
It recorded the webhook's role `relayshield-breach-check-role-1sapnwdl` as returning **implicitDeny
on `dynamodb:GetItem` and `dynamodb:PutItem`** against `relayshield_watchlist`, with the conclusion
that **a Stars purchase would take the money and fail to credit it.** That was true when it was
written and is not true now. `sh tools/grant_stars_watchlist_iam.sh` run read-only reports:

    dynamodb:GetItem                       allowed
    dynamodb:PutItem                       allowed
    secretsmanager:GetSecretValue          allowed

and `relayshield-stars-watchlist-grant` is in that role's ATTACHED MANAGED policies, so the script's
`--apply` path ran at some point and nobody recorded it. **A DOC RECORDING AN OPEN ITEM IS A LEAD,
NOT A FACT, EXACTLY AS A DOC RECORDING A DONE ONE IS.** This file already says that in the other
direction and the cost is the same either way: a stale open item spends a round proving it is shut,
and the only reason this one was cheap is that the read is one command.

Note the role is carrying **26 inline policies plus 11 attached managed policies** as of that run.
The inline budget is spent and the managed slots are at 11 of 10-plus-defaults, so the IAM SPLIT
runbook (`iam_role_split.md`) is closer to forced than it looks.

**Read this alongside the deploy-invoke grant above, which IS still outstanding and is a different
thing entirely.**

## THE MERGE THAT FAILED THREE TIMES: REPRODUCED, AND THE FIX IS ONE LINE

**2026-09-11. Andrew ran the same block three times across two turns and got the same
"0" result each time.** Two of those turns were spent on my diagnosis rather than on the fix,
and the diagnosis was wrong twice before it was right. **It has now been REPRODUCED in a
scratch repo, byte for byte**, so this section is a measurement rather than a theory.

**The exact failure:**

    No local changes to save
    error: Your local changes to the following files would be overwritten by merge:
      ansible-relayshield relayshield-snap
    warning: unable to rmdir 'ansible-relayshield': Directory not empty
    Merge with strategy ort failed.

**The cause, and it is a LOOP I built.** Rule A2 already records that `git add -A` stages his
two embedded git repositories as gitlinks. What A2 did not work out is what happens next:

1. `git add -A` puts `ansible-relayshield` and `relayshield-snap` in the INDEX as gitlinks.
2. `git stash --include-untracked` **cannot stash a nested git repo.** It prints
   "No local changes to save" and leaves them exactly where they are.
3. A **fast-forward** merge survives this. A **three-way** merge does not -- and every merge
   from now on is three-way, because `origin/main` already carries a merge commit.
4. The failed merge partially unwinds the index, so a *second* run of a block WITHOUT
   `git add -A` would have worked.
5. **But the block HAD `git add -A` at the top**, which re-staged them before every attempt.

So each run re-created the exact condition that made the previous run fail. That is why three
identical failures looked like one stubborn problem and were actually the same fix, refused
three times by my own block.

**THE FIX, VERIFIED END TO END IN A SCRATCH REPO INCLUDING IDEMPOTENCY:**

    git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap

`--cached` touches only the index, so **the embedded repos and their history are untouched on
disk** -- confirmed by reading their git log after the merge. `-f` is required and the first
version of this line omitted it, failing with "staged content different from both the file and
the HEAD"; that was caught by running it, not by reading it. `--ignore-unmatch` makes it exit 0
when there is nothing to remove, so it is safe on every future merge.

**AND `git add -A` IS GONE FROM EVERY BLOCK, PERMANENTLY.** Rule A2 said so on 2026-09-11 and a
block shipped with it anyway on the same day. The standard merge block is now:

    cd ~/dev/relayshield
    git checkout main
    git --no-pager fetch origin claude/<branch>
    git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap
    git stash push --include-untracked -m "pre-merge untracked"
    git -c pull.rebase=false merge --no-edit FETCH_HEAD

**The permanent fix is his to choose and is one command:** move the two embedded repos out of
the clone, `mv ~/dev/relayshield/ansible-relayshield ~/dev/relayshield/relayshield-snap ~/dev/`.
A repository inside a repository will keep generating this class of problem no matter how many
lines the block carries -- the same reasoning that separated the clone from the documents
folder on 2026-09-05. Until he does, the `git rm --cached` line handles it.

**The general form, and it is the one worth carrying: when the same instruction fails three
times, the instruction is the loop.** I spent two turns hypothesising about `.gitignore` and
about gitlinks on `origin/main` -- both disproved by one `git ls-tree` -- when reproducing it
locally took four minutes and settled it completely. **A failure that reproduces is not a
mystery, it is a test case, and building the test case first is cheaper than the third guess.**

## STARS SELL WATCH SLOTS. NOT CHECKS, AND NOT ALERTS. DECIDED AND BUILT 2026-09-11.

**This SUPERSEDES the "charge for the alert, not the scan" conclusion in
`miniapp_stars_the_alert_not_the_scan.md`**, which was mine and was wrong, and the reason it was
wrong is worth more than the conclusion.

**Charging for the ALERT charges at the moment the user's money is already moving.** The free
tier's promise is "we will tell you if this changes"; attaching an invoice to that message makes
the promise bait. It is the same defect as a paywall on `/v1/link-check`, one step further down
the funnel and harder to see.

**A SLOT IS THE HONEST UNIT, because it is the one thing that actually costs us money.** Every
watched target is a TON Center call, a DexScreener call and a corpus query, on every cycle,
forever. That bill scales with slots and with nothing else. So:

  * **Checking: free, unlimited, unchanged.** `/v1/link-check` and `/v1/ton-address` are keyless
    and stay keyless. `test_checking_is_never_metered` fails if any of them appears in
    `relayshield_watchlist.py`, and it was proven by adding one.
  * **Watching: 3 slots free**, alerted fully and immediately, no delay and no degradation.
  * **Stars: 50 ⭐ raises it to 25 slots for 90 days.** A capability upgrade, never a tax.

This satisfies the standing principle exactly as written: **Stars pay vendor bills, they never
tax the free tier.** And it is self-limiting by construction -- it can only ever charge for the
thing with a marginal cost, so it cannot drift into taxing the thing the app is for.

**90 days rather than forever**, because Stars are a one-off purchase with no subscription
primitive, so an expiry has to live on our side or not exist at all, and a permanent
entitlement bought once outlives the feature.

### READING THE PAYMENT CODE BEFORE WIRING STARS FOUND TWO DEFECTS, ONE OF THEM A BILLING HOLE

Rule C says an instruction that writes to a live surface is preceded by the one that reads it.
Applied to code rather than to BotFather, it paid immediately.

**1. A 50-STAR PAYMENT WOULD HAVE BOUGHT A FULL SUBSCRIPTION.** `handle_successful_payment`
maps the payment amount to a plan with `tier_map.get(amount, TIER_PERSONAL)`. A Stars purchase
arrives as `total_amount=50`, matches no plan, and falls through to the **default**. The buyer
would have been given a paid subscription for about a dollar and then sent down the phone-number
onboarding for SIM-swap monitoring they never bought. **Currency is the discriminator, not the
amount:** `XTR` is Stars and every real plan is priced in fiat, so the XTR branch returns before
the tier map is ever consulted, and a test asserts that ORDER rather than merely the presence of
the branch.

**2. NO `pre_checkout_query` BRANCH EXISTED, SO NO TELEGRAM PAYMENT COULD EVER COMPLETE.**
Telegram sends a pre-checkout query and gives **ten seconds** to answer it. An unanswered query
fails the payment on the buyer's side and logs nothing on ours. The most expensive shape a
missing branch can take: every part of the purchase looks built, the invoice opens, and no money
can ever arrive. It approves unconditionally and **fulfils nothing** -- granting there would
hand out slots to anyone who opens an invoice and abandons it.

**The grant is idempotent on `telegram_payment_charge_id`.** Telegram retries a webhook it did
not get a 200 from, and a retry that extended the entitlement again is a free upgrade for anyone
who can make our handler time out once.

## PINNING A MINI APP: TELEGRAM HAS NO SUCH THING. YOU PIN A CHAT, AND WE HAD TO CREATE ONE.

**Asked four times across three turns and answered wrongly three times, because every answer was
about where to FIND the app.** That was not the question.

**The fact that settles it: Telegram has no primitive for pinning a Mini App.** What a user pins
is a CHAT. A Mini App opened from a direct link (`t.me/relayshield_bot/idcheck`) does not create
one -- the web view opens over the app and the bot never appears in the chat list. So a new user
who has never messaged `@relayshield_bot` has **nothing to long-press**, which is exactly what
Andrew kept reporting, on both laptop and phone, and it was correct every time.

**And pinning the BOT does not help**, which was his second question: the existing pinned chat is
the TI monitoring bot, and pinning it gives no route to the Mini App.

**THE FIX, AND IT IS IN OUR CONTROL RATHER THAN TELEGRAM'S.** A bot may message a user who has
opened it through a Mini App, and that message is what creates the chat entry. So **the first
watch now sends one**, and it says how to pin. Three things at once:

1. The chat exists, so it can be pinned, muted or archived -- all the things a user expects.
2. It **proves the alert channel before an alert is needed.** Finding out the bot was blocked at
   the moment something got drained is the worst possible time to find out.
3. It turns a Mini App user into a bot subscriber, which is the flywheel
   `relayshield_watchlist.py`'s own docstring has claimed since 2026-09-09 and did not do.

Only on the FIRST watch: a confirmation on every add is a notification tax on the feature's own
power users.

**The home-screen route (`addToHomeScreen`, Bot API 8.0) stays as it is** -- feature-detected,
Android-mostly, higher friction, and now the second option rather than the only one.

## THE WATCHLIST PROMISED ALERTS AND NOTHING SENT THEM, FOR TWO DAYS

Found 2026-09-11 while scoping the monitor, and it is the worst kind of gap because every part
of it looked finished.

`relayshield_watchlist.py` shipped on 2026-09-09. Its docstring says the chat_id is **encrypted
rather than hashed** specifically because "we cannot send an alert without the chat_id". The
table, the KMS grants, the initData verification and the CORS preflight were all built and all
correct. **There was no scheduled monitor, no notification code and no workflow.** Every user who
tapped "Tell me if this changes" was told something untrue.

`relayshield_watchlist_monitor.py` is the sender. **TON only, deliberately** -- Telegram Mini
Apps live inside Telegram's rules and TON is the chain Telegram ships, which is Andrew's
instruction and also the right call. Rows of other kinds are **counted and logged, never
deleted and never silently dropped**, and the Mini App labels them "not re-checked yet" in the
list: a watchlist that hides what it cannot re-check is indistinguishable from one that works.

**THE THREE RULES IN IT THAT MUST NOT BE RELAXED:**

1. **THE FIRST RUN AGAINST A ROW NEVER ALERTS.** Rows written before the monitor existed carry no
   snapshot, so every signal would read as "changed from nothing" and the first scheduled run
   would message every user about every target at once. That is how a security bot gets reported
   rather than uninstalled, and it is one `if` away. Proven by deleting the branch and watching
   the test fail.
2. **IMPROVEMENTS ARE RECORDED, NEVER SENT.** An alert is for action. "Good news" at 3am trains
   people to ignore the next one, and the next one is the one that mattered.
3. **"WE COULD NOT CHECK" MUST NEVER RENDER AS "IT IS GONE".** An upstream outage that reads as
   an emptied pool sends a false rug alert, which is the single mistake that would make this
   product actively harmful. Every unreadable number is `None`, never `0`, and a failed lookup
   leaves the stored snapshot untouched so the NEXT run diffs against the last real observation.

**It imports `handle_ton_address` from `relayshield_api.py` rather than calling the vendors
itself**, for two reasons and the second decided it. A fifth copy of the TON calls would drift
from the endpoint it is meant to be monitoring. And the alternative that looks cleaner is worse:
calling our own public `/v1/ton-address` over HTTP would work once per cap window, because the
**keyless per-IP cap would see every invocation arriving from one NAT address and throttle the
monitor against itself.** The dependency walk was run against the deployer's own `resolve_deps`
grep and packages five files -- checked, not assumed.

## A MEASUREMENT TOOL WRITTEN FROM WHAT THE CODE *SHOULD* LOG IS A FALSE ABSENCE

`tools/miniapp_funnel.py` answers the founder's high-priority question -- tg-miniapp arrivals,
bot signups, Stars, and traffic to the API landing site -- and **two of its seven filters were
wrong on the first draft, both in the direction that reports a live channel as dead.**

- It filtered the webhook log for `SRC_miniapp`. That is the **deep-link payload**; the webhook
  strips the prefix and lower-cases it before logging, so the line reads
  `acquisition source=miniapp` and the filter would have matched nothing, forever.
- **`/v1/ton-address` logged no source at all.** `/v1/link-check` has logged one since it was
  written, so half the Mini App's traffic was uncountable. Fixed in the same commit rather than
  noted: a key that is sent, accepted and never logged is the same false absence as a key that
  was never registered.

Both are pinned by tests that read the filter out of the tool and assert it against the line the
code actually writes, and both were proven by reintroducing them.

**The general form: a zero from a measurement tool GETS ACTED ON.** That makes a wrong filter
more expensive than no tool at all, and it is the `sorted()`-on-version-strings lesson in a new
place -- a number I print is evidence the reader will act on.

## TELEGRAM STARS IN THE MINI APP: NOT NOW, AND NEVER AS A CAP ON THE FREE CHECKS

Asked 2026-09-10: *"Its still not clear how we can use the stars or what value they bring."* Full
reasoning in `miniapp_stars_monetization.md`; the parts that must not be re-derived:

**BOTH PAYWALL CANDIDATES ARE ALREADY FREE, AND ONE COSTS US NOTHING.** `/v1/link-check`'s own entry
in `KEYLESS_SCAN_ENDPOINTS` says it: *"no paid upstream at all: DynamoDB, Safe Browsing's free tier
and RDAP. The per-IP cap is here to stop it becoming an open proxy, not to protect a vendor bill."*
And `/v1/ton-address` has been keyless since Crypto Shield Mobile, so charging for it would REMOVE a
free feature rather than add a paid one. TON *token* checks are the one real gap and they are a
BUILD, not a paywall -- only `/v1/ton-address` exists.

**THE VALUE IS A SIGNAL, NOT REVENUE, AND THE SIGNAL IS UNINTERPRETABLE TODAY.** Stars reach a buyer
the other three rails structurally cannot -- an anonymous Telegram user with no account, card or
wallet -- and a payment measures value where opens and returns measure interest. But the six
discovery routes have not run and `tools/source_arrivals.py` has never been run against the
`tg-miniapp` keys, so this would be optimising a funnel nobody has measured. **The gate is that
measurement, not a date.**

**THE CONSTRAINT WORTH KNOWING EVEN THOUGH WE ARE BUILDING NOTHING: Stars are the ONLY compliant way
to charge a consumer inside a Telegram Mini App.** Telegram requires digital goods sold in Mini Apps
to be paid in Stars, because that is how it satisfies Apple's and Google's IAP rules. **Wiring
"upgrade" from inside the Mini App to Stripe, x402 or the developers page for a digital good is the
route that gets a bot restricted** -- and it is exactly what a future session would do, reasonably,
because all three rails already exist one link away. UNVERIFIED from the container
(`core.telegram.org` is egress-blocked); the check is one tab,
<https://core.telegram.org/bots/payments-stars>, read BEFORE any payment code.

**IF IT IS EVER BUILT, ONE PRINCIPLE DECIDES THE SHAPE: Stars pay vendor bills, they never tax the
free tier.** Never a cap on `/v1/link-check` or `/v1/ton-address`. The honest candidate is
`/v1/scan-url` -- VirusTotal, a real per-call bill, already $0.05 on the PAYG rail. Self-limiting by
construction: it can only charge for things that cost money, so it cannot drift into taxing the thing
the app is for.

**The expensive prerequisite is already built**, which is worth knowing before anyone re-scopes this
as large: `relayshield_watchlist.py` verifies Telegram's `initData` HMAC and derives the user id as
`HMAC-SHA256(pepper, telegram_user_id)`. A verified non-spoofable per-user identity is the hard half
and it is live.

## WHERE 2026-09-13/14 LEFT THINGS — READ THIS FIRST, IT SUPERSEDES THE 2026-09-09 TOP 15

### THE HEADLINE: STARS WORKS END TO END. A REAL PURCHASE COMPLETED.

**2026-09-13. The founder bought 50 Stars and the Mini App showed "25 watch slots,
alerted immediately and in full, until 2026-12-12."** That single event proves five
things no test could:

1. `createInvoiceLink` mints, `tg.openInvoice` opens it.
2. `handle_pre_checkout` answers inside Telegram's TEN SECONDS.
3. The **XTR branch returns before the fiat tier map**, so a `total_amount=50`
   did NOT fall through to `tier_map.get(amount, TIER_PERSONAL)` and hand him a
   full subscription for a dollar.
4. `grant_slots` wrote the entitlement row -- so the webhook role's DynamoDB
   grant is real.
5. The app refreshed to the PAID state and hid the buy button.

**The whole revenue path is live. Nothing about Stars is theoretical any more.**

**AND THE PURCHASE ROUTE MATTERS FOR ANYONE WHO REPEATS IT.** Telegram Desktop
refused to SELL him Stars -- "this payment method is not available for the
selected product", which is the top-up provider refusing, NOT our invoice. He
bought 100 Stars another way and the Mini App then paid from the balance with no
top-up sheet at all. **Stars are an ACCOUNT balance**: buy them by whatever route
completes, then spend them from any device. A desktop top-up failure says nothing
about our code, and the screenshot that shows "50 Stars Needed" over our invoice
is PROOF our side worked.

### THE BOT TOKEN WAS NEVER UNWRAPPED. THREE OF FOUR CALL SITES WERE DEAD.

**The defect underneath the Stars failure, and it was one layer past the secret
name fixed the day before.** `_get_secret` returns the SecretString VERBATIM and
the secret is a JSON object, so what it hands back is
`{"telegram_bot_token": "..."}` and **not a token**. Every caller has to unwrap
it. On 2026-09-12 the four that do were:

    verified_user_id      unwrapped with BOT_TOKEN_KEY first        CORRECT
    stars_invoice         did not unwrap at all                     DEAD
    first-watch greeting  tried only the two GUESSED keys           DEAD
    watchlist monitor     read the OLD hyphenated secret name       DEAD

`stars_invoice` put the whole JSON blob into the Bot API path, so Telegram
answered 404 for a token that is not a token and the user saw "could not start
the purchase" over a log that said Not Found. **A wrong answer, not an
exception** -- which is why fixing the secret NAME made `list_watches` work while
the buy button stayed dead. Two different bugs one layer apart.

**THE MONITOR WAS THE EXPENSIVE ONE.** Its `BOT_TOKEN_SECRET` still said
`relayshield/telegram-bot-token` with HYPHENS, so **every alert it ever tried to
send raised ResourceNotFoundException** -- in the one function whose whole job is
keeping the watchlist's promise -- with no trace but a WARNING saying the send
failed. Its IAM ARN named the hyphenated secret too, which is the half that would
have SURVIVED fixing the name: ResourceNotFound becomes AccessDenied.

**`bot_token()` in `relayshield_watchlist.py` is now the single owner** and the
monitor imports it module-level, where `resolve_deps` packages it. Nine tests,
four EXECUTED against a stubbed Secrets Manager because every dead call site was
syntactically perfect.

**The general form, for the fifth time: N copies of a three-line unwrap is N
chances to be wrong, and the copies do not fail loudly, they fail with a wrong
value.**

### THE FUNNEL WAS HUNG, NOT BROKEN. `filter_log_events` IS A SCAN.

Reported twice as "I'm still getting no reply to your terminal command". Nothing
raised and no output was lost: `tools/miniapp_funnel.py` printed its header and
then sat inside a pagination loop. **`filter_log_events` returns a `nextToken` to
continue walking log streams even when the page it just returned held no matching
events**, so a rare pattern over 30 days of `/aws/lambda/relayshield-api` is
thousands of sequential round trips -- and EIGHT such sweeps ran before a single
number could print.

It reads **CloudWatch Logs Insights** now: one query plus a short poll, progress
on stderr per query. Three things it could not do before:

* **NEVER INVOKED separated from ZERO.** A group-level probe says whether the
  function ran at all, so "idle" and "ran constantly and matched nothing" stop
  being the same output. The docstring had claimed this distinction for weeks
  and the code could not deliver it.
* **CAPPED.** Insights returns at most 10,000 rows; beyond that the number is
  rendered `>=N` as a FLOOR rather than silently under-reported.
* The observed window comes from the group's earliest event rather than the
  earliest MATCHING event, which is what that section actually claims.

**The stage regexes are NOT restated in Insights' parse syntax.** The query
filters on the coarse substring and the existing Python regex still matches, so
there is one copy. 16 tests, proven by reintroducing the scan call.

**IT NEEDS NEW IAM: `logs:StartQuery`, `logs:GetQueryResults`, `logs:StopQuery`.**
UNVERIFIED whether `relayshield-deployer` has them. A refusal comes back NAMED
(`ERROR AccessDeniedException` against the group that refused) and is never
rendered as a zero.

### THE WATCHING TAB COULD NOT ADD A WATCH

Reported in those words. The only route to a watch was Check tab, paste, check,
then press the verdict card's button -- so **the tab that explains watching, names
the price and carries the buy button was the one place a slot could not be used**,
and somebody who had just paid for 25 had nowhere to spend them.

It is not a looser path: the box runs the same off-chain gate (watching an EVM
address writes a row the TON monitor never re-checks) and the same `check()`
first (a row with no baseline reads as "changed from nothing" on the monitor's
first pass). Both pinned by tests that assert the ORDERING, not the presence.

### A RECOGNISER WITH NO PROMPT IS A FEATURE NOTHING POINTS AT

**The sharpest self-inflicted defect of the session, and it is a lesson this file
had recorded TWO DAYS EARLIER.**

The founder asked for Check-tab copy distinguishing bot developers. I shipped
`BOT_HANDLE`, a developer card, a registered `tg-miniapp-bottoken` key and its own
landing-page banner -- and **the placeholder still said "Paste a link, or a TON
address" and nothing anywhere mentioned a bot.** Deploy run 14 succeeded. The
feature was live and undiscoverable, which is the INLINE MODE defect exactly:
complete, live, and pointed at by nothing.

**The recogniser is not the feature. The route to it is.** There is now a visible
prompt that prefills `@relayshield_bot` -- ours, deliberately, because prefilling
a stranger's handle would point our app at somebody else's product and render a
card about it.

**AND HE CORRECTED MY REASONING, RIGHTLY.** I had written that a bot developer
"is already an API buyer". They are not. They are a developer whose own product
has the problem our endpoints solve -- a hypothesis about FIT, not a fact about
purchase, and stating it the other way round is how a plan ends up describing a
company we do not have.

### THREE OF MY OWN DEFECTS CAUGHT BY THE CHECKS THAT EXIST, IN ONE COMMIT

All before they left the container, and each one is a guard earning its place:

1. **Backticks in a comment inside the PAGE template literal.** That ends the
   template and ships a module registering no handlers. `node --check` caught it.
2. **Escapes eaten twice** -- a Python heredoc took one layer and the template
   literal took the rest, so the served text was `/^(?:https?://` and the module
   threw. **`node --check` PASSED. `miniapp_smoke.mjs` caught it**, which is the
   exact case it was written for.
3. **`openTelegramLink` about to be handed an `api.relayshield.net` URL**, and the
   CTA link never restored -- so the NEXT ordinary check would have offered a
   consumer developer documentation.

**AND TWO TESTS WERE WRONG RATHER THAN THE CODE**, which is the half worth
remembering:

* The three-lists guard required an ALIAS for every loop key and failed on
  `tg-miniapp-bottoken`. **Adding the alias would have broken what it protects**:
  `_resolve_source` applies aliases BEFORE the banner table, so an alias makes an
  own-banner unreachable. That is the `rsscan -> github` defect, already paid for
  once. The test accepts either and forbids BOTH now.
* The CTA-severity test took the FIRST `cta-line` write in the file and became
  the wrong block the moment a second branch wrote that element. Anchored on the
  severity ternary now.

### CSM-SIMSWAP-1: THE APP SOLD SIM SWAP MONITORING AND ENROLLED NOBODY

Five surfaces claimed it -- the paywall modal, the paywall screen, the phone
field, onboarding step 3, and the Solana dApp Store listing -- and
**`checkSimSwap()` in `crypto-shield-app/src/api/relayshield.ts` has ZERO
CALLERS.** The number is written to SecureStore and read by nothing, so
`scan_sim_swap_users()` has never had a Crypto Shield Mobile user in its set.

**IT WAS FOUND ON 2026-08-14 AND WRITTEN INTO THE DOCSTRING OF THE FILE BUILT TO
FIX IT.** `relayshield_sim_swap_consent.py` says so verbatim. That audit found
four defects, one per surface; three were wired and this one was recorded and
left. **A finding with no guard is a finding that comes back.**

Copy corrected on all five. The guard keys on whether any app source posts
`/v1/sim-swap/enroll`, so **shipping the feature unblocks the copy automatically**.
Two traps named before they are walked into: `checkSimSwap` posts
`/v1/metered/sim-swap`, a one-shot $0.25 lookup that enrols NOTHING, and the
monitor sends no Expo push, so an enrolled app user would be watched correctly and
told nothing (the join is `enrolled_by_account` against the push table's
`user_id`, both holding the API key, in two tables where `user_id` means different
things).

**MY FIRST VERSION OF THAT GUARD WAS TOO BLUNT AND I FIXED THE GUARD, NOT THE
CLAIM.** It failed on the Developer API product card, which says the API does SIM
swap monitoring -- and that is TRUE. A check that forces you to delete a true
sentence to be honest about a different product is a check that gets loosened.

### BOT-TOKEN-1 PHASE 0 SHIPPED: WE NOW DETECT TELEGRAM BOT TOKENS

There was **no Telegram bot token pattern anywhere** -- not in `NHI_PATTERNS`, not
in `_NHI_PATS`, not in the rsscan mirror -- while AWS, GitHub, Stripe, Slack,
OpenAI, Anthropic, OpenRouter and twenty others were covered. **So the corpus
count was UNMEASURED, not zero.**

Two entries, in all four tables that must agree, context-anchored because
`digits:opaque` is one of the commonest strings in a config dump. **The SECOND
entry exists only because running the first showed it could not see the commonest
leak**: `_ctx_key` requires an assignment operator, so
`https://api.telegram.org/bot<TOKEN>/sendMessage` matched nothing. Found by
EXECUTING the pattern, never by reading it.

**Remediation says REVOKE IN BOTFATHER, never "rotate".** A bot token is
session-shaped, not key-shaped. 13 tests, every one executing the regex against
real and decoy shapes including a raw TON address (`-?<digits>:<64 hex>`, this
shape with a longer tail).

**THE HARD LINE, from actually reading `soxoj/telegram-bot-dumper` after being
rightly rebuked for dismissing it from its name: `getMe` ONLY, NEVER
`getUpdates`.** `getUpdates` drains the owner's pending update queue and returns
other people's conversations. That tool does it correctly because it runs WITH the
owner's authorization. We have none.

### IAM: THE SHARED ROLE IS OVER THE CAP, NOT NEAR IT

The snapshot ran and is committed at
`iam/snapshots/relayshield-breach-check-role-1sapnwdl.json`:

    inline : 26 policies, 10127/10240 bytes, 113 free
    managed: 11 attached of 10 allowed
    lambdas running as this role: 42

**11 of 10.** The next permission anyone needs on that role cannot be attached by
either route. 42 Lambdas against the 22 in `LAMBDA_MAP`.

The dry run produced per-function policies for all 42 and dropped 649 statements,
which is the split working. **`relayshield-intel-feed` is the first migration: 5
statements, 1,124 bytes**, smallest by a clear margin, scheduled rather than
customer-facing. Its `DenyWalletPrivateKey` statement survives the derivation. It
has **no `logs:` statement and that is fine** -- `iam_split_roles.py:306` attaches
`AWSLambdaBasicExecutionRole` by ARN separately, checked rather than assumed.

**The verification after applying is NOT the import probe.** `ci.import-probe`
returns before touching DynamoDB, so it passes whether or not the role works --
the probe-takes-the-cheap-path trap. The real check is the next scheduled run
writing rows.

### MICROSOFT: LET THE POWER PLATFORM DEVELOPER ENVIRONMENT LAPSE

Asked as "MS Azure Sentinel", and **the expiring thing is not Azure at all.**
Three screens settled it:

* **Power Platform admin**: "Andrew Gibbs Work's Environment", Developer,
  **Ready (4 days until disabled)**, Dataverse Yes. The other row, Default
  Directory, is not expiring -- and TODO.md records the MS-4 custom connector as
  created in *Default Directory*.
* **Azure**: *"Welcome to Azure! Don't have a subscription?"* -- **there is no
  Azure subscription.** No Log Analytics workspace, no Sentinel, nothing billing.
  MS-1 is blocked on a workspace that was never created and MS-1b's cleanup
  warning is moot.
* **Partner Center**: an account with no workspaces -- **no commercial
  marketplace enrolment**, which MS-1 and MS-3 both need.

**Let it lapse.** Worst case it holds the custom connector, whose definition is
committed (`powerplatform_connector/relayshield_swagger2.json`,
`apiProperties.json`) and regenerated by a committed script. A custom connector
is visible only in our own tenant and its certification is blocked on two known
items. **A Power Platform environment cannot contain a Log Analytics workspace**,
so nothing about Sentinel is at risk either way.

### MINI APP DIRECTORY SUBMISSION IS UNRESOLVED AFTER FOUR ROUNDS. READ THIS BEFORE SPENDING A FIFTH.

**Nothing has been submitted to any directory. The blog channel is the only route
that has run.** Three separate failures, and the pattern matters more than any of
them:

**1. `@telegtapps` is a PAID AD CHANNEL, not a directory. DO NOT SUBMIT.** Its own
description reads *"Clickers. Telegram apps. HighRisk Dapps."* Every post is
forwarded from one source and is an advertisement. No pinned message, no
submission process. The only way in is buying a post. And the audience is wrong
twice over: clicker traffic does not buy identity security, and a security product
listed in a channel advertising high-risk dapps is a bad first impression rather
than a cheap one.

**THE DEFECT IS IN HOW THE RANKING WAS BUILT.**
`tools/find_miniapp_channels.py` measured SUBSCRIBER COUNTS and never recorded
channel TYPE, so paid promo channels were ranked alongside real catalogues on
audience size alone -- and I then sent the founder at the top of that ranking
without checking what the channel was. **Every remaining channel gets a type check
FIRST: a curated catalogue with a submission route, or a broker selling posts. All
posts forwarded from one source is the second kind.**

**2. The funnel doc said "ANDREW SUBMITS" and never said how**, which is the FD-2
defect in our own file. Fixed, with the read that finds the route as an explicit
step.

**3. `@app_moderation_bot` DOES NOT ANSWER `/start`.** I named it as the tApps
Center submission bot on four SECONDARY sources agreeing -- Adsgram, the TON blog,
the TON Builders Portal, a developer's write-up -- and **not one of them was the
destination's own page**, because tapps.center, docs.ton.org, medium.com and
peakd.com are ALL egress-blocked from this container. He tried twice and got
nothing. **A bot that does not answer /start is dead, and that is the FD-2 lesson
being broken by the person who wrote it down.**

**THE NEXT ACTION IS `tapps.center` IN A BROWSER, NOT IN TELEGRAM.** Every attempt
so far went through Telegram, where a catalogue shows its contents and hides its
plumbing. A website shows its navigation in one look. `@tapps_bot` IS the
catalogue -- opening it was never going to reveal a submission route.

**I RECOMMENDED DEPRIORITISING DIRECTORIES AND THE FOUNDER OVERRULED IT, CORRECTLY.
His words: "It is critical to expand the discovery surface for the Tg bot and our
api landing site. That is the sole reason we built this miniApp. We have to be
able to register it to catalogs."**

He is right and my recommendation answered the wrong question. Four wasted rounds
are an argument about METHOD, not about whether the goal is worth pursuing -- and
the Mini App has no other justification. **Catalogue registration is not
optional. Do not re-propose dropping it.**

**WHAT ACTUALLY CHANGES IS THE KIND OF CATALOGUE WE GO AT FIRST, and this is the
finding that came out of the four rounds:**

    A TELEGRAM-CHANNEL directory shows you its CONTENTS and hides its plumbing.
    A WEB directory shows you its NAVIGATION.

Every failure this session was a Telegram-first attempt: `@telegtapps` turned out
to be an ad broker, `@tapps_bot` is the catalogue rather than the submission
route, and `@app_moderation_bot` does not answer. **A website puts "Submit your
app" in the header or the footer, visible in one look, and it names the CURRENT
mechanism rather than one a blog post recorded a year ago.**

**So the running order inverts: web front door first, Telegram channel second.**
Three candidates, all with real sites, and the founder can check each in under a
minute because a browser is the one tool that works here and the container has
none:

| Catalogue | Web front door | Key already registered |
|---|---|---|
| miniTelegram | `minitelegram.com` | needs one |
| FindMini | `findmini.app` | `tg-miniapp-findminiapp` |
| tApps Center | `tapps.center` | `tg-miniapp-tapps` |

**miniTelegram is the one to try FIRST**, because its submission flow is described
rather than inferred: sign in with Telegram, submit an app card (official link,
description, categories, screenshots, language), and their team reviews before
publication. **UNVERIFIED from the container** -- minitelegram.com, findmini.app
and tapps.center are ALL egress-blocked here, which is precisely why the read is
the founder's and why guessing a handle from secondary sources failed three times.

**REGISTER THE `?source=` KEY BEFORE SUBMITTING TO ANY OF THEM.** miniTelegram has
none. An unregistered key is silently downgraded to the generic `tg-miniapp` at
the Worker's edge and logs `unmatched:` on the landing page, which is attribution
that looks like it worked -- FD-8, four months of it.

**ONE ORDERING RULE THAT IS EASY TO GET BACKWARDS**, recorded because it will
apply to whichever channel finally works: **opening the deep link yourself logs
NOTHING against the route key** -- the counter reads `source=` lines in
`/aws/lambda/relayshield-api` and opening the app calls nothing there. **Pressing
"Check it" DOES.** So verify a link BEFORE taking the baseline; a self-visit
inside the baseline is harmless, the same visit after it becomes part of the delta.

**AND NO BASELINE EXISTS FOR THE BLOG CHANNEL.** `miniapp_funnel_snapshots/` holds
only its README, because the funnel was hanging when that submission went out. The
blog channel's effect is permanently unmeasurable. Do not repeat it.

### THE TOP 15, REGENERATED 2026-09-14

**Regenerated, not annotated. This supersedes the 2026-09-09 list above.**

**Closed since then:** the watchlist is mapped in the deployer AND the drift
check; Stars is proven end to end by a real purchase; the Stars IAM grant is
measured closed; the funnel works; the Watching tab can add a watch; the
developer route is built and discoverable; CSM-SIMSWAP-1's copy is corrected;
BOT-TOKEN-1 phase 0 has shipped; the IAM snapshot is committed and the first
migration is chosen.

1. **REGISTER THE MINI APP IN A CATALOGUE. WEB FRONT DOOR FIRST, IN THIS ORDER:
   `minitelegram.com`, then `findmini.app`, then `tapps.center`.** Open each in a
   BROWSER and look at the header and footer for "Submit your app" / "Add app" /
   "For developers". miniTelegram first because its flow is described rather than
   inferred (sign in with Telegram, app card, team review).
   **This is the founder's explicit priority and overrules a recommendation I
   made to deprioritise it: the Mini App exists to expand discovery for the bot
   and the API landing site, and it has no other justification.**
   Register the `?source=` key for whichever one takes us BEFORE submitting --
   miniTelegram has none -- and take the `--snapshot before-<id>` baseline before
   the submission, never after.

2. **IAM split, first migration. The command is ready and the policy has been
   read.**
   `AWS_PROFILE=relayshield python3 tools/iam_split_roles.py --from-snapshot iam/snapshots/relayshield-breach-check-role-1sapnwdl.json --only relayshield-intel-feed --apply`
   **Verify with the next scheduled run's log, NOT the import probe**, which
   returns before touching DynamoDB. Do not migrate a second function until rows
   are written.

3. **Batch 2 outreach addresses. Two commands, both built, neither run.**
   `export GITHUB_TOKEN=$(gh auth token)`, then
   `tools/resolve_prospect_emails.py --in prospects_batch2.txt --out prospects_batch2.jsonl`,
   then `tools/merge_prospect_emails.py --drafts outreach_bot_prospects_batch2.md
   --resolved prospects_batch2.jsonl`. The merge writes a send-ready file where
   every draft carries a To: line and unreachable rows are parked, not hidden.

4. **CSM-SIMSWAP-2: the dApp Store listing copy.** A portal form field, no review
   cycle, and it is what a buyer reads before installing. Do it before the EAS
   build. The corrected source is
   `crypto-shield-app/store-assets/dapp-store-metadata.md`.

5. **The funnel's Insights IAM grant.** `logs:StartQuery`, `logs:GetQueryResults`,
   `logs:StopQuery` on `relayshield-deployer`. UNVERIFIED whether it already has
   them; the tool names the refusal rather than reporting a zero.

6. **CSM-SIMSWAP-1 proper: the enrol call.** ~3 days.
   `enrollSimSwap` posting `/v1/sim-swap/enroll` (NOT `/v1/metered/sim-swap`), the
   carrier authorization clause gating the button, `withdrawSimSwap`, and Expo
   push as a delivery channel on the monitor. Full scope in
   `simswap_crypto_shield_mobile_scope.md`.

7. **BOT-TOKEN-1 phase 1.** `getMe` liveness, hash-only storage, username
   indexing, severity split on liveness, and the `getUpdates` prohibition as a
   test. One day, gated on nothing. Phase 2 (the Mini App lookup) is gated on a
   NON-ZERO corpus count, not a date.

8. **Map `relayshield_watchlist_monitor.py` in `deploy_lambdas.yml`.** It is in
   the drift check and `iam_github_deploy_invoke.json` but not the deployer, so
   `check_deploy_invoke_policy.py` prints it as "granted but not in LAMBDA_MAP"
   on every run. **The mapping commit must touch the `.py`.**

9. **Map `relayshield-mpp-settlement`**, same shape, same rule.

10. **FD-11: Smithery.** Still two commands, still the cheapest open item.
    `npx -y @smithery/cli@latest auth login` then `mcp publish <hf sse url> -n relayshield/relayshield`.

11. **Bundle D change set**, dimension AND listing copy in one submission.

12. **Apify: the form is open now.** The article must NOT appear on
    blog.relayshield.net first.

13. **ABS-1: the measured agent-bait false-positive rate**, which gates the
    dimension in item 11.

14. **INTEL-5.** `tools/diagnose_stolen_sessions.py`. Until it runs, no count out
    of `relayshield_stolen_sessions` means anything.

15. **The Commerce Agents post.** Register `?source=commerce-agents` first.
