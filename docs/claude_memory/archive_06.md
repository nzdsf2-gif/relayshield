<!-- Verbatim sections moved out of CLAUDE.md on 2026-10-18, original order. Not auto-loaded.
     Find one with: grep -n 'WORDS' docs/claude_memory/INDEX.md -->

## EVERY KEYLESS ENDPOINT WAS 502ing IN PRODUCTION AND EVERY CHECK WE OWN WAS GREEN

**2026-09-22. Deploy run 161 shipped `d0c9477` to AWS at 16:48 UTC, conclusion SUCCESS, and it
took `/v1/link-check`, `/v1/wallet-risk` and twelve other keyless endpoints off the air.** Found
two hours later by a test written for something else entirely.

    _check_keyless_ip_quota(_source_ip, _link_check_units(path, params))

**`params` was bound forty lines further down.** The only earlier assignment is inside the
`/v1/app/feedback` arm, which returns, so on the keyless path the name was never bound at all.
And that call sits **ABOVE the try block**, so the `except Exception` two screens down never sees
it: the UnboundLocalError propagates out of `lambda_handler`, API Gateway answers **502**, and the
handler writes **no log line**. Reproduced by executing `origin/main`'s exact bytes.

**IT WAS MINE, SHIPPED THIS MORNING**, in the commit that made the keyless cap count UNITS rather
than requests so a 25-URL batch could not multiply the daily allowance by 25. The counting change
was right. Reading the body to do the counting, above the line that parses the body, was not.

### THE THREE THINGS THAT SHOULD HAVE CAUGHT IT AND STRUCTURALLY COULD NOT

**1. Forty-five tests, every one of them green, and every one called a HANDLER.**
`handle_link_check(params)`, `handle_breach(params)`, `handle_wallet_risk(params)`. **Nothing in
the suite had ever invoked `lambda_handler`**, so the dispatcher -- the code between the edge and
every handler in the file -- was untested in its entirety. A suite can be thorough about
functions and know nothing about the thing that calls them.

**2. `ci.import-probe` cannot reach it, and this file already says so.** The probe payload carries
no `path`, so it falls through to the 404 branch without ever entering the keyless block. The
deploy went green because the module IMPORTS, which was never in question. **"Deployed and the
probe passed" means the file parses and imports. It has never meant a request works.**

**3. `node --check` has a Python twin and this is it.** Syntactically perfect, runtime dead,
invisible to a reader -- the `INLINE_TEXT` and temporal-dead-zone family, in the dispatcher of the
API rather than in a Worker's page.

**THE RULE: a test that calls a handler proves the handler. The dispatcher needs its own tests,
and they go through `lambda_handler` with an event.** `TheOnwardRoute` in
`test_muse_connector_features.py` is now the first class in this repo that does, and it found this
on its first run while looking for something else. Every new keyless endpoint gets at least one
test that arrives the way a client arrives.

**And the ordering is pinned with `ast`, deliberately, because a behavioural test cannot hold it.**
Once the parse is above the quota check both orderings behave identically on the happy path, so
the only thing that can fail on a regression is an assertion about the LINE NUMBERS. Proven by
moving the parse back: six errors plus the ordering guard.

### THE SAME TEST FOUND THE HALF-APPLIED FIX SITTING ON TOP OF IT

The `onward` consumer route was attached inside the two link-check handlers, **leaving
`/v1/wallet-risk` -- the other half of the Muse connector -- with no route back at all.** Half the
fix, which is the shape of nearly every defect in this file: the reasoning was right and it was
applied to the endpoint in front of me rather than to the surface.

`_with_onward` is the single owner now, at the dispatcher, for every keyless endpoint. It attaches
only to a 200 carrying an `ok: true` envelope (an advert under a 4xx reads as a product deflecting
its own failure) and **it never raises** -- losing an onward link is a missed impression, losing
the verdict tells a user the product is broken. A test asserts `_onward_route` is called in
exactly ONE place, with `ast`, because a comment naming a helper is not a call to it.

## ON DECK: `/v1/email-check`. THE SCORING HALF PORTS. THE PARSING HALF DOES NOT NEED TO.

**Recorded 2026-09-22 at Andrew's request: "Add email checking as an endpoint as a ToDo for next
session."**

**`cloudflare_worker_checkemail.js` IS 1,707 LINES AND ROUGHLY HALF OF IT IS MIME PLUMBING WE DO
NOT NEED.** `splitHeadersAndBody`, `decodePart`, `extractText`, `stripHtml`, `decodeEncodedWords`,
`parseAddress`, `extractLinks`, `unwrap` and `detectForwardedOriginal` exist because email arrives
at that Worker as **raw RFC822 from Cloudflare Email Routing**. An agent reading a mailbox has
already parsed it: Gmail hands over the sender, the display name, the subject, the body text and
the links as fields.

**So the endpoint takes structured JSON and ports the SIGNALS and the WEIGHTING, not the parser:**

    POST /v1/email-check
    { from, display_name, subject, body_text, links[], auth_results?, attachment_names? }

The functions that must move are `parseAuthResults`, `domainOf`, `normaliseBrandText`,
`impersonatedBrand`, `attachmentSignals`, `publicHostSignal`, `pressureSignals`, `headerSignals`
and the weighting model underneath them. **Two to three days, and that is an estimate from the
function list rather than a measurement** -- the weighting has not been read line by line, and
this file has been wrong about a scope in exactly this way before.

**THREE THINGS THAT DECIDE WHETHER IT IS WORTH IT, and they are not obvious:**

1. **It is the first keyless endpoint whose answer is not a lookup.** Every other one asks a
   corpus or a vendor. This one REASONS about a document, and the 78 verdict tests are the asset:
   the model exists and is proven, it is just trapped behind an email address.
2. **It calls `/v1/scan-url` today and must NOT in the API version.** VirusTotal is $0.05 a call
   and has never been keyless. The link half of an email check goes through `_assess_domain`, the
   same zero-cost path `/v1/link-check` uses, so the endpoint can be keyless for the same reason.
   **Wiring it to `/v1/scan-url` would silently attach a per-call vendor bill to a free surface.**
3. **`checkemail@` stays exactly as it is.** It is live, it works, and it reaches people with no
   account and no agent. The endpoint is a second door onto one model, not a migration.

**The guard to write FIRST, before any of the port:** a test that fails if the endpoint's verdict
disagrees with the Worker's on any of the 78 fixtures. Two implementations of one scoring model
is this repo's most-repeated defect wearing its most expensive hat -- a security verdict that
differs by surface is a product that tells two users different things about the same email.

## MUSE'S TELEGRAM INTEGRATION DOES NOT POINT AT OUR BOT. IT MAKES THE USER CREATE ONE.

**2026-09-22, from a TestingCatalog screenshot: Muse Settings -> Messaging channels -> Telegram ->
"Bot token ... Get a token by contacting @BotFather and sending the /newbot command."**

**THE NAIVE READ IS WRONG AND IT IS WORTH KILLING BEFORE A SESSION BUILDS ON IT.** Muse is not
going to connect to `@relayshield_bot`. A Muse user creates **their own** bot and pastes its token
into a third-party web UI, and Muse's agent then operates inside their Telegram. There is no
inbound route from Muse to any bot we own, and nothing we can register to create one.

**WHAT IT ACTUALLY CHANGES, AND ONE OF THE THREE IS A PRODUCT ANGLE RATHER THAN A LINK:**

1. **The onward route stops being a context switch.** `t.me/relayshield_bot/idcheck?startapp=...`
   returned to an agent that is already inside Telegram opens **in the same app, one tap**. Every
   keyless verdict we serve that user now carries it, both endpoints, after the dispatcher fix.
2. **Messenger and Signal do not change this.** The route is a `t.me` link either way; it simply
   costs an app switch there, which is what it cost everywhere before today.
3. **A BOT TOKEN PASTED INTO A THIRD-PARTY WEB UI IS THE EXACT CREDENTIAL CLASS WE DETECT**, and
   Muse's own onboarding step creates the exposure. BOT-TOKEN-1 phase 0 shipped those patterns on
   2026-09-13, and the Mini App already recognises a bare `@handle` and answers with what a token
   is worth to a thief and why the fix is `/revoke` in BotFather rather than a rotation.

**THE HONEST LIMIT ON THAT THIRD ONE, because it is the tempting thing to overstate:** the Mini
App's bot branch says in its own copy *"We have not looked at your bot. This is what we check for,
not a finding about you."* BOT-TOKEN-1 phase 1 -- `getMe` liveness and a corpus lookup -- is Top
15 item 9 and is **NOT BUILT**. So this is a real editorial angle and a real reason for a Muse
user to open our Mini App. **It is not yet a check.** Claiming otherwise is the `_APIFY_BANNER`
mistake with a credential on the end of it.

## WHERE 2026-09-22 LEFT THINGS. READ THIS FIRST; IT SUPERSEDES THE 2026-09-17 TOP 15.

### THE ONE THING THAT MATTERS BEFORE ANYTHING ELSE: THE 502 FIX IS NOT ON MAIN

**`origin/main` at `d0c9477` carries a dispatcher that raises `UnboundLocalError` before
reaching any handler, and deploy run 161 shipped it to AWS at 16:48 UTC on 2026-09-22,
conclusion SUCCESS.** Every keyless endpoint -- `/v1/link-check`, `/v1/wallet-risk` and
twelve others -- answers **502** with no handler log line. Reproduced by executing
`origin/main`'s exact bytes, not inferred. The fix is `aaa6b78` on
`claude/tender-planck-cb2qrx` and it is pushed but **unmerged**. Full write-up in the
section above. **Merge and push is the first action of the next session, before any
question is answered.**

### WHAT SHIPPED, all on `claude/tender-planck-cb2qrx`, five commits

* **`_with_onward`**, the consumer route, at the DISPATCHER rather than in two handlers --
  so `/v1/wallet-risk` carries it too. Attaches only to a 200 with an `ok: true` envelope,
  never raises, and `_onward_route` is called in exactly one place (asserted with `ast`).
* **`tg-miniapp-muse`** registered in all three lists that must agree, before submission.
* **The OpenAPI spec learned the two free endpoints exist**, and then learned they need no
  credential: both inherited the document's top-level `security`, so a client generated
  from it -- which is how Muse integrates -- would have demanded an API key on the only
  two endpoints the connector is built on.
* **49 tests in `test_muse_connector_features.py`**, including the first class in this repo
  that goes through `lambda_handler` rather than calling a handler.
* Three CLAUDE.md records: the outage, the `/v1/email-check` scope, and what Muse's
  Telegram step really is.

### x402 PRICING: THERE IS NO SUMMARY DOCUMENT, AND THERE SHOULD NOT BE ONE

Asked as "where can I find our summary pricing". **Nowhere, on purpose, and the live
answer is better than a document would be:**

    https://api.relayshield.net/.well-known/x402.json     machine-readable, all prices
    https://api.relayshield.net/docs                      Swagger UI, x-price-usd per call
    https://api.relayshield.net/openapi.json              the same document as JSON
    https://api.relayshield.net/developers                the human pricing page

**`handle_x402_manifest` builds every entry by calling `_build_payment_requirements`**, the
same function the live 402 challenge uses, so the published price cannot drift from what a
buyer is asked to pay. A committed markdown price list would be a fifth copy with no such
property, and this repo's most-repeated defect is two files that must agree with nothing
checking that they do. **Do not write one.**

**MEASURED 2026-09-22, because a count in a reply is evidence the reader acts on:**

    relayshield_api.py        PAYG_PRICE_UNITS   28 endpoints   $0.05 - $0.50
    relayshield_agentic_api.py PAYG_PRICE_UNITS   3 endpoints   $0.35 - $0.50
    distinct paths                                29

The two tables share `mcp-registry-risk` and `prompt-injection-breach` and **both price
them at $0.35, which agrees today and is checked by nothing.** That is the 402-at-the-
wrong-price defect waiting to happen, in the two files that already produced it once.

**AND `/v1/payg/agent-bait-scan` IS NOT IN THE MANIFEST.** `handle_x402_manifest` iterates
`relayshield_api.py`'s table, and that endpoint lives only in the agentic file. So a paid
endpoint we built, priced and deployed **cannot be discovered by any x402 indexer**, which
is the inline-mode defect with a price on it: live, working, pointed at by nothing. One
line to fix and a test to pin both halves. It is Top 10 item 4.

### HEAVYGRAM: THE IOCs NEED NO WORK. THE BOT TOKEN IS THE PART THAT IS OURS.

Asked as "worth adding to our TI corpus?" after a Group-IB write-up: 29 new samples tied
with moderate confidence to Handala Hack, delivered over messaging apps as
`Telegram_authenticator.exe` and `WhatssApp.exe`, a **Python Windows backdoor whose C2 is
Telegram bots, users and groups**, with an `@@`-prefixed message running arbitrary system
commands.

**NO, not as an ingestion task, and the reason is the doctrine rather than laziness.**
`relayshield_intel_feed.py` already pulls ThreatFox, URLhaus, Feodo, MalwareBazaar and
Malpedia's family taxonomy. If anyone uploads a HEAVYGRAM sample those hashes arrive with
**zero work**, and hand-loading one vendor's IOC list is precisely what MEASUREMENT
DOCTRINE calls making the headline better and the product worse. **UNVERIFIED whether
Malpedia already carries the family name:** `malpedia`, `bazaar.abuse.ch` and
`group-ib.com` all return HTTP 000 from this container, which is a fact about the egress
policy and nothing about those sites.

**THE HALF THAT IS GENUINELY OURS IS BOT-TOKEN-1, AND THIS IS THE BEST ARGUMENT FOR PHASE 1
THAT HAS TURNED UP.** HEAVYGRAM's command channel is a **Telegram bot token embedded in a
Windows binary**. We shipped patterns for exactly that shape on 2026-09-13 -- `telegram_bot_token`
and `telegram_bot_token_url`, in all four tables -- and phase 1 (`getMe` liveness) is Top
15 item 9 and **NOT BUILT**. A token lifted from a sample and checked with `getMe` answers
*is this C2 still live*, which is a question a malware report cannot answer and a vendor
feed does not carry.

**AND IT MAKES THIS REPO'S `getUpdates` PROHIBITION CONCRETE RATHER THAN PRINCIPLED.** That
rule was written as "it drains the owner's pending update queue and returns other people's
conversations". For a HEAVYGRAM token the owner is the OPERATOR and the queue holds
**victims' exfiltrated data**. Calling `getUpdates` on it would pull stolen material into
our systems and destroy the operator's evidence in one request. `getMe` only. The
prohibition is not a nicety and now has a named case behind it.

**Not worth building: a detector for the `@@` prefix or the green-circle check-in.** Those
are host-artefact signatures for an EDR product. We screen counterparties and credentials;
we do not analyse binaries, and claiming otherwise is the rsscan-as-server-control mistake.

### TWO THINGS TO VERIFY WHEN THE MUSE CONNECTOR IS FIRST USED

Andrew's, recorded because neither can be checked from here and both are cheap in the app:

1. **Does the Muse agent render a connector-supplied link as TAPPABLE?** Most agent
   surfaces render markdown links; **this is Meta's renderer, not ours**, and the `onward`
   field is a JSON object rather than markdown. If it renders as bare text the route still
   works and reads worse.
2. **What does a non-Telegram user get?** `t.me` without Telegram installed drops to a web
   preview plus an install prompt. That is an acceptable fallback and it is worth knowing
   it is what happens rather than discovering it in a complaint.

**His third point is already the design and is worth keeping stated:** the link is in the
API RESPONSE rather than only in the connector wrapper, so every downstream surface
inherits it -- Messenger and Signal when Muse ships them, and any future partner keyed into
`CONSUMER_ROUTES`.

### THE TOP 10, REGENERATED 2026-09-22

**Regenerated, not annotated. This supersedes the 2026-09-17 Top 15.**

**Closed since then:** Bundle B is PUBLIC (`prod-szi2wdww3obry`); the withdraw change set
for the two duplicates exists and is guarded; the Muse connector's three features are built
and its form copy is written; the OpenAPI spec carries the free endpoints; the AWS banner
names both bundles.

1. **MERGE AND PUSH `claude/tender-planck-cb2qrx`.** Every keyless endpoint is 502ing in
   production right now. This is not a queue item, it is an outage with the fix already
   written and pushed. After the deploy, prove it with a real request rather than the
   import probe, which cannot reach the dispatcher.

2. **Submit the Muse connector**, after that deploy so the spec and the key are live. Copy
   is field by field in `muse_connector_submission_2026-09-22.md`, including the page-2
   fields and the charging answer.

3. **Create `relayshield_breach_cache`.** `AWS_PROFILE=relayshield sh
   tools/setup_breach_cache.sh`. The code ships inert without it, the TTL step is the one
   that cannot be skipped, and this unblocks adding breach to the connector.

4. **`/v1/payg/agent-bait-scan` is missing from `/.well-known/x402.json`**, because the
   manifest iterates one of two price tables. A paid endpoint no indexer can find. Fix the
   iteration, and pin the two tables' shared prices with a test in the same commit.

5. **Withdraw the two Bundle B duplicates.** `prod-v5nr5gjtdnofi` and
   `prod-p3ei5nmgufnnq`, both still `Limited` and both still carrying the live listing's
   display name. `bundle_b_withdraw.json` through `marketplace_changeset.yml` with the id
   as an input. `Restricted` on a `Limited` product is UNVERIFIED and fails in seconds.

6. **BOT-TOKEN-1 phase 1**, which HEAVYGRAM has just made concrete. `getMe` liveness,
   hash-only storage, username indexing, severity split on liveness, and the `getUpdates`
   prohibition as a test. One day, gated on nothing.

7. **`/v1/email-check`.** Scoped in the section above: the signals and the weighting port,
   the MIME parser does not, it must NOT call `/v1/scan-url`, and the 78 Worker fixtures
   become a cross-implementation guard written FIRST.

8. **IAM split, first migration.** `relayshield-intel-feed`, command ready, policy read.
   Verify with the next scheduled run's log, never the import probe. The shared role is at
   11 managed policies of 10 allowed.

9. **Deploy the TI demo Worker, recovery FIRST.** Cards edited and unshipped since
   2026-09-16. `sh tools/recover_live_worker.sh relayshield-ti-demo
   cloudflare_worker_ti_demo.js`; only `IDENTICAL` makes the deploy safe.

10. **The Bundle B duplicate-products post**, gated on item 5. Three SaaS products with one
    display name, a portal that selects by name, seven refusals, and the one-command
    `list-entities` read that separates them. An afternoon, and nothing on the internet
    describes it. Omit the entity ids.

**Carried and not in the ten**, so they are not lost: `WA_NUMBER` still empty in both
Workers; StoreBot submission; the WhatsApp Channel question (can a Twilio-hosted number own
one); FD-11 Smithery; mapping `relayshield_watchlist_monitor.py` and
`relayshield-mpp-settlement` in the deployer; INTEL-5.

## WHERE 2026-09-23 LEFT THINGS

**Confirmed rather than re-derived, per the WHERE THE CURRENT WORK LIST LIVES rule: the two Bundle
B duplicate product entities were withdrawn to `Restricted` in the prior session (see "THE
DANGEROUS DIRECTION INVERTED THE DAY BUNDLE B WENT PUBLIC" above), and the TI demo Worker's cards
were recovered and corrected in the prior session (see "THE TI DEMO CARDS ARE UPDATED" above).
Neither needed re-checking this session; both sections above are the record.**

### `/v1/email-check` IS BUILT: A SECOND DOOR ONTO `checkemail@`'S SCORING MODEL

Per the ON DECK note this file already carried, and scoped exactly as that note specified. Keyless,
registered in `KEYLESS_SCAN_ENDPOINTS` and `ROUTES`, wired into the onward-route and OpenAPI-spec
guards the Muse connector session built. `handle_email_check` in `relayshield_api.py`; `_score_email`
is the pure scoring core.

**Ported: the SIGNALS and the WEIGHTING**, not the MIME parser -- a caller here has already parsed
the message (Gmail API, an inbox connector), so `splitHeadersAndBody`, `decodePart`, `extractText`,
`stripHtml`, `parseAddress`, `extractLinks`, `unwrap` and `detectForwardedOriginal` from
`cloudflare_worker_checkemail.js` are deliberately NOT ported. What IS ported, verbatim as data:
`BRAND_DOMAINS`, `AUTHORITY_WORDS`, `WEBMAIL`, `PUBLIC_PAGE_HOSTS`, the ask/deadline/threat phrase
lists, and the attachment extension tables (`_EMAIL_*` prefix in `relayshield_api.py`).

**LINKS GO THROUGH `_heuristic_url_check_many` -- THE SAME ZERO-COST PATH `/v1/link-check` USES --
NEVER `/v1/scan-url`.** Per "THE CONSUMER-COMPELLING CHECKS ALL HAVE A VENDOR BILL" above: wiring
this to VirusTotal would have silently attached a per-call vendor bill to a keyless surface.

**TWO COPIES OF ONE SCORING MODEL IS THIS REPO'S MOST-REPEATED DEFECT, SO THE TWO COPIES ARE PINNED
TO AGREE BY TEST, NOT BY EYE.** `test_email_check.py`'s `TableAgreement` class reads
`cloudflare_worker_checkemail.js` and asserts the API's Python tables match it exactly. Its first
run failed on `ASK_PHRASES`: the comment two lines above that table quotes two example phrases
("please add your email now", "verify or lose access") as prose, and an unstripped regex counted
both as table entries that do not exist -- the guard-fooled-by-its-own-comment shape, for the
seventh time in this file, caught before it shipped rather than after. Comments are stripped in
the FIRST version now, not the second.

35 tests, `test_email_check.py`, three classes: `HandlerBehaviour` (executed against the handler
directly -- DMARC fail, brand impersonation on a real company domain, the unrelated-small-business
guard, ask-alone-is-not-a-flag, forwarded-mail auth is not scored), `Dispatcher` (through
`lambda_handler`, because that is where the UnboundLocalError and missing-onward defects both
lived and a handler-only suite cannot see either class), and `TableAgreement`.

**`checkemail@relayshield.net` is unchanged and keeps running.** This is a second door onto the
same model, not a migration.

### SPEC HYGIENE: 113 CHANNELS, 7.8M CITATIONS. THE UNIQUE-INDICATOR COUNT IS NOT GUESSED.

The API docs intro (`_DESCRIPTION` in `relayshield_openapi_spec.py`), the `asset-intel` endpoint
description, and the live TAXII discovery/collection responses in `relayshield_api.py`
(`handle_taxii_discovery`'s `description` field and `TAXII_COLLECTION`) all quoted **95 monitored
channels** and **5.8 million sightings**, both stale. Updated to **113 monitored criminal Telegram
marketplaces** and **7.8 million citations**, the current figures Andrew supplied.

**THE DISTINCT-INDICATOR COUNT (previously "494,000+") WAS NOT BUMPED TO A GUESSED NUMBER.**
Andrew flagged it needs checking since it has grown, and MEASUREMENT DOCTRINE is explicit: never
invent a number for a customer-facing document. The intro now describes the corpus by its SOURCES
("collected continuously from 113 monitored criminal Telegram marketplaces, infostealer log dumps
and authoritative public indicator feeds") rather than repeating an unmeasured distinct count --
the same resolution this file already reached for the AWS Marketplace listing and the TI demo
cards, both of which paid for quoting a count that drifted.

**ON DECK: measure the current distinct-indicator count** and, if it is worth quoting at all,
add it back as a fresh, dated figure. `tools/ti_demo_metrics.py --distinct` already does a full
`relayshield_intel_iocs` scan for this and states the cost before it runs (this is the tool the
TI demo Worker's own cards are refreshed from). It needs `AWS_PROFILE=relayshield` and has not
been run this session:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/ti_demo_metrics.py --distinct

### HEAVYGRAM: `tools/triage_channels.py` GAINED `--add`, FOR A CHANNEL THE CRAWLER WOULD NOT REACH ON ITS OWN

Asked as: add Heavygram to the bot-token discovery corpus, since it matches the leaked-bot-token /
C2 shape BOT-TOKEN-1 already targets. There was no route to seed a channel that has never been
discovered -- `relayshield_intel_discovery.py`'s cross-promotion crawler only walks OUTWARD from
channels already `active=True`, and `triage_channels.py --activate` only promotes a row already
sitting in `pending_review`. Neither reaches a channel named by hand that the crawler has not
found yet.

`--add` seeds a brand-new row directly (`update_item` on a key that does not exist creates it --
there is no separate insert path on this table), defaulting `category` to `credential_dump` rather
than `infostealer`, because a leaked bot token is a credential, not an infostealer log.

**THIS IS AN AWS WRITE AND CANNOT RUN FROM THIS CONTAINER.** Per "NO AWS IN THIS SANDBOX IS NEVER
A REASON TO SKIP A CHECK", the work moved into a committed script rather than stopping:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/triage_channels.py --add heavygram --apply

Dry-run (omit `--apply`) first if you want to see what it would do before writing. It also
handles any future manually-named channel the same way, not just this one.

### FOUR NEW ROADMAP ITEMS, ADDED AT ANDREW'S REQUEST 2026-09-23

**None of these has been scoped or built.** Recorded here so they survive to the next session
rather than living only in a chat reply, per "A SESSION THAT CANNOT PUSH HAS NOT DELIVERED
ANYTHING" applied to backlog items generally: an item that exists only in conversation is an item
the next session cannot see.

1. **Scam-kit fingerprinting.** Bigger than link/wallet flagging -- clusters REUSABLE KITS
   (phishing kits, wallet drainers, credential-theft kits, fake-support kits, investment-fraud
   kits, malicious OAuth flows) rather than scoring one URL at a time. Candidate fingerprint
   surfaces: DOM/page structure, form flow, wording (including repeated translation mistakes),
   logo/favicon/CSS/JS/asset hashes, screenshot perceptual similarity, redirect chains,
   shortener/QR routes, exfiltration endpoints, registration/TLS/DNS/hosting/ASN data, drainer
   scripts and crypto addresses, and campaign clustering across related domains. Response shape:
   kit family, confidence, matched fingerprints, related infrastructure, first/last seen,
   recommended action. **Sensible MVP, per Andrew's own framing:** DOM/asset/screenshot
   similarity plus infrastructure clustering, fed by URLs the product already sees through
   `/v1/link-check` and `/v1/scan-url`. **Run any rendering/fetching in an isolated sandbox, never
   with real credentials** -- this is the same boundary `relayshield-agent-bait` already draws
   around reading a repository's agent-facing files. Natural charge points: per-fingerprint API
   lookups, and a campaign-tracking tier layered on top of watchlist monitoring. Unscoped: needs a
   sizing pass (sandbox infra, hashing/similarity library choice, storage shape for a
   fingerprint-to-campaign join) before a build estimate is honest.

2. **A separate MCP server for free RS Identity & Scam Checks.** Distinct from the existing
   16-tool `relayshield-mcp` (PyPI, stdio, paid endpoints) and the HF-hosted Bundle D server --
   this one is scoped to the KEYLESS surface: `/v1/link-check`, `/v1/wallet-risk`, and (now)
   `/v1/email-check`, plus identity-protection checks worth adding keyless: breached-password
   exposure, phone-number risk, package/repo reputation, and MCP-server/tool risk (the
   `relayshield-agent-bait` logic, exposed as a callable tool rather than only a skill). **The
   framing worth keeping: one-click install in Claude, Cursor and Windsurf is the agent-era
   equivalent of a directory listing** -- FD-11/FD-12/FD-13/FD-14 are all "get listed where agents
   look", and a free, no-signup MCP server is a listing that also does the work. Unscoped: needs a
   decision on hosting (a new HF Space vs. a mode flag on the existing one) and on which of the
   "strong identity-protection checks" already have a keyless code path today vs. need one built
   (breached-password and phone-number risk both currently sit behind `/v1/breach` and
   `/v1/metered/*`, which are NOT keyless).

3. ~~Spec hygiene~~ **DONE THIS SESSION**, see above.

4. **A single-identity "incident timeline" composite endpoint.** Correlates breach + infostealer +
   SIM-swap + session-risk into one verdict for one identity, productised as a chargeable JSON
   endpoint. Andrew's framing: **"We have a demo version but should productize a JS chargeable
   endpoint."** Unscoped from this session: the demo referenced has not been located or read, so
   before building, find it (likely candidates by name: something under `relayshield_watchlist*`,
   `relayshield_oauth_watchlist*`, or a `tools/*demo*` / `*timeline*` script) and read what it
   already correlates before designing the endpoint's request/response shape and its price point.

5. **Dev-facing free doors, three of them:**
   - **A GitHub Action wrapping `secret-scan-text`** (per Andrew: "scans diffs for secrets --
     developers adopt it, then buy credits"). `rsscan` already does the equivalent locally via a
     pre-commit hook (`scan.py`, `--staged` default, `--rev-range A...B` for CI) -- check whether
     this is "package the existing rsscan CI mode as a published Action" (cheap) or a distinct
     build before estimating.
   - **An embeddable "check this link" JS widget** for forums and marketplaces. Note
     `widget/relayshield-widget.js` already exists and is described elsewhere in this file as "a
     copy-in file... for third-party Telegram bots", built against `/v1/link-check` and
     `/v1/wallet-risk`. Check whether that file already covers this ask (a generic embed, not
     Telegram-specific) or whether a forum/marketplace embed is a genuinely different shape
     (DOM injection into someone else's page vs. a bot handler) before scoping as new work.
   - **A browser extension on the free `/v1/link-check` endpoint.** Genuinely new; no existing
     artifact in this repo does this. Unscoped.

**All five items above (1, 2, 4, and the two unbuilt items in 5) need a sizing pass before the
next session's Top 15 can rank them honestly against what is already in flight** (the IAM split,
Bundle B's remaining duplicate cleanup follow-through, BOT-TOKEN-1 phase 1, the catalogue
submissions still pending review). This section is intentionally NOT a renumbered Top 15 --
regenerating that list means reviewing every open item in this file, which this session did not
do, and this file's own rule is that a doc claiming something is done is a lead, not a fact.

### ITEM 4 (THE COMPOSITE ENDPOINT) IS NOT A GAP. IT ALREADY EXISTS, AS A DIFFERENT SHAPE.

**Corrected same session, at Andrew's instruction.** The "demo version" the item-4 note above
refers to searching for is `relayshield_breach_monitor.py`'s `ATTACK_CHAINS` /
`check_and_fire_correlation` engine: a 72-hour cross-surface correlation window, eleven named
attack chains, and predictive warnings fired mid-chain, imported by
`relayshield_whatsapp_webhook.py`, `relayshield_domain_monitor.py`,
`relayshield_telegram_webhook.py` and `relayshield_sim_swap_monitor.py`. It already correlates
breach + SIM-swap + domain + wallet-risk signals for a given user.

**It is PROACTIVE, not on-demand, and that is the entire difference from item 4's ask.** It fires
Telegram/WhatsApp alerts from background monitor runs against signals already recorded for a
verified user; it is not a callable, priced JSON endpoint a caller can invoke for an arbitrary
identity. Productising it as a `/v1/metered/*` endpoint (the second half of Andrew's original
framing -- "productize a JS chargeable endpoint") is therefore still a real, unscoped build: request
shape, price point, and whether an on-demand read of `ATTACK_CHAINS`-tracked signals needs a new
query path or can reuse the existing per-user record. Not attempted this session; item 4 is closed
as "the correlation logic exists," not as "the endpoint exists."

### BOT-TOKEN-1 PHASE 1 IS BUILT: `getMe` LIVENESS, HASH-ONLY STORAGE, SEVERITY SPLIT

Scoped in `leaked_bot_token_finding_scope.md` section 6 ("One day. Gated on nothing.") and built
to that scope, no more: `check_telegram_bot_token_liveness` and `_store_bot_token_finding` in
`relayshield_intel_monitor.py`, wired into `_parse_passwords_file`'s existing NHI loop for both
`telegram_bot_token` and `telegram_bot_token_url` matches.

**The hard boundary from section 3 is enforced by a test that reads the two functions' SOURCE, not
by a comment.** `check_telegram_bot_token_liveness` calls `getMe` and nothing else; a second test
asserts `_store_bot_token_finding` makes no Telegram call at all (it delegates). Comments and
docstrings are stripped before either check runs -- the "guard fooled by its own comment" shape has
hit this exact class of guard six times before in this repo, and the first version of THIS test
walked straight into it: the docstring's own prose describing what the function delegates to
("the one getMe call") made the un-stripped guard fail on correct code.

**Storage is keyed on `sha256(token)`, mirroring `relayshield_stolen_cards`'s `pan_hash` key.** The
token itself never leaves the two functions that touch it; a test executes `_store_bot_token_finding`
and asserts the raw token string does not appear in any value of the DynamoDB item it writes.

**Idempotent on the hash: a token re-observed across channel sweeps gets ONE `getMe` call, not one
per sighting.** `_store_bot_token_finding` checks for an existing row before calling the liveness
function; a test proves the liveness function is never invoked a second time for the same token.

**Severity: CRITICAL when live, MEDIUM when a live `getMe` call reports the token dead (HTTP 401),
and something else -- `UNKNOWN` -- when the call could not be completed at all.** The third state
is the one this phase exists to protect: a timed-out `getMe` call must never render as "dead",
which would tell a bot developer a live credential is safe. A test fabricates a timeout and asserts
the stored severity is neither `CRITICAL` nor `MEDIUM`.

**A pre-existing bug in the customer-facing NHI alert was fixed in the same commit.** Every NHI
finding, bot tokens included, closed with an unconditional *"Rotate these credentials
immediately"* -- directly contradicting this file's own standing rule (*"Remediation says REVOKE
IN BOTFATHER, never rotate"*) and the finding's own per-item description, which already said so.
The alert now names BotFather specifically when any bot-token finding is present, and drops the
rotate line entirely when EVERY finding in the batch is a bot token.

**NOT BUILT THIS SESSION, and correctly so per the scope doc's own gate:** Phase 2 (the Mini App /
bot-command username lookup) is gated on a NON-ZERO corpus count, not a date -- exactly the
ABS-1/OpenRouter-webhook shape this repo has already paid for building against zero rows.

**SHIPS INERT UNTIL THE TABLE EXISTS, ON PURPOSE**, same pattern as the breach cache:
`_store_bot_token_finding` catches every DynamoDB error and logs a warning, so nothing in the
ingestion pipeline breaks while this is outstanding -- the corpus simply does not accumulate
bot-token findings yet. `tools/setup_bot_tokens_table.sh` creates `relayshield_bot_tokens` (keyed
on `token_hash`), enables TTL, and checks whether `relayshield-intel-monitor`'s role can already
write to it before proposing a grant the shared role's inline budget cannot make.

    AWS_PROFILE=relayshield sh tools/setup_bot_tokens_table.sh

19 tests, `test_bot_token_liveness.py`, all executed against stubbed `urllib` and `boto3` rather
than read: a live `getMe` response, a 401 (checked-dead, not inconclusive), a timeout and a 5xx
(both inconclusive, never dead), the source-level `getMe`-only boundary, hash-only storage,
severity assignment for all three liveness states, the once-per-token dedup, the wiring from
`_parse_passwords_file` for both pattern shapes, and the remediation-text fix.

## ITEM 4, THE REST OF IT: `POST /v1/metered/incident-timeline` IS BUILT

**2026-09-23, at Andrew's explicit follow-up: "I do want the JS chargeable endpoint for the
attack sequencing chain."** The section above answered a different question -- whether the
correlation logic existed -- and correctly said yes, proactively, for our own WhatsApp users.
This is the thing that did not exist: an on-demand, priced, JSON endpoint any caller can hit for
any identity, with no prior monitoring relationship.

**THE CHAIN TABLE IS IMPORTED, NOT COPIED.** `relayshield_api.py` now carries
`from relayshield_breach_monitor import ATTACK_CHAINS` and matches against the exact same table
the WhatsApp monitor's `check_and_fire_correlation` does. Two copies of one correlation model is
this repo's single most-repeated defect -- the pattern tables, the three source lists, the
LAMBDA_MAP/invoke-policy pair, `BRAND_DOMAINS` between the Worker and the API twice already this
week -- so this one is a reference, pinned by `test_incident_timeline.py`'s
`test_atack_chains_is_the_same_object_not_a_second_copy` asserting object IDENTITY, not equality:
equality would still pass the day someone forks the table by accident and only diverges later.

**THE FOUR SUB-CHECKS ARE THE LIVE HANDLERS, CALLED DIRECTLY, NEVER THEIR HTTP CALLS AGAIN.**
`handle_breach`, `handle_session_risk`, `handle_sim_swap`, `handle_domain` are invoked in-process
and their Lambda-proxy responses unwrapped by one small `_unwrap()` helper. This gets the breach
cache, the partner-budget gate, Twilio's `error_code=60606` handling and the typosquat sweep for
free, and it means a fix to any one of those four (there have been several this quarter) fixes
this endpoint too, with nothing to re-synchronise.

**WHAT IT DOES NOT CHECK, ON PURPOSE.** `suspicious_sms` and `otp_warning` are EVENTS observed
inside a monitored WhatsApp conversation, not identity properties -- there is no "check for one"
for an arbitrary caller's identity, and treating "never observed" as "clean" would be exactly the
false-negative shape MEASUREMENT DOCTRINE and the SIM-swap monitor's "we could not check must
never render as it is gone" rule both forbid. So only `breach_sim_swap` and
`domain_phishing_breach` can ever fire here; `smishing_to_sim_swap` and `breach_otp_intercept`
never will, and a test pins that this is not merely likely but a property of what the endpoint can
query, not an accident of the fixtures used to test it.

**AND SESSION-RISK IS REPORTED, NEVER SCORED AS A SIGNAL.** It is not one of `ATTACK_CHAINS`' own
signal types -- that table predates this endpoint and was built for WhatsApp-observed events --
so folding a found session into `signal_types` would be a silent SECOND definition of what
"session_risk" means to the correlation model. `test_session_risk_never_joins_signal_types_or_
decides_the_chain` proves a CRITICAL session-risk hit alongside a lone breach still resolves
`chain_matched: null`.

**PRICED AS A BUNDLE, DERIVED IN A COMMENT RATHER THAN GUESSED.** `email` is required and always
runs breach ($0.10) + session-risk ($0.30) = a $0.40 floor. `phone` and `domain` are optional and
add sim-swap ($0.25) and/or the domain lookalike sweep ($0.30) when supplied, up to $0.95 fanned
out. $0.50 sits between the two, the same bundle-discount shape `bulk-identity-risk` already uses
for its $2.00/up-to-10-domains price. A test pins `METERED_CREDIT_COSTS` and the OpenAPI spec's
`price_cents` equal, so the two cannot quietly disagree the way a public listing price and a
billing table have disagreed before in this repo.

**NO PAYG/x402 TWIN in this build.** Nine other metered endpoints already ship metered-only
(asset-intel, brand-monitor, bulk-ioc, card-exposure, crypto-intel, cve-identity-risk,
dependency-risk, ioc-pivot, threat-actor), so this is established precedent, not a shortcut taken
under time pressure.

**NO NEW API GATEWAY RESOURCE NEEDED.** Unlike `relayshield-watchlist` or
`relayshield-bundle-fulfillment`, which are separate Lambda functions and have each cost a session
a "route added to the dispatch table is not a route" lesson, this endpoint lives inside
`relayshield_api.py` behind the existing `/v1/metered/{proxy+}`-style catch-all already serving
every other `/v1/metered/*` path to the same `relayshield-api` function. Registration is therefore
entirely in-Lambda: `METERED_CREDIT_COSTS`, the `metered_routes` dispatch dict inside
`handle_metered_request`, and the OpenAPI spec. `relayshield_api.py` is already deployed on every
push per the standard pipeline, so this ships on the next merge with no new AWS object to create.

13 tests, `test_incident_timeline.py`, all executed against the real handler with the four
sub-checks monkeypatched rather than hitting the network: email-required, the always-run-vs-
skipped split, both reachable chain matches, no-chain-on-a-lone-signal, the session-risk
non-signal guard, a failed sub-check reading as `checked: false` rather than clean, domain
scheme/`www.` stripping, `ATTACK_CHAINS` order deciding priority when a signal set could satisfy
more than one chain, the chain-table identity guard, and the dispatcher/spec-agreement guards --
the last of which was proven by deleting the `metered_routes` entry and watching it fail before
restoring it.

## `origin/main` HAD LIVE CONFLICT MARKERS COMMITTED INTO IT. THE IAM SPLIT IS STILL NOT DONE.

**2026-09-23, second session, after Andrew asked "didn't we already split the IAM role" and the
answer required checking rather than trusting either of us.**

**Repo-wide search found no evidence the split was ever applied**, per the rule two sections up:
`git fetch --all --prune` then search with no pathspec, across every ref this container could
reach. `tools/iam_split_roles.py` and the read-only snapshot exist; no derived per-function role,
no commit saying it ran, no AWS confirmation artifact. Two independent sessions' own most-current
status write-ups -- one dated 2026-09-22, one 2026-09-23 -- **both still list it as pending**:
*"IAM split, first migration. `relayshield-intel-feed`, command ready, policy read."* Neither says
applied. **If it was run on the Mac, the result was never committed back**, which this file's own
rule already covers: work that cannot push has not been delivered.

**AND FINDING THAT ANSWER SURFACED A WORSE PROBLEM ON THE WAY.** `origin/main` at `b60d17f`
("Merge branch 'claude/awesome-fermi-yntdwk'") carried **literal, uncommitted-looking git conflict
markers baked into a committed file** -- `<<<<<<< ours` / `=======` / `>>>>>>> theirs` sitting in
CLAUDE.md, around the "WHERE 2026-09-22 LEFT THINGS" / "WHERE 2026-09-23 LEFT THINGS" sections.
Exactly the failure rule A exists to prevent (`git checkout --merge CLAUDE.md`, delete the marker
lines BY HAND, keep both sides), except this time it happened ON MAIN rather than on a Mac clone --
someone ran `git commit --no-edit` on a conflicted merge without resolving it first.

**FIXED THE SAME SESSION, by merging `origin/main` into this branch and resolving by hand: every
real section from BOTH the 2026-09-22 and 2026-09-23 write-ups kept, only the six literal marker
lines deleted (three original broken ones, three new ones from this merge, since this branch's own
unmerged "ITEM 4" section collided with the same region).** `grep -c` for all three marker patterns
returns 0 in the result. Verified by reading both seams, not just by the grep returning empty --
a grep that passes on a file with the WRONG content merged in would look identical to one that
passes on the right content.

**THE GENERAL FORM, and it is new: a merge conflict marker can survive INSIDE a successful-looking
merge commit, not just as an aborted merge state.** Every check this repo runs for "did the merge
succeed" (exit code, `git status` after) says nothing about whether the CONTENT of a resolved file
is still full of markers -- that requires reading the file, or grepping for the marker patterns
specifically. Worth adding to any future merge-block EXPECT: after a conflict resolution, `grep -c
"^<<<<<<<\|^=======\|^>>>>>>>" <file>` must print 0, not just "the merge command exited 0".

## `relayshield-intel-feed` IS ALREADY SPLIT ONTO ITS OWN ROLE. MEASURED 2026-09-24, THIS SUPERSEDES EVERY "IAM split, first migration" LINE ABOVE.

Confirmed directly against AWS, by Andrew, not inferred:

    AWS_PROFILE=relayshield aws lambda get-function-configuration \
      --function-name relayshield-intel-feed --query 'Role' --output text
    arn:aws:iam::239677749008:role/relayshield-intel-feed-role

That is not `relayshield-breach-check-role-1sapnwdl`. The split for this one function ran,
successfully, in a prior session -- by Andrew's own account, painfully -- and the repo never
learned about it.

**WHY NOTHING HERE COULD EVER HAVE SHOWN THIS, and it is worth saying plainly rather than
defending the miss: a Lambda's execution role is pure AWS state.** Nothing in this codebase
records which role a function runs under. `tools/iam_split_roles.py` derives and WRITES the
policy; the role ASSIGNMENT is a separate `aws lambda update-function-configuration --role ...`
call with no file behind it to diff. So a successful `--apply` leaves the identical repo it
started from -- confirmed the previous turn by blob hash: `tools/iam_split_roles.py` is
byte-identical across all 14 branches on GitHub, because running the tool does not change the
tool. There was never going to be a commit to find.

**AND THIS REPO HAD ALREADY PAID FOR THE IDENTICAL SHAPE ONCE, IN THE STARS WATCHLIST GRANT, AND
THE CONNECTION WAS NOT MADE.** "THE STARS GRANT IS CLOSED" above records, four days earlier in
this same file: *"the script's `--apply` path ran at some point and nobody recorded it. A DOC
RECORDING AN OPEN ITEM IS A LEAD, NOT A FACT, EXACTLY AS A DOC RECORDING A DONE ONE IS."* That
sentence describes this incident exactly and was sitting in the file while it was diagnosed from
scratch instead of recognised as the same pattern with a different grant's name on it.

**THE GAP IS PROCEDURAL, NOT A READING FAILURE.** An AWS action that succeeds outside a session
that can commit is invisible to every future session, forever, unless someone closes the loop
with a follow-up note. The fix: whoever runs an `--apply` -- a session, or Andrew on the Mac --
pastes the confirming output back in afterward, specifically so it gets written down, the way
this section exists now. Every "IAM split, first migration" line in every Top 15/Top 10 above
(2026-09-14 item 2, 2026-09-17 item 4, 2026-09-22 item 8, 2026-09-23's carried list) is now
closed for `relayshield-intel-feed`. Those lists are historical snapshots per this file's own
rule and are not edited in place, but nothing after this section should read any of them as
still open for this function.

**STILL UNKNOWN, cheap and not urgent:** whether `relayshield-intel-feed` was the only function
migrated, or others moved too, and the shared role's current policy counts. Read-only:

    AWS_PROFILE=relayshield aws iam list-attached-role-policies \
      --role-name relayshield-breach-check-role-1sapnwdl --no-cli-pager \
      --query 'length(AttachedPolicies)' --output text

## SESSION 2026-09-25: THE SECRET-SCAN-TEXT x402 FIX AND THE MANIFEST GAP ARE ON MAIN NOW.
## MOST OF `claude/gallant-hawking-4oerzg` IS STILL NOT. READ THIS BEFORE TRUSTING THAT BRANCH.

**Started from a user claim to verify**: *"secret-scan-text v2 is not on main -- `X402_V2_ENABLED_
PATHS` has no entry and the spec still says `x402_version: 1`. Presumably unpushed or on a
branch."* Checked directly against `origin/main` (then `c2dcc42`) rather than trusted: **both
halves confirmed true**, and the "presumably on a branch" half was exactly right --
`839e709` ("Move secret-scan-text onto x402 V2 for real, not just in the spec") already fixed
it, sitting on `origin/claude/gallant-hawking-4oerzg`, pushed to GitHub, never merged.

**That same read surfaced something bigger: an entire unmerged session's worth of work sitting on
that branch, including its own already-regenerated Top 10** (commit `bde2a2b`, "Record this
session's fixes and regenerate the Top 10 against actual code state", dated 2026-09-25). That
write-up is accurate and is the best current status of several open items -- an OpenAI partner
key that was never actually issued (the issuance script ran before a merge, so it hit
file-not-found on Andrew's Mac), and the finding that the x402 manifest gap was WORSE than
previously recorded: `relayshield_agentic_api.py` has NO manifest handler of its own at all, so
it was never just `agent-bait-scan` missing, all three of its priced endpoints
(`agent-bait-scan`, `mcp-registry-risk`, `prompt-injection-breach`) were invisible to every x402
indexer. **None of that write-up is on main's CLAUDE.md** -- it only exists on the branch. This
section is the record on main; treat `bde2a2b`'s content as accurate but not yet delivered here.

### WHAT ACTUALLY SHIPPED TO `origin/main` THIS SESSION, two commits, both tested

**1. `1b1f6ff` -- cherry-picked ONLY `839e709`, not the whole branch.** The user asked to merge
that one specific fix. My first attempt did `git merge --no-ff origin/claude/gallant-hawking-
4oerzg`, which pulled in the OpenAI partner key script, Muse connector changes, and unrelated
CLAUDE.md notes along with it -- caught before committing, `git reset --hard` back to
`origin/main`, redone as a clean `git cherry-pick 839e709`. **Match the scope of the request; a
branch is not a commit.** `secret-scan-text` is now in `X402_V2_ENABLED_PATHS` in
`relayshield_api.py` and the spec says `x402_version: 2`. `test_x402_version_agreement.py` (that
commit's own guard) passes.

**2. `3ad5641` -- the manifest fold-in, written fresh this session.** It did not exist as code
anywhere reachable (the branch's own `bde2a2b` write-up correctly called it "not fixed this
session; now item 4"). `handle_x402_manifest()` in `relayshield_api.py` only ever iterated its
own `PAYG_PRICE_UNITS`; it now also reads `relayshield_agentic_api.py`'s table via a
function-local `import relayshield_agentic_api` (precedented by `relayshield_mpp_settlement.py`
already importing that same module -- the file's "deployment package independent" comment is a
one-way rule about *it* not importing `relayshield_api.py`, not the reverse). New shared helper
`_x402_manifest_entries()` so both tables go through one entry-building path rather than two.
`test_x402_manifest_completeness.py` (5 tests) executes the real handler with boto3 stubbed and
was proven against the regression by `git stash` on `relayshield_api.py` alone: 3 tests failed
with the exact three missing URLs before the fix, all green after restoring.

**Both are now on `origin/main` (`git log --oneline -2 origin/main` should show `3ad5641`,
`1b1f6ff`) and will deploy on the next Lambda push per the standard `deploy_lambdas.yml`
pipeline -- no separate deploy step needed.**

### WHAT IS STILL ONLY ON `origin/claude/gallant-hawking-4oerzg`, NOT ON MAIN

Four commits past `839e709` never made it into this session's push, because the user's request
was scoped to one specific fix plus the manifest gap, not "merge the branch":

    72d085f  Fix Muse partner-key gate reaching the wrong route, price and document
             incident-timeline, and correct the Bundle B duplicate-entity record
    dd44aa5  Add the missing /v1/metered/dependency-risk price card to the landing page
    add6b75  Build the general METERED_CREDIT_COSTS/landing-page guard; issue an OpenAI
             partner key alongside Muse's, generalizing the issuance tool
    bde2a2b  Record this session's fixes and regenerate the Top 10 against actual code state

**Concretely absent from main right now**: `tools/setup_partner_key.py` does not exist here, so
the OpenAI partner key has still not been issued to anyone. `relayshield_developer_signup.py`,
`cloudflare_worker_miniapp.js`, `miniapp_routes.json`, `test_dependency_risk.py`,
`test_metered_pricing_landing_page.py` and `test_muse_connector_features.py` all carry changes on
that branch that are not reflected here. **Checked for conflict risk before writing this down,
not assumed**: `git diff main origin/claude/gallant-hawking-4oerzg -- relayshield_api.py` shows
that branch's copy of `handle_x402_manifest()` is simply the OLD (pre-fix) version -- it branched
before this session's fix existed, so there is no competing edit to that function waiting to
collide, only an absence. A future merge of that branch should apply cleanly there. Whether the
rest of the branch (the Muse route/price fix, the dependency-risk card, the landing-page guard)
still applies cleanly against current main has NOT been checked.

**Next session's first move: `git fetch --all --prune` then decide what to do with the rest of
`claude/gallant-hawking-4oerzg`** -- merge it (after review, since the OpenAI/Muse changes were
never independently verified here), or treat it as superseded and extract only what's still
correct. Do not assume it is either fully live or fully stale; check it, per this file's own
"a doc recording an open item is a lead, not a fact" rule, which applies to an unmerged branch's
commits exactly as it applies to a status paragraph.

### ITEM 3 OF THE USER'S THREE-PART REQUEST -- NOT CONFIRMED RUN

`sh tools/setup_breach_cache.sh` (creates `relayshield_breach_cache` in DynamoDB) was handed to
Andrew as an `ANDREW RUNS THIS` block, because this container's AWS credentials are dead
placeholders. **No confirmation it has been run.** This is the first thing to check next session
-- the breach-check code ships inert (falls through to a live HIBP call every time) without it,
exactly as recorded in the 2026-09-22 section on this same table.

### ONE MORE BRANCH SEEN IN PASSING, NOT EXAMINED

`git branch -r --sort=-committerdate` this session listed `origin/feature/scam-kit-fingerprinting`
as the single most recently committed branch in the whole repo, ahead of `gallant-hawking-4oerzg`.
**Not opened, not read.** Worth a look before assuming scam-kit fingerprinting (recorded above as
unscoped, item 1 of the four 2026-09-23 roadmap additions) is still just a roadmap entry -- it may
no longer be.

## SESSION 2026-09-28: THE CHROME EXTENSION (FD-6) IS SUBMITTED FOR REVIEW. TWO REAL GOPLUS/API
## BUGS FOUND AND FIXED ALONG THE WAY, ONE STILL OPEN ON CS MOBILE.

**A note on continuity, first, because it matters for how to read everything below.** This session
started with a large amount of prior narrative in context, running through material dated as late
as 2026-09-27/28 -- specifics about an IAM split, a duplicate Bundle B product, WhatsApp front-door
work. Checked directly against `origin/main`'s actual tracked `CLAUDE.md` at the END of this
session: **none of that material is in the file.** The real, tracked file's last entry before this
one is "SESSION 2026-09-25" above, at line 8513, and the file is exactly 8607 lines through the end
of that section -- confirmed by fetching `origin/main` fresh and reading it directly, not assumed
from memory. Whatever produced that extra material, it was never committed here. **This section
continues from the real, verified state (SESSION 2026-09-25), not from the phantom one.** Recording
this so a future session that also gets handed a large context block knows to check it against the
tracked file the same way, per this file's own "a doc recording an open item is a lead, not a fact"
rule -- which turns out to apply to an entire session's worth of assumed history, not just a status
paragraph.

### THE CHROME EXTENSION: BUILT, TESTED, SUBMITTED. FOUR REAL BUGS FOUND TESTING IT WITH ANDREW.

`chrome-extension/` reached v0.2.1 this session and was submitted to the Chrome Web Store for
review by the end of it (as `relayshieldadmin@gmail.com`, publisher ID
`44788069-4790-4e5d-8791-894fe1052258`). Along the way, testing with real input rather than mocks
found four genuine defects, each the same shape this file has recorded before: **built, and wrong
in a way only a real check catches.**

1. **Explorer/DEX URLs only checked the domain, never the embedded address.** A Jupiter token page
   for a confirmed scam token read as "nothing known against it" because `jup.ag` itself is a
   legitimate platform and nothing extracted the mint from the URL path. Fixed with
   `rsExtractEmbeddedAddress()` -- walks path segments and query values through the same
   chain-detection regex the bare-address path already trusts, then checks the domain AND the
   embedded address in parallel, worse wins.
2. **The toolbar icon was muted.** It reused a brand asset built for a large dark tile (16%-opacity
   fill, solid dark background); at 16-32px it read as grey next to other extensions' icons.
   Rebuilt from a new source (`assets/miniapp/relayshield_icon_action.html`) with a transparent
   background and solid fill.
3. **The footer implied features the extension doesn't have, TWICE, and I introduced the second
   instance myself while fixing the first.** "Breach and infostealer checks need a free key" sat
   right below the extension's own three (unrelated) checks, implying they were gated -- fixed by
   rewording it as a generic developer CTA. The SIBLING line, "Want ongoing monitoring, not just
   one-off checks?", carried the identical implication (that the extension does a lesser version of
   breach/SIM-swap checking) and I caught it myself immediately after fixing the first, before
   Andrew had to point it out a second time.
4. **No version bump across three real fixes.** 0.2.0 shipped the embedded-address fix, the icon,
   and the footer wording with no version change between them, so `chrome://extensions`'s own
   version number gave Andrew no way to tell "reloaded the old code" from "reloaded the new code"
   when something didn't look different. Bumped to 0.2.1 specifically to restore that signal --
   same shape as the Mini App's BUILD id, a different surface.

**Registration mechanics worth remembering, since none of this is written down anywhere else in
this repo:**
- **$5 one-time fee, not $25** -- confirmed against Google's own current developer docs; the $25
  figure belongs to a different store.
- **A payment decline reading `[OR_FGPMH_11]` on two different cards was resolved by registering
  from an Incognito window instead** -- root cause UNCONFIRMED (a stale Google payment session in
  the normal browser profile is the leading guess, since a bank decline shows a different message
  and two different cards hitting the identical Google-side error code rules out the cards
  themselves). If it recurs, Incognito is the known workaround, not a diagnosed fix.
- **Trader declaration**: RelayShield LLC is a trader account by Andrew's own decision, and the
  address/phone/DUNS (`14-989-2087`) that gets posted PUBLICLY on the listing footer is the same
  address already public via Massachusetts state business registration -- a knowing choice, not an
  oversight, recorded here so it isn't re-litigated.
- **"Are you using remote code?" was wrongly set to Yes.** The extension fetches JSON from
  `api.relayshield.net` and renders it as escaped text -- no `eval`, no injected remote `<script>`
  tag -- which is a data fetch, not remote code execution in Chrome's policy sense. Corrected to No,
  which should also reduce the compounding review delay that answer adds on top of the (separate,
  expected, largely unavoidable) host-permission review.
- **`support@relayshield.net` was flagged by Chrome's own validator as unreachable.** Could not
  verify why from this container -- every DNS tool (local `dig`/`host`/`nslookup`, and two different
  DNS-over-HTTPS providers) is blocked by this container's egress policy. Worked around by pointing
  the Support URL field at `https://api.relayshield.net/developers?source=chrome-extension` instead,
  which is confirmed live. **Andrew was asked to send a real test email to confirm whether the
  mailbox is genuinely dead -- no confirmation received this session.**

### THE GOPLUS SOLANA SCHEMA STORY -- A METHOD WORTH REMEMBERING, NOT JUST A BUG

Testing the Chrome extension's wallet check against real confirmed-scam Solana tokens (found by
Andrew, not invented) surfaced a genuine gap in `/v1/wallet-risk`: GoPlus's `address_security` API
answers "does this ACCOUNT have a history of bad behaviour" -- phishing, dark web, sanctions. A
freshly-minted scam token contract has no such history by definition, so that call alone can never
catch one. The check that WOULD catch it -- mint authority, honeypot, impersonation -- is a
separate GoPlus endpoint, `token_security`, already used by the paid `/v1/token-security` handler
but never called from the free `/v1/wallet-risk` path.

**The first fix shipped wrong, silently, and stayed wrong until Andrew tested three more scam
tokens and none of them changed.** It assumed Solana was "just another chain_id" on the same URL
GoPlus uses for EVM (`/api/v1/token_security/{chain_id}`) and reused EVM's field names
(`is_honeypot`, `is_airdrop_scam`, `fake_token`, `sell_tax`). Both assumptions were wrong:

- **The real Solana endpoint is `/api/v1/solana/token_security`** -- the same two path segments,
  opposite order, a separately-versioned ("beta") API entirely, not a parameter on the EVM one.
- **The real response schema is nested capability objects**, `{"status": "0"|"1", "authority":
  [...]}`, one per field (`freezable`, `mintable`, `closable`, `balance_mutable_authority`,
  `metadata_mutable`, `none_transferable`) -- nothing resembling EVM's flat booleans.

**How this was found, and it is the reusable part: `api.gopluslabs.io` is not reachable from this
container (403 on every attempt), and neither is `docs.gopluslabs.io`. `pypi.org` is.** GoPlus
publishes an official Python SDK (`pip install goplus`), generated by swagger-codegen straight from
their own OpenAPI spec, and downloading the wheel (`pip download goplus --no-deps`) and reading the
generated `api/token_security_api_for_solana__beta_api.py` and its response models gave the exact
real endpoint path and field names with no live API access needed at all. **The same
"BLOCKED SOURCE WAS REACHABLE ALL ALONG" shape this file has recorded for Stripe's `mppx` package
and Smithery's CLI, in a third vendor.** When a vendor's docs and live API are both blocked, check
whether they publish an official SDK on PyPI or npm before concluding the shape is unverifiable --
a generated client is a more literal contract than prose anyway.

Corrected: `freezable` and `balance_mutable_authority` graded CRITICAL (the direct Solana analogues
of a honeypot -- an active mechanism to trap or drain funds after purchase, decisive alone, same
reasoning as `sanctions_hit`); `mintable`/`closable`/`metadata_mutable` graded WARNING, mirroring
EVM's own `is_mintable` tier. 15 tests. **One thing still genuinely unverified and labelled as such
in the code**: the exact `"0"`/`"1"` string convention for Solana's own fields is inferred from
GoPlus's established EVM convention, never confirmed against a live Solana response, because the
live API still cannot be reached from here. The first real honeypot/scam SOL token to hit this path
in production is the actual test.

### CS MOBILE: A REAL 400, ROOT CAUSE STILL UNKNOWN -- BUT A REAL BUG FOUND ON THE WAY THAT EXPLAINS WHY IT'S UNKNOWN

Arjen reported `RS API error 400` scanning a Solana token mint
(`5aXSfstoUYp4uBEpJoMyMrzLFNFyrMQZ5d2u7yVFD`) via the SOL Token scan type in Crypto Shield Mobile.
**Executed `handle_solana_token_risk` directly with that exact address rather than guessing**: the
mint passes format validation (41 chars, valid base58), and every code path in the handler returns
200 regardless of whether the upstream vendors (Rugcheck.xyz, DexScreener) succeed or fail. The one
dispatcher-level check that could plausibly reject a keyless call before reaching the handler --
the daily per-IP quota -- returns 429, not 400. **Nothing in the code that runs today can produce
this 400 for this input.** Genuinely unresolved; the leading unverifiable-from-here guess is a
corrupted or malformed stored API key on Arjen's device causing a header-level rejection before
Lambda is even invoked.

**The real, fixable bug found on the way: the app's own API client was throwing away the reason.**
`rsPost`/`rsGet` in `crypto-shield-app/src/api/relayshield.ts` threw on the bare HTTP status code
before ever reading the response body -- and every server-side rejection (`_err()` in
`relayshield_api.py`) puts the actual reason in that body. So "RS API error 400" was not an
incomplete report Arjen gave; it was the entire report the app was CAPABLE of producing, because
the one piece of information that would explain it was discarded before the user ever saw it. Three
other functions in that same file (`getSubscriptionByEmail`, `confirmCheckoutSession`,
`openBillingPortal`) already read the body correctly -- it was specifically the two most-used
helpers that didn't. Fixed: both now parse the JSON body first and surface the server's own error
text, falling back to the bare status only if the body isn't JSON.

**This fix is on `main` and does NOT reach any device on its own.** Unlike every Lambda change this
session (which deploy automatically via `deploy_lambdas.yml` on push), `crypto-shield-app` is the
Expo mobile app and only reaches a device through an actual EAS build and store submission. The next
time this error fires in a build that includes this commit, the message will say why; Arjen's
current install will not.

### THE TOP 10 FOR THE NEXT SESSION

1. **Check the Chrome Web Store review outcome** -- the account is `relayshieldadmin@gmail.com`, the
   Developer Dashboard shows status directly. If rejected, get the specific reason and fix it; if
   approved, get the listing URL (see item 7).
2. **Confirm whether `support@relayshield.net` is a real, monitored mailbox.** Andrew was asked to
   send it a real test email; no confirmation happened this session. If it's dead, decide whether to
   provision it for real or make the developers-page URL the permanent public support contact
   everywhere this repo references one, not just a one-field workaround.
3. **EAS rebuild and republish Crypto Shield Mobile** so the `rsPost`/`rsGet` error-surfacing fix
   actually reaches a device -- it is on `main` and nowhere else right now.
4. **Once that new build is live, have Arjen retry the exact same SOL Token scan**
   (`5aXSfstoUYp4uBEpJoMyMrzLFNFyrMQZ5d2u7yVFD`) and report whatever specific error text now
   appears, if it recurs. That is the only way left to learn the actual root cause of the original
   400 rather than continue guessing at it.
5. **Check whether Arjen's stored API key is corrupted or malformed** -- a plausible cause for a 400
   that never reaches Lambda at all (a malformed header value rejected at the edge), and something
   this container cannot verify without AWS/CloudWatch access.
6. **The GoPlus Solana `"0"`/`"1"` status convention is still unverified against a live response.**
   Watch for the first live hit on `metadata.is_token_contract` in `/v1/wallet-risk`'s logs and
   confirm the flags it produces make sense against the actual token, since `api.gopluslabs.io` still
   cannot be reached from this container to test directly.
7. **Once the Chrome extension is approved, wire it as a discovery surface**, not just a published
   artefact: link the Store listing from the developers page and the Mini App, and register a NEW
   `?source=` key for arrivals FROM the Store listing itself (distinct from `chrome-extension`,
   which is for people already using the installed extension and is registered in all three of
   `miniapp_routes.json`, `ALLOWED_SOURCES`, and `_SOURCE_ALIASES` already) -- a listing is a
   standing shelf, per this file's own established doctrine, and needs its own attribution to be
   measurable separately from the extension's own footer traffic.
8. **A third Chrome extension screenshot** (the Email tab, or a clean "nothing known" result) was
   offered and not built. Worth doing once real usage data exists to screenshot against.
9. **`/v1/wallet-risk` returns `risk_level: "LOW"` -- a positive, reassuring label -- whenever
   nothing is found, unlike `_link_check_level`'s explicit "never low, only unknown" rule.** This is
   a real, deliberate inconsistency, confirmed by grep to touch two dozen-plus files across Crypto
   Shield Mobile, the Mini App, the widget, and the Chrome extension. Recommended fix (rename to
   `"unknown"`), NOT made this session given the blast radius -- this needs Andrew's explicit
   sign-off before touching, since it changes what every existing surface shows for the majority of
   addresses checked (most addresses are clean).
10. **Everything in "SESSION 2026-09-25" above -- the `gallant-hawking-4oerzg` branch
    reconciliation, the unconfirmed `relayshield_breach_cache` table creation, the unexamined
    `feature/scam-kit-fingerprinting` branch -- is UNCHANGED and UNREVIEWED this session.** This
    session's work was entirely the Chrome extension and Crypto Shield Mobile; none of the wider
    AWS/IAM/catalogue backlog was touched or re-verified. Re-read that section before assuming any
    of it has moved.

## SESSION 2026-09-28: WEEKLY METRICS GAINED TWO REAL CORPUS FIELDS, AND HAS NO DEPLOY PATH

Asked for: monitored-marketplace count and unique-indicator count in the weekly metrics
report's Alerts Fired section, plus whether any CS Mobile trial signups have happened.

**THE TRIAL DATA ALREADY EXISTS.** `_cs_mobile_stats()` has tracked the 7-day trial cohort
(started/active/converted/lapsed, conversion rate over DECIDED trials only) since
2026-08-27, and it is already in the weekly email. Nothing needed building there. What
CANNOT be answered, checked rather than assumed: **the Stripe Payment Links CS Mobile
uses (`PaywallScreen.tsx`) carry no platform or distribution-channel tag at all** --
`Linking.openURL(STRIPE_MONTHLY_URL)` with no `client_reference_id` or metadata. So today,
while the app is live ONLY on the Solana dApp Store, every trial in the report IS a Solana
dApp Store trial by elimination. The moment the Google Play build ships, that stops being
true and the two channels' trials become indistinguishable in this report -- worth adding a
platform tag to the Payment Link URL before that build goes out, not after.

**THE TWO NEW FIELDS, added the same way the TI demo's cards were corrected on 2026-09-16
rather than by inventing numbers:**

- **Monitored Telegram marketplaces (active)** -- `_monitored_marketplaces()`, a filtered
  scan of `relayshield_intel_channels` on `active=True`. Same definition
  `tools/ti_demo_metrics.py` already uses for its own card, reused rather than re-derived.
- **Unique indicators (all-time, distinct)** -- `_unique_indicators()`, the ROW COUNT of
  `relayshield_intel_first_seen`. That table writes exactly one row per `ioc_value` ever
  (a conditional put in `_record_first_seen`, no TTL by design), so its count IS the
  distinct-indicator number directly -- cheaper and more honest than scanning and collapsing
  `relayshield_intel_iocs` (millions of sighting rows) the way `--distinct` mode does for the
  TI demo. The pre-existing `ioc_total` row is relabeled "IOC sightings (total, incl.
  repeats)" rather than removed, so the report stops implying a sightings count IS the
  indicator count -- the exact defect the TI demo's cards paid for once already.

Both are additive; 8 new tests in `test_weekly_metrics.py` (a file that did not exist before
this session -- `relayshield_weekly_metrics.py` had NO test suite at all), executed against a
fake DynamoDB that actually applies the filter expression rather than a MagicMock that
answers every scan the same way regardless of it.

**AND THIS FUNCTION IS THE SIXTH-OR-SEVENTH INSTANCE OF THIS REPO'S MOST-REPEATED DEFECT:
source in the repo, live weekly traffic (it has clearly been hand-deployed and re-deployed
many times -- every fix described above `_cs_mobile_stats` is a dated comment written
in-file, which only makes sense if each one made it to AWS), and `relayshield_weekly_metrics`
is in NEITHER `deploy_lambdas.yml`, NOR `lambda_drift_check.yml`, NOR
`iam_github_deploy_invoke.json`.** Confirmed by grep, not assumed. The live function name is
`relayshield-weekly-metrics`, read from `tools/rotate_stripe_key.py` and the IAM snapshot --
it runs under the shared `relayshield-breach-check-role-1sapnwdl` role. This change cannot
reach AWS by merging; it needs a hand deploy. Unlike `relayshield_bundle_fulfillment.py`,
this file imports nothing else in the repo (stdlib + boto3 only), so a drift recovery here
would be a pure single-file diff with nothing else at risk -- the safest shape this repo's
own drift rule describes, but the check is one command and costs nothing to run first.

## MINI APP AND DIRECTORY REGISTRATIONS, SAME SESSION

**`tg-miniapp-dramex` registered in all three lists** (`miniapp_routes.json` rank 21,
`ALLOWED_SOURCES` in `cloudflare_worker_miniapp.js`, `_SOURCE_ALIASES` in
`relayshield_developer_signup.py`) BEFORE any submission, per the standing rule.
`Dramex/telegram-mini-apps-catalog`'s own `CONTRIBUTING.md` (read via
raw.githubusercontent.com, github.com is reachable from the container) states a PR-based
submission, one app per PR, a decision within 7 days, and a `data/apps.json` entry with
required fields `name`, `url`, `description`, `category` (one of
`Products`/`Games`/`Open Source Projects`/`Libraries & Templates`), `contributedBy`,
`lastChecked`, `status`. **This session could not open the PR itself** -- `add_repo` and
`fork_repository` both refuse `Dramex/telegram-mini-apps-catalog` outright (`Access denied:
repository ... is not configured for this session`), and `list_repos` confirms it is not
reachable from this account's GitHub App installation. The prior PR to
`telegram-mini-apps-dev/awesome-telegram-mini-apps` (#77) was evidently opened under looser
constraints than this session has; that route is not available here. The exact JSON entry
and PR text are handed to Andrew to paste via GitHub's own web editor (which auto-forks on
edit for a repo you don't own).

**Four directories (`MCP.Directory`, `LibHunt`, `ZPlatform.ai`, `PulseMCP`) were researched
via WebSearch, since all four are egress-blocked for WebFetch from this container** (same
policy as `docs.stripe.com`, `glama.ai` etc. elsewhere in this file):

- **MCP.Directory** (`mcp.directory/submit`) auto-pulls metadata from a public GitHub repo
  within 24 hours -- confirmed the repo it would read, `github.com/relayshield/relayshield-mcp`,
  actually loads (this ALSO closes the open "ANDREW CLICKS THIS" verification FD-9 left
  hanging: the repo is real, not a 404, so the registry record's and Glama's `repository.url`
  need no fix).
- **PulseMCP** currently has submissions PAUSED while they rework ingestion -- their own
  submit page says so. Do not submit now; the key is registered so a later submission
  attributes correctly once they reopen.
- **ZPlatform.ai** appears to be a pure automated ranking page pulling from the official MCP
  registry and GitHub adoption data, with no self-serve submission form found in search
  results. If that holds, there is nothing to submit -- RelayShield's presence there (if any)
  rides on already being on the official registry, which it is (FD-8/FD-9).
- **LibHunt** is a general open-source directory (not MCP-specific), so it was NOT folded
  into the `mcp-registry` banner; `libhunt.com` was added as a referer host to the existing
  `github` banner instead, since its audience (developers comparing tools) is the one that
  banner already addresses. Its exact submission form URL could not be confirmed from search
  results alone (libhunt.com itself is egress-blocked); Andrew's own read of the site settles
  it in one look, the same "a website shows its navigation in one look" finding this file
  already recorded for Mini App directories.

`mcp.directory`, `zplatform.ai`, `pulsemcp.com` were added as referer hosts to the existing
`mcp-registry` banner (already shared by glama.ai, smithery.ai and mcp.so) rather than each
getting a new banner -- same kind of destination, same accurate copy, no reason to write it
three more times.

## SESSION 2026-09-28 (second): STRIPE CHECKOUT NOW TAGS SOLANA VS FUTURE GOOGLE PLAY

Asked for: measure unique indicators and 7-day trial starts, add a platform tag to CS
Mobile's Stripe checkout so Solana and a future Google Play build stay distinguishable,
and help with three directory submissions plus verifying the Dramex PR.

**THE TAG.** `PaywallScreen.tsx`'s two Payment Link URLs now carry
`?client_reference_id=solana`. Stripe copies that onto the Checkout Session it creates;
`relayshield_weekly_metrics.py` reads it back per subscription via
`GET /v1/checkout/sessions?subscription=...` (`client_reference_id` lives on the
session, not the subscription, so there is no cheaper read). New helper
`_checkout_platform_tag()`, wired into `_cs_mobile_stats()`'s activation and trial-start
counters, rendered as a "by platform" sub-row under each in the email. **Every
subscription on the currently-live build predates the tag and reads "unattributed" --
that is correct, not a bug**, and will stay the only value until a build carrying this
edit reaches a device via EAS + a new Solana dApp Store submission. Editing the file is
not a release. A future Google Play build tags its own copy `"googleplay"` in the same
spot; do not reuse `"solana"` for it. 6 new tests in `test_weekly_metrics.py`.

**MEASURING THE TWO NUMBERS ASKED FOR NEEDS THE PRIOR SESSION'S DEPLOY TO HAVE RUN,
WHICH IS UNCONFIRMED.** The monitored-marketplace and unique-indicator fields, and this
session's platform tags, only reach AWS through the hand-deploy steps the prior session
handed Andrew (`relayshield_weekly_metrics` has no CI deploy path -- see that session's
entry). The reply hands him one merge → drift-check → deploy → **invoke** sequence that
also fires the report immediately by hand rather than waiting for Monday, so the numbers
land in his inbox in the same round rather than requiring a second one.

## DRAMEX PR #2: OPEN, NO CONFLICTS, NO REVIEW YET -- THAT IS THE EXPECTED STATE

Verified live via WebFetch (github.com is reachable) rather than trusting the
screenshot alone: **Open**, "No conflicts with base branch", zero reviews so far.
`Dramex/telegram-mini-apps-catalog`'s own `CONTRIBUTING.md` states a decision within 7
days, so an unreviewed PR at this stage is the SLA working, not a stall. Nothing to do
until then. `miniapp_routes.json`'s `dramex` row updated `ready` → `submitted`.

## THREE MORE DIRECTORY SUBMISSIONS, RESEARCHED AND HANDED OVER AS FORM VALUES

**MCP.Directory** -- Andrew reports submitted. Nothing further.

**ZPlatform.ai** -- a generic AI-tool submission form (name/email/tool
name/URL/category/pricing URL/one-line description), distinct from their
**registry-derived** MCP Servers page (163 servers pulled automatically from the
official MCP registry, per the 2026-09-28 first-session research -- so relayshield-mcp's
presence there needs no manual submission at all). Recommended submitting the **API
product** (`api.relayshield.net/developers`) rather than a bot username or the Mini App,
because the form's own fields (a URL, a price, "what does it do, for whom, what does it
cost") match a priced product page, not a Telegram surface. **The user's personal email
(`nzdsf2@gmail.com`, this session's own userEmail context) was deliberately NOT
prefilled into this third-party form** -- that context says explicitly not to send it to
an unrelated service unless asked, and `andrew@relayshield.net` is the more appropriate
contact for a business tool submission besides.

**LibHunt** -- a GitHub-repo-based submission (repo/description/topics/website/docs
URL/language/license/self-hosted), matching `github.com/relayshield/relayshield-mcp`
directly. **The License field could not be filled**: no `LICENSE` file was found at
that repo's root (`raw.githubusercontent.com/.../main/LICENSE` returns 404) and no
license badge was visible on the repo page. Left for Andrew to fill from what is
actually there rather than guessed -- a license claim is not one to invent.

## THE DEPLOYED REPORT CAME BACK MISSING BOTH NEW FIELDS. DIAGNOSING RATHER THAN GUESSING AGAIN.

**2026-09-29.** Andrew ran the merge/drift-check block and the deploy/invoke block from the prior
session and received a Weekly Metrics email, but it shows none of: the active-marketplace count,
the unique-indicator count, or a usable CS Mobile trial number -- which is exactly the input his
Solana-vs-Google-Play decision needs and does not have.

**THREE DIFFERENT FAILURES PRODUCE THIS IDENTICAL SYMPTOM, AND THIS FILE'S OWN RULE IS TO NAME
WHICH ONE RATHER THAN GUESS A FIX.** `monitored_marketplaces` and `unique_indicators` are two bare
calls inside the `metrics` dict literal with NO try/except around them -- if either raised, the
whole `lambda_handler` would raise before `ses.send_email()` and Andrew would have gotten no email
at all, not an incomplete one. He got an email, so either (a) those two calls ran fine and are IN
it (and something about the layout made them easy to miss), or (b) the merge before his deploy did
not actually bring the new code onto disk, so the OLD `relayshield_weekly_metrics.py` got zipped
and deployed. Separately, `_cs_mobile_stats()` wraps its ENTIRE body in one broad try/except that
returns an all-zeros dict on any exception -- so if the new `_checkout_platform_tag()` call (an
extra Stripe API round trip per subscription that did not exist before this session) throws for
any reason, every CS Mobile number in the email reads 0, which would look exactly like "no trial
information" even though the report itself did not fail.

**THE DIAGNOSTIC, READ-ONLY, NO MERGE (this only inspects what is already on disk and already
deployed -- nothing here writes anything):**

    ANDREW RUNS THIS:
    ```zsh
    cd ~/dev/relayshield
    grep -c "_checkout_platform_tag\|_monitored_marketplaces" relayshield_weekly_metrics.py
    AWS_PROFILE=relayshield aws lambda get-function-configuration --no-cli-pager \
      --function-name relayshield-weekly-metrics --query 'LastModified' --output text
    AWS_PROFILE=relayshield aws logs tail /aws/lambda/relayshield-weekly-metrics --no-cli-pager --since 2h
    ```
    EXPECT: line 1 prints `2` (both new functions are in the file that's on disk right now -- if
    it prints less than that, the merge never landed the fix and the deploy shipped stale code).
    Line 2 prints a timestamp matching roughly when the deploy command was run. Line 3 prints the
    actual log lines from the invoke, ending in "Weekly metrics email sent to ..." with no
    traceback and no "CS Mobile stats fetch failed" warning anywhere in between.
    STOP IF line 1 is `0` or `1` -- paste `git --no-pager log --oneline -3` from the same
    directory; the file that got zipped was never updated.
    STOP IF line 3 contains "CS Mobile stats fetch failed" or a Python traceback -- paste that
    exact line. That is the real cause, not a guess at one.
    STOP IF the `aws logs tail` line prints nothing at all -- the log group name may differ; run
    `AWS_PROFILE=relayshield aws logs describe-log-groups --no-cli-pager --log-group-name-prefix
    /aws/lambda/relayshield-weekly` and paste what comes back.

**Not yet run. This is the first thing to act on next.**
