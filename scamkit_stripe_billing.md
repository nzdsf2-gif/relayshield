# Scam-kit Stripe billing — checkout sessions, webhook, meter events

Branch: `feature/stripe-checkout-metering` (2026-09-28). Not merged, not
deployed. Nothing here creates Stripe objects — the products, prices, and
meters were created on 2026-09-28 and verified read-only against the live
API (all active, correct event names, `count` aggregation, customer mapping
`by_id`).

## Why checkout sessions instead of payment links

Stripe Payment Links cannot carry metered prices: the API demands a quantity
on every line item, and metered prices reject quantities. The existing
`$199`-only payment link (`https://buy.stripe.com/5kQfZi7Yq4CNe56esn0Ny0k`)
stays as-is; metered tiers are sold through per-customer Checkout Sessions
created server-side.

## The flow

```
developer (has RS API key)
  │ POST /v1/billing/checkout-session {"tier": "monthly"|"payg"}
  ▼
Lambda → Stripe: POST /v1/checkout/sessions (subscription mode)
  line items: monthly = $199 base (qty 1) + overage (metered, no qty)
              payg    = fingerprint $0.50 + match $0.10 + campaign $5.50 (all metered, no qty)
  client_reference_id = caller's RS API key
  subscription_data[metadata] = {api_key, tier}
  │ returns {"checkout_url", "session_id", "tier"}
  ▼
developer completes checkout in the browser
  │ Stripe → POST /v1/billing/webhook  (checkout.session.completed)
  ▼
webhook verifies Stripe-Signature (HMAC-SHA256, 5-min tolerance), then
stamps the key record in relayshield_api_keys:
  stripe_customer_id, stripe_subscription_id, scamkit_tier, scamkit_subscribed_at
  │ later scam-kit calls: POST /v1/metered/scamkit-fingerprint|match|campaign-scan
  ▼
metered dispatcher sees scamkit_tier on the key record → skips the credit
check (scoped to the three scam-kit endpoints only) → handler runs →
on success, one meter event is posted:
  monthly → scamkit_monthly_execution (value=1; 500 included, then $0.40/unit)
  payg    → scamkit_payg_fingerprint | scamkit_payg_match | scamkit_payg_campaign (value=1)
  │ customer.subscription.deleted → tier cleared, key stops passing the gate
```

The x402 `/v1/payg/` rail is untouched — per-call on-chain billing never
reaches this code. The aggregate `relayshield_api_usage` meter is untouched —
scam-kit subscribers never post to it (the new branch sits above the credit
branch and the aggregate-meter fallthrough).

## Endpoints

| Endpoint | Auth | Body | Returns |
|---|---|---|---|
| `POST /v1/billing/checkout-session` | RS API key (`X-RS-API-KEY`) | `{"tier": "monthly"\|"payg", "success_url"?, "cancel_url"?}` | `{"tier", "checkout_url", "session_id"}` |
| `POST /v1/billing/webhook` | Stripe-Signature | Stripe event JSON | `{"received": true, "action": "activate"\|"deactivate"\|"ignore"}` |

Default `success_url`/`cancel_url` point at
`https://api.relayshield.net/developers?billing=...`; both are overridable
per request.

## Key-record fields (relayshield_api_keys)

Set only by the billing webhook, never by signup or admin edits:

- `scamkit_tier` — `"monthly"` or `"payg"`; presence is the subscription gate
- `stripe_customer_id` — kept after cancellation for history/lookups
- `stripe_subscription_id` — removed on cancellation
- `scamkit_subscribed_at` — ISO timestamp of activation

## Setup before this can go live (not done on this branch)

1. Register `POST /v1/billing/webhook` in the Stripe dashboard; copy its
   signing secret into Secrets Manager as
   `relayshield/stripe_billing_webhook_secret`. Until it exists, every
   webhook call returns 500 and Stripe retries.
2. The Lambda needs `relayshield/stripe_secret_key` (already exists) and
   DynamoDB write access to `relayshield_api_keys` (already has it).
3. API Gateway must route `/v1/billing/*` POST to the relayshield-api Lambda.

## Failure behavior

- Checkout creation failure → 502, no Stripe objects left behind.
- Bad webhook signature → 400, nothing written.
- Meter-event post failure → logged warning only; the execution already
  succeeded and is returned normally. Until the wiring is deployed, usage
  bills $0 — the meter events are the billing.
- Unknown webhook event types → 200 `{"action": "ignore"}` so Stripe stops
  retrying them.

## Files

- `relayshield_scamkit_billing.py` — all billing logic; pure functions are
  unit-testable, AWS/network calls take injectable clients. No boto3 clients
  at import time.
- `relayshield_api.py` — wires the two endpoints, the `scamkit_tier`
  subscription gate, and the post-success meter-event branch.
- `test_scamkit_billing.py` — 30 unit tests, no network/AWS.
  Run: `python3 test_scamkit_billing.py`
