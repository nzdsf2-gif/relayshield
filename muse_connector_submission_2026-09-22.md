# Muse connector submission: field-by-field copy

**The connector is the two keyless endpoints**, decided in
`muse_connector_scope_2026-09-21.md` and unchanged: `/v1/link-check` and
`/v1/wallet-risk`. Not the MCP server, whose fourteen tools are questions a
security engineer asks and a consumer does not.

**THE SCOPE'S BLOCKER IS SMALLER THAN IT SAID, AND THAT IS READ OUT OF THE
DISPATCH RATHER THAN RECALLED.** That document says a partner key is
*"a small build rather than a new product ... Half a day."* **There is no
build.** `relayshield_api.py:13073` already does it:

    if path in KEYLESS_SCAN_ENDPOINTS:
        _scan_key = _header(..., "X-RS-API-KEY") or _header(..., "X-API-Key")
        if not (_scan_key and _verify_rs_api_key(_scan_key)):
            ... per-IP cap ...

A valid key skips the cap entirely and falls straight through to
`return handler(params)`. There is no free-tier decrement in that path, no
metering, and `_verify_rs_api_key` is a pure read with no counter in it. The
cap's own comment names this as the intended answer: *"The durable fix is
per-install free-tier keys."*

**So issuing the connector a key is an existing operation, not a project, and
submission does not wait on it.** Do it before the connector goes live, not
before it is reviewed: a reviewer makes a handful of calls and 300 per day per
IP is ample for that, while a live consumer platform behind Meta's egress
addresses is not.

**UNVERIFIED and it stays labelled:** `muse.ai` is egress-blocked from the
container, so every statement below about Muse's form comes from the two
screenshots. **Step 2 of their wizard, "Technical specs", has not been seen at
all**, so nothing here anticipates it.

---

## The fields

### Connector name

    RelayShield Scam Check

**A recommendation, and the reasoning is tg.app's, measured rather than
assumed.** Their guidance was that titles matching what people type beat brand
names alone, and nobody types "RelayShield". The brand stays attached because
the listing is also how a reviewer identifies the company. Plain `RelayShield`
is the alternative if their form prefers a bare brand.

### Company / developer

    RelayShield

### Product website

    https://api.relayshield.net/developers?source=muse

**That URL, and both halves are deliberate.** `api.relayshield.net/developers`
is the API landing page and `api.relayshield.net` is the API host; they are
different things. And `?source=muse` only renders on `/developers`, because
`_SOURCE_BANNERS` is read by `handle_landing_page` in
`relayshield_developer_signup.py` and nowhere else. **The key was registered
before this file was written**, which is the whole point of that rule: an
unregistered key is sent, accepted and never logged.

Executed rather than read, against the real resolver:

    ?source=muse              -> logged 'muse'                      banner YES
    ?source=nope-not-reg...   -> logged 'unmatched:nope-not-reg...'  banner NO

### Example prompts

    Is this link safe? https://example-shop.co/checkout
    Someone sent me this link in a message. Has it been reported for scams?
    Check this wallet address before I send anything to it.
    Is 0x0000000000000000000000000000000000000000 a known scam address?
    I got an email with a link that looks like my bank. Is the domain real?

**Every one maps to one of the two endpoints and nothing else.** A prompt the
connector cannot serve is a promise a reviewer will test, and the fastest way
to fail a review is an example that returns nothing.

**No live scam URL and no live wallet address appears here.** The link is a
placeholder domain and the address is the zero address. Shipping a real
malicious link inside a submission invites a reviewer to tap it, and a real
flagged address that stops being flagged turns our own example into a false
negative we cannot see.

### Connector icon

    assets/miniapp/relayshield_icon_512.png

**Measured, not assumed:** PNG, 512x512, 8-bit RGB, non-interlaced, no alpha,
68 KB. It is TRACKED in git, so the merge puts a byte-identical copy on the Mac.
**Do not use a copy sent through chat** -- the chat layer re-encodes images to
`.webp`, which an upload dialog filters out of the file picker entirely, and
that cost three rounds on the miniTelegram submission.

### Payments category

**UNVERIFIED: the options on this field have not been seen.** The answer
whatever they are: **this connector has no payment surface.** Both endpoints are
free and keyless, nothing is sold through the host, and there is no checkout,
subscription or upgrade path reachable from inside it.

That is a deliberate scope rather than an omission. FD-14 found that selling
digital goods inside a host platform is not permitted on OpenAI's side, and it
is the same shape as the Telegram Stars rule. **A connector over two free
endpoints has nothing to review and nothing that can get us restricted.** The
paid rails stay outside the host, reached the way every other API customer
reaches them.

### Your name / work email

    Andrew Gibbs
    andrew@relayshield.net

### Support email or URL

    https://support.relayshield.net

### Privacy policy URL

    https://privacy.relayshield.net

### Terms of service URL

    https://terms.relayshield.net

**Both are live subdomains with their own Workers** (`wrangler.privacy.toml`,
`wrangler.terms.toml`), not paths. `relayshield.net/privacy` appears in
`cloudflare_worker_pricing.js` and is the wrong form; do not copy it from there.

### Anything else

> RelayShield answers two questions in plain language: is this link known-bad,
> and is this wallet address associated with a scam. Both endpoints are free and
> keyless, so there is no OAuth app, no account and no consent screen in this
> integration. The OpenAPI 3.1 spec is at
> https://api.relayshield.net/openapi.json and is explicitly allowed in our
> robots.txt.
>
> One operational note so it is on the record before launch rather than after.
> The unauthenticated endpoints are rate-limited per source IP, which is there
> to stop them being used as an open proxy. Platform traffic arrives from a
> small set of egress addresses, so we issue integration partners an API key
> sent as X-RS-API-KEY, which lifts that limit. It does not make the endpoints
> paid and it does not change what they return. Tell us where to send it.
>
> One thing the connector will never do: answer "safe". The ceiling on a clean
> result is "nothing known against it", because an absence of evidence is not
> evidence of absence and a security tool that says "safe" is wrong the first
> time it matters.

**That last paragraph earns its place rather than being a flourish.** It is a
property two of our own test suites enforce, it is the thing that distinguishes
this from a blocklist lookup, and a reviewer who reads it knows what the
connector returns before they test it.

---

## WHY NOT EMAIL CHECKING, AND WHAT ELSE IS ACTUALLY AVAILABLE

Asked 2026-09-22: *"Why not also add email checking to the connector. Are there any other
consumer-friendly APIs we can add? We get one chance to impress and link and wallet checking
dont seem compelling enough."*

**The critique is right and the free set is thin for a general consumer.** Read from
`KEYLESS_SCAN_ENDPOINTS` in `relayshield_api.py` rather than recalled: there are **fourteen**
keyless endpoints, not two, and **twelve of them are crypto** --
`/v1/token-security`, `/v1/nft-security`, `/v1/dapp-security`, `/v1/approval-security`,
`/v1/nft-floor`, three Solana, `/v1/ton-address`, `/v1/xrp-address`, `/v1/scan-wallet`,
`/v1/wallet-inbound`. For somebody with Gmail, a calendar and a music subscription those are
as narrow as the two the scope picked. **Only `/v1/link-check` is universal.**

### THERE IS NO EMAIL-CHECK ENDPOINT TO ADD

`checkemail@relayshield.net` is a **Cloudflare Worker, not an API route.** The verdict scoring
that makes it good -- brand impersonation, sender mismatch, the weighting model, the 78 verdict
tests -- lives in `cloudflare_worker_checkemail.js` as JavaScript. The only API calls it makes
are `/v1/scan-url` and `/v1/result`, and **`/v1/scan-url` is not keyless**: it is VirusTotal, a
real per-call bill, already $0.05 on the PAYG rail.

So "add email checking" is a BUILD -- moving a scoring model out of a Worker into an endpoint --
and not a field on a form.

### AND `/v1/breach` IS THE ONE THAT WOULD ACTUALLY HURT

It is the most consumer-compelling check we own: *has my email been in a breach*. It is also the
one addition that would damage a live product, and the reason is not cost.

    handle_breach -> haveibeenpwned.com/api/v3/breachedaccount/
    ONE subscription key, from _hibp_api_key()
    NO CACHE ANYWHERE in the function
    429 is handled explicitly: "HIBP rate limit reached"

**The $0.10 on our rate card is our RESALE price, not our cost.** HIBP bills a subscription with
a rate limit, so the constraint is requests per minute against one key -- and that key is shared
by the Telegram bot, the WhatsApp bot, the OAuth watchlist and every paying API customer.

**A consumer platform pointed at it does not run up a bill, it runs us into the rate limit, and
the 429 lands on the paying customers too.** That is a worse failure than the connector simply
not offering the feature, and it is invisible until it happens.

### THE RECOMMENDATION: DO NOT ADD AN ENDPOINT. CHANGE WHAT THE CONNECTOR IS FOR.

**`/v1/link-check` is not compelling as "check a link". It is compelling as "check every link in
my inbox", and Muse reads the inbox.** That is the same endpoint, the same zero vendor cost, and
a question a general consumer actually has. The example prompts and the description lead with the
message a link arrived in rather than with the link, because the agent has the message.

Nothing is built for this and nothing needs to be: an agent that walks a user's mail and calls
`/v1/link-check` per link costs us nothing at any volume, once the partner key lifts the per-IP
cap.

**Breach is the right v2 and it needs two things first, neither of which is a connector change:**

1. **A cache on `handle_breach`.** A breach result for an address is stable for days -- HIBP's
   data changes when a new breach is loaded, not per-minute -- and there is no cache at all
   today. Worth doing whatever happens with Muse: it also speeds up the bot.
2. **A separate HIBP key or an explicit rate budget for partner traffic**, so a consumer
   platform cannot starve paying customers through the shared key.

Roughly a day for both. **Until they exist, adding breach to this connector is a decision to
degrade the breach check for every existing customer**, and that is not a trade the connector is
worth.

### PAYMENTS: NO

Asked directly. **Do not select "My connector accepts payments".**

Both endpoints are free and keyless, nothing is sold inside the host, and there is no checkout,
subscription or upgrade path reachable from the connector. Selecting it claims a billing surface
that does not exist, which invites a review of something we cannot show them.

It is also the FD-14 shape pointed at a different host: selling digital goods inside a platform
is what gets an integration restricted, and the whole reason this connector is two free endpoints
is to have nothing there to review.

### THE ICON PATH, EXACTLY

    assets/miniapp/relayshield_icon_512.png

**There is no `rs_icon`.** That directory holds six images and five of them are `idcheck_*`,
which is the Mini App's brand mark and the wrong one here. Measured: PNG, 512x512, 8-bit RGB, no
alpha, non-interlaced, 68 KB. It is tracked in git and on `origin/main`, so the merge puts a
byte-identical copy on the Mac -- upload THAT file, never a copy that has been through chat,
which arrives re-encoded as `.webp` and cannot be selected in an upload dialog.

---

## Before the form

1. **Merge**, so `?source=muse` is deployed. An unregistered key renders no
   banner and logs `unmatched:`, which is attribution that looks like it worked.
2. **Take the baseline**, and take it BEFORE the listing is live, never after:

       AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --snapshot before-muse

   It refuses to overwrite, which is the most important line in that tool: a
   late baseline is a comparison of a number with itself.
3. **Search their directory for RelayShield first.** tg.app keys one listing per
   bot username and rejected our second submission for it. A connector platform
   may key on the company, and finding that out from a rejection costs a round.

## Not done, and named so it is not discovered at launch

**The partner key is not issued.** It is one existing operation, it is not a
build, and it must be done before the connector is live rather than before it is
submitted. Until it is, the connector is capped at 300 calls per day across all
of Meta's egress addresses combined, which a consumer platform exhausts in its
first busy hour.
