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

Both files are ON the branch, and both were ALSO saved by hand into `~/Side SaaS Hustle` from a chat
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

## Two shapes that are DERIVED, not verified, and the script that settles them

`docs.stripe.com` is blocked from the container. So the parameter names for
`POST /v1/crypto/deposit_addresses` and for the `transaction_verification` PaymentIntent come from
the reading in `miniapp_discovery_and_stripe_choice.md` section 7 of Stripe's published pages, not
from the API reference. **A derived name is a guess with good manners.**

Both are isolated in single builder functions -- `stripe_deposit_address_params` and
`stripe_payment_intent_params` -- with no branching, so correcting one is a one-line edit.
`tools/mpp_settlement_selftest.py` posts exactly those dicts and prints Stripe's own reply. Stripe
names a rejected parameter precisely, so one run either confirms the shape or hands over the
corrections.

The same honesty applies to the `mpp` block in the 402 body: the MPP specification is not reachable
from the container either, so that block reports `"version": "unverified"` and says in its own
`note` that the `x402` block beside it is authoritative. A test asserts it does not claim a version
it has not read, and another asserts the two blocks quote the same price -- two blocks disagreeing
about a price in one 402 is worse than one block.

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

1. **Does x402 settlement count toward early-adopter status?** Still carried, still Jake Lamoine's to
   answer. This endpoint makes the question concrete rather than hypothetical: there is now a live
   endpoint to point at.
2. **Can machine payments settle against an account that already runs metered subscriptions?**
   Unanswered. The endpoint is built so that finding out costs an environment-variable flip.
3. **The exact MPP wire schema.** Unverified, flagged in the code and in the response body.
