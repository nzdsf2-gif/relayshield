# Leaked Telegram bot tokens as a RelayShield finding — scoped

**Asked 2026-09-12: *"Add the ToDo to add leaked bot token from our corpus as a finding to alert bot
owners. We ought to be able to find these credentials. If/when we do, would this add more value to
our miniApp as a discovery surface for the Tg bot? Scope it."***

**And the correction that prompted it, which is his and is fair:** I was asked to look at
`soxoj/telegram-bot-dumper` and declined on the strength of its name. It is a pentest tool — its own
stated use case is *"pentesting a leaked bot token"*, loading a token to show the owner the real
blast radius of every conversation their internal bot has had. Reading it is what produced the one
hard constraint in section 3 below, so the review was not a formality.

---

## 1. THE HONEST STARTING POINT: WE HAVE NEVER LOOKED

**There is no Telegram bot token pattern anywhere in this codebase.** Checked, not recalled:

    NHI_PATTERNS   relayshield_api.py           source of truth, ~30 shapes   no telegram
    _NHI_PATS      relayshield_intel_monitor.py collection side              no telegram
    patterns.py    rsscan/rsscan/               generated from the first     no telegram

AWS, GitHub, Stripe, Slack, OpenAI, Anthropic, OpenRouter, Groq, xAI, Bedrock, HuggingFace,
SendGrid, Twilio, JWTs — and not the credential format of the platform two of our three consumer
products live on.

**So the corpus count today is not zero. It is UNMEASURED**, and those are different findings with
different fixes. This is the `sk-or-v1-` lesson exactly: OpenRouter keys were dropped silently for
months because the generic catch-all could not match them, and nobody could see it because nothing
was looking. A zero from a measurement tool gets acted on, and a zero from a tool that was never
pointed at the thing is not a measurement at all.

**Nothing in this scope may be reported as a corpus number until the pattern has shipped and
collected.** MEASUREMENT DOCTRINE, and the 100-indicator floor applies here as it does everywhere.

---

## 2. WHY THIS ONE IS DIFFERENT FROM EVERY OTHER ROW IN THAT TABLE

Every other credential we detect has the same weakness: we can prove a string *looks like* a key and
we cannot tell whose it is or whether it still works. An `AKIA...` in a log dump is a lead. We
cannot ask AWS whose it is.

**A Telegram bot token is self-identifying and self-validating with a single unauthenticated call.**
`getMe` returns the bot's `username` and display name. That turns a string in a criminal channel
into two things nothing else in the table gives us:

* **Liveness.** A token that answers is a working credential somebody can use right now; a token
  that 401s is a historical artefact. That is the severity discriminator, and it is the
  402-at-the-wrong-price rule again — when two things produce the same shape, check the field that
  differs.
* **Attribution.** `@AcmeSupportBot` names a project, usually a company, usually a domain. Every
  other NHI finding needs the victim to already be a customer before we can tell them.

**And the blast radius is unusually bad, which is what makes it worth telling people about.** A bot
token is not scoped. Whoever holds it can read every message sent to that bot, impersonate it to
every user who trusts it, and — for the very common case of an internal ops or alerting bot — sit
inside a company's own operational chat. It is closer to a session token than an API key, which is
the distinction the 2026-08-30 Claude-session post was built on: **the remediation is `/revoke` in
BotFather, and rotating anything else does nothing.**

---

## 3. THE HARD LINE, AND IT IS THE WHOLE ETHICAL BOUNDARY

**`getMe`, once, per distinct token. NEVER `getUpdates`. NEVER `setWebhook` or `deleteWebhook`.**

`getUpdates` is what `telegram-bot-dumper` uses and it is correct for that tool, because that tool
runs **with the owner's authorization**. We have none, and the call is destructive twice over:

* It **acknowledges and drains the pending update queue**, so the owner permanently loses messages
  they had not processed. A read that deletes the victim's data is not a read.
* It **returns the content of other people's conversations** with that bot. Reading a stranger's
  support chats to tell them their token leaked is not a defensible trade at any ratio.

`getMe` is the minimum necessary to know whom to notify, and it is the standard practice for
credential-leak notification. The boundary is not a preference and it gets a test, not a comment:
**no RelayShield module may name `getUpdates`, `setWebhook` or `deleteWebhook` against a token that
is not ours.**

**And we never store the token.** `sha256(token)` plus the username from `getMe` plus `first_seen`,
in the shape `relayshield_stolen_sessions` already uses. A table holding live bot tokens is a
breach with our name on it, and the hash is sufficient for every question we want to answer.

---

## 4. THE PATTERN, AND THE ONE THING THAT WILL GO WRONG

The shape is `<bot_id>:<35 chars>` — digits, a colon, then base64url:

    [0-9]{8,10}:[A-Za-z0-9_-]{35}

**Bare, that will produce false positives**, because `digits:opaque-string` is a common shape. The
repo already has the answer: `_ctx(...)` context-anchoring, used for the DeepSeek, Moonshot, Qwen
and legacy-OpenAI patterns, which requires a nearby `telegram`, `bot_token`, `TELEGRAM_BOT_TOKEN` or
`api.telegram.org`.

**Anchor on the context, keep the body permissive.** That is written on the OpenRouter and Venice
entries in the same table, in those words, because a too-tight length is exactly how OpenRouter keys
were missed. A `getMe` call settles any remaining doubt for free, which no other pattern in the
table can say.

**It touches four files that must agree**, which is this repo's most-repeated defect shape:

1. `NHI_PATTERNS` in `relayshield_api.py` — the source of truth.
2. `python3 tools/sync_patterns.py` — regenerates `rsscan/rsscan/patterns.py`. Never hand-edit it.
3. `_NHI_PATS` in `relayshield_intel_monitor.py` — the collection side. **This is the one that
   decides whether the corpus ever contains any**, and it is the copy that drifts.
4. `_LLM_KEY_PATTERNS` in `relayshield_telegram_webhook.py` — customer-facing, and the copy that has
   drifted before without anything noticing.

---

## 5. DOES IT MAKE THE MINI APP A BETTER DISCOVERY SURFACE?

**Yes, and it is the best answer to that question anyone has proposed — but not yet, and the reason
matters more than the answer.**

**Why the fit is genuinely good.** The Mini App's problem is that its audience is consumers pasting
addresses, and consumers are not who buys from us. **Telegram bot developers are the one audience
that is both inside Telegram already and commercially interesting**, and a leaked-token check is a
question only they have. It needs the criminal-channel corpus, so it is not replicable by anyone
scraping GitHub — which is the same "signal 4" argument that justified agent-bait-scan.

**The shape that works, and the shape that does not.**

* **NEVER accept a token in a form.** Asking a developer to paste a live credential into a web page
  is the thing we tell everyone else not to do, and being the ones who ask for it is unrecoverable.
* **Look up by USERNAME.** We already learn the username from `getMe` when we find a token, so the
  corpus can be indexed by `@username` and the user pastes nothing secret. `@mybot` → *"not in our
  corpus"* or *"seen in a monitored channel on <date> — revoke it in BotFather now."*

**Why not yet: the gate is a non-zero count, not a date.** A tab that answers *"nothing known"* to
every single visitor is not a feature, it is the OpenRouter revocation webhook's mistake — building
against zero rows. Ship the detector, let it collect, and build the surface when the category has
something in it. The same gate, for the same reason, as ABS-1's false-positive rate.

**And there is a free first home that is not the Mini App at all: `rsscan`.** It reads
`git diff --cached` on a developer's own machine, so the same pattern catches a bot token **before**
it is committed, which is worth more to that developer than finding out afterwards that it leaked.
That costs one line in the source of truth plus `sync_patterns.py`, it ships today, and it needs no
corpus at all.

---

## 6. THE PLAN, IN THREE PHASES THAT EACH STAND ALONE

**Phase 0 — detect it. Half a day. Do this one now.**
The pattern into all four tables, `getMe` liveness not yet involved. Ships the finding to rsscan
(pre-leak), to the API's NHI scan, and to the collection monitor so the corpus starts accumulating.
After this, the question "how many are there" becomes answerable instead of unmeasured.

**Phase 1 — verify and attribute. One day. Gated on nothing.**
`getMe` once per distinct token, hash-only storage, username indexing, severity split on liveness
(`CRITICAL` live / `MEDIUM` dead, the same split the Anthropic OAuth-versus-key rows use because the
remediation differs). The `getUpdates` prohibition as a test. Remediation text that says **revoke in
BotFather**, never "rotate".

**Phase 2 — the surface. Two days. GATED ON A NON-ZERO COUNT.**
A username lookup, in the Mini App and as a bot command, plus notification for the cases where the
username resolves to a domain we can already reach through the existing breach path. Do not scope
this further until Phase 0 has produced a number.

**What I would not do:** build a notification pipeline for strangers. Cold-contacting the owner of
`@SomeBot` is the same unsolved outreach problem every other NHI finding has, and it is not made
easier by the credential being a bot token. The leverage is the self-serve lookup, where the person
who needs the answer comes to us.

---

# PHASE 1 AND 2, SCOPED 2026-09-13 AFTER PHASE 0 SHIPPED

Founder: *"Lets scope and build the capability to add and monitor developer bot tokens found in RS TI
corpus to our Watch feature in miniApp. Bot devs will need to opt-in via a new prompt where they pay
stars to watch for their bot tokens. Do we need to build new regex table and monitor function to
detect this type of tokens with greater precision? How should we tighten our monetization flywheel
with these users who we want to steer to using our API landing site?"*

## 1. THE REGEX: BUILT, AND IT IS NOT A NEW TABLE

**Phase 0 shipped in this session.** Two entries, in all four tables that must agree:
`NHI_PATTERNS` in `relayshield_api.py` (source of truth), the generated `rsscan/rsscan/patterns.py`,
`_NHI_PATS` in `relayshield_intel_monitor.py` (the copy that decides whether the corpus ever contains
any), and pinned by `test_bot_token_pattern.py`.

**A FIFTH TABLE IS THE ANSWER TO AVOID, NOT THE ANSWER.** This repo already carries four copies of
one pattern set and has been bitten by the disagreement repeatedly. Precision comes from the anchor,
not from a separate home.

**Precision, and how it was actually obtained:**

* **Context-anchored.** `<8-10 digits>:<35 base64url>` bare would fire on DSNs, ports, ids and
  timestamps, and a noisy CRITICAL is how a detector gets ignored. `_ctx_key` requires `telegram`,
  `bot_token`, `TELEGRAM_BOT_TOKEN` or `api.telegram.org` nearby.
* **A SECOND ENTRY FOR THE URL FORM, and it exists only because the first was RUN.**
  `_ctx_key` needs an assignment operator, so `https://api.telegram.org/bot<TOKEN>/sendMessage` --
  a curl line, a log, a paste, a stack trace, and the commonest real leak -- matched nothing.
  Reading the pattern would never have shown that.
* **Permissive body.** Written on the OpenRouter row already: a too-tight length is how `sk-or-v1-`
  keys were dropped in silence for months.

**And the precision nothing else in that table can reach: `getMe`.** One unauthenticated call says
whether the token is LIVE and returns the owner's bot username. No other credential we detect can be
confirmed or attributed without a vendor relationship. That is the real precision layer, and it is
Phase 1.

## 2. THE MONITOR: NO NEW FUNCTION. A NEW `kind` IN THE ONE THAT EXISTS.

`relayshield_watchlist.py` and `relayshield_watchlist_monitor.py` already carry everything the hard
half needs and none of it is Telegram-chain-specific:

    verified initData HMAC          the non-spoofable per-user identity
    user_key = HMAC(pepper, uid)    the unreversible partition key
    KMS-encrypted target + chat_id  reversible on purpose, so an alert can be sent
    slots, Stars, grant_slots       the entitlement, idempotent on charge id
    first-run-never-alerts          the rule that stops one run messaging everyone
    "could not check" != "it is gone"

**So the work is a `kind` of row, not a second monitor.** A TON row re-checks against TON Center and
DexScreener; a `bot_token` row re-checks against the corpus and `getMe`. Same table, same alert
path, same slot accounting, same expiry.

**THE THREE RULES CARRY OVER UNCHANGED AND ONE GETS SHARPER.** "We could not check" must never render
as "it is gone" applies with more force here: a `getMe` timeout must never be reported as "your token
is live in a criminal channel". Every unreadable answer stays `None` and the stored snapshot is left
untouched.

**What the row stores, and it is the whole privacy design:** `sha256(token)` and nothing else. The
user proves ownership by pasting their bot's **username**, never the token -- see §5 below, which is
the part most likely to be got wrong by a future session in a hurry.

## 3. THE OPT-IN PROMPT, AND WHY IT IS A DIFFERENT SALE

The Watching tab sells slots to a consumer watching an address their money is in. A bot developer is
a different buyer with a different question, and the same 50-Stars-for-25-slots offer is the wrong
shape for them: they have one bot, or three, not twenty-five.

**Recommended: bot-token watching is a SLOT LIKE ANY OTHER, and the free tier covers it.** Three free
slots already exist. A developer with one bot spends one slot and pays nothing, which is correct --
they are the audience we most want to reach and the marginal cost of one corpus query is near zero.
Stars are still the upgrade for somebody running many bots, and the existing tier line already says
so without a word changing.

**This is the standing principle applied rather than re-litigated: Stars pay vendor bills, they never
tax the free tier.** A bot developer who finds out from us that their token is in a criminal channel
must never have been charged to learn it. That is the paywall-on-the-alert defect wearing a new hat,
and it is the one shape this design exists to refuse.

## 4. THE FLYWHEEL, WHICH IS THE QUESTION WORTH THE MOST

**A bot developer is the only Mini App visitor who is already a buyer of the API.** Consumers pasting
TON addresses are not; developers shipping Telegram bots are exactly the `/v1/link-check` and
`/v1/wallet-risk` audience the widget was built for, and they arrive holding a concrete security
problem we just named for them.

**So the route is: free finding in the Mini App, then the thing they cannot get there.**

1. **The finding is free and complete.** No teaser, no "upgrade to see the channel". A partial
   security finding is worse than none.
2. **The remediation names BotFather**, never "rotate". Getting that right is the credibility.
3. **The next step is the API, and it is offered as CAPABILITY rather than as more of the same**:
   the Mini App watches the bots they paste; `/v1/link-check` and `/v1/wallet-risk` are what their
   bot calls to protect its own users. Different product, adjacent need, and it is the one they can
   put in their own code.
4. **`?source=tg-miniapp-bottoken`, REGISTERED FIRST.** In `miniapp_routes.json`, `ALLOWED_SOURCES`
   and `_SOURCE_ALIASES` -- three lists that must agree, and a gap in either mirror produces
   attribution that looks like it worked. FD-8 was four months of exactly that.
5. **The widget is the conversion**, not the signup. A developer who copies
   `widget/relayshield-widget.js` into their bot has integrated us, and every call it makes carries
   `source=tg-widget` forever.

**The measurement decides whether any of this is real, and it already exists:**
`tools/miniapp_funnel.py` has a DEVELOPERS stage counting arrivals on the API landing page carrying
a Mini App key. That is the number that says whether the flywheel turned.

## 5. THE FOUR RULES A FUTURE SESSION MUST NOT RELAX

1. **NEVER ACCEPT A TOKEN IN A FORM.** Look up by `@username`. We learn the username from `getMe`
   when we find a token, so the corpus is indexed by username and the user pastes nothing secret.
   Asking a developer to paste a live credential into a web page is the thing we tell everyone else
   not to do.
2. **`getMe` ONLY. NEVER `getUpdates`, `setWebhook` or `deleteWebhook`.** `getUpdates` drains the
   owner's pending update queue and returns other people's conversations.
3. **STORE `sha256(token)`, NEVER THE TOKEN.** A table of live bot tokens is a breach with our name
   on it.
4. **PHASE 2 IS GATED ON A NON-ZERO COUNT, NOT A DATE.** A tab answering "nothing known" to every
   visitor is the OpenRouter-webhook mistake of building against zero rows. Phase 0 shipped today;
   the corpus starts accumulating now, and `tools/miniapp_funnel.py` plus a corpus count decide when
   Phase 2 is worth building.
