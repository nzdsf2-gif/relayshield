# Capturing the SIM swap consent screenshots for Twilio

*Written 2026-08-14. For ticket #28883049, Avinash Sawant. The consent surfaces went live at
00:24:55Z (WhatsApp) and 00:25:03Z (Telegram).*

## Recommendation: WhatsApp

Three reasons, in order of weight.

1. **It is the strongest consent provenance available.** The number enrolled is the number the reply
   arrives *from*. The person consenting is holding the handset whose carrier we would query. No
   other surface can say that, and it is exactly what the clause means by "**you** authorize your
   wireless carrier".
2. **Twilio is the WhatsApp provider.** The auditor sees the consent happening on their own rail,
   with message SIDs in their own console if they want to check.
3. **Telegram would need production records disturbed.** The founder's Telegram record
   (`user-onboard-test-001`, chat `1729226804`) is deliberately inactive, and `get_user_by_chat_id`
   filters on `active == True`, so the bot will not recognise it. The only other Telegram users are
   **Arjen's four duplicate records, which are under a standing do-not-touch decision.** Reactivating
   the founder's record to take a screenshot means re-entering the state that caused double Twilio
   billing. Not worth it for a picture.

**Do it from the founder's own phone, on the number already in the system.**

---

## Before you start

**You need an active WhatsApp user record for the number you will message from.** Reply `HELP` to
the RelayShield WhatsApp number first. If you get the menu, you are recognised and can proceed. If
nothing comes back, stop and tell me, and I will check the record rather than have you guess.

**Turn off any screenshot beautifier.** Twilio wants unmodified captures, and the existing pack says
"Unmodified screen capture" on every page. Do not crop out the timestamp or the sender.

---

## The three captures

### Capture 1: the consent prompt

**Send `SIMSWAP`** to the RelayShield WhatsApp number.

You will get back the consent message containing the carrier authorization clause verbatim, the link
to https://terms.relayshield.net, and the YES / NO instruction.

**Screenshot the whole message**, including your own `SIMSWAP` above it so the auditor can see what
triggered it. **The clause must be fully readable and not cut off** — scroll so the entire quoted
paragraph is in frame, and take a second shot if it spans two screens.

> This command exists as of today. It was referenced in five user-facing messages before it was
> implemented, which was itself a defect. It is now the supported way to re-show the prompt, so this
> capture is repeatable rather than a one-shot during onboarding.

### Capture 2: consent given

**Reply `YES`.**

You will get: *"✅ SIM swap monitoring is on for this number."* plus the STOPSIM instruction.

**Screenshot it with the previous message still visible if possible.** The pairing of the clause and
the affirmative reply in one frame is the single most useful image in the pack.

### Capture 3: withdrawal is real

**Send `STOPSIM`.**

You will get confirmation that monitoring is off and lookups have stopped.

**Screenshot it.** This matters more than it looks: both the Terms and the Privacy Policy promise
withdrawal at any time, and an auditor who sees consent captured but no way to revoke it will ask.
Showing it working closes that question before it is asked.

**Then send `SIMSWAP` and `YES` again** to leave your number enrolled, if you want it monitored.

---

## After the captures

Send me the three images and I will:

1. Rebuild `RelayShield_SIMSwap_UserExperience_Screenshots.pdf` with these as the user flow, replacing
   the Crypto Shield Mobile pages, which show a flow that does not reach the Lookup call.
2. Add the enrollment architecture section: per-number `consent_state`, `consent_source`,
   `consent_method`, `consent_at`, `consent_terms_version`. **This is the part that makes the package
   approvable rather than merely complete**, because a carrier's real question is "show me consent for
   this specific number".
3. Finalise the reply, quoting the consent language in full since it is already live in the Terms.

## What to verify while you are in there

Worth a glance, since you will be looking at the bot anyway:

- The clause text should match https://terms.relayshield.net word for word. Both come from
  `CARRIER_CONSENT_TEXT` in the shared module, so they cannot drift, but confirm it once by eye.
- `STOPSIM` should work even if monitoring was never on. It should say monitoring is not currently
  enabled rather than erroring.

## If something does not respond

Tell me which step and what came back. **Do not retry repeatedly** — every inbound message is a
Twilio-billed conversation, and a stuck onboarding state is more useful to me un-poked than
half-advanced.
