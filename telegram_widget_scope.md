# The Telegram bot widget: scope, and what shipped

*2026-09-03. Item 1 of the 2026-09-02 list. Scoped and built in one session.*

---

## What this is, in one sentence

A third-party Telegram bot adds one function call, and every link or wallet
address its users paste gets screened against RelayShield, with no signup, no
key and no card for the first call.

## Why this rung of the ladder, and not the others

`telegram_miniapp_and_app_inventory_scope.md` set out a three-level on-ramp:
affiliate link, then a one-line widget, then the full API. The widget is the rung
that was missing, and it is the one that matters most, because the prospect list
is not a list of websites. It is a list of **bot repositories**: 206 rows at
`stars:5..50`, 109 with a website or an email, and 19 of the top 25 tagged
`wallets` or `payments`.

That single fact decides the shape of the build. A bot is server-side code in
Python or JavaScript. It is not a web page, so a `<script>` embed is the wrong
artefact for almost every prospect on the list. **The widget is a file you copy
into your bot, not a tag you paste into your HTML.**

## The finding that made this cheap

Three of the endpoints this needs were already keyless.

`KEYLESS_SCAN_ENDPOINTS` in `relayshield_api.py` has served
`/v1/wallet-risk`, `/v1/token-security`, `/v1/ton-address` and nine others with
no API key since Crypto Shield Mobile's free tier needed them, capped at 300
calls per source IP per day. So the wallet half of the widget needed no new
product decision at all: EVM, Solana, TON and Bitcoin address screening, keyless,
today.

The link half did not fit. `/v1/scan-url` submits to VirusTotal and returns
`"pending"` with a poll endpoint, which is the right shape for a security tool
and the wrong shape for a message handler that has to answer now, and it costs
real money per call, which is why it needs a key.

**So the one new thing built here is `POST /v1/link-check`:** the three signals
we can produce immediately and at effectively no marginal cost, which are the
same three Telegram's own `/scan` shows first.

| Signal | Source | Cost |
|---|---|---|
| Domain in the criminal IOC corpus | our DynamoDB | one query |
| Google Safe Browsing hit | Google, free tier | none |
| Domain registered in the last 30 days | RDAP | none |

Because the marginal cost is about zero, it is keyless under the same per-IP cap
as the wallet endpoints. **A first call that needs a signup is not a one-line
integration**, and the whole premise of this rung is that first call.

## Two rules the clients are built around

**1. It never throws.** Every failure path, including a timeout, a DNS failure,
a 429 at the daily cap and a JSON change on our side, returns a verdict with
`ok=false` and `level="unknown"`. A bot that crashes because our API had a bad
minute is uninstalled that week, and rightly.

**2. It never says "safe".** A clean link check is an absence of evidence across
three sources. The ceiling on a clean URL is "nothing known against it", with
the caveat attached. We are putting words into someone else's product, in front
of users who never chose us, and "safe" is a promise we cannot keep and cannot
withdraw.

Both rules are pinned by tests rather than by intent: 25 in Python, 14 in
JavaScript, mirroring each other case for case, all offline.

## The Telegram Markdown trap, which we have already paid for once

Telegram's legacy `Markdown` parse mode **has no escape syntax**. A backslash
before an underscore is a backslash, not an escape, and an unclosed entity makes
Telegram reject the whole message with a 400. So a scam URL containing an
underscore can silently drop the bot's reply, verdict included, and the more
suspicious the link the more likely it is to contain one.

RelayShield shipped exactly this bug on its own Quickstart card and spent a
session finding it. The widget therefore puts every attacker-controlled value in
a code span, which legacy Markdown treats as literal, and strips the one
character that could close it. `.html` is offered for anyone who prefers
`parse_mode="HTML"`.

If this widget ever broke a partner's bot with a 400 on a malicious link, it
would break it at the exact moment the bot needed to work.

## What shipped

| Piece | File |
|---|---|
| Keyless heuristic endpoint | `handle_link_check` + `_link_check_level` in `relayshield_api.py` |
| Structured signals behind it | `signals` added to `_heuristic_url_check`, additively |
| Python client | `widget/relayshield_widget.py`, stdlib only, 3.9+ |
| JavaScript client | `widget/relayshield-widget.js`, ESM, Node 18+ |
| Tests | `test_relayshield_widget.py` (25), `widget/relayshield-widget.test.mjs` (14) |
| Install and use | `widget/README.md` |
| Attribution key | `tg-widget` in `_SOURCE_BANNERS`, registered BEFORE the widget ships |
| Gateway route | `tools/create_link_check_endpoint.sh` |

## Three deliberate omissions

**No browser embed in v1.** A `<script>` tag for Mini Apps needs CORS headers
the API does not send today, and the prospect list is overwhelmingly server-side
bots. The Mini App is its own item with its own scope.

**No new Telegram session, and no discovery.** This is the integration rung. The
inventory that feeds it is Item 16, and it stays blocked on the second Telegram
account for the reason the scope doc gives: the prospecting session must never
share a code path with the one 99 channels of collection depend on.

**No outreach copy here.** Item 2 is the tailored draft per prospect, and it now
has something concrete to point at, which it did not before. "Here is a function
that screens the links your users paste, and it needs no signup" is a capability
offer. It is not a claim about what their bot lacks, which is the framing the
external study got wrong and which reads as a threat from a security vendor.

## Ship sequence, in order, because two steps are invisible if reversed

1. Merge to `main`. That deploys `relayshield-api` with the endpoint in it,
   because `relayshield_api.py` is in `LAMBDA_MAP`.
2. `sh tools/create_link_check_endpoint.sh`. **This gateway is not a `{proxy+}`
   catch-all**: a route added to `ROUTES` is live in the Lambda and returns 403
   "Missing Authentication Token" at the edge until API Gateway has a resource
   and a method for it, and the stage is redeployed. The script proves the
   result with a real request rather than reporting success.
3. `sh tools/handler_drift.sh relayshield_developer_signup.py`. **The
   `tg-widget` banner does not reach a single visitor until that Lambda
   deploys**, and it is the sixth handler found with source in the repo, live
   traffic and no deploy path. Read its first diff before anything is mapped.

Steps 1 and 2 are both required and neither is sufficient. Step 3 is the
attribution, not the product.

## How this gets measured, so it does not become another silent channel

Every call carries `source: "tg-widget"` and every outbound link carries
`?source=tg-widget`. The number that decides whether this rung works is
**installs that make a second day of calls**, not total calls: one enthusiastic
evaluation and a real integration look identical on day one.

`_SOURCE_BANNERS` deliberately registers `tg-widget` with **no referer hosts**,
which is a departure from every other entry. The widget writes its own links and
always appends the parameter, so referer matching would add nothing except
mis-attribution: every un-keyed click from our own Telegram bot and blog channel
would be counted as a third-party widget install, and that is precisely the
number we want to be able to trust.
