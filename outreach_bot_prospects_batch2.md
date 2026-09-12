# Batch 2 outreach drafts, prospects 13 to 27

Written 2026-09-12. Batch 1 (prospects 1 to 12) is in `outreach_bot_prospects_curated.md`, which
also carries the Tier A/B/C selection and the reasoning for every rejection. **This file is the
copy for the rest of that list.** It does not re-litigate who is on it.

## The rules from batch 1 apply unchanged, and two of them decide most of this file

**Never assert anything about their security.** Every draft is an offer of a capability keyed to
what their own README says the bot does. We can read a README; we cannot see anyone's backend, and
"we analysed your app and found exposures" from an unknown security vendor is one word away from an
extortion email. **Every draft below is checkable against the repo's own front page and says
nothing else.**

**Send a few a day, by hand.** Fifteen near-identical messages in an afternoon is how a sending
domain gets blocked, and we have one.

## THE HONEST CONSTRAINT ON THIS FILE, stated before the drafts

**No contact address in here is resolved.** `prospects_wide.jsonl` and any batch-2 resolution
output live on the Mac, not in this repo, so the container cannot see who is reachable. Every draft
therefore names its channel as a QUESTION rather than a fact, and the resolution step from batch 1
still gates the whole batch:

    export GITHUB_TOKEN=$(gh auth token)
    python3 tools/resolve_prospect_emails.py --in prospects_batch2.txt --out prospects_batch2.jsonl

It rejects `users.noreply.github.com`, because that address is not deliverable and counting it is
how a list looks reachable and is not. **Mail only the resolved rows.** The number to track is
candidates that became a sent message, which was under 50% for batch 1.

---

# Tier A: holds or moves other people's money

## 13. glazybyte/Crypto-Escrow-Telegram-Bot (15 stars)

Their README: an escrow bot that holds crypto in its own wallet and releases on both parties'
approval.

Subject: Screening the release address, before escrow releases to it

> Your bot holds funds until both sides approve, then releases to the address the deal names. That
> release is the one irreversible step in the whole flow.
>
> RelayShield answers one question about that address: has it been seen in criminal Telegram
> channels, infostealer dumps or public indicator feeds. One call, no key, no signup:
>
>     curl -s https://api.relayshield.net/v1/wallet-risk \
>       -H 'content-type: application/json' \
>       -d '{"address":"<the release address>","source":"tg-widget"}'
>
> It never returns "safe". The best answer it gives is "nothing known against it", because an
> absence of evidence is not proof, and an escrow bot telling a user an address is safe would be
> worse than saying nothing.
>
> There is a copy-in file for Telegram bots if that is easier than calling the API:
> https://api.relayshield.net/developers?source=tg-widget

## 14. Libermall/Telegram-Cryptocurrency-Wallet-Libermall (14 stars)

Their README: a TON wallet with cheques, fiat invoices, staking and a DEX gateway, and it says
outright that the repo is in security-maintenance only.

**So the pitch is NOT this repo.** Say so in the first line, or the message reads as if we did not
read the page.

Subject: Not about the archived repo, about the live products it points at

> Your repo says it is maintained for security only, so this is not about the code. It is about the
> five money paths it describes: cheques, fiat invoices, staking, the DEX gateway and ordinary
> sends.
>
> Each of those ends at an address or a counterparty somebody chose. RelayShield screens that
> address against indicators collected from criminal Telegram channels, and `/v1/ton-address` is
> TON-specific rather than a generic EVM check. Keyless, no signup:
>
>     curl -s https://api.relayshield.net/v1/ton-address \
>       -H 'content-type: application/json' -d '{"address":"<TON address>"}'
>
> If the live products are elsewhere now, point me at them and I will look at the right thing.

## 15. TegroTON/Telegram-Cryptocurrency-Wallet-TON-Kotlin (29 stars)

**Same org as batch 1's prospect 6, `TegroTON/ai-telegram-pay-miniapp`. This is a follow-up, not a
cold approach, and it must not read as a second cold email to the same people.**

Subject: Following up, the Kotlin wallet rather than the pay Mini App

> I wrote about `ai-telegram-pay-miniapp` a little while ago. Same offer, pointed at the Kotlin
> wallet instead, since virtual cheques and in-bot payments both end at an address the sender did
> not choose.
>
> `/v1/ton-address` is keyless and TON-specific. If the pay Mini App was the wrong door, this one
> may be the right one, and if neither is I will stop.

## 16. bruhxax/Link-Bot (23 stars)

Their README: sells and manages VPN subscriptions, with payments and a Mini App.

Subject: A subscription bot takes a payment method from someone it has never met

> Recurring payments from strangers is a different risk from a one-off sale: a chargeback lands
> weeks later and the service has already been delivered.
>
> We do not screen cards. What we do screen is the other half nobody checks: the links your users
> arrive through and the addresses crypto payments come from. `/v1/link-check` is keyless and
> returns three signals immediately, with no VirusTotal poll to wait on: our indicator corpus,
> Google Safe Browsing, and how old the domain is.
>
>     curl -s https://api.relayshield.net/v1/link-check \
>       -H 'content-type: application/json' -d '{"url":"https://example.com"}'

## 17. JumpCodeFrog/telegram-shop-bot (10 stars)

Their README: a catalogue with Stars and USDT payments, subscriptions, a Mini App and an admin
panel.

Subject: A shop bot's risk is the buyer's address, not its own code

> You take USDT as well as Stars, which means an address arrives from someone you have never met,
> and the refund path for crypto is "there is none".
>
> One keyless call screens that address against indicators collected from criminal Telegram
> channels. It never says "safe"; the ceiling is "nothing known against it", which is the honest
> answer for most addresses and the useful one for the few it is not.
>
>     curl -s https://api.relayshield.net/v1/wallet-risk \
>       -H 'content-type: application/json' -d '{"address":"<buyer address>"}'

## 18. king-tri-ton/TelegramStarsBot (17 stars)

Their README: a reference implementation for taking Telegram Stars, which means it gets forked.

**The value here is the PATTERN, not this one bot. Say that plainly: it is why the message is worth
their time rather than ours.**

Subject: The example everyone forks is the best place for a check to live

> Yours is the Stars implementation people copy, so anything in it propagates in a way a single
> bot's code does not. That is the only reason I am writing about a reference repo rather than a
> product.
>
> The check is one keyless call and about five lines: screen a link or an address before the bot
> acts on it. There is a copy-in file rather than a dependency, deliberately, because a reference
> implementation should not hand its forks a new package to trust:
> https://api.relayshield.net/developers?source=tg-widget
>
> Not asking you to endorse anything. If it does not belong in an example, that is a fair answer.

## 19. slightbasebo/fragment-api-dev (134 stars)

Their README: a Stars and Premium API with GRAM and USDT payments, a Python SDK, and **no API key**.
The highest-star payments target on the list.

**Lead with the keyless symmetry. It is true of us and it is the thing they chose.**

Subject: Keyless is our shape too

> You ship an API with no key, which is unusual enough that it is the reason I am writing.
> `/v1/wallet-risk` and `/v1/link-check` need no key either, and are capped per IP rather than
> behind a signup, for the same reason: the first call should cost nothing.
>
> Your GRAM and USDT paths end at addresses your callers supply. We screen those against
> indicators collected from criminal Telegram channels, infostealer dumps and public feeds.
>
>     curl -s https://api.relayshield.net/v1/wallet-risk \
>       -H 'content-type: application/json' -d '{"address":"<address>"}'
>
> There is a Python SDK on our side as well if that fits your own better than raw HTTP.

## 20. exmanka/ksiVPN-telegram-bot (46 stars)

Their README: P2P payments plus YooKassa, promocodes and referrals.

Subject: P2P means the other side is unvetted by definition

> A card processor vets its own customers. P2P has nobody in that role, which is exactly why it is
> cheaper and exactly why the counterparty question has no owner in that flow.
>
> One keyless call screens the address a P2P payment comes from, against indicators collected from
> criminal Telegram channels. It returns a level and the reasons behind it, and it never returns
> "safe".
>
>     curl -s https://api.relayshield.net/v1/wallet-risk \
>       -H 'content-type: application/json' -d '{"address":"<payer address>"}'

## 21. Tonwed/gpt-upi (54 stars)

Their README: a UPI scanner and order hub with Telegram login, wallets and a worker dashboard.

**The only non-crypto payments target on the list. Our UPI coverage is not something we can claim,
so the message ASKS rather than asserts. That is the honest shape and it is also the more useful
message: the answer tells us whether this category is worth building for.**

Subject: A question rather than a pitch, about UPI

> You are the only UPI project on a list I built of Telegram payment bots, which makes you the one
> I know least about.
>
> What we screen today is links and crypto addresses: our indicator corpus from criminal Telegram
> channels, Safe Browsing, and domain age. **None of that is UPI-specific**, and I am not going to
> pretend otherwise.
>
> So the question is whether the link half is any use to you at all: your order hub presumably
> takes URLs from somewhere, and `/v1/link-check` is keyless. If the answer is no, that is genuinely
> useful for me to know, and I will not follow up.

---

# Tier B: agent-shaped, where the buyer is the agent

## 22. x402agent/SolanaOS (9 stars)

**The org is named `x402agent`. We run 28 live x402 endpoints priced $0.05 to $0.35, settling USDC
on Base. That is a protocol conversation, not a security pitch, and it should read like one.**

Subject: We settle on x402 too, 28 endpoints on Base

> Your org name is the protocol we bill in, so this is a compare-notes message rather than a pitch.
>
> We have 28 live x402 endpoints, exact EVM scheme on Base, $0.05 to $0.35 a call. The agent signs
> an EIP-3009 authorisation and the facilitator broadcasts it, so the wallet never needs gas, which
> took us a while to get right.
>
> What they answer is the counterparty question: given an MCP server, a URL or an address an agent
> is about to pay or connect to, is it known bad. There is a worked demo of an agent paying $0.35
> to screen two MCP servers and refusing one on a typosquat finding.
>
> If you are on Solana rather than Base for settlement I would like to hear how that went.

## 23. gokhantos/opencrow (23 stars)

Their README: a multi-agent platform across Telegram and WhatsApp, 90+ tools, MCP in its topics,
crypto and DeFi.

**This is the agent-bait audience exactly, and the pitch is the newest thing we have.**

Subject: 90 tools is 90 sets of instructions your agent will follow

> An agent that mounts ninety tools reads ninety sets of instructions, and any one of them can tell
> it to fetch a script, read a credential file, or ignore what you told it. That is a different
> problem from a malicious binary and almost nothing checks for it.
>
> `/v1/metered/agent-bait-scan` reads a repository's agent-facing files -- README, AGENTS.md,
> CLAUDE.md, .cursorrules, copilot-instructions, mcp.json, smithery.yaml -- and reports what those
> instructions would cause an agent to DO, including directives hidden in zero-width characters. It
> then checks every domain they reference against our criminal indicator corpus.
>
> That last part is the half nobody can replicate: the corpus is collected from criminal Telegram
> channels rather than bought.
>
> There is also an MCP server, so the check can be a tool your agents call rather than a service you
> integrate: https://api.relayshield.net/developers?source=tg-widget

## 24. fciaf420/moonbags (40 stars)

Their README: Solana auto-trading with an LLM exit advisor and Jupiter swaps.

Subject: An LLM deciding a swap is an agent paying a counterparty

> Your exit advisor decides when to sell. What nothing in that loop decides is whether the token on
> the other side of the swap is a known scam, and an LLM will happily route into one.
>
> We screen the counterparty rather than the trade. **Worth saying plainly: our TON coverage is
> deeper than our Solana coverage**, so the honest offer here is the link and domain check plus the
> indicator corpus, not a token-level Solana verdict.
>
> If a Solana token check is what would actually help, tell me and I will say whether we can build
> it rather than implying we already have.

## 25. uerax/all-in-one-bot (181 stars)

Their README: smart-money tracking and on-chain address analysis. 181 stars, the largest on the
list.

**They already do address analysis. So this is an integration conversation and a pitch would insult
the reader.**

Subject: You already do address analysis, so this is about a source rather than a feature

> You analyse addresses on chain. We do not, and we are not going to try to sell you that.
>
> What we have is a source you cannot get on chain: indicators collected from criminal Telegram
> marketplaces and infostealer dumps. An address that looks unremarkable on chain and appears in a
> channel selling drainer kits is a finding neither half produces alone.
>
> One keyless call, and the response carries the reasons rather than just a score:
>
>     curl -s https://api.relayshield.net/v1/wallet-risk \
>       -H 'content-type: application/json' -d '{"address":"<address>"}'
>
> If that is additive to what you already compute, there is a conversation. If not, no follow-up.

## 26. vooi-app/vooi-signals-bot-example (18 stars)

Their README: Telegram signals into an LLM parser into a trading API. An org account, so a support
address is likely to exist.

Subject: A signal is a stranger's instruction, parsed by an LLM

> Your pipeline takes a message somebody posted, has an LLM read it, and turns it into an API call.
> That is prompt injection with money attached, and it is the one risk in the design that is not a
> trading risk.
>
> Two things of ours touch it. `/v1/link-check` screens any URL a signal carries, keyless. And
> `agent-bait-scan` reads text for instructions aimed at the model rather than the human, including
> the zero-width kind, which is closer to what your parser actually eats.
>
> The example repo is the right place to ask: whatever the example does is what people copy.

---

# 27. punkpeye/awesome-remote-mcp-servers (47 stars): NOT OUTREACH

**Do not mail this. It is a LISTING, and mailing a curated index is how you get left off it.**

It is a curated list of remote MCP servers, which is exactly FD-15's artefact: one hosted URL,
already decided and already watched.

    https://relayshieldadmin-relayshield-agentic-attack-surface.hf.space/gradio_api/mcp/sse

**Read its CONTRIBUTING before opening anything.** That is the FD-2 lesson with the label already
read: a PR to a destination whose own page says how submissions work, submitted the wrong way, is
effort spent on a door that was open and now is not.

---

# Tier C stays on hold, with one exception

`skharchikov/polymarket-bot` · `IvanWng97/TradingAgents-Telegram` ·
`ozgen/binance-telegram-bot` · `sbauwow/schwagent` · `NadirAliOfficial/trading-scanner` ·
`Formyselfonly/invest-alert-bot` · `lukmanc405/neko-futures-trader` · `zargarkhan1/quorum-alpha-dash`

**No drafts written, deliberately.** A trading bot's user is not paying an unknown counterparty;
they are trading on an exchange they chose, so the wallet check has no natural moment and a message
that invents one is the "describing somebody else's company" failure. Writing eight drafts nobody
should send is worse than writing none.

**The exception is `zargarkhan1/quorum-alpha-dash` (119 stars)**, and the reason is audience rather
than fit. If Tiers A and B produce replies, the agent-bait angle from prospect 26 is the one to
adapt, because an LLM reading signals is the same shape whatever it trades.

---

# Tracking

Add these rows to the batch 1 table rather than starting a second one. The comparison that matters
is **batch 2's candidates-that-became-a-sent-message against batch 1's, which was under 50%** --
that is the number the resolution step exists to move, and replies are too sparse at this volume to
compare.

| # | Repo | Channel resolved? | Sent | Reply | Notes |
|---|---|---|---|---|---|
| 13 | glazybyte/Crypto-Escrow-Telegram-Bot | | | | |
| 14 | Libermall/Telegram-Cryptocurrency-Wallet-Libermall | | | | archived repo, ask for the live product |
| 15 | TegroTON/Telegram-Cryptocurrency-Wallet-TON-Kotlin | | | | FOLLOW-UP to prospect 6, same org |
| 16 | bruhxax/Link-Bot | | | | |
| 17 | JumpCodeFrog/telegram-shop-bot | | | | |
| 18 | king-tri-ton/TelegramStarsBot | | | | reference repo, pattern not product |
| 19 | slightbasebo/fragment-api-dev | | | | highest stars in Tier A |
| 20 | exmanka/ksiVPN-telegram-bot | | | | |
| 21 | Tonwed/gpt-upi | | | | ASKS about UPI, claims nothing |
| 22 | x402agent/SolanaOS | | | | protocol conversation, not a pitch |
| 23 | gokhantos/opencrow | | | | agent-bait, the strongest fit on the list |
| 24 | fciaf420/moonbags | | | | states our Solana coverage is thinner |
| 25 | uerax/all-in-one-bot | | | | integration conversation |
| 26 | vooi-app/vooi-signals-bot-example | | | | |
| 27 | punkpeye/awesome-remote-mcp-servers | n/a | n/a | n/a | LISTING. Read CONTRIBUTING, do not mail |

## Three drafts here deliberately weaken their own pitch, and that is the point

**21 (UPI), 24 (Solana) and 25 (address analysis) each say out loud what we do not cover.** That is
not modesty. Every one of those three prospects can check the claim in about a minute, and a
security vendor caught overstating coverage in a first email has spent the only introduction it
gets. The reply that says "no, but here is what we do need" is worth more than a sale of something
we would then have to build in a hurry.
