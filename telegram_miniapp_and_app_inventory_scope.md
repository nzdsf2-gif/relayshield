# Telegram Mini App + automated bot/Mini App inventory: scope

*2026-08-27. Reviews the external study, then scopes the two builds it points at.*

---

# Part 1: the study, reviewed

## What it gets right, and it is the important part

**The reframe is correct.** "Outreach → permission → integration" is a bottleneck we cannot staff.
"Discoverable utility → self-service integration → inbound demand" is the right shape, and the
three-level ladder (affiliate link → one-line widget → full API) is the right on-ramp because each
rung is cheaper for the partner than the one above it.

**Separating end users from developers is right.** They are different acquisition problems and
trying to solve both through community outreach is what created the silence.

**"Don't cold-message bots" is right**, and for a stronger reason than the study gives. See the
session risk below: it is not just ineffective, it is dangerous to an asset we depend on.

## What it gets wrong or understates

### 1. The Telethon session is a production asset, and the study would burn it

This is the finding that changes the plan, and it comes from our own code rather than the study.

`relayshield_intel_discovery.py` and `relayshield_intel_monitor.py` share **one Telegram session**,
and the monitor's own comments record how tight the limits already are: `ResolveUsernameRequest` has
a per-session flood limit that "a 122-channel resolve burst trips almost immediately", which is why
resolved peers are cached as `InputPeerChannel` to avoid re-resolving. `regenerate_telethon_session.py`
exists because that session has had to be rebuilt before.

The study proposes building an inventory of **10,000 to 50,000** Telegram apps and bots. Running
that through the same session would flood-wait or ban the account that **99 channels of intel
collection depend on**. That is not a hypothetical: it is the same call, at 100x the volume.

**Requirement, non-negotiable: prospecting discovery runs on a SEPARATE Telegram account and
session, with its own secret, its own rate budget, and no shared code path with the intel monitor.**
If the prospecting session gets limited, collection must be unaffected.

### 2. "We found a security exposure in your Telegram app" is the wrong hook as written

The study proposes generating a report saying an app has "no URL reputation layer", "no wallet risk
detection", and calling those "security opportunities detected".

Two problems:

- **It is inferred, not measured.** We would be looking at public metadata and concluding what a bot
  does not do internally. We cannot see their backend. Claiming a security gap we have not verified
  is exactly what our own measurement doctrine forbids, and it is worse here because it is an
  assertion about someone else's product.
- **It reads as a threat.** An unsolicited "we analysed your app and found exposures" from an unknown
  vendor is one word away from the shape of an extortion email, and a security company sending it
  has more to lose than most.

**Reframe that keeps the value and drops the risk:** do not claim what they lack. Show what they
could add, using their own public description. "Your bot accepts user-submitted links. Here is a
one-line call that screens them, and a free key to try it." That is a capability offer, not a
verdict on their security, and it needs no claim we cannot support.

### 3. The Mini App is being asked to do three jobs

The study is right that the Mini App can sit above consumer security, Crypto Shield and the API
business. But that is a positioning statement, not a v1 scope. **A Mini App that tries to be a
consumer product, a developer portal and a partner centre at once will be bad at all three.** The
developer surface belongs on the website (which already serves `/developers`), and the Mini App
should do one consumer thing well.

### 4. Crypto Shield Mobile inside a Telegram Mini App — RESOLVED 2026-08-29

I had this framed as one blocking question. It is two, and separating them removes the block.

**What is actually restricted is promotion of a competing multi-chain wallet or storefront.** The
CS Mobile app cannot be pointed to, linked, or sold from inside the Mini App, and that is settled:
no CS Mobile tie-in, no exceptions, no "just a link".

**Crypto security analysis is not that.** A wallet or token scan that returns a risk verdict is a
security tool, not a wallet and not a store, and TON is Telegram's own chain. So v1 ships:

- **Free TON wallet and token scans**, as the freemium hook. Address in, counterparty and token risk
  out. This is the single most native thing we can offer inside Telegram.
- **Wallet counterparty scans for other chains** as a paid or signed-in step. The scan is a verdict
  on an address, not a wallet product, and it never routes a transaction.
- **Links to the RelayShield Telegram bot, the Telegram blog channel, and the API developer page.**
  All three are our own Telegram-native or web surfaces, all three are attributed.

**What stays out:** any CS Mobile reference, any in-app swap, transfer or bridge, and any payment
rail that competes with Stars inside the Mini App itself. Payments for the paid scan tier go through
the existing web checkout, opened outside the Mini App.

That leaves the Mini App with a real front door to everything except CS Mobile, which is what was
wanted, and it removes the dependency on a policy reading I could not verify from this container.

---

# Part 2: Item 16, the automated inventory

## The good news: most of the engine exists

`relayshield_intel_discovery.py` already does, for criminal channels, nearly everything the study
asks for:

- `SearchGlobalRequest` per keyword, `MAX_PER_KEYWORD = 50`
- resolves each result, verifies accessibility, reads member counts
- classifies by keyword-to-category mapping
- writes to DynamoDB with provenance (`discovery_method`, `found_via`)
- cross-promotion crawl from seed categories
- writes new finds as `pending_review` rather than trusting them

**The Item 16 build is that engine pointed at a different target, not a new engine.** That is a
fundamentally cheaper project than the study implies.

## What is genuinely new

1. **A second Telegram account and session** (see above). Highest priority, and everything else is
   blocked on it.
2. **Bot and Mini App resolution rather than channel resolution.** A bot's `@name` resolves to a
   `User` with `bot_info`, not a `Channel`. Different entity type, different fields, and the Mini App
   URL lives in the bot's menu button or `web_app` attachment rather than in a description.
3. **A capability classifier.** The scoring in the study needs a signal, and the only honest one is
   the bot's own public description and command list: a bot whose `/help` mentions wallets, links,
   or file uploads is describing its own surface. Classify from what they say they do, never from
   what we guess they lack.
4. **Contact enrichment off Telegram.** The study is right that GitHub, a website or an email beats a
   Telegram DM. This is a separate enrichment pass and it is where the prospecting value actually is.

## Data model

    relayshield_tg_apps
      PK   handle (S)           @examplebot, lowercase
      SK   kind (S)             "bot" | "miniapp"
      title, description (S)
      miniapp_url (S)           when present
      members (N)               when readable
      commands (SS)             from bot_info, their own words
      capability_tags (SS)      links | wallets | payments | files | identity | ugc
      contact_github / contact_site / contact_email (S)
      opportunity_score (N)
      discovered_at, last_checked (S)
      status (S)                new | scored | contacted | replied | integrated | rejected

## Scoring, stated as a formula rather than a vibe

    score = capability_fit (0-50)      how many of our checks map to what they SAY they do
          + reach (0-20)               members, log-scaled, capped so a huge off-theme bot cannot win
          + contactability (0-20)      a non-Telegram channel we can actually reach
          + freshness (0-10)           active in the last 90 days

Anything under a threshold is never contacted. The point of the score is to make the top 1%
findable, not to rank the whole universe.

## Source ranking, honestly

| Source | Volume | Automatable | Gives contact | Risk |
|---|---|---|---|---|
| Telethon `SearchGlobalRequest` | high | yes, engine exists | rarely | session limits |
| Third-party Mini App directories (tApps Center and similar) | medium | scraping, ToS-dependent | sometimes | ToS, brittleness |
| GitHub search for `python-telegram-bot`, `grammy`, `aiogram` | medium | yes, good API | **yes, best** | none |
| Telegram channels that announce new bots | low-medium | yes, reuses collection | rarely | none |

**GitHub is the underrated one.** Open-source Telegram bots come with a repository, an author, an
issue tracker and often a website. It is the only source in the table that reliably yields a
developer we can reach on a professional channel, and it needs no Telegram session at all.
**Start there**, not with a 50,000-app scrape.

## Effort

| Piece | Estimate |
|---|---|
| Second Telegram account, session, secret, isolation from the intel session | 0.5 day |
| Fork discovery for bots/Mini Apps, new entity handling | 1.5 days |
| GitHub source and contact enrichment | 1 day |
| Capability classifier from public description and commands | 1 day |
| Scoring and the shortlist report | 0.5 day |
| **Total** | **4.5 days** |

---

# Part 3: the Mini App

## What v1 should be

**One consumer thing, done well: paste a link, or forward a message, and get a verdict.** That is
`/scan` and the fraud analyser, which already exist and are already the most-used commands. The Mini
App is a better interface to a capability we have, not a new capability.

## Requirements

- **Entry from the existing bot.** The bot has users today; the Mini App should be a menu button on
  it, not a separate thing needing its own audience.
- **Anonymous first use.** No account for the first N scans. Signup only when a result is worth
  keeping.
- **One paid step, clearly justified.** Continuous monitoring is the upgrade, one-off scans are free.
- **Attribution on every outbound link**, `?source=tg-miniapp` and per-surface variants, registered
  in `_SOURCE_BANNERS` **before** the app ships. The unregistered-key failure has bitten this project
  three times.
- **No developer portal inside it.** A single "Build with RelayShield" link out to
  `api.relayshield.net/developers?source=tg-miniapp-dev` is the whole developer surface in v1.

## What v1 must not be

- Not a CS Mobile storefront, and not a CS Mobile link. Settled 2026-08-29, see §4. TON and
  multi-chain wallet risk **scans** are in scope; the CS Mobile app is not, in any form.
- Not a partner centre. That is a website page, and the study agrees. **Built and settled
  2026-08-29:** `partners.relayshield.net` publishes **20% recurring for 12 months** on the six
  monitored subscription plans, with a 60-day clawback and no self-referrals. The Mini App may link
  to it; it must not reimplement it. Attribution is `client_reference_id=p_<code>` through the
  Stripe payment links, so any partner link the Mini App ever surfaces has to carry that exact form
  — a bare code in that field routes the customer into the Telegram onboarding flow and drops them.
- Not gated behind Telegram Stars until we know how Stars revenue interacts with our existing Stripe
  and x402 paths. Two payment rails in one product is a support problem before it is a revenue one.

## Effort, honestly

A Mini App is a web app in a webview with Telegram's SDK for identity and theme. The frontend is
small; the work is in the plumbing we already have. **5 to 8 days for v1** as scoped, assuming it
reuses the existing scan endpoints and adds no new backend capability.

---

# Recommended sequence, and the one thing to do first

1. **One blocking question left, not two.** (a) is answered — see §4: CS Mobile is out permanently,
   TON and multi-chain wallet **scans** are in, and the Mini App is the front door to everything
   else. (b) still stands: set up the second Telegram account on a dedicated prepaid SIM, because
   everything in Item 16 is blocked on it and it costs half a day.
2. **Build the GitHub half of Item 16 first.** No Telegram session, best contact data, immediate
   output. If the first 200 scored prospects produce nothing, that is a cheap and early answer about
   the whole thesis, and it arrives before the Mini App is built.
3. **Then the Telegram half of Item 16**, on the separate session.
4. **Then the Mini App**, scoped to one consumer job.

The study's instinct to build discovery in parallel with the Mini App is right. The correction is
which half of discovery to build first: **GitHub, not Telegram**, because it is cheaper, safer, and
answers the same question sooner.

## Measurement, so this does not become another silent channel

Track per prospect: source, score, channel used, reply, integration. The number that decides whether
Item 16 works is **replies per 100 contacted, by source**. If GitHub-sourced prospects reply and
Telegram-sourced ones do not, build more of the first and stop the second. That is knowable in weeks
with a few hundred prospects, and it is the same discipline the outreach tracking in
`xcitium_outreach.md` uses.
