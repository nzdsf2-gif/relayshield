# Handover, written end of 2026-08-08

Read `project_session_snapshot_2026-08-08` in memory first. This file is the task-level pickup.

## Start here tomorrow

**1. Build the MetaMask Snap.** Founder put it on deck and settled the open question:
**the user funds their own screens.** The Snap asks for the user's own RelayShield key or x402
wallet; we bundle no allowance. Transaction Insights only, which maps onto `/v1/payg/wallet-risk`
with zero backend work. Touch **no** key-management API and the mandatory third-party audit does not
apply. Full requirements in task #12.

**2. Run the $0.01 Bundle A test.** Still the only thing between Bundle A and going public.
Subscribe from `442429445748` to **`offer-d75uqa4lwqsuo`**, NOT the $150 public offer. Then verify a
key is provisioned with `aws_product_code=cvfvhwhmichl13kcuuutkbwmp` and `bundle_a_access=true`, all
6 Bundle A endpoints 200, all Bundle D endpoints 402, and that a metering record actually lands. The
API deploy that was blocking this is **done**.

**3. Then `UpdateVisibility` to Public** as a separate change set. AWS serialises submissions per
seller account, so it cannot ride along with anything else.

## Waiting on the founder, nothing else needed from us

- **Twilio Request# 28883049**, submitted 2026-08-08 06:46 PDT, open with their onboarding team.
  Everything is filed. Until it is approved `/v1/metered/sim-swap` returns 503 on every call by
  design, which is correct but means a Bundle A dimension visibly does not work. Weigh that before
  going public.
- **Verdict Watch cannot deliver yet.** `relayshield-verdict-watcher` is deployed and its EventBridge
  schedule is deliberately **DISABLED**. It needs `RELAYSHIELD_INTERNAL_API_KEY` provisioned as a
  **non-billed** key, because the customer pays a flat licence and we absorb the re-screen cost.
  Provisioning a key with billing implications is a founder decision. It fails safe until then.

## Shipped today, all verified live

| | |
|---|---|
| Privacy policy + ToS | SIM swap disclosure, telecom provider named, US-only data location |
| CS Mobile legal links | repointed at source; **installed app still has dead links until v1.5.0 ships** |
| `handle_sim_swap` | no longer returns a false clean; 503 on `error_code`, and 503 is not billed |
| Freshness contract | all 6 Bundle A endpoints, plus `degraded` on domain and crypto-intel |
| Verdict Watch API | `/v1/watch`, `/v1/watch/list`, `/v1/watch/remove`, gated on `watch_access` |
| `/.well-known/x402.json` | 28 resources, built from the same code as the live 402 |
| 402 Index | domain verified, all 28 listed and healthy |
| agent-tools.cloud | x402 service live, MCP server indexed |
| rsscan | own landing banner, `--org` default-on, exposure line in terminal output |
| Two unpriced endpoints | $0.35, closing a live revenue leak |
| `@relayshield` | reserved at cloudflare.pay |

## Open decisions, none blocking

- **#19 SKU audit.** Verdict Watch has no price and should probably never get one. Nine ways to pay
  against zero paying customers. Recommendation on file: attach it to Bundle A/D and the screening
  endpoints rather than shipping a tenth menu item.
- **#22** is the mechanical half of that: set `watch_access=true` at fulfilment. No AWS change set,
  so it cannot reopen either audit. Naming it in the listing text WOULD trigger one.
- **#14** age-scaled TTLs. Needs an upstream call per request we do not currently make, so it is a
  pricing decision. Reasoning is in the comment above `_FRESHNESS_PROFILES`.
- **#16** the five-step LLMjacking attack chain onto `/developers` and the MSP brief. Approved, not
  started. Positioning copy only, explicitly NOT a licence to build model-layer features.
- **#13** 26 double-hyphens in the published API reference.

## Traps that cost time today

- **A 404 body tells you whose 404 it is.** The watch routes returned "unknown endpoint" from our own
  Lambda, not API Gateway. Reading the body found it in seconds; the status code alone would have
  sent me to the wrong system.
- **The API Lambda role has no blanket DynamoDB access**, only per-table ARNs. A new table needs its
  own grant or you get AccessDenied at runtime, not at deploy.
- **Verify PDFs with a non-macOS rasterizer.** ReportLab's default Helvetica is not embedded and
  renders as tofu boxes under `pdftocairo` while looking perfect in Preview.
- **Directory health probes want a full resource URL.** Probing the bare domain root reports
  "degraded" because the root is not a paid resource.
- **`searchOpenIndexes` ignores its query** and returns the same 37 results for anything. Check the
  402index.io UI instead.

## One correction to carry forward

I claimed rsscan had produced "zero org signals in a year of installs" and reasoned from it. The org
signal shipped **2026-08-02**, six days before. Six days of zero is not evidence of anything. The
changes made on the back of it stand on their own merits, but do not repeat the claim.
