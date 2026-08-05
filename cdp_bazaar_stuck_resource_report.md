# CDP Bazaar — stuck resource tracking report

## Summary

A specific resource in CDP's x402 Bazaar discovery index appears to have stopped
tracking usage entirely around 2026-07-12, despite genuine, on-chain-verified
settlements continuing against it since. A sibling resource on the same account,
same code path, same facilitator, continues to track correctly in the same
window — ruling out an account-wide or client-side issue.

## The stuck resource

- **Resource URL:** `https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod/v1/payg/domain`
- Discovery search (`GET /platform/v2/x402/discovery/search?query=relayshield%20domain`) shows:
  - `lastUpdated`: `2026-07-12T14:03:38.317Z`
  - `quality.lastCalledAt`: `2026-07-12T14:03:38.196Z`
  - `quality.l30DaysTotalCalls`: `1`
- **A real settlement was made against this exact resource on 2026-07-15**, well after that timestamp:
  - Transaction: `0x7f47a8af14135d1ddc48eaaed556e4bffa0e89fbfda34e200988529112b41e3a` (Base mainnet)
  - Independently verified via `eth_getTransactionReceipt` on `mainnet.base.org` — `status: 0x1` (success), correct USDC Transfer event (500000 units = $0.50) from the payer to our registered `payTo` address
  - Verified server-side via our own Lambda's CloudWatch logs: the `/verify` call was sent to `https://api.cdp.coinbase.com/platform/v2/x402/verify` (your facilitator, not a fallback), and `/settle` returned `success: true` with the same transaction hash
- Despite this, the discovery record's `lastUpdated`/`quality.lastCalledAt` still show 2026-07-12 as of this report — the July 15 settlement was never reflected.

## The working sibling resource (control)

- **Resource URL:** `https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod/v1/payg/supply-chain`
- Same account, same Lambda, same facilitator-selection code path (`_select_facilitator`), settled through the same CDP facilitator.
- Discovery search shows:
  - `lastUpdated`: `2026-07-14T14:03:11.666Z`
  - `quality.lastCalledAt`: `2026-07-14T14:03:11.451Z`
  - `quality.l30DaysTotalCalls`: `2`
- This resource's tracking is current and reflects recent real activity, in the same time window the `domain` resource has been frozen.

## What this rules out

- Not a client-side/payer issue — the July 15 settlement against `domain` is independently verified on-chain.
- Not a facilitator-selection issue — both resources route through the identical code path and the same CDP facilitator (confirmed via our own request logs, not just code inspection).
- Not an account-wide indexing outage — `supply-chain` on the same account continued tracking correctly through the same window.
- Not a duplicate-entry/search-ranking artifact — the full discovery response for `domain` shows exactly one entry for this resource URL.
- Not the empty-probe-rejection pattern reported elsewhere in this class of issue (e.g. a server 400ing on an empty/probe body before reaching its 402 logic, preventing your crawler from ever successfully re-validating it) — tested directly: `domain`, `breach`, and `supply-chain` all return a clean `402` on an empty or malformed body with no payment header, since our server checks for the payment header before it ever inspects the body. Ruling this out explicitly since it's a known cause for other builders hitting similar symptoms.

## Broader concern — not just a V1→V2 migration issue

We were originally investigating this as part of migrating our endpoints from x402 v1 to v2 shapes, but the evidence above shows the actual break is narrower and more concerning: **it's not specific to a shape change at all — it's that an already-indexed resource's tracking can apparently freeze permanently, for reasons unrelated to what the resource is serving.** That means this could affect *any* future update to an already-indexed listing (a price change, an output schema fix, a description update), not just a protocol version migration. We haven't tested whether other already-indexed resources on our account beyond these three are similarly at risk — flagging this as an open, unverified concern rather than something we're claiming applies universally.

## Related context

- We independently observed a real CDP status incident the same week ("Payments on new payment links are failing," 2026-07-14 10:42–11:31 PDT, resolved) — noting this for completeness, though it reads as a different product surface (payment links) than Bazaar discovery specifically, so we're not claiming it's the same root cause.
- Posting this under [x402-foundation/x402#2814](https://github.com/x402-foundation/x402/issues/2814), since that's the actively-tracked thread other builders have used for this same class of symptom ("settled payments that never surfaced").

## What we're asking

Could you check why `https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod/v1/payg/domain`'s
discovery/quality tracking appears to have stopped updating after 2026-07-12,
while a sibling resource on the same account kept updating normally? We also saw
the same frozen-tracking symptom on two other resources under this account
(`/v1/payg/breach`, `/v1/payg/sim-swap`), all originally registered around the
same July 12 window — happy to provide the same evidence for those if useful.
Separately, if this points to a general limitation on updating any already-indexed
resource's tracking, that's worth knowing regardless of the V1/V2 question.
