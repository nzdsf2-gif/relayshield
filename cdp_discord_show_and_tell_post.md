# CDP Discord, #show-and-tell post

**Gate check: PASSED.** MKTPL-15 held this until the x402 V2 migration completed. Verified
2026-08-05: 25 of 26 main-Lambda PAYG paths are V2-enabled, and the holdout, `secret-scan-text`, is
one of the three deliberately excluded from Bazaar indexing. Both agentic endpoints are V2 and
indexed.

**Before posting:** re-verify the x402scan numbers (past-30-days, they move) and that the blog URL
renders.

---

## The post

```
Just finished migrating our catalogue to x402 V2 on Base and Solana. 28 live endpoints, 25
discoverable in the Bazaar.

While measuring the ecosystem we hit a number that stuck with us. Past 30 days on x402scan: 12.08M
transactions, $767K volume, average payment $0.0635.

At six cents there's no human approval step anywhere. Agent resolves a service, gets a 402, signs,
pays. So what checks who received the money? Nothing does, and that's correct protocol design, but
a correct payment to a drainer is still a correct payment.

So we put counterparty screening on x402 itself. wallet-risk is $0.05, less than the average
payment it protects.

Writeup: https://blog.relayshield.net/your-agent-has-a-wallet-nothing-asks-who-it-is-paying

Happy to share our V2 payload shape if anyone's mid-migration, we made most of the mistakes already.
```

**~110 words.** Post as a single message.

---

## Even shorter, if the channel skews terse

```
Migrated our catalogue to x402 V2 on Base and Solana. 28 endpoints, 25 in the Bazaar.

Odd thing we found while measuring: past 30 days, 12.08M transactions at an average of $0.0635.
At six cents nobody's approving anything, and nothing in the flow checks who received the money.

So we shipped counterparty screening as x402 endpoints. wallet-risk $0.05, which is less than the
average payment it protects.

https://blog.relayshield.net/your-agent-has-a-wallet-nothing-asks-who-it-is-paying
```

---

## Keep in your pocket for replies, do not post upfront

**The V2 payload shape**, if anyone takes you up on it:

```
curl -X POST https://api.relayshield.net/v1/payg/domain \
  -H 'Content-Type: application/json' -d '{}'
```

Full x402Version 2 challenge with Bazaar metadata, no key needed. Worth mentioning the challenge
nests under an `x402` key rather than a top-level `accepts` array, which tripped up our own tooling.

**The rest of the price list:** token-security $0.05, scan-wallet $0.10, mcp-registry-risk $0.35,
wallet-screen-batch $0.50.

**The sharper opinion, if someone engages:** the one to add first is `mcp-registry-risk` on the
*service*, not the address. Wallet screening is backward looking and a fresh scam has a clean
address by definition. Typosquatting a discovery entry is the cheapest attack in this ecosystem.

**Why only 25 of 28:** `cert-expiry`, `ip-intel` and `secret-scan-text` are developer and ops tooling
with no natural buyer in an agent discovery index. Deliberate, so do not dodge it.

**Other likely follow-ups:**
- *Empty probe body?* We check the payment header before inspecting the body, so a probe reaches a
  clean 402 rather than a 400.
- *Which facilitator?* CDP's, confirmed from our own request logs.
- *Solana too?* Yes, both chains on every listed endpoint.

---

## Posting notes

**Do not say "28 endpoints discoverable in the Bazaar."** 28 live, 25 indexed. This audience checks.

**Do not link or revive x402-foundation/x402#2814.** Closed, and dominated by a third-party seller
posting hourly automated updates about an unrelated host.

**No fraud-wave claim.** We have not measured one, and $767K a month is a rounding error. If it comes
up, say so plainly. The argument is direction, not alarm.
