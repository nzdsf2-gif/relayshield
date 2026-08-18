# SIM swap enrollment: one consent service for every RelayShield product

*Design 2026-08-14, answering four questions. Context and the defects that forced this:
`twilio_simswap_submission_2026-08-14.md`.*

## The shape, in one line

**Build a product-agnostic enrollment service, not an app endpoint, and record consent provenance in
the record itself.** Everything else follows from that.

---

## Q1. Does this make it available to every RS product? Only if built this way.

**Not if it is `/v1/app/enroll-sim-swap`.** That would be a third enrollment path beside the two that
already exist, and a third copy of the same bug. The project's own history is explicit that
duplicated code means duplicated defects, and SIM swap has already been fixed twice in two places.

**Build `POST /v1/sim-swap/enroll`, product-agnostic**, then **migrate the two existing direct
writers to call it**:

| Today | After |
|---|---|
| `relayshield_stripe_webhook.py:367` writes `USERS_TABLE` directly | calls the enrollment service |
| `relayshield_whatsapp_webhook.py:1714` writes `USERS_TABLE` directly | calls the enrollment service |
| Crypto Shield Mobile writes nothing | calls the enrollment service |
| Telegram, web signup, API customers | call the enrollment service |

**That migration is the requirement**, not an optional tidy-up. Without it there is no single place
where consent is recorded, and no single answer to a carrier asking "show me consent for this
number".

**The monitor does not change at all.** `scan_sim_swap_users()` already scans one table for
`sim_swap_monitoring == True AND active == True`. Every product's enrollments land in that one scan,
which is exactly the shared-consumption property already in place. The gap was never the scan, it was
that there was no shared way in.

---

## Q2. Does this block behind Solana dApp Store review? No, and do not design it so it does.

**Going Crypto Shield Mobile first would put two external approval queues in series**: the dApp Store
review of v1.6.0, and then Twilio's carrier approval. dApp Store reviews do not transfer between
versions, so that is an unbounded wait on the critical path of a revenue blocker.

**Decouple them.** Once consent capture and enrollment live server-side, the fastest
consent-capturing surface does not have to be the app:

- a **WhatsApp consent prompt** before enrollment, deployable today
- the **Telegram bot**, deployable today
- a **web enrollment page** on Cloudflare, deployable today

Any of those ships in hours and needs no store review. **Twilio's approval then rests on a flow that
is actually live**, which is the only kind worth submitting. Crypto Shield Mobile adopts the same
endpoint in v1.6.0 whenever it clears review, and nothing about the Twilio package depends on that
date.

**This also fixes the honesty problem.** Submitting app screenshots for a build that is not published
would show a carrier a flow that is not the one producing the numbers being looked up.

---

## Q3. Encryption in transit. Already enforced. The real risks are elsewhere.

**In transit is done.** `api.relayshield.net` has a minimum TLS policy of **TLS_1_2**, verified
2026-08-14. Any client calling the enrollment endpoint gets that automatically. No app-layer
encryption is warranted on top, and adding it would introduce key management for no gain.

**Three things that must be explicit in the implementation**, because these are where phone numbers
actually leak:

1. **The number goes in the POST body, never a path or query parameter.** Query strings land in
   access logs, proxies and browser history.
2. **Every log line uses the existing `_redact()` helper** at `relayshield_api.py:518`, which emits a
   salted non-reversible stand-in. This codebase has already had plaintext PII sitting in CloudWatch
   with unlimited retention; that must not be reintroduced by a new endpoint.
3. **At rest, use the same KMS `encrypt_phone` / `hash_phone` the other writers use**
   (`relayshield_stripe_webhook.py:295-301`), so the monitor's existing `decrypt_phone` can read it.

**The one real dependency:** `relayshield_api.py` has no encryption helpers today, so the API
execution role needs `kms:Encrypt`. **Check whether that role is the one already at the 10,240-byte
inline policy ceiling**, in which case the grant has to be a customer-managed policy.

---

## Q4. Employee consent. Yes, required, and it is what makes the package approvable.

**Recommended, and not as a nicety.** A carrier's question is not "do you have terms", it is "show me
that this specific number's owner authorised this". An admin adding an employee cannot answer that.

**Double opt-in, which the state machine gives you for free:**

| Enrollment type | What happens |
|---|---|
| **Self-enrollment**, person enters their own number on a screen showing the carrier clause | consent recorded at that moment, `sim_swap_monitoring = True` immediately |
| **Third-party**, admin adds an employee | record created with `sim_swap_monitoring = False` and `consent_state = PENDING`, a confirmation message goes to that number, and **only the recipient's own confirmation flips it to True** |

**The monitor needs no change to support this.** A pending record simply does not match
`sim_swap_monitoring == True`. That one filter already means "consented", which is why this design
fits without touching the scan.

**It also resolves a live contradiction.** Terms 1a says "You may not enroll a number belonging to
anyone else" and Privacy 2 says "we never accept a number submitted by one person about another",
while `create_employee_record()` does exactly that today. Either this changes or the published
documents are false.

**Until it ships, the safe interim is to stop setting `sim_swap_monitoring` on employee records.**
That costs a feature nobody can currently use anyway, since lookups return 503, and it removes the
contradiction immediately.

---

## The record shape

Extends what the monitor already reads, adding provenance:

```
user_id
phone_encrypted        KMS, same helper as the existing writers
phone_hash             for dedupe and lookup without decrypting
sim_swap_monitoring    True only when consent is confirmed
active
consent_state          CONFIRMED | PENDING | WITHDRAWN
consent_source         cs_mobile | whatsapp | telegram | web | stripe_checkout
consent_method         self_entry | double_opt_in_reply
consent_at             timestamp
consent_terms_version  which Terms text was accepted
created_at, updated_at
```

**`consent_terms_version` is the field that makes a carrier audit answerable later.** The Terms
gained the carrier authorization clause today; without a version stamp there is no way to show which
numbers were enrolled under which wording.

## Withdrawal

`POST /v1/sim-swap/withdraw` sets `consent_state = WITHDRAWN` and `sim_swap_monitoring = False`.
Both published documents promise withdrawal at any time, and consent that cannot be withdrawn is
worse than none.

## Two traps

**Do not duplicate an existing user.** A Crypto Shield Mobile user may already have a `USERS_TABLE`
record from a Stripe subscription. Look up by `phone_hash` first and update. This project already has
a live case of four duplicate records for one person.

**Do not let the app be the only writer of consent.** The point of the shared service is that consent
is recorded server-side, once, regardless of which surface collected it.

---

# BUILT AND DEPLOYED 2026-08-14

`relayshield-api` `2026-08-14T23:31:08Z`, Active, Successful. **36/36 state machine tests pass.**

| Endpoint | Purpose |
|---|---|
| `POST /v1/sim-swap/enroll` | self or third_party enrollment, records consent provenance |
| `POST /v1/sim-swap/confirm` | double opt-in completion, the only way third_party becomes monitored |
| `POST /v1/sim-swap/withdraw` | withdrawal, promised by both published documents |

**All three require a valid API key.** This was not true in the first deploy and it mattered: an
unauthenticated call created a live monitored record during smoke testing. The record was deleted,
the check added, and the fix verified live returning 401. Tests now cover it.

**No IAM work was needed.** The API role already carries `kms:Encrypt` on the exact key
`alias/relayshield-data-key` resolves to, and DynamoDB read/write plus the `phone_hash-index` GSI all
simulate as allowed. Worth noting the role sits at **10,127 of 10,240** inline policy bytes, so any
future grant on it must be a customer-managed policy.

**`create_employee_record()` no longer sets `sim_swap_monitoring = True`** (`relayshield_whatsapp_webhook.py`).
It writes `False` with `consent_state = PENDING`. **Not yet deployed**, that Lambda is a separate
push.

## What production actually looks like right now

| Measure | Value |
|---|---|
| User records | 12 |
| Employee (third-party) records | 2 |
| **Numbers currently monitored** | **1** |

**The single monitored number is `82f507ad-e7c8-43a7-b1a6-c4eb79128d53`, and it is an employee
record** created by admin `user-onboard-test-001`, the stale onboarding test record. It has no
`consent_state`, no `consent_source`, and no recorded consent of any kind.

**So the entire monitored set today is one third-party enrollment with no consent provenance.** That
is the exposure, and its small size is the good news: remediation is one record, not a migration.

**Recommended before Twilio approval lands:** withdraw that number, then re-enroll it through
`/v1/sim-swap/enroll` so it carries real consent and a terms version. Not urgent while lookups return
503, but it must happen before they start succeeding. **Left for the founder to action rather than
done unilaterally**, since it is live data and possibly his own number.

---

# COMPLETE: all four surfaces migrated 2026-08-14

**One shared module, `relayshield_sim_swap_consent.py`, imported by every Lambda that can enroll a
number.** Four copies of the write meant four different bugs, one per surface. This is the one copy,
and it is the only thing permitted to set `sim_swap_monitoring`.

Verified in the deployed artifacts: all three Lambdas that need it carry an **identical** copy,
md5 `b988be3e53c9`, matching local.

| Lambda | Deployed | Change |
|---|---|---|
| `relayshield-api` | 00:09:17Z | enroll / confirm / withdraw endpoints, delegating to the module |
| `relayshield-telegram-webhook` | 00:09:24Z | **fourth defect fixed**, see below |
| `relayshield-whatsapp-webhook` | 00:09:32Z | new consent step, employee path no longer auto-enrolls |
| `relayshield-stripe-webhook` | 00:09:39Z | no longer sets the flag off an unconsented checkout |

## The fourth defect, found while wiring Telegram

**Telegram had the best consent UX of any surface and enrolled nobody.** `handle_phone_confirm()`
wrote `phone_encrypted` and `phone_hash`, then sent the user **"✅ SIM swap monitoring activated"**,
and never set `sim_swap_monitoring`. The monitor filters on exactly that flag, so every Telegram user
who completed onboarding was told they were protected and was watched by nothing.

That is the same false-assurance family as the original two defects, and it was the only one that
said so out loud to the user.

Both Telegram and WhatsApp now refuse to claim protection they did not switch on: if enrollment
fails, the message says so plainly rather than showing the tick.

## What each surface does now

| Surface | Consent event | Type |
|---|---|---|
| **Telegram** | `request_contact` shares the user's OWN number, then a Yes/No that now shows the carrier clause | self |
| **WhatsApp** | new `AWAITING_SIMSWAP_CONSENT` state at the end of onboarding, YES/NO, clause shown in full | self |
| **Crypto Shield Mobile** | calls `/v1/sim-swap/enroll` once v1.6.0 ships | self |
| **Stripe checkout** | writes the number with `PENDING`, monitoring **off**. Consent is captured later in WhatsApp onboarding | none at checkout |
| **WhatsApp employee add** | creates `PENDING` only. Requires the employee's own confirmation | third_party |

**WhatsApp is the strongest provenance available.** The number enrolled is the one the reply arrived
*from*, so the person is consenting from the handset whose carrier would be queried.

## Verified live in production

Full lifecycle against `api.relayshield.net`, then the test record deleted:

```
third_party enroll  -> PENDING, monitoring False, 32-char token
confirm wrong token -> 403, stays off
confirm right token -> CONFIRMED, monitoring True
replay same token   -> 409
withdraw            -> WITHDRAWN, monitoring False
```

**40/40 unit tests pass**, kept in the repo as `tests_sim_swap_consent.py`. No IAM work was needed
anywhere: all three roles already had `kms:Encrypt` on the right key and Query on the GSI.

**Production now: 12 user records, exactly 1 monitored, and it carries `CONFIRMED` with
`consent_terms_version 2026-08-14`.** Every number in the monitored set has recorded consent.

# The Twilio submission workflow

Both of Avinash's questions get answered in one reply. Neither depends on Crypto Shield Mobile
v1.6.0 or on dApp Store review.

**Step 1. Ship one consent-capturing surface.** WhatsApp prompt or a web enrollment page, both
server-side, both deployable without store review. It must show the carrier authorization clause,
capture an explicit acknowledgement, and call `/v1/sim-swap/enroll`.

**Step 2. Remediate the one legacy record**, as above, so every monitored number has provenance.

**Step 3. Capture the three screens Twilio asked for**, from the surface shipped in step 1:
number entry, the consent acceptance, and the management screen where it can be withdrawn.

**Step 4. Add the enrollment architecture to the pack.** This is the part that makes it approvable
rather than merely complete. A carrier reviewer's real question is "can you show consent for this
specific number", and the answer is now yes, per record: `consent_state`, `consent_source`,
`consent_method`, `consent_at`, `consent_terms_version`.

**Step 5. Reply**, quoting the consent language in full (already live at terms.relayshield.net) and
attaching the rebuilt pack.

**Crypto Shield Mobile adopts the same endpoint in v1.6.0 whenever it ships.** Until then CS Mobile
users who enter a number get no monitoring, which is a real gap, but it is the gap that already
existed silently. It is now visible and it does not block the audit.

## Order of work

1. Enrollment service plus consent state machine, `kms:Encrypt` on the API role.
2. Migrate the Stripe and WhatsApp writers onto it. **Stop setting `sim_swap_monitoring` on employee
   records in the same change.**
3. Ship one server-side consent surface, WhatsApp prompt or web page.
4. Screenshots of that live flow, then the Twilio reply answering both questions.
5. Crypto Shield Mobile v1.6.0 adopts the endpoint on its own schedule.
