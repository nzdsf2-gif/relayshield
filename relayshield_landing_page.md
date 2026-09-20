# RelayShield Landing Page Copy
*Reference document for Carrd build*

---

## HERO SECTION

**Headline:**
Your 2FA can't protect your bank account if your phone number is already in a data breach.

**Sub-headline:**
RelayShield monitors the full attack chain — from the breach that exposes your data, through the SIM swap that silences your alerts, to the session theft that defeats your 2FA. Then walks you through every fix, step by step, right in your WhatsApp.

**Primary CTA:** Secure My Account →
**Secondary CTA:** See How It Works →

---

## TRUST SIGNAL (below hero)

> "Built by a 25-year telecom security professional. Most identity protection tools detect the breach and stop. RelayShield monitors what happens after — the SIM swap, the session hijack, the bank account takeover. That's the attack chain nobody else is watching."

---

## THE ATTACK CHAIN BLOCK

**Header:** The breach is step one. Your bank account is step five.

**Body:**
Most people think getting a breach notification is the problem. It isn't. The breach is just the starting pistol.

Here's what actually happens after your data is exposed:

```
Step 1 — Your email, phone number, and date of birth 
          appear in a data breach. Nobody tells you.

Step 2 — Attacker calls your carrier, impersonates you 
          using your breach data. Your number is ported 
          to their SIM in under 10 minutes.

Step 3 — Your phone goes silent. You assume a network issue.

Step 4 — Attacker hits "Forgot Password" on your bank.
          Your SMS verification code arrives on their phone.
          New password set. Zelle transfer initiated.

Step 5 — You find out 24–48 hours later. 
          Your bank says the transfer was "authorised."
          Average loss: $2,000–$15,000.
```

> The 2FA you set up to protect your account is only as strong as your phone number. And your phone number is already in a breach database.

**CTA:** Check If Your Data Is Exposed →

---

## THE PROBLEM BLOCK

**Header:** Every tool stops at the alert.

**Body:**
Aura alerts you. HIBP alerts you. Your bank alerts you.

Then they all stop.

Nobody tells you that attackers plant backdoors before you even knew you were breached — silent forwarding rules that copy every email you receive, rogue app permissions that survive password resets, session cookies stolen after a successful login that defeat your 2FA entirely.

Resetting your password without sweeping for backdoors is like changing your front door lock while leaving a window open.

RelayShield closes the window first.

---

## THE SESSION HIJACKING BLOCK

**Header:** Changed your password? The attacker may still be logged in.

**Sub-header:** A new class of attack called AiTM phishing defeats 2FA without ever touching your password.

**Body:**
Tools like Tycoon 2FA and EvilProxy sit between you and your real login page. You enter your credentials. You complete your 2FA. The proxy captures your authenticated session token — the cookie that proves you already logged in — and replays it from the attacker's device.

No password needed. No 2FA prompt. Full access.

This is how attackers get into Google accounts, Microsoft 365, and banking apps even when the victim "did everything right."

**What RelayShield does:**
→ When your breach exposes the data that enables session theft, RelayShield warns you explicitly — not just that you were breached, but that your data can be used to run an AiTM attack against you right now
→ Reply **SESSIONS** to get a guided audit: active logins, OAuth permissions, unknown devices — everything that needs to be revoked
→ The breach alert tells you which accounts to prioritise before the attacker does

---

## INFOSTEALER MALWARE BLOCK

**Header:** Your password manager can't protect you from infostealer malware.

**Sub-header:** A single silent infection steals everything — before you know it happened.

**Body:**
Infostealers like RedLine, Raccoon, and Vidar run silently in the background and exfiltrate:

→ Every browser-saved password across every site
→ Active session cookies — bypassing 2FA without needing your password
→ Credit card autofill data
→ Crypto wallet keys

Unlike a corporate breach (where your data leaks weeks later), infostealer logs appear on dark web markets within days of infection.

**What RelayShield does:**
→ Monitors your email against near real-time infostealer log databases
→ Alerts you on WhatsApp with the infection date, device OS, and credential count exposed
→ Guides you through the 4-step device remediation in the right order — isolate first, change passwords from a clean device second

---

## EMAIL SECURITY SWEEP — HERO BLOCK

**Header:** The most dangerous thing you can do after a breach is reset your password immediately.

**Sub-header:** Backdoors survive password resets. RelayShield sweeps for them first.

**The 5-step Email Security Sweep:**

→ **Silent forwarding rules** — attackers copy every email you receive without you noticing
→ **Unknown recovery options** — a rogue recovery email lets them lock you out at any time
→ **Malicious inbox filters** — rules that delete your bank alerts and security notifications
→ **Unauthorised app permissions** — OAuth access that survives password resets entirely
→ **Active sessions on unknown devices** — attackers already logged in, watching in real time

**Callout:**
> RelayShield runs this sweep automatically on every breach detection — before walking you through the password reset. No competitor does this.

**CTA:** See What a Sweep Looks Like →

---

## EMAIL CHECKER BLOCK
*(Placement: directly after the Email Security Sweep block. Same inbox, and it is the page's
first thing a visitor can DO rather than read.)*

**Header:** Not sure about an email? Forward it.

**Body:**
Forward any suspicious email to checkemail@relayshield.net and you get a plain-English verdict back, usually within a minute.

No account. No signup. Nothing to install. It works from the inbox you already have, on the phone you are already holding.

What it reads:
- Whether the sending domain is one we have seen in criminal markets
- Whether the reply-to address quietly differs from the sender, the oldest trick there is
- Whether the links go where the text claims they go
- Whether the display name is impersonating a brand you would trust

It will never tell you an email is safe. The most it says is that nothing is known against it, because an absence of evidence is not proof, and a checker that says "safe" is training you to trust the one it misses.

**CTA:** text rather than a button. There is nothing to click; the action is in their mail app.

> THE ADDRESS IS `checkemail@`, NOT `emailcheck@`. It has been written the wrong way round twice,
> once in the very message asking for it to be added to four surfaces, which is why
> `relayshield_forward_analysis.py` holds it as the single constant `CHECKEMAIL_ADDRESS`.

---

## THE RESPONSE LAYER

**Header:** Detection is not protection. Response is protection.

**Three capabilities:**

**1. Sweep**
Close every backdoor before you reset anything. One wrong step leaves attackers with permanent access even after you change your password.

**2. Remediate**
AI-powered step-by-step guidance delivered to your WhatsApp. Not a PDF. Not a help article. A conversation that walks you through every action — sweep, session revocation, password reset, SIM lock — in the right order, at any hour.

**3. Track**
RelayShield follows up until you are actually protected. Day 3: did you complete the password reset? Day 7: is remediation still open? Most breaches go unresolved not because people don't care — because nobody followed up.

---

## HOW IT WORKS

**Header:** Three steps. One WhatsApp conversation.

1. **RelayShield detects a breach** — daily monitoring across breach databases and carrier-layer signals
2. **You get a WhatsApp alert** — severity scored CRITICAL / HIGH / MEDIUM / LOW, with the specific downstream attack risk explained in plain English
3. **You reply and we fix it** — sweep for backdoors, revoke active sessions, reset the right accounts, lock your SIM — all guided, all tracked until confirmed complete

> *"Your phone number and home address were exposed in the DataBrokersPT breach (2024). Severity: HIGH — this data is used to impersonate you on a SIM swap call to your carrier. Reply SWEEP to audit your inbox, or SAFE to confirm you've read the SIM swap warning."*
> — Example RelayShield alert

---

## TELEGRAM MINI APP BLOCK
*(Placement: immediately above Pricing. It is the last thing read before the money and the only
thing on the page a visitor can try without giving us anything.)*

**Header:** Check something right now, free.

**Body:**
Paste a link, a TON address or a Telegram handle and get an answer in seconds. It runs inside Telegram, so there is nothing to install, no signup and no wallet to connect.

- A link is checked against Google Safe Browsing, our criminal indicator corpus and domain age
- A TON address is checked for drainer and scam-token signals
- A @handle is checked before you trust a bot or an account that messaged you

Watch up to three addresses free and get a message the moment something changes.

It is the same intelligence the monitoring plans run on a schedule. This is the part you can hold in your hand first.

**CTA button:** Open the checker in Telegram →
**URL:** https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-blog

> THE `?startapp=` KEY IS NOT OPTIONAL AND IS NOT INVENTABLE IN CARRD. An unregistered key is
> silently downgraded to the generic `tg-miniapp` at the Worker's edge and logs `unmatched:`,
> which is attribution that looks like it worked. Registered keys live in `miniapp_routes.json`.

---

## PRICING

**Header:** Simple pricing. No hidden fees. Cancel any time.

*Note: Pricing table rendered as HTML embed in Carrd. See below for content reference.*

| | Personal Shield | Business Starter | Business Basic | Business Shield |
|---|---|---|---|---|
| **Who it's for** | Individuals & families | Sole proprietors & freelancers | Teams up to 5 | Teams up to 10 |
| **Breach monitoring** | ✅ | ✅ | ✅ | ✅ |
| **WhatsApp alerts** | ✅ | ✅ | ✅ | ✅ |
| **AI remediation guidance** | ✅ | ✅ | ✅ | ✅ |
| **SIM swap monitoring** | ✅ | ✅ | ✅ | ✅ |
| **Session hijacking alerts** | ✅ | ✅ | ✅ | ✅ |
| **Vishing preparedness** | ✅ | ✅ | ✅ | ✅ |
| **Contractor / employee seats** | — | 2 seats | 5 seats | 10 seats |
| **Quarterly sweep reminder** | — | ✅ | ✅ | ✅ |
| **Monthly security digest** | ✅ | ✅ | ✅ | ✅ |
| **Team seat management** | — | — | ✅ | ✅ |
| **Domain monitoring *** | — | — | ✅ | ✅ |

*\* Planned roadmap feature. No pricing shown — visitors see pricing at checkout.*

**Benefit tagline (below table):**
🎁 Give your team something new: Personal breach protection as part of working with you — a benefit your employees and contractors will remember.

**Business Starter subtitle (below Business Starter button):**
*Your business email, personal email, and mobile number share one attack surface — RelayShield monitors all of them.*

---

## SELECT A PLAN

*Buttons in order: PERSONAL → BUSINESS STARTER → BUSINESS → (each preceded by ToS/Privacy links)*

**WhatsApp requirement notice (above buttons):**
📱 WhatsApp Required: Onboarding and interactive security alerts. Before subscribing, save +1 (740) 737-3961 as a contact in WhatsApp.

- PERSONAL → https://buy.stripe.com/14A8wQa6y1qB8KM2JF0Ny00
- BUSINESS STARTER → https://buy.stripe.com/fZucN6ceGglv3qs9830Ny0a
- BUSINESS → (Business Basic payment link)

---

## DEVELOPER / API CTA BLOCK
*(Placement: after Telegram bot notice, above "From the Founder" section)*

**Section heading:** Built for Security Teams

**Body:**
RelayShield does not wrap public breach databases.

Our intelligence pipeline collects continuously from criminal Telegram marketplaces, infostealer log markets, credential dump channels and SIM swap service listings, alongside public indicator feeds, and surfaces indicators before they reach the public aggregators. We deliberately do not quote a corpus headline: most of any vendor's total is ingested public feeds you already have, and the number that matters is what you find in it that you could not find anywhere else.

<!-- THE FIGURES THAT USED TO BE HERE WERE BOTH STALE AND AGAINST OUR OWN RULE.
     They read "25+ criminal Telegram channels", "1,000,000+ indicators across
     20 feeds" and "1,000+ malware families". Measured 2026-09-16: 494K distinct
     indicators, 5.8M sightings, 113 active channels -- so the channel count
     understated by four times and the indicator figure was in a different unit
     from the one that matters. MEASUREMENT DOCTRINE says the fix is not to
     correct them, it is to stop quoting them: most of the corpus is ingested
     public feeds every target buyer already has, quoting the headline nearly
     killed the Segment 1 outreach in front of people who checked, and the AWS
     listing was rewritten to name SOURCES AND CAPABILITIES rather than COUNTS
     for exactly this reason. The replacement stays true without maintenance. -->

**New: Agentic AI Identity Risk** — `POST /v1/metered/bulk-identity-risk` scores up to 10 organizational domains plus their individual AI agent identities in a single call. Built for teams running AI copilots, agent workflows, and automated systems that need to know whether the identities they operate on behalf of are compromised. Each domain returns a 6-dimension risk score (0–100); each agent email returns breach, infostealer, and active session signals. $2.00/call.

Available as a REST API for SOAR playbooks, SIEM enrichment, AI governance workflows and incident response. Pay as you go from $0.10 a call with no minimum, or subscribe: $499/month for 10,000 calls, $999/month uncapped.

<!-- THIS SENTENCE USED TO SAY "$499/month for unlimited access across all 23
     endpoints" AND BOTH HALVES WERE WRONG.

     THE PRICE IS THE SERIOUS ONE. relayshield_developer_signup.py's own comment
     above TI_PRICE_TIER_MAP: mp_499 is $499/mo with a 10,000 calls/month cap
     enforced by _check_and_increment_intel_quota, and mssp_999 is the unlimited
     one. So a buyer paying $499 expecting unlimited hits a quota gate, and this
     page is what sold them the expectation. Copy shown to a buyer that
     disagrees with what the server grants is a price we do not honour.

     THE COUNT WAS 23 AND IS 31, counted from the distinct /v1/metered/* paths
     in relayshield_api.py rather than recalled. It is dropped rather than
     updated: a number that moves every time we ship needs maintenance to stay
     honest, and this is the same reasoning that took the corpus figures out of
     the paragraph above. If a count is ever wanted here, read it out of the
     dispatcher; never type one from memory. -->

**CTA button:** View Developer API →
**URL:** https://api.relayshield.net/developers?source=relayshield-net

<!-- THIS BUTTON HAD NO ?source= AT ALL, for as long as the page has existed, so
     every developer arrival from our own consumer site was indistinguishable
     from organic traffic. `relayshield-net` is registered in _SOURCE_BANNERS
     with its own banner, BEFORE this link ships, which is the order that
     matters: an unregistered key logs `unmatched:` and renders nothing, which
     is FD-8 and four months of it. The path is /developers and never the bare
     host -- ?source= on the root is read by nothing. -->
**Style:** Outline/secondary

---

## FOUNDING MEMBER URGENCY BLOCK

🔒 **Founding Member Offer — Limited Spots**

Sign up today and pay the founding rate for your first 3 months.

| Tier | Standard Price | Founding Rate | Spots Remaining |
|---|---|---|---|
| Personal Shield | $14.99/month | **$12/month** | 20 spots |

> Founding rate applies to your first 3 months. Standard pricing applies from month 4. No surprise increases — you know exactly what you're signing up for.

**CTA:** Secure My Account →

---

## FINAL TRUST BLOCK

**Header:** Built differently. On purpose.

→ No CRM storing your PII — Aura's breach vector
→ No third-party data sharing beyond what monitoring requires
→ Built by a 25-year telecom security professional who has seen every attack vector from the carrier side
→ WhatsApp-native because that is where people actually respond
→ Monitors the full chain: breach → SIM swap → session hijack → bank account — not just step one
→ AI that acts — not AI that notifies

**Hold crypto?**
Crypto Shield is our read-only wallet monitor for Solana, EVM, TON, Bitcoin and XRP. It never asks for a seed phrase and it cannot move your funds. Available now on the Solana dApp Store.

**CTA:** See Crypto Shield →
**URL:** https://cryptoshieldmobile.relayshield.net

<!-- LINK, DO NOT DESCRIBE. Crypto Shield has a landing page of its own and a
     full product block here would compete with the thing this page exists to
     sell. It IS live: cloudflare_worker_cryptoshield_landing.js says "Available
     now on the Solana dApp Store" and carries v1.5.0 certificate-rotation
     notes. Checked rather than assumed -- the store metadata in the repo is
     headed "Draft", which reads as pre-launch and is in fact a draft of a copy
     CORRECTION to a listing that is already published. -->

---

## FOOTER

RelayShield — Identity Protection with a Response Layer
relayshield.net | relayshieldadmin@gmail.com | 📞 +1 (339) 203-9730

© 2026 RelayShield. All rights reserved.
Privacy Policy | Terms of Service
