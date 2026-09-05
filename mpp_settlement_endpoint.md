# The MPP settlement endpoint -- built 2026-09-04

One endpoint, on Stripe's machine-payments rail, alongside the 28 that already collect on the
existing one. This is the "single endpoint" `miniapp_discovery_and_stripe_choice.md` section 7 asked
for, built rather than described, because the thing Stripe's own team responds to is a live endpoint
on their rail and not an account of one.

    POST /v1/mpp/mcp-registry-risk    $0.35 USDC on Base, settled through Stripe
    GET  /v1/mpp                      descriptor: price, network, which rail is active

## First, the merge command that failed, and why

The command was right and the clone was not. `git merge` refused with:

    error: The following untracked working tree files would be overwritten by merge:
        agent_baiting_scope.md
        outreach_bot_prospects_curated.md

Both files are ON the branch, and both were ALSO saved by hand into `~/dev/relayshield` from a chat
paste -- which is the delivery process working exactly as CLAUDE.md describes it. Git will not
clobber an untracked file it did not write, so the two copies collided. The branch copies are
identical to what was pasted, so deleting the local ones loses nothing.

The other half of the failure follows from the first: `tools/stripe_machine_payments_probe.py` and
`tools/fd8_prepare_republish.py` did not exist on the Mac because the merge that would have brought
them in aborted. They exist, on that branch, and they are in this branch now.

**General form, worth keeping:** the chat-paste delivery rule and `git pull` collide by design.
Anything pasted into chat AND committed will block a later merge as an untracked file. Deleting the
hand-saved copy immediately before merging is the fix, not a `git checkout --theirs` dance.

## What was built

| File | What it is |
|---|---|
| `relayshield_mpp_settlement.py` | The handler. Self-contained Lambda, own package, own role. |
| `test_mpp_settlement.py` | 30 offline tests. No AWS, no network, no boto3. |
| `tools/mpp_settlement_selftest.py` | Puts the two Stripe call shapes in front of Stripe and prints its reply. |
| `tools/create_mpp_settlement_lambda.sh` | Creates the function, its IAM role, both gateway routes, proves the 402. |
| `iam_github_deploy_invoke.json` | Gained `relayshield-mpp-settlement`, so the first CI deploy does not repeat run 134. |

## Why it is a new file and not a branch in `relayshield_agentic_api.py`

`relayshield_agentic_api.py` carries **unreconciled live drift**. The deployed artifact holds a
branded `API_BASE_URL` and a Bundle D Stripe billing branch that main has never seen, recovered onto
`claude/recovered-live-relayshield-agentic-api` and still not merged. Adding an endpoint there and
giving that file a deploy path is the 2026-08-17 mistake exactly: the next repo-sourced deploy
deletes the live-only billing branch with no error anywhere.

A new file has no live counterpart, so it cannot drift from one. It also honours the isolation
mandate that file already states for itself -- new, unproven payment logic gets its own package so a
bug in it cannot regress the endpoints collecting money today.

The **detector is imported, not copied.** `_assess()` calls
`relayshield_agentic_api.handle_mcp_registry_risk`, and the deployer's `resolve_deps` packages it
automatically (its grep is `^[[:space:]]*(import|from) relayshield_`, so the indented import inside
the function is still picked up -- checked against that grep, not assumed). This repo already
carries four copies of one pattern table that must agree with nothing checking that they do. It does
not need a fifth. The dependency is one-directional: this module needs the detector, the detector
does not need this module.

## What "Stripe's rail" actually changes

Nothing about the protocol. The agent still gets a 402, still signs an EIP-3009 authorisation, still
retries with proof. What changes is where the money lands:

    today      agent -> USDC on Base -> PayAI/CDP facilitator -> our Coinbase wallet
    this file  agent -> USDC on Base -> facilitator -> a Stripe crypto deposit address,
               recorded as a PaymentIntent, settling into the Stripe balance next to the
               subscriptions, with the same reporting, payouts, refunds and tax treatment

## The rail is not enabled yet, and the code assumes that

Stripe crypto reads `Ineligible` on `acct_1TGqqsL2dcjOeFiY` as a staged-rollout gate. So every
Stripe call is best effort and falls back:

- **Cannot mint a deposit address** -> the 402 quotes the existing wallet, `rail: "facilitator"`, and
  the endpoint collects on the rail that already works.
- **Cannot record the PaymentIntent** -> the caller still gets what they paid for, and the settlement
  row is written with `note: "stripe_record_failed"` and an empty `payment_intent`, so
  reconciliation is a query rather than an archaeology exercise.

`RELAYSHIELD_MPP_RAIL` decides: `facilitator` never calls Stripe at all (the setting it ships with),
`auto` prefers Stripe and degrades, `stripe` refuses rather than quietly using the wallet. A test
pins each of the three, including that the pinned facilitator makes **zero** Stripe calls.

An endpoint that 500s because a preview product is not switched on is worse than no endpoint.

## The two derived shapes are now VERIFIED, and one of them was wrong

Updated 2026-09-04. `docs.stripe.com` is still blocked from the container, but two
better sources are not, and neither had been tried:

- **`mppx` is on the npm registry**, which is reachable. It is Stripe's own reference
  implementation of MPP, shipped with readable source.
- **`github.com/tempoxyz/payment-auth-spec` is on raw.githubusercontent.com**, also reachable.
  It is the IETF draft `mppx` cites, co-authored by Tempo and Stripe.

Reading an implementation beats reading a blog. It settled every open question, and one of
the two derived shapes was wrong in three separate places.

| Thing | Derived (wrong) | Verified against mppx 0.9.2 |
|---|---|---|
| API version | `2026-05-27.preview` | **`2026-07-29.preview`** |
| PaymentIntent mode | absent | `payment_method_options[crypto][mode]` |
| PaymentIntent sub-object | `transaction_verification` | **`transaction_verification_options`** |
| Payment method types | absent | `payment_method_types: ["crypto"]` |
| Machine-payment tag | absent | `metadata[machine_payment] = "true"` |
| Deposit address | POST every time | **LIST first**, create only if none exists |
| Unit conversion | `round(units / 10^4)` | identical, independently confirmed |

The API version matters more than it looks: **a probe on the wrong preview version reports
"not enabled" for an account that is enabled.** `tools/stripe_machine_payments_probe.py`
carried the same wrong date, so its answer was never going to be trustworthy either. Both
are corrected.

The deposit-address fix is not cosmetic. POSTing unconditionally mints a fresh address every
time the in-process cache expires, and on Lambda that is every cold start, scattering machine
revenue across a growing set of addresses for no reason.

## MPP is not a JSON block. It is an HTTP authentication scheme.

The first version of this file emitted an invented `mpp` object in the 402 body and labelled it
`"version": "unverified"`. It was not merely unverified. It was **structurally wrong**: MPP does
not put its challenge in the response body at all.

MPP uses the `Payment` authentication scheme under RFC 7235. The challenge rides
`WWW-Authenticate`, the credential comes back in `Authorization`, and the receipt goes out in
`Payment-Receipt`:

    WWW-Authenticate: Payment id="<hmac>", realm="api.relayshield.net", method="stripe",
                      intent="charge", request="<base64url canonical JSON>"

The `id` is **HMAC-SHA256 bound to the challenge's own contents** — seven fixed pipe-delimited
slots, `realm | method | intent | request | expires | digest | opaque`, with absent fields as
empty strings so the slot count never moves. That binding is the difference between a payment
challenge and a suggestion: a client cannot alter the amount and still present an id we would
accept. The invented block had no binding at all. All of this is now implemented and pinned by
tests that assert the id changes when the amount, the realm or the secret changes.

## What is deliberately NOT implemented, and why the challenge is switched off

**We can issue a compliant MPP challenge. We cannot yet redeem an MPP credential.** The
credential is a Shared Payment Token, redeemed through Stripe, and SPTs are in private preview
on top of the crypto gate.

So `RELAYSHIELD_MPP_CHALLENGE` defaults to `off` and the 402 advertises only x402, which is the
rail we can actually honour. **Advertising a payment method we would then reject is worse for
the agent than never offering it** — it spends the agent's authorisation on a route that cannot
complete. Two tests pin this: MPP absent by default, and an unreachable Stripe never costing us
the x402 challenge.

`npx mppx@latest validate <url>` is the objective test of MPP compliance, it runs on the Mac,
and it is the acceptance criterion rather than our own reading of the spec.

## The money arithmetic, which has its own test class

USDC carries 6 decimals; Stripe wants an integer minor unit. `350000` atomic units is `35` cents. A
conversion wrong by a factor of ten is invisible until it appears in someone's ledger, so the tests
assert both the right answer and the two wrong ones.

A sub-cent amount rounds to `0` and is **not** floored up to one cent. That number is a record of
money that has already moved, and inflating $0.004 into $0.01 puts a figure into Stripe's own
reporting that never existed. The handler skips the PaymentIntent and flags the row instead, so the
residue is visible rather than invented.

The transaction hash is the idempotency key on the PaymentIntent. A facilitator retry, or a client
that pays once and calls twice with the same proof, must not produce two PaymentIntents for one
movement of money.

## Its own IAM role, with four permissions

CLAUDE.md's "one role per Lambda". `relayshield-breach-check-role-1sapnwdl` is at 10,127 of a hard
10,240-byte inline budget AND 10 of 10 managed slots. There is no room, and reaching for it is what
filled it. This function gets `relayshield-mpp-settlement-role` with exactly:

    logs:CreateLogGroup / CreateLogStream / PutLogEvents
    dynamodb:Query, GetItem   on relayshield_intel_iocs          (the detector's corpus lookup)
    dynamodb:PutItem          on relayshield_payg_settlements    (the settlement row)
    secretsmanager:GetSecretValue on relayshield/stripe_secret_key*

The create script rewrites that inline policy on every run rather than creating it once, so the
policy on the role is the policy in the file. A policy that drifts from the repo is what the DRIFT
RULE is about, and it applies harder to IAM than to code because a missing permission fails on
whichever code path needs it, whenever that path next runs.

## Why it is NOT in `deploy_lambdas.yml` yet

The deployer calls `update-function-code` on whatever `LAMBDA_MAP` names. Mapping a function that
does not exist in AWS turns the first push red with a `ResourceNotFoundException` that reads exactly
like a broken deploy and is not one. So: **create first, map second.** The create script's last
output is the mapping step, and the function is already in `iam_github_deploy_invoke.json` so the
first CI deploy does not repeat run 134's denied import probe.

The deployer's import probe was checked: `{"source": "ci.import-probe"}` has no path and no method,
falls through to the 404, and returns a real response. A test asserts that, because a raise there
reads as a broken deploy.

## Open questions this does not answer

1. **Does x402 or MPP settlement count toward early-adopter status?** Still Jake's to answer.
   The endpoint makes it concrete rather than hypothetical: there is a URL to point at.
2. **Can machine payments settle against an account that already runs metered subscriptions
   and an aggregate meter?** Unanswered, and it costs an environment-variable flip to find out.
3. **Redeeming a Shared Payment Token from Python.** The reference implementation is Node. This
   is the one genuine build left, and it is not a one-line fix.

## What the drift work alongside it closed

`relayshield_agentic_api.py` was reconciled the same session, and it was much smaller than
feared: **+22 / -1**, both hunks live-only. The branded `API_BASE_URL` with its reasoning, and
the Bundle D "Door 2" direct-Stripe billing branch that must sit above the `has_subscription`
test or the direct door bills nothing while the AWS door bills per call.

Main has been moved to the live bytes verbatim — a pure move, no edits — so live is now
byte-identical to main, and the function is mapped in `deploy_lambdas.yml` for the first time.
That ordering is the whole rule: recover, read, reconcile, then map.
