# SIM swap in Crypto Shield Mobile — the gap, scoped

**Asked 2026-09-12: *"CS M: I want you to scope the work as i believe the SIM Swap is currently not
supported in this product which is a significant gap."***

**He is right, and it is worse than "not supported". The app COLLECTS the phone number, TELLS the
user what it is for, SELLS it on the paywall, CLAIMS it in the store listing, and ships the alert
card and the remediation guide for it — and the number never leaves the device.**

Everything below was read out of the code in this session. Nothing here is recalled.

---

## 1. WHAT IS ALREADY BUILT, WHICH IS NEARLY ALL OF IT

**The server half is complete and has been for a month.**

| Piece | Where | State |
|---|---|---|
| Enrolment endpoint | `relayshield_api.py` → `/v1/sim-swap/enroll` | live, key-gated |
| Confirm / withdraw | `/v1/sim-swap/confirm`, `/v1/sim-swap/withdraw` | live |
| The consent contract | `relayshield_sim_swap_consent.py` | the single writer of `sim_swap_monitoring` |
| The monitor | `relayshield_sim_swap_monitor.py` | EventBridge every 4 hours, Twilio Lookup v2 |
| Twilio US approval | ticket 28883049, 2026-09-12 | approved, so real verdicts flow |

**And most of the app half is built too.**

| Piece | Where | State |
|---|---|---|
| Phone capture | `SettingsScreen.tsx` → `PhoneManager` | writes SecureStore `cs_phone_number` |
| The API client call | `src/api/relayshield.ts:73` `checkSimSwap()` | **ZERO CALLERS** |
| The alert card | `components/AlertCard.tsx`, type `SIM_SWAP` | built |
| The remediation guide | `components/SimLockGuide.tsx` | built, carrier by carrier |
| Push delivery | `usePushNotifications.ts` → `/v1/app/register-push` | live |

**`cs_mobile` is already in `CONSENT_SOURCES`.** Somebody reserved the enum value for this surface
and the call was never written.

---

## 2. THE THREE DEFECTS, IN THE ORDER THEY BITE

### A. NOTHING ENROLS. The number is written to SecureStore and read by nothing.

`grep -rn "checkSimSwap" crypto-shield-app/` returns exactly one line: the definition. The phone
number is stored on the device and no RelayShield surface ever learns it, so
`scan_sim_swap_users()` — which filters on `sim_swap_monitoring == True` — has never had a Crypto
Shield Mobile user in its set.

**AND THIS WAS FOUND ON 2026-08-14 AND WRITTEN DOWN, IN THE FILE THAT WAS BUILT TO FIX IT.**
`relayshield_sim_swap_consent.py`'s own docstring, verbatim:

> *"Crypto Shield Mobile stored the number on-device and never sent it, so it enrolled nobody."*

That audit found four defects, one per surface. The shared consent module was written, and the
Telegram, WhatsApp and Stripe halves were wired. **This one was recorded as a finding and left.**
It is the "a doc claiming something is done is a lead, not a fact" rule pointed at our own audit:
the audit was right, the fix was partial, and the record reads as if it were complete.

### B. `checkSimSwap()` IS THE WRONG ENDPOINT ANYWAY, AND THIS IS THE TRAP

It posts to **`/v1/metered/sim-swap`**, which is a **one-shot paid lookup**: it answers "has this
number been swapped recently" once, bills $0.25, and enrols nothing. Wiring the function that
already exists would produce a button that charges the user per press and still never monitors
them.

**The endpoint this needs is `/v1/sim-swap/enroll`**, which is unmetered and puts the number into
the 4-hourly scan. Two endpoints with nearly the same name, one of which is already imported into
the app — this is exactly the "the endpoint that does X and the endpoint this client calls are
different questions" shape, and the wrong one is the one sitting in the file.

### C. AN ENROLLED APP USER STILL WOULD NOT BE TOLD

**The one that would have been discovered after shipping A and B, so it is named first instead.**

`relayshield_sim_swap_monitor.py` delivers over **WhatsApp** as the primary channel, with an **SMS
fallback** and a **Telegram signal** for users who have that channel. It sends **no Expo push**.
A Crypto Shield Mobile user has no WhatsApp session with us and usually no Telegram chat, so the
alert would be computed correctly, logged as sent, and reach nobody.

Push is fully built — `relayshield_push.py`, `/v1/app/register-push`, `getLastAlert` for the
authoritative-state read — and simply is not wired into this monitor.

**The join is not obvious and is worth writing down**, because the two tables use `user_id` to mean
two different things:

    relayshield_users            user_id = a uuid
                                 enrolled_by_account = the API KEY that enrolled
    relayshield_push_tokens      push_token (key)
                                 user_id = the API KEY          <-- these two

So the monitor finds the device by querying push tokens whose `user_id` equals the enrolled
record's `enrolled_by_account`. Reading either field as "the same user id" gives an empty result
and no error, which is the failure mode to guard against with a test rather than a comment.

---

## 3. THE CONSENT CLAUSE IS NOT OPTIONAL AND THE APP DOES NOT SHOW IT

`enroll(enrollment_type="self")` **raises** unless `consent_acknowledged is True`, and the code
comment above that check says why: *"Required rather than defaulted: this flag is what a carrier
audit rests on."* US carriers require specific wording, and the clause reads **"YOU authorize your
wireless carrier"** — the subscriber, which is why third-party enrolment needs a double opt-in.

Today `PhoneManager` shows one line: *"Used for SIM swap monitoring. Must include country code."*
That is a description, not an authorization. **The app must render the clause and require an
explicit tick before it may send `consent_acknowledged: true`**, and a screen that sends the flag
without showing the clause is worse than no feature, because it manufactures a consent record that
would not survive being read.

Self-enrolment on your own phone needs **no** confirmation SMS: `enrollment_type="self"` with the
acknowledgement returns `CONFIRMED` and monitoring starts immediately. The double opt-in path is
for enrolling somebody else, which the app must never do.

---

## 4. WHAT I RECOMMEND, AND IT IS THE SMALL VERSION

**Do A, B, C and the clause. Do not add a "check my SIM now" button.**

A one-shot metered check is the feature that looks obvious and is wrong here: it charges per press,
it answers about the past rather than watching, and it duplicates the thing the 4-hourly monitor
does for free once the number is enrolled. The product promise on the paywall is *monitoring*, so
build monitoring.

**Order, and each step is independently shippable:**

1. **Fix the claim first, today, at zero engineering cost.** Until this ships, the paywall sells
   "SIM swap monitoring" and the store listing claims "SIM-swap and breach exposure alerts" for a
   feature that enrols nobody. That is the half that is not merely missing but *sold*. Either the
   copy comes down or the feature goes in, and the feature is about three days.
2. **The app: consent UI + enrol call.** Replace the `checkSimSwap` helper with
   `enrollSimSwap(phone, apiKey)` posting `{phone, enrollment_type: "self", consent_source:
   "cs_mobile", consent_acknowledged: true}` to `/v1/sim-swap/enroll`. Render the carrier clause
   with a tick that gates the button. Handle `409 ambiguous` and the `ValueError` text as real
   states rather than a generic failure. Add `withdrawSimSwap` beside it: a monitoring feature with
   no off switch is not one we can ship under those Terms.
3. **The monitor: Expo push as a delivery channel**, joined as in section 2C, with the WhatsApp
   path unchanged for the users who have it. The alert body already exists; this is a second
   sender, not a second message.
4. **A test that the app's enrol call names `/v1/sim-swap/enroll` and not `/v1/metered/sim-swap`.**
   The wrong endpoint is one character of muscle memory away and both are live.

**Cost: about three days.** One for the app screen and its states, one for the push channel and the
join, half for the tests, half for the store and paywall copy.

**Who does it:** mine, in a session pointed at the app. `crypto-shield-app/` is in this repo, so
none of it needs the Mac. Shipping to the device needs an EAS build, which is Andrew's.

---

## 5. THE SCOPE LINE THAT MUST NOT BE MISREAD

**Twilio approved the United States.** A non-US number returns `error_code=60606` on a Twilio
**200**, and `handle_sim_swap` correctly turns that into a **503** rather than a verdict, and the
metered dispatcher only bills a 2xx so a non-answer is never charged. That is correct behaviour and
**must not be read as a regression** when the first non-US app user sees it.

What the app owes that user is a sentence, not a spinner: *"SIM swap monitoring is available for US
numbers today."* Otherwise the correct 503 renders as a broken feature, which is the
"we could not check" versus "it is fine" distinction the watchlist monitor already holds as a rule.
