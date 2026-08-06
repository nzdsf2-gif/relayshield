# CDP Discord, #show-and-tell post

**Gate check: PASSED.** MKTPL-15 held this until the staged x402 V2 migration completed. Verified
2026-08-05: **25 of 26 main-Lambda PAYG paths are V2-enabled**, and the single holdout,
`/v1/payg/secret-scan-text`, is one of the three endpoints deliberately excluded from Bazaar
indexing on buyer-segment grounds. Both agentic endpoints are V2 and indexed. Nothing stale is being
marketed.

**Before posting, re-verify:** the x402scan figures (they are past-30-days and they move) and that
the blog URL renders.

---

## The post

```
Hey all, RelayShield here. We sell security checks as x402 endpoints, and we just finished
migrating our catalogue to x402 V2 on Base and Solana. 28 live endpoints, 25 of them discoverable
in the CDP Bazaar.

Two things that might be useful to this channel.

**1. A known-good V2 payload shape.** During the Bazaar stuck-resource investigation earlier this
summer we diffed our V2 challenge byte for byte against `supply-chain` and `netintel.dev` to rule
out a shape problem. It held up, so if you are migrating and want something to compare against,
ours is public and needs no key:

curl -X POST https://api.relayshield.net/v1/payg/domain \
  -H 'Content-Type: application/json' -d '{}'

That returns a full x402Version 2 challenge with Bazaar discovery metadata embedded. Worth noting
the challenge nests under an `x402` key rather than a top-level `accepts` array, which tripped up
our own tooling at one point.

**2. Something we found while measuring the ecosystem.** Past 30 days on x402scan: 12.08M
transactions, $767K volume, average payment $0.0635.

Six cents. At that size there is no human approval step anywhere in the flow. The agent resolves a
service, gets a 402, signs, pays. Which raises a question we could not find an answer to: what in
that flow checks *who received the money*?

Nothing does. x402 verifies the payment correctly and has no opinion on the recipient, which is
correct protocol design. But a correct payment to a drainer is still a correct payment.

So we put counterparty screening on x402 itself. wallet-risk is $0.05, which is less than the
average x402 payment it protects. token-security $0.05, scan-wallet $0.10, mcp-registry-risk $0.35,
wallet-screen-batch $0.50.

The one we would actually add first is mcp-registry-risk on the *service*, not the address. Wallet
screening is backward looking, and a fresh scam has a clean address by definition. Typosquatting a
discovery entry is the cheapest attack in this ecosystem right now.

Not claiming there is a fraud wave, we have not measured one. $767K a month is a rounding error.
But 12M transactions a month is already past where humans review payments, and these controls
usually get built after the first big loss rather than before it.

Full writeup with the numbers and the July on-chain AgentCore proof:
https://blog.relayshield.net/your-agent-has-a-wallet-nothing-asks-who-it-is-paying

Happy to answer anything about the V2 migration, we made most of the mistakes already.
```

---

## Notes for posting

**Tone check.** This channel rewards builders sharing findings, not vendors pitching. The post leads
with a reusable artifact (the V2 payload) and a measurement, and only then mentions what we sell.
Keep that order.

**Do not say "28 endpoints discoverable in the Bazaar."** It is 28 live, 25 indexed. That distinction
is deliberate, and this is an audience that would check.

**Do not link or revive x402-foundation/x402#2814.** It is CLOSED and dominated by a third-party
seller posting hourly automated updates about an unrelated host. Our stuck-resource report is in
there, but pointing at that thread now invites confusion rather than credibility.

**If asked why only 25 of 28 are indexed:** the three absent ones are `cert-expiry`, `ip-intel` and
`secret-scan-text`, left out deliberately because they are developer and operations tooling with no
natural buyer in an agent discovery index. That is an honest and slightly flattering answer, so do
not dodge it.

**Follow-ups worth being ready for:**
- *"How do you handle a 402 on an empty probe body?"* We check for the payment header before we
  inspect the body, so a probe reaches a clean 402 rather than a 400. That was ruled out explicitly
  during the stuck-resource work.
- *"Which facilitator?"* CDP's, confirmed from our own request logs, not just code inspection.
- *"Solana too?"* Yes, both Base and Solana on every listed endpoint.
