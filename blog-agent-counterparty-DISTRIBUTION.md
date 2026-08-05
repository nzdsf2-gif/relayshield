# Distribution copy: agent counterparty screening post

**Canonical URL (publish here FIRST, everything else points back):**
`https://blog.relayshield.net/your-agent-has-a-wallet-nothing-asks-who-it-is-paying`

**Attribution parameter per channel.** Register each key in `relayshield_developer_signup.py`
BEFORE posting, or the link logs `unmatched:` and renders no banner.

| Channel | CTA link |
|---|---|
| Farcaster | `https://api.relayshield.net/developers?source=x402-farcaster` |
| LinkedIn | `https://api.relayshield.net/developers?source=x402-linkedin` |
| Telegram | `https://api.relayshield.net/developers?source=x402-telegram` |
| Mastodon | `https://api.relayshield.net/developers?source=x402-mastodon` |
| Medium | canonical set automatically by import |

**Re-verify the x402scan numbers the morning you publish.** They are past 30 days and they move.
Figures below verified 2026-08-05: 12.08M transactions, $767.29K volume, average $0.0635.

---

## 1. Blog (canonical): publish first

Source: `blog-agent-counterparty-wallet-screening.md`, everything above the NOT FOR PUBLICATION line.

- **Slug:** `your-agent-has-a-wallet-nothing-asks-who-it-is-paying`
- **Tags:** `x402`, `ai-agents`, `agent-payments`, `wallet-screening`, `counterparty-risk`,
  `crypto-security`, `stablecoins`
- **Meta description:** 12 million autonomous agent payments a month, averaging $0.0635. Nothing in
  the x402 flow checks who is receiving the money. Measured data and the five checks that close it.
- **OG image:** reuse the pattern from the July AgentCore post.

Wait for the live URL to render in a browser before posting anywhere else. A publish is not done
until the public URL renders.

---

## 2. Farcaster: HIGHEST VALUE, post within the hour

Native x402 audience. Limit ~1,024 **bytes**, so keep it ASCII. No hashtag culture; use channels.

**Post to channels:** `/x402`, `/ai-agents`, `/base`, `/dev`

```
12.08M x402 payments in the last 30 days. $767K volume. Average payment: $0.0635.

At 6 cents a call nobody approves anything. No review, no procurement, no invoice. The agent
resolves a service, gets a 402, signs, pays.

So what checks who received the money?

Nothing does. x402 verifies the payment perfectly and has no opinion on the recipient. A correct
payment to a drainer is still a correct payment.

We put five counterparty checks on x402 itself. wallet-risk is $0.05, which is less than the
average payment it protects.

The one I'd add first isn't wallet screening though. A fresh scam has a clean address by
definition. Typosquatting a discovery entry is the cheapest attack in this ecosystem.

Full writeup, with the July on-chain proof: <CANONICAL_URL>
```

---

## 3. LinkedIn: 3,000 chars, link in the FIRST COMMENT

Body links suppress reach. Post the body, then immediately comment with the URL.

**Hashtags (3-5 max, end of post):** `#AIAgents` `#PaymentSecurity` `#Stablecoins` `#Fintech`
`#CyberSecurity`

```
12,080,000 autonomous payments in 30 days. $767,290 in volume. The average payment: $0.0635.

Those are live x402 network figures I pulled this week, not projections.

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

**First comment:**
```
Full writeup with the measured figures and the July on-chain transaction anyone can verify:
<CANONICAL_URL>

Endpoints are x402 native, no signup or API key. Free tier of 20 calls if you prefer an API key:
https://api.relayshield.net/developers?source=x402-linkedin
```

---

## 4. Telegram: 4,096 chars, effectively unconstrained

Markdown supported. No hashtags needed.

```
*Your agent has a wallet now. Nothing in the flow asks who it is paying.*

Live x402 network figures, past 30 days:
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
<CANONICAL_URL>
```

---

## 5. Mastodon: 500 chars HARD, URLs count as 23

Infosec audience. Lead with the gap, not the volume. **Do not exceed 500.**

**Hashtags:** `#infosec` `#AIagents` `#x402`

```
12.08M autonomous agent payments last month. Average: $0.0635.

At six cents nobody approves anything. The agent finds a service, gets a 402, signs, pays.

Nothing in that flow checks who received the money. x402 verifies the payment and has no opinion on
the recipient.

A correct payment to a drainer is still a correct payment.

<CANONICAL_URL>

#infosec #AIagents #x402
```

---

## 6. Medium: IMPORT, do not paste

Use "Import a story" with the canonical URL. That sets the canonical link in one step and avoids
the duplicate-content penalty. Pasting does not.

**Tags (5 max):** `AI Agents`, `Cryptocurrency`, `Cybersecurity`, `Payments`, `Fintech`

---

## Channels deliberately excluded

- **X / Twitter.** @RelayShieldHQ suspended since 2026-07-02, appeal denied same day. Do not build
  the plan around it.
- **Hashnode.** Abandoned, and it has silently unpublished a post twice.
- **Facebook.** Wrong audience for this post entirely, and currently limited pending Business
  verification. Revisit for consumer-facing Crypto Shield content, not this.

---

## Sequencing

1. **x402scan registration** is NOT ready. It requires a discovery spec our `/openapi.json` does not
   yet satisfy. See the audit note below. Do not let this block the post.
2. Publish canonical, confirm it renders in a browser.
3. Farcaster within the hour. This is the native audience.
4. LinkedIn, then immediately the first comment with the link.
5. Telegram.
6. Medium import.
7. Mastodon.
8. CDP Discord Show and Tell only after checking the MKTPL-15 gate.

## Note for whoever picks up x402scan

Registration requires a published discovery spec: OpenAPI at `/openapi.json` with `x-payment-info`
on every payable operation, a structured `price`, `protocols: [{"x402": {}}]`, and a declared `402`
response. Audited 2026-08-05: our live spec has **32 operations, 29 of them `/v1/metered`, and zero
`/v1/payg` operations**. `x-payment-info` appears nowhere. Their own hard rule is not to register
until the audits are clean, so this is a real change to `relayshield_openapi_spec.py`, not a form
fill.
