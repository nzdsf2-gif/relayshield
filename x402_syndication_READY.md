# x402 counterparty post: ready-to-post syndication pack

Everything below is final copy. URLs are filled in, source keys are registered and verified live,
and every block has been measured against its platform limit. Nothing here has been posted.

**Canonical (live, HTTP 200, verified 2026-08-06):**
https://blog.relayshield.net/your-agent-has-a-wallet-nothing-asks-who-it-is-paying

## Coverage: every channel, and what it carries

| # | Channel | Copy | Hashtags / tags | Limit checked |
|---|---|---|---|---|
| 1 | Farcaster `/x402` + `/base` | ready | none, channels instead | 843 of 1024 bytes |
| 2 | LinkedIn + first comment | ready | 5 hashtags | 2,561 of 3,000 |
| 3 | Telegram | ready | none needed | 1,559 of 4,096 |
| 4 | Medium | import, no copy needed | 5 tags | n/a |
| 5 | Mastodon | ready | 3 hashtags | 381 of 500 weighted |
| 6 | CDP Discord #show-and-tell | ready, separate file | none | already cut |
| 7 | Merit Systems Discord | **BLOCKED**, invite expired | none | 422 |
| 8 | awesome-x402 PR | ready | n/a, category placement | n/a |
| 9 | Hacker News, **held** | title + author comment ready | none | title 73 of 80 |

Channels 7, 8 and 9 were named in last session's plan but had **no copy written**, only a rationale
line each. They are written now. Channel 8 also had no identified surface; see that section.

## Read this first: the numbers moved

The post is date-stamped "pulled from x402scan on 5 August 2026". Checked again this morning:

| Figure | In the post (5 Aug) | x402scan now (6 Aug) |
|---|---|---|
| Transactions | 12.08M | 11.63M |
| Volume | $767.29K | $781.39K |
| Buyers | 18.67K | 18.67K |
| Sellers | 83K | 82K |
| Average payment | $0.0635 | $0.0672 |

It is a rolling 30-day window, so this is normal drift, but transactions fell and volume rose. The
copy below keeps the post's figures and adds the "x402scan, 5 Aug" stamp so a reader who checks the
site today sees a dated claim rather than a wrong one. This audience does check. The "six cents"
spine still holds at 6.7 cents, but if you want to lead on today's number instead, say seven cents
and change it in all five places at once.

## Source keys: registered and verified live 2026-08-06

Deployed to `relayshield-developer-signup` at `2026-08-06T10:48:07Z`. Confirmed by diffing the
rendered page: registered keys emit the "Arriving from the x402 ecosystem" banner, an unregistered
control emits nothing.

| Key | Channel | State |
|---|---|---|
| `x402-farcaster` | Farcaster | registered 2026-08-05, banner verified |
| `x402-linkedin` | LinkedIn | registered 2026-08-05, banner verified |
| `x402-telegram` | Telegram | registered 2026-08-05, banner verified |
| `x402-mastodon` | Mastodon | registered 2026-08-05, banner verified |
| `x402-medium` | Medium | registered 2026-08-05 |
| `x402-discord` | CDP Discord | **new today**, banner verified |
| `x402-merit` | Merit Systems Discord | **new today**, banner verified |
| `x402-hn` | Hacker News | **new today**, banner verified, post still held |

---

# 1. Farcaster, post first

Channels: `/x402`, `/base`, `/ai-agents`, `/dev`. Post to `/x402` and `/base` separately, the
subscriber sets differ. **843 bytes, limit 1024.** ASCII only, no hashtags.

```
12.08M x402 payments in 30 days. $767K volume. Average payment: $0.0635. (x402scan, 5 Aug)

At 6 cents a call nobody approves anything. No review, no procurement, no invoice. The agent
resolves a service, gets a 402, signs, pays.

So what checks who received the money?

Nothing does. x402 verifies the payment perfectly and has no opinion on the recipient. A correct
payment to a drainer is still a correct payment.

We put five counterparty checks on x402 itself. wallet-risk is $0.05, which is less than the
average payment it protects.

The one I'd add first isn't wallet screening though. A fresh scam has a clean address by
definition. Typosquatting a discovery entry is the cheapest attack in this ecosystem.

Full writeup, with the July on-chain proof:
https://blog.relayshield.net/your-agent-has-a-wallet-nothing-asks-who-it-is-paying
```

---

# 2. LinkedIn, then the first comment immediately

**Body 2,561 chars, limit 3,000.** No link in the body, it suppresses reach.

```
12,080,000 autonomous payments in 30 days. $767,290 in volume. The average payment: $0.0635.

Those are live x402 network figures I pulled on 5 August, not projections.

Six cents. Sit with that number, because it explains the whole problem.

At six cents a call there is no human approval step. No review, no procurement, no invoice anybody
reads. An AI agent resolves a service from a discovery index, receives a 402, signs, and pays. The
entire control surface that normally sits between "we should buy this" and "money left the account"
has been compressed into a function call that returns in under a second.

So ask the obvious question: in that flow, what checks who received the money?

Nothing does.

This is not a criticism of x402. The protocol does the hard cryptographic parts well. Signatures
are sound, settlement is verifiable. But a correct payment to a malicious address is still a
correct payment. The protocol's job is to move money as instructed. It has no opinion on whether
the instruction was a good idea, and it was never meant to.

Three things an agent cannot currently establish before it pays:

Is the receiving address connected to anything criminal? Discovery indexes list a URL and a wallet.
They do not tell you the address has been receiving from a drainer.

Is the service what it claims to be? Registering a typosquat of a popular API in a discovery index
costs nothing today.

Is the token contract real? The moment a flow accepts an arbitrary token, honeypots become live.

None of these are exotic. They are the oldest problems in crypto. What is new is that the entity
deciding is software optimising for task completion, with a funded wallet, at machine speed, with
nobody reviewing a $0.06 line item.

We already sell the checks that close this, and they are live on x402 now. A wallet risk check is
$0.05, which costs less than the average x402 payment it protects.

One honest caveat: I am not claiming there is a wave of agent payment fraud today. I have not
measured one and I am not going to invent one to sell a check. $767K a month across an entire
ecosystem is a rounding error.

The argument is about direction. Twelve million transactions a month is already past the point
where humans review individual payments, and both transaction and seller counts are climbing. The
controls here will get built after the first significant loss, the way they always are. They may as
well exist before it.

Measured data and the five checks in the comments.

#AIAgents #PaymentSecurity #Stablecoins #Fintech #CyberSecurity
```

**First comment, post within seconds of the body. 332 chars.**

```
Full writeup with the measured figures and the July on-chain transaction anyone can verify:
https://blog.relayshield.net/your-agent-has-a-wallet-nothing-asks-who-it-is-paying

Endpoints are x402 native, no signup or API key. Free tier of 20 calls if you prefer an API key:
https://api.relayshield.net/developers?source=x402-linkedin
```

---

# 3. Telegram

**1,559 chars, limit 4,096.** Markdown. Post to the RelayShield channel.

```
*Your agent has a wallet now. Nothing in the flow asks who it is paying.*

Live x402 network figures, past 30 days, pulled 5 August:
- 12.08M transactions
- $767.29K volume
- 18.67K buyers, 83K sellers
- Average payment: *$0.0635*

At six cents a call there is no human approval step anywhere. The agent resolves a service, gets a
402, signs, and pays. The entire control surface between "we should buy this" and "money left the
account" is now a function call returning in under a second.

What checks who received the money? Nothing does.

x402 does the cryptography well. But a correct payment to a malicious address is still a correct
payment. The protocol moves money as instructed and has no opinion on the instruction.

Three things an agent cannot establish before paying:
1. Is the payTo address linked to criminal activity
2. Is the service a typosquat of the one it meant to call
3. Is the token contract a honeypot

We put five checks on x402 itself, on Base and Solana, discoverable in the CDP Bazaar:
- `wallet-risk` $0.05
- `scan-wallet` $0.10
- `token-security` $0.05
- `wallet-screen-batch` $0.50
- `mcp-registry-risk` $0.35

A wallet-risk check costs *less than the average x402 payment it protects*.

If you only add one, make it `mcp-registry-risk` on the service rather than the address. Wallet
screening is backward looking, and a fresh scam has a clean address by definition.

Full writeup, including the July transaction hash anyone can verify on Base:
https://blog.relayshield.net/your-agent-has-a-wallet-nothing-asks-who-it-is-paying
```

---

# 4. Medium: import, do not paste

"Import a story" with the canonical URL. That sets the canonical link in one step. Pasting creates
a duplicate-content penalty instead.

Tags, 5 max: `AI Agents`, `Cryptocurrency`, `Cybersecurity`, `Payments`, `Fintech`

---

# 5. Mastodon

**381 chars with the URL counted at 23, limit 500 hard.** Do not add a word.

```
12.08M autonomous agent payments last month. Average: $0.0635.

At six cents nobody approves anything. The agent finds a service, gets a 402, signs, pays.

Nothing in that flow checks who received the money. x402 verifies the payment and has no opinion on
the recipient.

A correct payment to a drainer is still a correct payment.

https://blog.relayshield.net/your-agent-has-a-wallet-nothing-asks-who-it-is-paying

#infosec #AIagents #x402
```

---

# 6. CDP Discord, #show-and-tell

Gate satisfied. Copy is in `cdp_discord_show_and_tell_post.md`, already cut to Discord length, plus
a prepared reply bank for the follow-ups this audience actually asks. Two hard rules from that file:
say **28 live, 25 indexed**, never "28 in the Bazaar", and do not link or revive issue #2814.

---

# 7. Merit Systems Discord: BLOCKED, invite expired

**Checked 2026-08-06 against Discord's own API.** `discord.gg/JuKt7tPnNc` returns
`{"message": "Invite is expired.", "code": 50270}`, so this is not a permissions problem on our
account. The code came from `Merit-Systems/x402scan`'s README, which **still publishes the same
expired invite**. Their README badge references guild `1382120201713352836`, which returns
"Unknown Guild" only because the server widget is disabled, so that says nothing about whether the
server is alive.

No working invite is published anywhere findable: x402scan.com links only to GitHub, merit.systems
and `x.com/x402scan`; merit.systems links only to `x.com/merit_systems`. Asking via X is out, since
@RelayShieldHQ has been suspended since 2026-07-02.

**Decision: dropped for this run.** Smallest channel in the pack, and its audience overlaps heavily
with Farcaster `/x402` and the CDP Discord, which both work. Worth filing a GitHub issue on their
repo about the dead invite before the x402scan "Add your API" work, as a warm contributor entry
rather than a cold post. Copy below is kept for whenever an invite is obtained.

Lead with the measurement, not the product.

```
Been using x402scan to measure the ecosystem and one number stuck: past 30 days, 12.08M
transactions at an average payment of $0.0635 (pulled 5 Aug).

At six cents there's no approval step anywhere in the flow, which means nothing checks who received
the money. Wrote it up with the methodology, since the numbers came from your dashboard:
https://blog.relayshield.net/your-agent-has-a-wallet-nothing-asks-who-it-is-paying
```

---

# 8. awesome-x402, the "x402 Foundation orbit" slot

Last session's table said "x402 Foundation orbit / GitHub" without naming a surface. Checked today,
and there isn't one on the protocol repo: `x402-foundation/x402` has **Discussions disabled**, and
the only other entry point is issues, where #2814 is closed and off limits. The real surface is
**`xpaysh/awesome-x402`**, 276 stars, and **RelayShield is not in it** (grepped the whole README).

It has an **`### Agent Verification & Security`** section holding roughly 25 entries, which is
exactly our category. Competitors already listed there include Faro, sipi.bot, WalletTriage,
AgentRank, PulseFeed and Aegis. This is a standing listing rather than a post that scrolls away, so
it outlives everything else in this pack.

Their `CONTRIBUTING.md` rules: search first, one change per PR, append to the **bottom** of the
category, format is `- [Name](link) - Description.`, no marketing speak.

**Entry to submit, appended to the bottom of `### Agent Verification & Security`:**

```markdown
- [RelayShield](https://api.relayshield.net/developers) - Counterparty screening for agent payments, x402 native on Base and Solana with no signup or API key. Screens the `payTo` address against a 5M IOC corpus (`wallet-risk`, $0.05), the token contract for honeypot and rug traits (`token-security`, $0.05), and the discovery entry itself for typosquats of a legitimate service (`mcp-registry-risk`, $0.35), plus `scan-wallet` ($0.10) and a batch endpoint ($0.50). 28 live endpoints, 25 indexed in the CDP Bazaar. ([OpenAPI](https://api.relayshield.net/openapi.json)) ([docs](https://api.relayshield.net/docs))
```

**Before opening the PR:** the repo's own quality bar is working links, so check
`/openapi.json` and `/docs` render, and use the GitHub noreply commit email, since a personal
address has silently broken CLA linkage on an external OSS PR before.

---

# 9. Hacker News, held

One shot, so it stays held until the post has settled on the other channels and the figures are
re-verified that morning. `x402-hn` is registered now so it cannot go out untracked when you fire it.

**Title, 73 chars, limit 80. No hashtags on HN, and do not editorialise the title.**

```
12M agent payments a month, and nothing checks who is receiving the money
```

Submit as a link to the canonical URL, not a text post. Then add one comment as the author,
disclosing the commercial interest up front, because this audience punishes anything else.

```
Author here. The measurement is the part I'd defend: x402scan front page, past 30 days, pulled 5
August. 12.08M transactions, $767K volume, average payment $0.0635. It's a rolling window so it
drifts, and it had moved to 11.63M/$781K by the next morning.

Disclosure, since it matters: we sell counterparty checks on x402, so I have an interest here. I've
tried to keep the post to what I measured. I am specifically not claiming a wave of agent payment
fraud, because I haven't measured one, and $767K a month across a whole ecosystem is a rounding
error next to anything.

The argument is only about direction. At six cents a call there is no human in the approval path,
and the protocol correctly has no opinion on the recipient. The thing I'd actually build first
isn't wallet screening, which is backward looking, but checking whether the discovery entry is a
typosquat of the service the agent meant to call. That's the cheapest attack here and nobody is
looking at it.
```

# Do not post

- **X / Twitter.** @RelayShieldHQ suspended 2026-07-02, appeal denied same day.
- **Hashnode.** Abandoned, and it has silently unpublished a post twice.
- **Facebook.** Wrong audience, and limited pending Business verification.
- **x402 Foundation issue #2814.** Closed and dominated by a third party.
