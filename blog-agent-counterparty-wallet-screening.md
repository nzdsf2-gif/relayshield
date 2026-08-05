# Your Agent Has a Wallet Now. Nothing in the Flow Asks Who It Is Paying.

In July we put an AI agent on Base mainnet with a real wallet and let it find and pay for a
security API on its own. No human in the loop, no custom discovery code. The transaction is still
on chain and anyone can check it:
`0xe90d302b5eda6b66545cf9a506c3bd73f273ff9390f309e4f021d3150a388016`. The full writeup is
[here](https://blog.relayshield.net/aws-bedrock-agentcore-x402-bazaar-autonomous-agent-payment).

That post was about proving the loop closes. This one is about the part of the loop nobody built.

## The number that should worry you

We pulled these from x402scan on 5 August 2026, past 30 days across the whole x402 ecosystem:

| | |
|---|---|
| Transactions | 12,080,000 |
| Volume | $767,290 |
| Buyers | 18,670 |
| Sellers | 83,000 |

Twelve million autonomous payments in a month. Eighty three thousand sellers. And the average
payment is **$0.0635**.

Sit with that last figure, because it explains the whole problem. At six cents a call, no human
approves anything. There is no review step, no procurement, no invoice anybody reads. An agent
resolves a service from a discovery index, gets a 402, signs, and pays. The entire control surface
that normally sits between "we should buy this" and "money left the account" has been compressed
into a function call that returns in under a second.

Now ask the obvious question. In that flow, what checks who received the money?

Nothing does.

## The gap is not payment security. It is counterparty security.

x402 does the hard cryptographic parts well. The signature is sound, settlement is verifiable, the
facilitator does its job. When we traced our own settlement end to end we could confirm every hop.

But a correct payment to a malicious address is still a correct payment. The protocol's job is to
make sure the money moves as instructed. It has no opinion on whether the instruction was a good
idea, and it was never supposed to have one.

Three things an agent cannot currently tell you before it pays:

**Is this `payTo` address connected to anything criminal?** Discovery indexes list a resource URL
and a wallet address. They do not tell you that the address has been receiving from a drainer, or
that it appeared in a stealer log last week.

**Is this service what it claims to be?** A seller entry is a name, a description and an endpoint.
Registering a typosquat of a popular service in a discovery index costs nothing. Your agent
searches for a well known API, finds a name one character off, and pays it.

**Is the token you are being asked to accept real?** Most x402 flows are USDC and that is fine. The
moment a flow accepts an arbitrary token contract, honeypots and fake mints become live.

None of these are exotic. They are the oldest problems in crypto. What is new is that the entity
making the decision is a piece of software optimising for task completion, with a funded wallet,
operating at machine speed, and with nobody watching a $0.06 line item.

## What we already sell against exactly this

We did not build these endpoints for x402. We built them because wallet screening and counterparty
risk are what we do. They happen to be exactly what an agent payment flow is missing, and they are
all live on x402 right now, on Base and Solana, discoverable through the CDP Bazaar:

| Endpoint | Price | Answers |
|---|---|---|
| `/v1/payg/wallet-risk` | $0.05 | Is this address associated with known criminal activity |
| `/v1/payg/scan-wallet` | $0.10 | Deeper wallet history and exposure |
| `/v1/payg/token-security` | $0.05 | Is this token contract a honeypot or a fake mint |
| `/v1/payg/wallet-screen-batch` | $0.50 | Screen many counterparties in one call |
| `/v1/payg/mcp-registry-risk` | $0.35 | Is this service a typosquat, newly registered, or in a criminal IOC corpus |

Look at the pricing against the ecosystem average of $0.0635. A `wallet-risk` check costs **less
than the average x402 payment it protects**. `token-security` is the same. You are not adding a
material cost layer, you are adding one call of roughly the size your agent is already making
constantly.

The batch endpoint is the honest recommendation for anything at scale. You do not screen the same
counterparty on every call. You screen a new one once, cache the verdict, and re-screen on a
schedule. At $0.50 for a batch, an agent transacting with a few hundred distinct counterparties a
month spends a few dollars on knowing who they are.

## The check that matters most is not the wallet

If you only add one call, make it `mcp-registry-risk` on the service, not the address.

Wallet screening tells you an address is already known to be bad. That is useful and it is
backward looking. A fresh scam has a clean address by definition. What it usually does not have is
a plausible history as a service: it was registered days ago, its name is one edit away from
something popular, and its endpoint has no track record.

Typosquatting a discovery entry is the cheapest attack in this whole ecosystem and there is
currently nothing stopping it. That is where we would spend the first $0.35.

## What we are not claiming

We are not claiming x402 is unsafe, and we are not claiming there is a wave of agent payment fraud
happening right now. We have not measured one and we are not going to invent one to sell a check.
The volumes today are small: $767K in a month across the entire ecosystem is a rounding error next
to any real payment rail.

The argument is about direction. Twelve million transactions a month is already past the point
where humans review individual payments, and both the transaction count and the seller count are
climbing. The controls that eventually get built here will get built after the first significant
loss, the way they always are. They may as well exist before it.

We would rather have this conversation now, when the honest framing is "here is a gap and here is a
cheap way to close it", than in six months when it is a post mortem.

## Try it without an account

Every endpoint above is x402 native. There is no signup, no API key and no subscription. Point an
agent at it, take the 402, pay it, get the answer:

```
curl -X POST https://api.relayshield.net/v1/payg/wallet-risk \
  -H 'Content-Type: application/json' \
  -d '{"address":"0x..."}'
```

That returns a well formed x402 version 2 challenge on Base or Solana. Your x402 client handles the
rest. If you prefer an API key and prepaid credits, the same checks are on the metered routes and
there is a free tier of 20 calls at
[api.relayshield.net/developers](https://api.relayshield.net/developers?source=x402-post).

Full API reference: [api.relayshield.net/docs](https://api.relayshield.net/docs).

---

NOT FOR PUBLICATION BELOW THIS LINE

## Pre publication checklist

1. **Re-verify the x402scan figures on the morning of publication.** They are past 30 days and
   they move. The whole credibility of this post is that the numbers are measured. Source:
   x402scan.com front page, "Past 30 Days" panel. Verified 2026-08-05: 12.08M transactions,
   $767.29K volume, 18.67K buyers, 83K sellers, average $0.0635.
2. **Confirm the July transaction hash still resolves** on Base mainnet.
3. Confirm all five endpoint prices still match the live 402 challenges. Verified 2026-08-05.
4. Register `x402-post` as an attribution source key in `relayshield_developer_signup.py` before
   publishing, or the CTA link logs `unmatched:` and renders no banner.
5. Run a dash sweep. No em-dashes, no en-dashes, no ` -- `.

## Why this angle and not the other one

The obvious post was a re-tell of the July AgentCore proof. That would be strictly weaker: the July
post already has the transaction hash, AgentCore, the Bazaar and a verifiable curl, and it is live
and indexed. A second "we did a transaction" post competes with our own better one. Cite it, do not
repeat it.

The counterparty angle is differentiated because it reframes RelayShield from "an API that accepts
x402" into "the control agent payments do not have". That is a much better thing to be, and it is
true rather than positioning.

## Channel strategy

The x402 world is small, public and reachable, which is the opposite of infosec. A post with a
verifiable on chain transaction is a legitimate reason to enter those conversations. A cold
partnership email is not.

**Canonical:** self hosted blog at `blog.relayshield.net`. Everything else points back to it.

| Channel | Limit | Treatment |
|---|---|---|
| LinkedIn | 3,000 chars | Link in the **first comment**, never the body. Lead with the $0.0635 figure. |
| Farcaster | ~1,024 bytes | **Highest value channel for this post.** Byte counted, so keep it ASCII. |
| Telegram | 4,096 chars | Effectively unconstrained. Full summary plus link. |
| Mastodon | 500 chars | One tight post. Infosec audience, lead with the counterparty gap not the volume. |
| Medium | n/a | **Import, do not paste.** Sets the canonical link in one step. |

**Not X.** @RelayShieldHQ suspended since 2026-07-02, appeal denied. Do not build the plan around it.
**Not Hashnode.** Abandoned, and it silently unpublishes.

**x402 specific, in priority order:**

1. **Farcaster.** This is where the x402 and agent payments crowd actually is. Native audience, no
   gatekeeper, and the $0.0635 average is the kind of measured detail that circulates there.
2. **x402scan "Add your API".** The site has a submission path on the front page. We are a seller
   with 25 indexed endpoints and we are not featured. Free placement in front of exactly this
   audience. Do this regardless of the post.
3. **CDP Discord Show and Tell.** Tracked as MKTPL-15 and currently gated on the x402 V2 migration
   batches completing. We are already an evidenced participant in the CDP Discord thread on stuck
   Bazaar resources, so this is not a cold post. Check the gate before posting.
4. **Cloudflare and Coinbase devrel.** Reachable, and the post gives a real reason to engage. Do
   not pitch a partnership, share the measurement.

**Sequencing:** blog first, then Farcaster the same hour, then LinkedIn and Telegram, then Medium
import, then Mastodon. x402scan submission is independent and should be done first since it takes
minutes.

**One honest gap to note if anyone asks:** three of our 28 endpoints (`cert-expiry`, `ip-intel`,
`secret-scan-text`) are not yet indexed in the CDP Bazaar. None of them are counterparty endpoints,
so the post's claims are unaffected, but do not say "all 28 are discoverable" anywhere.
