# Twilio Marketplace Listing request

## Who to send it to, and why there is no form

`twilio.com/docs/marketplace/publishers` states: **"Publishing is available by invitation only.
Contact your Twilio Account Executive for details."** There is no self-serve application, so this is
a relationship request, not a submission.

**Route, in order of preference:**

1. **Your named Twilio Account Executive**, if one is assigned. Check the Twilio Console under
   **Account, then your profile or billing contacts**, or look for a named sender on any Twilio
   renewal, upgrade or pricing email you have received.
2. **`sales@twilio.com`** if no AE is named. Subject line matters here, since this routes on keywords.
3. **Twilio Console Support ticket**, product area **Marketplace**, as a fallback that creates a
   paper trail if the first two go quiet.

**Do not use `support@twilio.com` for this.** It is a technical support queue and will deflect a
partnership request.

---

## The message

**Subject:** Marketplace Listing invitation request, existing Lookup and WhatsApp customer

Hi <NAME>,

I am the founder of RelayShield. We are an existing Twilio customer, using Lookup v2 for SIM-swap
and carrier signals and WhatsApp through Twilio as our BSP.

I would like to ask about an invitation to publish a Listing on Twilio Marketplace.

The reason I think it is a fit: your two documented Add-on tutorials are Prove TCPA and Trestle
Reverse Phone, both phone and identity data providers. RelayShield sits in that same category, but
covers signals those providers do not. We correlate a phone number or email against criminal
underground sources rather than carrier or public records: infostealer stealer-log marketplaces,
breach corpora, stolen session-cookie archives, and around 87 monitored criminal Telegram channels,
against a corpus of over 5 million indicators.

The practical difference for a Twilio customer is this. Lookup can already tell them a number was
recently ported or swapped. It cannot tell them that the same subscriber's credentials showed up in
a stealer log three days earlier. One of those is a fact. Both together are the difference between a
targeted account-takeover attempt and somebody upgrading their phone.

We already run this as a live, metered API with per-call pricing, so the Add-on billing model is a
natural fit rather than something we would need to build.

A few things you may want to know up front:

- Live production API, currently 28 pay-per-call endpoints, with published OpenAPI documentation
  at api.relayshield.net/docs
- Existing integrations with n8n (verified community node), Zapier (approved, entering beta),
  Elastic Security, and listings on AWS Marketplace and the x402 agent-payments registry
- US entity, RelayShield LLC

Could you tell me whether we qualify for a Marketplace Listing invitation, and what the process and
timeline look like from here? Happy to provide anything else useful.

Thanks,
Andrew Gibbs
RelayShield
support@relayshield.net

---

## Before sending, verify these three numbers

They are in the message and they have all drifted before.

- **Over 5 million indicators.** Re-measured 2026-08-06 from `relayshield_intel_iocs`: **5,089,873**.
  Four public surfaces once claimed between 4.4M and 4.9M; all were reconciled on 2026-08-05. Use the
  live figure, never a remembered one.
- **87 Telegram channels.** Re-counted live 2026-08-06: `relayshield_intel_channels` where
  `active = true` returns **87**, up from 85 yesterday. Count `active`, never the raw row count,
  which is 294 and includes unverified auto-discovered candidates.
- **28 endpoints.** 26 PAYG in `relayshield_api.py` plus 2 in `relayshield_agentic_api.py`. Do **not**
  say "28 discoverable in the CDP Bazaar"; only 25 are indexed, deliberately.

## What a yes actually costs

Worth knowing before asking. Twilio Add-ons are consumed through the Lookup and Messaging APIs, so a
listing implies conforming to their Add-on request and response contract and their billing
integration, not just pointing them at our existing endpoints. Treat the invitation as the gate to a
scoping conversation, not as the work itself.

## If they say no or go quiet

Per the AGGREGATOR TODO item, do not then spend effort on Vonage and Sinch. If invitation-only is the
norm in this category, that finding applies to all three and the whole item drops below XSOAR,
Microsoft Sentinel and AWS Bundles A-C.
