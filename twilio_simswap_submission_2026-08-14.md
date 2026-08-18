# Twilio SIM Swap: page 3 copy and ticket reply

> # STOP. Do not send this reply yet.
>
> **Found 2026-08-14 while capturing the page 3 screenshot: the phone number entered in Crypto Shield
> Mobile never reaches the backend.** The screenshots pack shows the mobile app as the consent and
> collection flow, but numbers collected there are never looked up. Full evidence in the section
> "The blocker" at the bottom. The terms deploy is done and unaffected; this is about the screenshots.

*Ticket #28883049, Avinash Sawant, Twilio Account Security onboarding. Drafted 2026-08-14.*

**Answer to "does this satisfy his request": yes, once two things are true.** The consent language is
written but **not yet deployed**, and page 3 needs one screen capture that does not exist yet. Both
are listed in the checklist at the bottom. Do not send the reply before them.

---

## Page 3 copy, for the screenshots PDF

Matches the voice of the existing two sections. Header and footer lines are the same as pages 1 and 2.

> **RelayShield LLC - SIM Swap Monitoring - User Experience Screenshots**
> Application: Crypto Shield Mobile v1.5.0 (net.relayshield.cryptoshieldmobile) | Twilio Account SID: ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
>
> ### 3. Where the Lookup SIM Swap API call is made
>
> The Lookup SIM Swap call is made server side by RelayShield. It is not made by the mobile
> application, and there is no screen from which a user triggers a lookup.
>
> The call is made by `relayshield-sim-swap-monitor`, a scheduled backend job. On each run it selects
> only those accounts that have SIM swap monitoring enabled and a stored E.164 number that the
> account holder entered themselves, and calls:
>
> `GET https://lookups.twilio.com/v2/PhoneNumbers/{number}?Fields=sim_swap,line_type_intelligence`
>
> Only the phone number is sent. No name, email address, wallet address, or other account data
> accompanies the request.
>
> No lookup is ever performed against a number that has not been enrolled through the screen shown in
> section 1. The phone number step is optional and skippable, and if a user skips it, no Lookup call
> is made for that account at any point.
>
> The screen below is Settings, Phone Number, where an enrolled number is reviewed, changed, or
> removed. Removing the number withdraws consent and stops all further lookups immediately.
>
> **[SCREEN CAPTURE: Settings, Phone Number section]**
>
> *Unmodified screen capture from Crypto Shield Mobile v1.5.0 running on Android.*

### The capture you need

**Settings, Phone Number section** in Crypto Shield Mobile. Rendered by `PhoneManager` in
`crypto-shield-app/src/screens/SettingsScreen.tsx:388`. It shows the section title, the description
"Used for SIM swap monitoring. Enter the phone number associated with your crypto exchange accounts",
the input, and the Save button.

**Use a real but non-personal number**, or blur it. Do not put the founder's own number into a
document going to a carrier review queue.

### Optional page 4, if you want to strengthen it

A capture of a `SIM_SWAP` alert card with its "Lock SIM with carrier" action. Twilio did not ask for
it, so it is not required. It would evidence the "solely to... prevent fraud" clause in the consent
language by showing the fraud-prevention purpose actually being served. **Skip it if it costs more
than ten minutes**, because an unrequested extra is not worth delaying the reply.

---

## FINAL ticket reply, ready to send 2026-08-14

Both items are now genuinely satisfied. The pack is rebuilt around the live WhatsApp consent flow,
4 pages, fonts embedded.

```text
Hi Avinash,

Thank you for the review. Both items are addressed.

1. Required consent language

The consent language is now live in our Terms and Conditions at https://terms.relayshield.net, in section 1a, SIM Swap Monitoring. It appears verbatim, with RelayShield LLC as the customer name:

"You authorize your wireless carrier to use or disclose information about your account and your wireless device, if available, to RelayShield LLC or its service provider for the duration of your business relationship, solely to help them identify you or your wireless device and to prevent fraud. See our Privacy Policy for how we treat your data."

The same language is also shown in full to the user at the moment they are asked for permission, so they see it without having to open the link.

2. Screenshots of the user flow

Attached, covering the three stages you asked for:

  Section 1: where the user grants consent. The prompt quotes the carrier language verbatim and links to the Terms.
  Section 2: where the user accepts, and monitoring is enabled.
  Section 3: where the user withdraws consent and lookups stop.
  Section 4: where the Lookup SIM Swap call is made.

Two points that may help the carrier submission:

The Lookup call is never made from the handset. It is made by our backend on a schedule, only for numbers whose own owner has granted consent, and we send the phone number alone with no other account data attached.

Consent is recorded per number rather than per account, so for any individual number we can show the state, which surface collected the consent, the method, the timestamp, and which version of our Terms was in force at the time. A number is only ever queried while that record shows consent as confirmed.

Happy to provide anything else you need.

Thanks,
Andrew Gibbs
RelayShield LLC
```

**Why the extra paragraph on per-number consent is there.** A carrier's real question is not "do you
have terms", it is "show me that this number's owner authorised this". Saying up front that we can
answer that per number is what turns a complete submission into an approvable one.

## Superseded draft, kept for reference: ticket reply

```text
Hi Avinash,

Thank you for the review. Both items are addressed.

1. Required consent language

The consent language is now in our Terms and Conditions at https://terms.relayshield.net, in section 1a, SIM Swap Monitoring. It appears verbatim, with RelayShield LLC as the customer name:

"You authorize your wireless carrier to use or disclose information about your account and your wireless device, if available, to RelayShield LLC or its service provider for the duration of your business relationship, solely to help them identify you or your wireless device and to prevent fraud. See our Privacy Policy for how we treat your data."

Users accept these Terms on the first screen of onboarding, before the phone number step and before any lookup can take place.

2. Screenshots of the user flow

Attached is an updated PDF covering the three stages you asked for:

  Section 1: where the user provides the phone number. This step is optional and can be skipped.
  Section 2: where the user accepts our Terms of Service and Privacy Policy.
  Section 3: where the Lookup SIM Swap call is made, plus the screen where a user can remove the number and withdraw consent.

One clarification that may help the carrier submission: the Lookup call is never made from the handset. It is made by our backend on a schedule, only for numbers the account holder entered themselves, and we send the phone number alone with no other account data attached.

Happy to provide anything else you need.

Thanks,
Andrew Gibbs
RelayShield LLC
```

### Two deliberate choices in that reply

**It answers only the two things raised.** No status updates on anything else, no volunteering of
unrelated detail. Same discipline as any reviewer reply: an auditor asked two questions, so they get
two answers.

**It quotes the consent language in full in the body.** The reviewer can then approve without opening
the link, which removes a round trip from a queue that has already cost weeks.

---

## Before sending. All three, in order.

1. **Deploy the terms.** `cloudflare_worker_terms.js` is changed locally and syntax-checked, and it
   is **not live**. The new paragraph sits directly after the existing section 1a text.
2. **Verify `https://terms.relayshield.net` actually renders the paragraph.** Load the real URL and
   read it. Claiming to a reviewer that language is published when the page does not show it is the
   one failure that would cost real credibility here, and reviewers check.
3. **Capture the Settings screen and rebuild the PDF** with the new section 3.

**Confirm before step 1:** that **RelayShield LLC** is the exact registered entity name. Carriers
approve against the name in the clause, so a mismatch with the entity on the Twilio account is worth
catching now rather than after another review cycle.

---

# The blocker

**A phone number entered in Crypto Shield Mobile is stored on the device and never sent anywhere.**
Traced end to end 2026-08-14 while capturing the page 3 screenshot.

| Step | Evidence |
|---|---|
| The app saves the number | `SettingsScreen.tsx:214` `savePhone()` writes `SecureStore.setItemAsync(PHONE_STORE, clean)` and nothing else |
| It is never read for sending | `PHONE_STORE` (`cs_phone_number`) appears in exactly three places, all in `SettingsScreen.tsx`: the constant, one read, one write |
| The API client has a method for it | `relayshield.ts:73` `checkSimSwap()` exists and **is never called from anywhere in `src/`** |
| The one call that does sync to the backend omits it | `registerPushToken()` sends push token, wallet addresses, NFT collections and optionally `telegram_id`. **No phone number** |
| The monitor reads a different source | `scan_sim_swap_users()` scans the users table for `sim_swap_monitoring == True` |
| Which is set by two things, neither of them the app | `relayshield_stripe_webhook.py:367` and `relayshield_whatsapp_webhook.py:1714` |

**Conclusion: the mobile app is a dead end for SIM swap.** A user completes onboarding step 3, enters
their number, and nothing is ever enrolled, looked up, or alerted on. Enrollment happens only via
**Stripe subscription signup** and **WhatsApp**.

**This is a third independent defect**, on top of the two already recorded in
[[project-sim-swap-never-worked]].

## Why it blocks the submission specifically

Pages 1 and 2 of the screenshots pack present Crypto Shield Mobile as the flow where the user
provides the number and accepts the terms. Page 3 would describe the Lookup call. **Those two halves
do not connect.** The numbers a carrier would be approving lookups for do not come from the flow
being shown to them.

Writing "the call is made for numbers the account holder entered on the screen in section 1" would be
false. This is a carrier compliance reviewer, and consent provenance is the entire thing they are
checking.

## It is worse than the app gap. Neither working path captures consent.

Checked after finding the app gap, because the obvious fallback was "document the flow that does
work". That fallback does not survive inspection.

**`sim_swap_monitoring = True` is set in exactly two places.**

**1. `relayshield_whatsapp_webhook.py:1714`, inside `create_employee_record()`.** This is an **admin
adding another person's phone number** via `ADD +1XXXXXXXXXX Name`. It enrolls that number for SIM
swap lookups.

That contradicts RelayShield's own published documents:

| Document | What it says |
|---|---|
| Terms 1a | "You may not enroll a number belonging to anyone else" |
| Privacy 2 | "we never accept a number submitted by one person about another" |
| Privacy 4 | "You consent to this monitoring when you enroll the number, on a screen that states this purpose" |

And it is the precise thing the carrier clause is about. "**You** authorize your wireless carrier"
means the subscriber authorizes. An admin adding an employee is not that, unless the employee
separately consented, and **no consent capture exists on that path**: grepping the WhatsApp webhook
for consent, authorize, "you own" or terms returns nothing relevant.

**2. `relayshield_stripe_webhook.py:367`**, on subscription creation, using the phone from checkout.
Defensible in principle, since the subscriber gave their own number. But there is **no
`consent_collection`, no `terms_of_service` acceptance and no `phone_number_collection`** configured
anywhere in the Stripe checkout code, so there is no recorded acceptance to point a carrier at.

**Net position: the only surface with a real consent UI is the one whose numbers are never used, and
the two surfaces whose numbers are used have no consent capture.** That is the finding, and it is
larger than the ticket.

## Three ways forward

**Option 1 is dead** now that the consent check came back negative. Documenting the Stripe or
WhatsApp path would show a carrier a flow with no recorded consent, and in the employee case a flow
that enrolls third parties. That is worse than saying nothing.

**Recommended: make Crypto Shield Mobile the enrollment path, because it is the only surface that
already has the consent UI.** It states the purpose on the number-entry screen, it gates on Terms
acceptance beforehand, and the Terms now carry the carrier clause. Wiring it up makes pages 1 and 2
of the pack **true** rather than aspirational, and page 3 then describes a real chain.

### The work, in dependency order

**A. Backend enrollment endpoint.** New route in `relayshield_api.py`, e.g.
`/v1/app/enroll-sim-swap`, that takes an E.164 number plus an explicit consent flag and writes a
`USERS_TABLE` record matching the shape the monitor already reads:

```
user_id, phone_encrypted, phone_hash, sim_swap_monitoring=True,
active=True, created_at, updated_at
```

This keeps **one** scan for the whole service, which is the right shape:
`scan_sim_swap_users()` stays untouched and picks up app users automatically.

**Two things to get right.**
`relayshield_api.py` has **no phone encryption helpers today**; `encrypt_phone` and `hash_phone` live
in `relayshield_stripe_webhook.py:295-301` and use KMS. So the API Lambda needs those helpers **and**
`kms:Encrypt` on its execution role. Check whether that role is the one already at the 10,240-byte
inline policy ceiling, in which case the grant must be a customer-managed policy.
And the endpoint must **update rather than duplicate** when the user already has a record from a
Stripe subscription, or this creates the same duplicate-record mess as the Telegram case.

**B. Withdrawal.** Removing the number in Settings must clear `sim_swap_monitoring`. Consent that
cannot be withdrawn is worse than no consent, and both published documents promise withdrawal.

**C. App change and release.** `savePhone()` calls the endpoint after storing locally. This is the
expensive step, and it is unavoidable: the app is compiled, and no existing call carries a phone
number.

**D. Then the screenshots and the reply.** Both of Avinash's questions get answered together.

### The employee-add path is a separate decision, and it is urgent

Either capture the employee's own consent before their number is ever enrolled, or stop setting
`sim_swap_monitoring` on employee records. **Leaving it as is means looking up third-party numbers
against a carrier consent clause that does not cover them**, while the published Terms say it does
not happen.

## Why this matters beyond the ticket

`/v1/metered/sim-swap` is a live paid Bundle A endpoint at $0.25 that currently returns 503, and SIM
swap detection has never worked in production. This ticket is the remaining external blocker on that.
