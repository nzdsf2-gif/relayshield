# The x402 / agent-economy angle

*Assessed 2026-08-14, prompted by the founder asking whether Predi by Virtuals has an x402 angle
alongside the Discord bot. Short answer: yes, and it is a better fit than the bot for this audience.*

## Verified live, not assumed

Both PAYG endpoints were checked against production today and return a correct x402 challenge:

```
POST /v1/payg/wallet-risk  -> HTTP 402, x402Version 2, $0.05 USDC (Base or Solana)
POST /v1/payg/scan-url     -> HTTP 402, x402Version 2, $0.05 USDC (Base or Solana)
```

**The resource description is already written for this audience**, which was a pleasant surprise:

> "Screen a wallet address across EVM, Solana, TON, or Bitcoin for known scam, exploit, drainer, or
> sanctions-list association before your agent transacts with it. Returns a risk level and specific
> risk flags. **The recommended first call for any autonomous trading or DeFi agent before
> interacting with a new counterparty wallet.**"

Nothing needs building to start this conversation. That is the main finding.

## Why x402 beats the Discord bot for agent platforms

**An autonomous agent cannot become a customer the normal way.** It cannot fill in a signup form,
accept terms, or rotate an API key. It can hold a wallet and pay per call. **x402 is the only
distribution channel that works when the buyer is software**, which is exactly why the PAYG endpoints
exist.

**Virtuals' ACP is agent-to-agent commerce.** Confirmed from their own whitepaper: ACP is "a
framework that enables secure, transparent, and verifiable commerce between autonomous AI agents",
with every transaction recorded onchain.

**Agent-to-agent commerce is counterparty risk by definition.** An agent about to transact with
another agent's wallet has precisely the question `wallet-risk` answers. That is not a stretched
analogy, it is the same sentence.

**So pitching the Discord bot to Virtuals would be bringing the wrong product.** Their users are
agent developers, not people pasting an address into a chat window and asking whether it is safe. A
slash command serves a human. An x402 endpoint serves the agent.

**Base is already a supported rail.** Both endpoints settle in USDC on Base or Solana, and Virtuals
and PREDI are Base-native. No new integration, no new facilitator, no new chain. Worth saying out
loud in any pitch, because "we already work on your chain today" removes the usual first objection.

## The honest weakness, so it does not get discovered later

**Predi specifically is a weak example.** PrediBot places predictions on its own protocol,
PredictBase, so it is not screening arbitrary counterparties. The counterparty-risk need is real for
general trading, DeFi and ACP marketplace agents, and thin for a bot betting on its own venue.

**Do not build the pitch around Predi.** Pitch the ecosystem, use a general trading or ACP agent as
the example, and mention Predi only if asked.

## What ACP actually is

**Agent Commerce Protocol, by Virtuals.** A marketplace where autonomous agents hire each other for
**USDC-escrowed onchain jobs**. Agents are treated as economic actors with their own wallets, email
and virtual cards. They browse, hire, fund, and complete jobs against each other.

The pieces that matter to RelayShield, taken from the `acp-cli` README, which is a primary source:

| Concept | What it is |
|---|---|
| **Agent identity** | `acp agent create`. A wallet and identity. The entry ticket |
| **Offering** | A service with pricing, SLA and requirements. `acp offering create` |
| **Resource** | "External data/service endpoints your agent exposes. Each resource has a name, description, URL, and a `params` JSON schema" |
| **Discovery** | `acp browse` lets agents find providers, their offerings and their resources |

**"Resource" is a description of RelayShield's API almost word for word.** Name, description, URL,
params schema. That is the shape the product already has.

### The unresolved contradiction, flagged rather than smoothed over

**Two sources disagree on whether an agent identity is mandatory.**

- A secondary summary says teams "do not need to develop or operate an autonomous agent" and can
  integrate an existing API directly via the SDK.
- The **`acp-cli` README, which is their own tool, says registering "still requires creating an agent
  identity first, no option to offer existing APIs standalone."**

**Trust the README.** But note the distinction that actually matters: *creating an agent identity* is
a CLI command that mints a wallet. It is not *building an autonomous agent*, and it is not launching
a token. Tokenization is described separately and carries a launch fee, which implies it is optional.

**Cost of finding out: running one command.** Do not resolve this by more searching.

### Fees, as documented

Tokenisation carries a launch fee, but appears optional. Compute accounts need a USDC top-up with a
**$1 minimum**. No staking requirement documented. Nothing here is a real financial commitment.

## Is listing on ACP stronger than approaching the Virtuals team? Yes.

**Listing wins on every axis that has hurt us before.**

- **It is self-serve.** No reply needed, no gatekeeper, nobody to go quiet on you. Compare Joyce at
  Vouch, or Moshe on XSOAR.
- **It is permanent.** A listing keeps working; a relationship needs maintenance.
- **It has a discovery mechanism.** `acp browse` is agents actively looking for providers, which is
  inbound rather than outbound.
- **The buyer pays at call time.** USDC escrow means an agent that finds you is a customer, not a
  lead. There is no sales cycle to lose.

**Approach the team only after the listing exists**, and only with usage data to point at. A cold
partnership ask with nothing live is the weaker version of the same conversation.

## The honest counterweight, which should not be skipped

**RelayShield is already registered on x402scan, and total revenue is about $0.01.** The agent
economy thesis has not produced money yet. ACP is a second bet on the same thesis, not a different
one.

That is not a reason to skip it, because the cost is roughly an evening and the mechanics are
self-serve. It **is** a reason to **time-box it hard** and to keep it away from the channel sales
work, which is the founder's own stated constraint.

## Stripe MPP vs CDP/AgentKit. I ranked the wrong thing first time.

**Correction, founder-flagged 2026-08-14.** I evaluated Stripe's *Agentic Commerce Protocol* and
called it a poor fit. That was the wrong artefact. The relevant one is **MPP, the Machine Payments
Protocol**, shipped by **Stripe and Tempo on 18 March 2026**. My "distant third" ranking was about a
protocol nobody asked about.

**Three different things share confusingly similar names**, which is worth pinning down once:

| Name | Owner | What it is |
|---|---|---|
| **ACP**, Agent Commerce Protocol | Virtuals | Agents hiring each other for USDC-escrowed onchain jobs |
| **ACP**, Agentic Commerce Protocol | OpenAI + Stripe | Consumers buying products through an agent. Powers ChatGPT Instant Checkout |
| **MPP**, Machine Payments Protocol | Stripe + Tempo | Billing agents over HTTP. The direct x402 counterpart |

### What MPP actually is

Same core mechanic as x402: an agent hits an endpoint, gets a `402 Payment Required` with a price,
pays, and receives the resource in one request-response cycle. It also covers price discovery,
subscriptions and balance reconciliation, and works over MCP as well as plain HTTP.

**The difference that matters is what the agent can pay with.**

| | x402 | MPP |
|---|---|---|
| Rails | USDC on Base, Polygon, Solana | **Stablecoins via Tempo, cards via Stripe and Visa, Bitcoin via Lightning**, custom methods |
| Buyer must hold | Crypto | **Anything, including a card** |
| Our integration cost | **Zero, already live** | PaymentIntents API, "a few lines of code" per Stripe |
| Directory | x402scan, we are listed | **MPP payments directory, 100+ services at launch, including data services** |

### Why this reverses the ranking

**x402 and MPP are not the same bet.** x402 requires an agent funded with crypto. MPP lets an agent
pay by card. **RelayShield's own evidence is that the crypto-funded agent population has not paid**:
registered on x402scan, total revenue about $0.01. Adding another crypto-native venue is doubling
down on the leg that has already been tested and returned nothing.

**MPP reaches a different population**, and it is the population RelayShield's real buyers live in.
MSPs, security teams and insurers are Stripe-shaped, not crypto-shaped.

**And the billing rail already exists.** RelayShield already bills through Stripe, on the aggregate
meter. MPP is an extension of infrastructure that is live and that the founder already understands,
rather than a new rail.

**The directory is five months old.** 100+ services at launch, explicitly including data services.
Early entry buys visibility that x402scan no longer offers.

### BLOCKED 2026-08-14: Stripe crypto is INELIGIBLE for this account

**Checked live the same day, before writing any code.** In the Dashboard, Stablecoins and Crypto
shows **Ineligible** with no request button, and the API confirms it: `crypto_payments` capability is
**`inactive`** on `acct_1TGqqsL2dcjOeFiY`, while `card_payments` and `link_payments` are `active`.

**Stripe support's answer, paraphrased from their own docs:** *"If you're unable to onboard or don't
see Crypto as a payment method in your Settings, we are unable to support your account at this time.
We're working quickly to expand this capability to more accounts."* They do not disclose the criteria.

**That is staged-rollout language, not compliance language.** Two hypotheses fit the evidence:

| Hypothesis | Evidence for | Verdict |
|---|---|---|
| Processing volume / account maturity | $115.92 lifetime across 8 charges, Apr to Jul 2026, none in the last month, zero balance. MPP and stablecoins both shipped March 2026 | **Most likely.** "Expand to more accounts" is capacity language |
| Business entity type | Account is `business_type: individual`, and the docs require a US or Canada legal entity | Possible, but Stripe names this explicitly when it is the blocker |

**Do NOT convert the account from individual to company as a fix for this.** It triggers
re-verification on a live revenue account and probably changes nothing. The entity mismatch is real
and worth correcting on its own merits, since RelayShield LLC is the name in the Terms' carrier
consent clause and on the Vouch and Corix policies, but it is a separate piece of work.

**Consequence for MPP.** With the crypto rail closed, MPP is fiat-only at the $0.50 SPT minimum,
which at current pricing covers **4 of 28** PAYG endpoints and reaches no crypto-funded agents at
all. That is not the proposition that put MPP first. **MPP is parked, not dropped**: "at this time"
implies the door opens later, and the implementation is a known quantity when it does.

**Cheap marker worth leaving:** a short note to Stripe sales framing RelayShield as a US security API
already monetising machine-to-machine calls via live x402 endpoints on Base and Solana, asking what
the path to crypto eligibility looks like. Low odds, one paragraph, and the "already doing machine
payments elsewhere" angle is both true and the only leverage available.

**Ignore the Bridge suggestion** from Stripe support for now. It is their stablecoin platform, a
materially heavier integration than MPP, and almost certainly gated the same way.

### The ranking, revised

1. **MPP.** Highest value. Different buyer population, existing Stripe rail, young directory. This is
   the one worth real effort.
2. **CDP/AgentKit.** Cheapest. The endpoints are already live on Base and the CDP relationship
   exists, so the work is discoverability rather than build. **Do it because it is nearly free**, not
   because it is the better bet.
3. **Virtuals ACP.** Queued as a todo per founder direction.

**If only one gets real effort, it is MPP.** AgentKit should happen anyway because it costs almost
nothing.

**Honest caveats.** MPP is five months old, so this is a bet on a young standard, albeit Stripe's.
And note Stripe supports **both** MPP and x402, so this is not a defection from one to the other.
Tempo is a new chain, but Stripe handles settlement through PaymentIntents, so it should not mean new
chain work on our side. **Confirm that before scoping**, because it is the assumption that would cost
the most if wrong.

## What to actually do, cheapest first

1. **Nothing to build.** The endpoints are live, priced and already registered on x402scan. Confirm
   RelayShield is discoverable in whatever index Virtuals developers actually use, which may not be
   x402scan.
2. **Target agent developers, not communities.** The Virtuals Discord has a developer audience, but
   **two servers currently resolve under the name "Virtuals Protocol"** (12,661 at 9.2% and 5,677 at
   4.5%). One of them is not theirs. **Confirm the invite from `virtuals.io` before going near
   either.**
3. **Read the ACP integration docs** for whether third-party services can be listed as callable by
   agents. If that listing exists, it is the highest-leverage item here and it is a form, not a
   build.

## Defect found while checking, unfixed

**The module docstring misstates the price.** `relayshield_api.py:30` says
`POST /v1/payg/wallet-risk — $0.15 USDC`. The actual price map at line 261 is `50000` micro-USDC,
which is **$0.05**, annotated "teaser price, CDPX-3". The live 402 confirms $0.05.

The $0.05 figure is correct and deliberate. **The header is stale.** It is an internal docstring and
is not served anywhere, so this is low severity, but a wrong price in the file's own header is
exactly how a wrong price ends up quoted in a sales conversation. One-line fix.

Related: [[project-bundle-d-x402-facilitators]], [[project-x402scan-registration]],
[[project-developer-funnel-strategy]]
