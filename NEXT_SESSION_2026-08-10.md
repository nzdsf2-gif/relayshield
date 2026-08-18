# Handover, written end of 2026-08-09

Read `project_session_snapshot_2026-08-09` in memory first. This is the task-level pickup.

## Start here tomorrow

**1. Run the $0.01 Bundle A test, then go Public.** Unchanged from yesterday and still the only
thing between Bundle A and revenue. Subscribe from `442429445748` to **`offer-d75uqa4lwqsuo`**,
NOT the $150 public offer. Verify a key is provisioned with
`aws_product_code=cvfvhwhmichl13kcuuutkbwmp` and `bundle_a_access=true`, all 6 Bundle A endpoints
200, all Bundle D endpoints 402, and a metering record lands. Then `UpdateVisibility` to Public as
a **separate** change set.

Weigh first: `/v1/metered/sim-swap` still 503s by design until Twilio #28883049 is approved, so one
Bundle A dimension visibly does not work.

**2. Test the Snap's `onTransaction`.** The only untested path. Needs a funded testnet account:
Flask is installed in Chrome, wallet created, Snap installed and configured. Get Sepolia or Base
Sepolia faucet ETH, start a send, read the panel, reject. **Review takes up to a month, so there is
time**, but if it is broken we publish 0.1.1 and email `andrew@relayshield.net` to update the
version under review. Full detail in `project_relayshield_snap`.

**3. Verdict Watch key, now a smaller decision than it looked.** I told you the cost was
"unbounded" and that was wrong. Marginal cost per re-screen is about zero: HIBP is a flat
subscription, GoPlus is called with no auth on its free tier, domain uses free sources. Only Twilio
sim-swap is genuinely per-call and it 503s today. **Recommendation: create the key, exclude `phone`
as a watchable subject until Twilio pricing is known.** Mechanically it is an api_keys record whose
`source` bypasses billing, wired as the Lambda env var, then enable the schedule.

## Waiting on other people

- **MetaMask Snaps Directory**, submitted 2026-08-09, up to a month, needs two internal approvals.
- **Twilio #28883049**, submitted 2026-08-08, still open.
- **XSOAR demo promised by Friday 21 August.** Reply posted. Community Edition tenant exists.
  Unverified: whether the free tier (post 30-day trial) still allows installing a custom pack from
  a contribution branch. **Check that before the date gets close.**

## Shipped today, all verified live

| | |
|---|---|
| MetaMask Snap | built, `relayshield-snap@0.1.0` on npm, repo public, directory form submitted |
| `/v1/metered/wallet-risk` | new, $0.05, plus OpenAPI entry. The recorded PAYG plan was not implementable |
| PII in logs | 18 statements redacted, salted per cold start, unlinkable across time |
| Log retention | 90 days on all 54 groups, was unlimited |
| Privacy policy | corrected from "1 year" to 90 days, live |
| Monday report | attribution rebuilt, was showing 4 of 39 keys |
| `/developers` | 7 changes, 89 dashes removed, comments stripped, semantic h2s, **first ever media query** |
| CS Mobile | non-doxxing copy in onboarding + public site + dApp Store draft |
| Telegram | founder's account fixed, `/help` now answers in every state |
| First-seen table | recording started, nothing reads it yet |

## Open, not started

- **#19 SKU audit.** Nine ways to pay, zero paying customers. Verdict Watch should attach to
  Bundle A/D rather than becoming SKU ten. **#22** is the mechanical half: `watch_access=true` at
  fulfilment, no AWS change set needed.
- **#13** 26 double-hyphens in the published API reference (`relayshield_openapi_spec.py`).
- **#16** the five-step LLMjacking attack chain onto `/developers` and the MSP brief. Positioning
  copy only.
- **`Arjen_CS_Mobile_Data_Handling_Answer.md`** is written but marked not-for-sending. It now
  matches reality since retention is set. Needs one read-through before it goes to him.
- **dApp Store metadata** has the new privacy section but it is a draft file. It only reaches the
  listing when v1.5.0 is submitted.

## Decisions recorded today

- **Do not build for Coinbase, Bitget or Kraken.** None runs third-party code inside the wallet.
  Not a judgement call, there is nothing to build. The real route is being the intelligence behind
  their built-in warnings, the Blockaid pattern, which is a high-friction partnership sale. Parked
  as a named target, Coinbase first if ever.
- **Low-friction self-serve is the preferred motion.** Too many channels is unscalable. High
  potential ones still worth pursuing, one at a time.
- **No Coldcard blog.** Founder declined on the grounds of not relishing others' misfortune.
- **Arjen's 4 duplicate Telegram records stay as they are.**
- **Log-defect disclosure stays internal**, out of all customer-facing copy.

## Traps that cost time today

- **Spaces in the project path break `mm-snap build`.** It URL-encodes `Side SaaS Hustle` and
  cannot find its own eval worker. Build in a space-free directory and copy back `dist/` **and the
  rewritten manifest**, since the tool edits the manifest in place.
- **A grep for `logger.(info|warning|error|debug)` misses `logger.exception`.** Left 7 plaintext
  PII lines after I had announced the fix.
- **MetaMask's "not on the allowlist" error means you are talking to stable MetaMask, not Flask.**
  Flask has no allowlist. The two cannot both be enabled in one browser profile.
- **EVM addresses must be lowercased before use as a storage key.** Otherwise one row per casing
  variant and every address looks new.
- **`except botocore.exceptions.ClientError` when botocore is not imported** raises NameError
  while handling the exception.
