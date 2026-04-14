# RelayShield — Strategic Business Document
*Generated: March 2026 | Last Updated: April 2026 — Vishing Preparedness Engine added (Section 8): AI voice attack warning layer for consumers and businesses, triggered automatically on breach detection. Session Hijacking Detection Engine added (Section 9): AiTM phishing awareness, session cookie exposure detection, and active session audit — addresses Tycoon 2FA and EvilProxy attack vectors that bypass 2FA entirely.*

---

## 1. Product Overview

**RelayShield** owns the response layer of identity protection. Every other service — Aura, LifeLock, HIBP, Foretrace — sends an alert and stops. RelayShield is what happens next: a conversational AI in your WhatsApp that walks you through exactly what to do, catches the backdoors attackers leave behind that survive a password reset, and follows up until you are actually protected. Built on a 25-year telecom security foundation, with a carrier-layer detection capability no competitor has attempted.

**The core insight:** Detection is commoditised. Google, Apple, and Firefox all monitor for breaches for free. The gap nobody has filled is response — guiding a real person through real remediation steps at 11pm when they are panicked, without a hold queue and without jargon.

### Core Positioning Statement
> *"Every security service tells you when you've been breached. RelayShield is the only one that fixes it."*

### Supporting Taglines
> *"Changing your password after a breach is not enough. Attackers leave backdoors that survive a password reset. RelayShield finds them first — in your WhatsApp, step by step."*

> *"Already using Aura or Incogni? They told you about the breach. We close it."*

> *"Built by a 25-year telecom security professional. Priced for people who want protection, not a product bundle they will never use."*

---

## 2. Founder Profile

- 25 years telecommunications industry experience
- Product Management and Business Development background
- Identity Management and Zero-Trust expertise
- Cryptography and encryption knowledge
- Vibe-coding capability: AWS Lambda, DynamoDB, Twilio/WhatsApp, Python, webhooks
- Completed SmartAsst project (Task Manager/Scheduler with WhatsApp front-end)

---

## 3. Target Market

### Primary Segments
- **SMBs** (Small/Medium Businesses) — recurring B2B contracts, self-serve onboarding
- **Privacy-conscious consumers** — volume play, $12/month for first 3 months / $14.99 standard thereafter

---

### Target Persona — The Breached Consumer

**Profile:** Adult with one or more personal email accounts, multiple online accounts (banking, shopping, social media), and a smartphone. Has likely been in at least one data breach — HIBP has over 14 billion records across thousands of historical breaches. Has received a breach notification from Google, Apple, or Firefox at some point. Changed their password. Assumed they were protected. Was not.

**Not a technical user.** Does not know what an OAuth token is. Does not know that forwarding rules survive a password reset. Does not have the time or knowledge to audit their inbox at 11pm when a breach alert arrives.

**Key insight — why this consumer is underprotected despite free tools:**

Google, Apple, and Firefox Monitor all detect breach credentials and notify users. None of them do what happens next:

```
Free tools stop here:    "Your password was in a breach. Change it."

What attackers do first:  Log in and plant 3–5 backdoors that
                          survive the password reset:
                          → Silent forwarding rule
                          → New recovery phone number
                          → Inbox filter deleting security alerts
                          → OAuth app access granted to attacker
                          → Active session on attacker's device

What the consumer does:   Changes password. Feels protected.
                          All 5 backdoors still active.

What happens next:        Attacker uses "forgot password" on
                          banking, PayPal, Amazon.
                          Reset emails arrive. Forwarding rule
                          copies them to attacker before consumer sees them.
                          Consumer locked out of financial accounts.
```

**Why this is the consumer's most exposed surface:**

Email is the recovery mechanism for every other account. Whoever controls the email controls the "forgot my password" button on banking apps, PayPal, Amazon, Apple ID, Google account, and social media. A compromised email is not one breach — it is a master key to the entire digital life.

**The attack chain in plain language:**

```
Step 1 — Email credentials appear in a data breach
          (consumer never finds out — no one is monitoring daily)

Step 2 — Attacker logs into Gmail/Outlook/Yahoo using breached credentials

Step 3 — Plants silent forwarding rule — all emails copied to attacker
          Consumer never notices — emails still arrive normally

Step 4 — Adds attacker's recovery phone number to the account

Step 5 — Creates inbox filter deleting security alerts and bank notifications

Step 6 — Consumer eventually changes email password — feels safe

Step 7 — Attacker still has full access via forwarding rule and OAuth token
          Password change did nothing

Step 8 — Attacker triggers "forgot password" on banking app, PayPal, Amazon
          Reset emails intercepted before consumer sees them

Step 9 — Consumer locked out of financial accounts
          Average loss: $1,500–$8,000 (FTC 2024 identity theft data)
```

**Why RelayShield is the only solution for this persona:**

| Her Risk | What exists today | RelayShield |
|---|---|---|
| Email breach — backdoors planted | Google/Apple detect breach, do not check backdoors | Email Security Sweep — 5-step audit before password reset |
| Forwarding rule installed | No tool checks for this post-breach | Step 1 of sweep — most dangerous, caught first |
| OAuth tokens granted to attacker | No consumer tool checks this | Step 4 of sweep — survives password reset |
| Same password on 10 accounts | No tool identifies which other accounts are at risk | Cross-account password risk detection |
| Breach ignored after alert | Every tool sends one alert and stops | Day 3 / 7 / 14 follow-up until remediation confirmed |
| Multiple historical breaches — which to fix first | HIBP shows all equally — no prioritisation | Breach severity scoring — told exactly which to fix first |
| SMS 2FA exposed via SIM swap | No consumer tool monitors carrier layer | SIM lock onboarding during signup + Phase 2 monitoring |

**The second attack chain — SIM swap + session hijacking → bank account takeover:**

Most consumers believe 2FA protects their bank account. It does not — if the attacker controls their phone number or their authenticated session token.

```
Step 1 — Breach exposes: email, phone number, date of birth, address

Step 2 — SIM swap: attacker calls carrier, impersonates consumer 
          using breach PII → ports number to attacker's SIM

Step 3 — Consumer's phone goes silent — assumes network issue

Step 4 — Attacker hits "Forgot Password" on banking app
          SMS OTP arrives on attacker's device
          New password set in under 2 minutes

Step 5 — Zelle transfer out — banks rarely reimburse "authorised" 
          transfers, even when enabled by SIM swap
          Average loss: $2,000–$15,000

   — OR —

Step 2 — AiTM phishing: attacker uses breached email + password to 
          run a Tycoon 2FA proxy page
          Consumer completes login including 2FA
          Proxy harvests the authenticated session cookie

Step 3 — Attacker replays session cookie from their device
          No password needed. No 2FA prompt. Full account access.
          Works on banking apps, Google, Microsoft 365, social media.
```

**The consumer insight that drives conversion:**
> *"2FA protects your login. It does not protect your session once you are logged in. And it does not protect your bank account if your phone number is already in a data breach."*

**Why RelayShield is the only solution for this persona:**

| Her Risk | What exists today | RelayShield |
|---|---|---|
| Email breach — backdoors planted | Google/Apple detect breach, do not check backdoors | Email Security Sweep — 5-step audit before password reset |
| Forwarding rule installed | No tool checks for this post-breach | Step 1 of sweep — most dangerous, caught first |
| OAuth tokens granted to attacker | No consumer tool checks this | Step 4 of sweep — survives password reset |
| Same password on 10 accounts | No tool identifies which other accounts are at risk | Cross-account password risk detection |
| Breach ignored after alert | Every tool sends one alert and stops | Day 3 / 7 / 14 follow-up until remediation confirmed |
| Multiple historical breaches — which to fix first | HIBP shows all equally — no prioritisation | Breach severity scoring — told exactly which to fix first |
| Phone number exposed → SIM swap → bank takeover | No consumer tool monitors carrier layer | SIM swap detection alert fires before attacker reaches the bank |
| Session cookie stolen via AiTM phishing (Tycoon 2FA) | No consumer tool warns about session hijacking risk | AiTM awareness block in breach alert + SESSIONS command to revoke active sessions |

**The consumer sales pitch in one sentence:**
> *"Your 2FA cannot protect your bank account if your phone number is already in a data breach. RelayShield monitors the full attack chain — from the breach that exposes your data, through the SIM swap that silences your alerts, to the session theft that defeats your 2FA — and walks you through every fix before the attacker gets there."*

**Why $14.99/month is justified for this persona:**

The consumer is not paying for breach detection — they can get that free. They are paying for:
1. The Email Security Sweep — the only tool that checks for backdoors before the password reset
2. SIM swap monitoring — carrier-level alert before attacker reaches the bank account
3. Session hijacking awareness — explicit AiTM warning when breach data enables session theft
4. AI-guided remediation in WhatsApp — available at 11pm, no hold queue, plain language
5. Severity scoring — tells them which of their 10+ breach hits to act on first
6. Follow-up until actually protected — the one thing every free tool refuses to do

One prevented Zelle transfer reversal saves 3–10 years of RelayShield fees. One prevented account takeover saves more than a year.

**Target communities to reach this persona:**
- r/privacy — lead with the forwarding rule insight: "changing your password is not enough"
- r/personalfinance — frame as bank account takeover risk: "your 2FA doesn't protect your Zelle"
- r/scams — value-first post: "5 things to check in your email after any breach notification"
- r/technology — the full attack chain from breach to bank takeover — credibility audience
- r/banking — SIM swap → Zelle fraud angle; banks won't reimburse authorised transfers
- Facebook groups: "Online Privacy", "Identity Theft Support", "Cybersecurity for Beginners"
- Twitter/X: reply to breach announcement threads and SIM swap news stories with free value

**Validation approach:**
Ask 3–5 people who have received a Google or Apple breach notification: "Did you change your password?" (Yes.) "Did you check whether they had already set up a forwarding rule?" Watch the confusion. That confusion is the conversion moment. If they ask what a forwarding rule is — they are a paying customer.

---

### Target Persona — The Mobile-Dependent SMB Owner

**Profile:** Small retail, food service, or service business owner. Runs the business from her phone. Uses Square (or similar mPOS: Toast, Clover, PayPal Zettle) for payment processing. Business bank account is directly connected to the POS system. Has employees or contractors whose credentials also represent risk exposure. Not technical — security is not her domain. Her phone is her business.

**Why this persona is the highest-priority SMB target:**
- Her phone number IS her authentication factor for almost every critical business system
- A single SIM swap hands an attacker her Square account, business bank account, email, and customer data simultaneously
- She has no IT department — no one is watching for threats
- The financial impact of a successful attack is immediate and potentially business-ending
- She is currently unprotected by any purpose-built tool at her price point

**The attack chain that keeps this persona up at night:**

```
Step 1 — Her email or phone number appears in a data breach
          (she never finds out — no one is monitoring)

Step 2 — Attacker buys breach data, initiates SIM swap
          (calls her carrier, impersonates her using breach PII)

Step 3 — Her phone goes dark — she assumes a network issue

Step 4 — Attacker triggers Square "forgot password"
          SMS verification code arrives on attacker's device

Step 5 — Attacker resets Square password, changes payout
          bank account to their own

Step 6 — Attacker plants email forwarding rule
          All Square alerts now silently go to attacker

Step 7 — Her next day's card sales flow to the attacker's account
          She does not notice until payout day — 1-2 business days later

Step 8 — Attacker exports her full customer transaction history
          Sells or uses it for targeted phishing against her customers

Total time from SIM swap to payout redirect: under 30 minutes
Average time until she notices: 24-48 hours
```

**Why RelayShield is the only solution for this persona:**

| Her Risk | What exists today | RelayShield |
|---|---|---|
| SIM swap → Square takeover | Nothing at her price point | Phase 2 telecom layer — SIM swap alert before attacker reaches Square |
| Email breach → forwarding rule | Google/Apple notify about breach, do nothing else | Email Security Sweep catches forwarding rule before password reset |
| Credential stuffing → Square login | Square has 2FA — bypassed by SIM swap | Breach detection + cross-account password risk flags reuse before attack |
| Phishing using her breach data | No protection | Breach alert warns her data is circulating before attacker uses it |
| API key exposure (integrations) | Nothing | Phase 2 GitGuardian monitoring |
| Payout account change alert lost in email | Square sends email — attacker deletes it | WhatsApp alert at 90%+ open rate, cannot be silently deleted |

**The sales pitch in one sentence:**
> *"Your Square account is only as secure as your phone number. If someone swaps your SIM, they own your business bank account in under 30 minutes. RelayShield watches your carrier line, monitors your credentials, and alerts you in WhatsApp before the attacker gets there."*

**Why this persona suits the founder's background:**
- 25 years telecom experience = credibility on SIM swap and carrier-layer threats that no software-only competitor can match
- WhatsApp-native delivery = meets this persona where she already operates
- SMB price point ($89.99-$299.99/month) = well within a retail business security budget, especially when framed against the cost of a single successful SIM swap attack
- No IT knowledge required = self-serve onboarding via WhatsApp conversation

**Target communities to reach this persona:**
- r/smallbusiness — lead with the Square/SIM swap attack chain
- r/Entrepreneur — frame as business continuity, not cybersecurity
- Square Seller Community forums — post educational content about SIM swap risk
- Local business Facebook groups — high concentration of mobile-dependent owners
- Toast, Clover, PayPal Zettle user communities — same persona, same vulnerability
- LinkedIn: target "small business owner", "retail owner", "restaurant owner" with telecom threat education content

**Validation approach:**
Find 3-5 Square/mPOS users in your network. Walk them through the 8-step attack chain above. The moment they hear "your phone goes dark and your next day's sales go to someone else" — that is the conversion moment. If they ask "how do I protect against this?", they are a paying customer.

---

### Mobile Number Theft — Threat Method Taxonomy
*Reference section for sales conversations, outreach content, and product positioning*

Mobile number theft is the master key attack against mobile-dependent business owners. A stolen number bypasses every SMS-based 2FA layer simultaneously — banking, Square, email, and anything else tied to that number. Here are the six primary methods, ranked by accessibility to low-skill attackers:

#### Method 1 — Social Engineering the Call Centre
**Attacker skill required: Very low | Cost: ~$0 | Time: 15–30 minutes**

The attacker calls the carrier's support line, impersonates the victim, and requests a SIM replacement citing a lost or damaged phone. Success depends on the call centre agent, not the attacker's skill.

**What the attacker needs** — all obtainable from a single breach data purchase:
- Victim's name and phone number
- Last 4 of SSN (147 million exposed in Equifax 2017 alone)
- Billing address
- Sometimes: last 4 of account number or a recent call made

**How it works:** Multiple agents are tried until one approves. Pre-2024 FCC rules, first-attempt success rate was reported at 15–20%. Higher with persistence. The incentive structure of call centres rewards speed, not verification rigour.

**SIM lock effectiveness:** Partial — a determined attacker tries multiple agents and escalation paths until one approves an override.

---

#### Method 2 — Insider Threat / Carrier Employee Bribery
**Attacker skill required: Low (just Telegram) | Cost: $300–$3,000 per swap | Time: Minutes**

Active Telegram channels recruit carrier store employees and call centre agents to execute swaps directly using their system access. This is a functioning criminal marketplace, not a theoretical risk.

**Documented rates:**
- Standard swap: $300
- High-value target (crypto, executive): up to $3,000

**Real cases:**
- March 2024: AT&T employee Jonathan Katz prosecuted under CFAA for facilitating SIM swaps
- 2025: T-Mobile ordered to pay $33 million in damages after an insider-facilitated swap enabled $38 million cryptocurrency theft

**SIM lock effectiveness: Zero.** The employee has direct system access and can override any lock.

---

#### Method 3 — Port-Out Fraud
**Attacker skill required: Low | Cost: ~$0 | Time: 2–4 hours**

The attacker ports the victim's number to a completely different carrier they control, rather than swapping the SIM at the existing carrier.

**How it works:**
1. Attacker opens an account at any MVNO (Mint Mobile, Cricket, etc.)
2. Submits a number port request with victim's name, address, and transfer PIN
3. Original carrier is legally required to release the number within hours under FCC portability rules
4. Victim's phone goes dead — number now active on attacker's device at a different carrier

**Why this matters:** Port-out fraud partially bypasses same-carrier SIM locks because the request originates externally. The 2024 FCC rules added mandatory port-out lock options, but opt-in rates are even lower than SIM locks.

**SIM lock effectiveness:** Partial — requires a separate port-out lock, which almost no one has enabled.

---

#### Method 4 — eSIM Remote Provisioning
**Attacker skill required: Medium | Cost: ~$0 | Time: 30–60 minutes**

The fastest-growing attack vector. eSIMs can be provisioned remotely via QR code — no physical SIM card required, no carrier store visit.

**How it works:**
1. Attacker socially engineers carrier support into issuing a new eSIM activation QR code
2. QR code is sent to an email or number the attacker already controls (compromised email account)
3. Attacker scans QR code — victim's number is now on the attacker's device
4. No physical interaction with the victim's phone ever required

**Why it is accelerating:**
- eSIM adoption growing 40% year-over-year
- Carrier support staff inconsistently trained on eSIM-specific fraud indicators
- Leaves fewer physical evidence traces
- SIM lock protocols were designed for physical SIM swaps — eSIM provisioning uses a different workflow

**SIM lock effectiveness:** Low — eSIM provisioning uses a separate approval path that SIM locks were not designed to block.

---

#### Method 5 — Carrier Account Credential Phishing
**Attacker skill required: Low | Cost: Nearly zero | Time: Automated**

The attacker phishes the victim's carrier account credentials (AT&T, T-Mobile, Verizon login) and executes the SIM swap themselves through the carrier's self-service portal — no phone call, no insider required.

**What self-service portals allow:**
- Add a new SIM to the account
- Change account PIN
- Request a SIM replacement
- Initiate a number transfer

**Phishing lure:** Spoofed carrier email — "Your account has been locked. Verify your identity." Personalised with victim's name and last 4 of phone number (from breach data) for higher click-through rate.

**SIM lock effectiveness:** Zero — the attacker is logged in as the account holder and can disable the lock themselves.

---

#### Method 6 — SS7 Network Interception
**Attacker skill required: High | Cost: $1,000–$10,000+ | Time: Real-time**

SS7 (Signalling System No. 7) is the 1970s-era protocol routing calls and SMS between carriers globally. Known architectural vulnerabilities allow interception of SMS messages in transit without ever touching the victim's SIM.

**How it works:**
- Attacker gains access to SS7 network via a rogue telecom operator, purchased access, or nation-state capability
- Routes the victim's SMS 2FA codes to themselves in real time
- Victim's phone continues working normally — they have no awareness the interception is occurring

**Who uses this:** Primarily nation-state actors, organised crime targeting high-value individuals (executives, journalists, politicians, large crypto holders). Less relevant for the typical SMB owner but increasingly accessible as criminal infrastructure matures.

---

#### Attack Method Summary

| Method | Skill | Cost | Time | SIM Lock Stops It? | RelayShield Detection |
|---|---|---|---|---|---|
| Call centre social engineering | Very low | ~$0 | 15–30 min | Partially | Carrier change event → instant WhatsApp alert |
| Insider bribery | Low | $300–$3,000 | Minutes | No | Carrier change event → instant WhatsApp alert |
| Port-out fraud | Low | ~$0 | 2–4 hours | Partially | Carrier change + new carrier detection |
| eSIM remote provisioning | Medium | ~$0 | 30–60 min | Low | eSIM provisioning event monitoring (Phase 2) |
| Carrier account phishing | Low | ~$0 | Automated | No | Carrier change event → instant WhatsApp alert |
| SS7 interception | High | $1K–$10K+ | Real-time | N/A | SS7 advisory in remediation flows |

**The key insight for RelayShield:** Methods 1, 2, 3, and 5 — the four most accessible attacks — all produce the same detectable signal: a carrier change event. The Twilio Lookup carrier monitoring layer fires on this event regardless of which method was used. This is why carrier monitoring is the right detection hook, not attempting to prevent each method individually.

**The SIM lock onboarding flow** closes the social engineering and phishing vectors for customers who complete it. **Monitoring** catches what gets through. Together they form a genuine prevention-plus-detection layer that no competitor offers at any price point.

---

### Pricing Strategy — Standard vs Founding Member

**Standard Pricing (Permanent — All New Customers After Founding Period):**

| Tier | Target | Seats | Monthly | Per Seat | Key Differentiator |
|---|---|---|---|---|---|
| **Personal Shield** | Consumers | 1 | $14.99 | $14.99 | Breach detection → WhatsApp alert → severity scoring → Email Security Sweep → AI remediation → follow-up until resolved + SIM/eSIM swap detection alert. Monitor up to **3 email addresses**. |
| **Business Starter** | Sole proprietors, single-owner businesses | 1 | $19.99 | $19.99 | All Personal Shield features + business-framed alert language + 3 monitored email addresses (personal + business + backup). Designed for owners whose business and personal identity are the same attack surface. No seat management. |
| **Business Basic** | Micro-SMBs | Up to 5 | $89.99 | $18.00 | All Personal Shield features + SIM/eSIM swap detection + carrier hardening steps + account management dashboard + domain monitoring. Monitor up to **2 email addresses per seat**. |
| **Business Shield** | SMBs | Up to 10 | $139.99 | $14.00 | All Business Basic features + per-seat SIM/eSIM monitoring + authenticator migration flow + aggregate risk visibility + priority alerts. Monitor up to **2 email addresses per seat**. |
| **Business Shield Pro** | Growing SMBs | Up to 25 | $299.99 | $12.00 | All Business Shield features + SIM lock onboarding flow + eSIM profile audit + priority support + compliance reporting. Monitor up to **2 email addresses per seat**. |

> 📧 **Email monitoring limits:** Personal Shield — 3 emails. Business Starter — 3 emails (sole owner, same as personal). Business Basic/Shield/Pro — 2 emails per seat (business address + one personal/backup). Total pool per account: Business Basic 10 (5 seats), Business Shield 20 (10 seats), Business Shield Pro 50 (25 seats). Rationale: 2 per seat covers real-world usage, keeps HIBP API costs predictable at scale, and leaves room for reputation scoring across the full account pool in a future release.

> 💡 **SIM/eSIM swap monitoring is included in ALL tiers.** Personal Shield receives detection alerts only. Business tiers additionally receive carrier-specific hardening steps, eSIM profile audit guidance, and (Pro) SIM lock onboarding. No competitor offers carrier-layer SIM/eSIM swap protection at any consumer or SMB price point. Validated by first prospective customer (salon owner, Square POS user): *"You identified a problem I didn't know I had. This is brilliant and I want to sign up."*

**Annual Subscription Option (All Tiers):**
Customers who pay upfront for a full year receive a **10% discount** on the monthly rate. This rewards commitment, improves cash flow, and reduces churn.

| Tier | Monthly | Annual (10% off) | Annual Total | Savings |
|---|---|---|---|---|
| **Personal Shield** | $14.99 | $13.49/month | $161.88/year | $18/year |
| **Business Starter** | $19.99 | $17.99/month | $215.88/year | $24/year |
| **Business Basic** | $89.99 | $80.99/month | $971.88/year | $108/year |
| **Business Shield** | $139.99 | $125.99/month | $1,511.88/year | $168/year |
| **Business Shield Pro** | $299.99 | $269.99/month | $3,239.88/year | $360/year |

> ⬜ **TODO:** Create annual pricing products and payment links in Stripe for all four tiers. Annual plans should be separate Stripe products with 10% discount baked in (not a coupon).

**Founding Member Pricing (Consumers Only — First 20 Customers — Discounted for First 3 Months):**

| Tier | Standard Price | Founding Rate | Saving | Duration |
|---|---|---|---|---|
| **Personal Shield** | $14.99/month | **$12/month** | $2.99/month | First 3 months |

> 🔒 **Founding Member Offer (Personal Shield only):** Limited to first 20 consumers. Sign up during the founding period and pay $12/month for your first 3 months — then move to standard pricing at $14.99/month. Stripe coupon: FOUNDING-PERSONAL ($2.99 off, 20 spots, fixed amount, repeating 3 months).
>
> **Business tiers do not offer founding member discounts.** Business buyers respond to ROI, not discounts. The SIM swap protection value proposition stands at full price.

### Stripe Payment Links

**Monthly Plans:**
| Product | Price | Payment Link | Status |
|---|---|---|---|
| Personal Shield | $14.99/month | https://buy.stripe.com/14A8wQa6y1qB8KM2JF0Ny00 | ✅ Active |
| Business Starter | $19.99/month | ⬜ Pending — create in Stripe | ⬜ Pending |
| Business Basic | $89.99/month | https://buy.stripe.com/aFa8wQ3Iab1b8KM9830Ny03 | ✅ Active |
| Business Shield | $139.99/month | https://buy.stripe.com/8x24gA6Um2uF2mo9830Ny04 | ✅ Active |
| Business Shield Pro | $299.99/month | https://buy.stripe.com/3cIeVeceG8T3f9a4RN0Ny05 | ✅ Active |

**Annual Plans (10% off):**
| Product | Price | Payment Link | Status |
|---|---|---|---|
| Personal Shield — Annual | $161.88/year | https://buy.stripe.com/eVqbJ26Um1qBbWY3NJ0Ny06 | ✅ Active |
| Business Starter — Annual | $215.88/year | ⬜ Pending — create in Stripe | ⬜ Pending |
| Business Basic — Annual | $971.88/year | https://buy.stripe.com/eVqfZifqSd9j1ikfwr0Ny07 | ✅ Active |
| Business Shield — Annual | $1,511.88/year | https://buy.stripe.com/cNiaEY0vYednaSUfwr0Ny08 | ✅ Active |
| Business Shield Pro — Annual | $3,239.88/year | https://buy.stripe.com/6oU5kE0vY5GR4uwbgb0Ny09 | ✅ Active |

**Archived (old pricing):**
| Product | Old Price | Status |
|---|---|---|
| Business Shield | $99.99/month | ⛔ Archived |
| Business Shield Pro | $199/month | ⛔ Archived |

### Why This Approach Is Strategically Superior

Founding members get a 3-month guaranteed rate — a meaningful, time-limited reward for early adoption. After 3 months they move to standard pricing, which they already knew going in. The frame is inverted entirely:

```
OLD APPROACH:   Launch at $79 → raise to $99.99 after 3 months
Customer hears: "You're charging me more"
Result:         Churn risk, complaints, negative reviews

NEW APPROACH:   $139.99 standard price, founding discount for consumers only
Customer hears: "I got 3 months at a great rate for being an early supporter"
Result:         Goodwill, word of mouth, smooth transition to standard pricing
```

### Founding Member Acquisition Strategy (Personal Shield Only)

Use the expiring discount — not a price increase — as the urgency driver:

> *"🔒 Founding Member Offer — First 20 customers only. Lock in Personal Shield at $12/month for your first 3 months. Standard price is $14.99/month. Sign up today and your founding rate is guaranteed for 3 months — no matter what features we add."*

When founding spots fill, simply close the offer. New customers pay $14.99. Founding members keep $12 for their first 3 months, then move to standard pricing. Clean transition, no surprise increases.

### Standalone Value Comparison (Phase 2 Justification)

| Capability | Standalone Tool | Standalone Cost |
|---|---|---|
| Email breach monitoring | HIBP direct | ~$30/month |
| Dark web data sale monitoring | Flare SMB | $50-100/month |
| Secret/API key scanning | GitGuardian | $29/month |
| Domain spoofing detection | BrandShield | $10-30/month |
| WhatsApp conversational AI | Nothing comparable | — |
| Telecom layer / SIM swap | Nothing comparable | — |
| **Total standalone** | **4 separate tools** | **$120-190/month** |

RelayShield Phase 2 delivers all of this in one product, one WhatsApp conversation, one dashboard, one invoice — at $99.99/month.

### Per-Seat Pricing Rationale

Business pricing is justified on value delivered per employee, not just headcount:

| Tier | Price | Seats | Per Seat | Comparable SaaS |
|---|---|---|---|---|
| Personal Shield | $14.99/mo | 1 | $14.99 | Baseline consumer |
| Business Shield | $99.99/mo | 10 | **$10.00** | Below 1Password Business ($7.99) + breach monitoring + AI remediation |
| Business Shield Pro | $199/mo | 25 | **$7.96** | Volume discount — still below Microsoft 365 Business Standard per seat |

One remediated credential breach at an SMB prevents average losses of $4,400 (Ponemon Institute). RelayShield pays for itself in the first month it catches one breach.

### Revenue Path to $2,500/Month

**During founding period:**
- Pure SMB founding: 32 clients × $79 = $2,528
- Mixed founding: 15 SMB ($1,185) + 110 consumers ($1,320) = $2,505

**After founding period closes (standard pricing):**
- Pure SMB standard: 26 clients × $99.99 = $2,600
- Mixed standard: 11 SMB ($1,100) + 94 consumers ($1,409) = $2,509
- Consumer only: 167 consumers × $14.99 = $2,503

**Break even:** 3 consumer subscribers at $14.99 covers all Phase 1 running costs (~$35/month)

---

## 4. Core Differentiators

RelayShield does not compete on detection. Detection is commoditised — Google, Apple, and Firefox already do it for free. RelayShield competes on **response**: what happens after detection, guided by AI, delivered in WhatsApp, tracked until complete. This is the gap every competitor has ignored.

### 1. Email Security Sweep — The Flagship Capability ✅ LIVE
**The insight no competitor has acted on:** Changing your password after a breach is not enough. Attackers plant backdoors that survive a password reset — forwarding rules that silently copy every email, OAuth tokens that persist regardless of password changes, recovery addresses they control. RelayShield catches these before the password reset, not after.

- Triggered automatically on every email breach detection
- Five-step inbox backdoor audit delivered as a WhatsApp conversation
- Step 1: Silent forwarding rules — the most dangerous and most overlooked
- Step 2: Unknown recovery email addresses and phone numbers
- Step 3: Malicious inbox filters deleting security alerts and bank notifications
- Step 4: Unauthorised OAuth app permissions (survive password resets entirely)
- Step 5: Active sessions on unknown devices
- Sweep must complete BEFORE password reset — this sequence is the product insight
- No competitor offers this. Not Aura. Not LifeLock. Not Foretrace.

### 2. Conversational AI Remediation in WhatsApp ✅ LIVE
**The channel is not a feature — it is the product.** Security alerts sent by email are ignored. Security guidance delivered as a two-way WhatsApp conversation at 90%+ open rates, available at 3am, with no hold queue, in plain language — that is a fundamentally different experience.

- Step-by-step guidance via WhatsApp conversation — powered by Claude API
- Two-way: users reply, ask questions, confirm steps — not a one-way broadcast
- Available 24/7 with no hold time, no upselling, no friction
- Competitors send one-directional alerts and assume users know what to do next

### 3. Remediation Status Tracking ✅ LIVE
**Every other service measures alerts sent. RelayShield measures people actually protected.**

- Per-breach remediation status tracked in DynamoDB (pending / started / completed / snoozed / ignored)
- Day 1: Breach detected → Email Security Sweep triggered
- Day 3: Follow-up if status still pending — "Have you completed the password reset?"
- Day 7: Reminder if remediation outstanding
- Day 14: Final prompt — close the loop or escalate
- Reduces churn: users who complete remediation feel protected and stay subscribed
- No competitor tracks whether you actually did anything after their alert

### 4. Breach Severity Scoring ✅ LIVE
**Not all breaches are equal. Only RelayShield tells you which one to fix first.**

- CRITICAL: Financial institutions, email providers, healthcare, government
- HIGH: Social media platforms, e-commerce with saved payment cards
- MEDIUM: Shopping sites, forums, subscription services
- LOW: Gaming sites, dormant accounts with minimal PII
- Claude API assesses severity from organisation type and exposed data classes
- Tells users which breach to remediate first when multiple are detected simultaneously
- No competitor offers this at consumer or SMB price point

### 5. Telecom Layer — Phase 2 Moat
**The only identity protection capability built on 25 years of carrier-layer expertise.**

- SIM swap detection and real-time alerts via carrier monitoring
- Port-out fraud monitoring — catches number transfer to a different carrier
- eSIM unauthorised provisioning detection — new attack surface carriers don't fully protect
- Phone number dark web exposure detection
- SS7 vulnerability awareness built into remediation flows
- Carrier change monitoring via Twilio Lookup API
- No competitor — not Aura, not Foretrace, not LifeLock — addresses telecom-layer identity threats
- Founder's background is the credibility moat; cannot be faked by a software company

**SIM/eSIM Swap Monitoring — tiered by plan:**

| Tier | What's included |
|---|---|
| Personal Shield | Detection alert only — "SIM or eSIM change detected. Call your carrier NOW." |
| Business Basic+ | Detection + carrier-specific hardening steps (AT&T/T-Mobile/Verizon) + eSIM profile audit guidance |
| Business Shield Pro | All above + SIM lock onboarding flow + eSIM provisioning disable option + FCC complaint guidance |

**eSIM-specific detection and response:**
- Twilio Verify SIM Swap API detects both physical SIM swaps and eSIM provisioning events via IMSI change detection
- On eSIM-flagged event: alert distinguishes eSIM vs physical SIM where detectable; delivers eSIM profile audit steps via carrier app
- eSIM provisioning disable: where carrier supports it, Pro users are guided to disable remote eSIM provisioning entirely — strongest available protection
- FCC July 2024 mandate requires carriers to immediately notify customers of SIM/eSIM changes — RelayShield intercepts this signal and acts before the attacker reaches financial accounts
- Port-out fraud detection: number transferred to a different carrier flagged as CRITICAL

**SIM Lock Onboarding Flow — Business Shield Pro only:**
During onboarding, RelayShield walks Pro users through enabling their carrier's SIM lock via WhatsApp — before any breach is detected. Carrier-specific steps delivered conversationally:
- AT&T: Enable Wireless Account Lock in myAT&T app; disable eSIM provisioning if supported
- T-Mobile: Enable SIM Protection (requires in-store photo ID to remove — strongest option)
- Verizon: Enable Number Lock in My Verizon app; check eSIM Management settings
This is genuine prevention layered on top of monitoring. Monitoring then catches bypass attempts — insider threats, social engineering, eSIM provisioning — even after the lock is in place.

**Why SIM locks don't eliminate the need for monitoring:**
- Carrier employees are actively bribed $300–$3,000 per swap (documented Telegram recruitment channels)
- T-Mobile call centre agents have issued remote eSIM QR codes despite "extra security" being enabled
- Port-out fraud to a different carrier partially bypasses same-carrier SIM locks
- FCC July 2024 mandate requires carriers to immediately notify customers of SIM changes — RelayShield intercepts this signal and acts before the attacker reaches financial accounts
- 56% of consumers still use SMS 2FA — they are directly exposed until they migrate to authenticator apps

**Authenticator app migration — built into breach remediation:**
When a breach is detected on any account using SMS 2FA, the remediation flow includes a carrier-specific step to migrate to an authenticator app (Google Authenticator, Authy). Delivered per platform — Gmail, Square, banking apps — via WhatsApp. Closes the SMS 2FA exposure window regardless of whether a SIM swap has occurred.

### 6. SMB Account Management Dashboard — Phase 2
**The only purpose-built breach response product for teams under 25 people, priced under $200/month.**

RelayShield's dashboard is an **account management tool, not an employer surveillance tool.** Alerts go directly to each individual's WhatsApp — the owner never sees breach details or personal data. This privacy-respecting design works across employees, contractors, partners, and family members equally.

**What the owner sees:**
- Seat usage and onboarding status (who has set up, who hasn't)
- Aggregate risk indicators (e.g. "2 team members have unresolved alerts") — without naming individuals or breach details
- Billing and subscription management
- Add / remove seats

**What the owner cannot see (by design):**
- Individual breach details or which services were exposed
- Personal data of any seat holder
- WhatsApp conversations or remediation actions taken

**Why this matters competitively:** Flare and employer-focused competitors route breach data through the employer. RelayShield routes it to the individual — making it the only product that works for businesses with contractors or partners where employer surveillance would be legally or ethically problematic.

- Domain-level scanning — catch new seat holder breaches as they join
- No SMB-priced competitor serves this segment with a purpose-built product

### 7. Exfiltration Detection — Phase 2
**Catches data being stolen now — not data stolen two years ago.**

- Stealer log monitoring via Flare API — real-time credential theft from info-stealer malware
- Telegram dark web channel monitoring — 57K+ channels, catches credentials before HIBP
- Secret and API key exposure via GitGuardian — developer credential leaks
- Dark web marketplace monitoring — data listed for sale detection
- Domain spoofing and typosquatting via dnstwist — impersonation early warning
- Closes the data depth gap with Foretrace while maintaining every delivery advantage

### 8. Vishing Preparedness Engine — Phase 1 Enhancement
**The only identity protection service that connects breach detection to AI voice attack preparedness — for both consumers and businesses.**

**Why this matters now:** AI voice cloning tools cost under $10/month and require under 10 seconds of source audio. AI-powered call centres run fully automated vishing campaigns at scale. The FBI reported $2.9 billion in losses from vishing and BEC combined in 2023. The Aura March 2026 breach — affecting a company with hundreds of security engineers — was caused by a single targeted phone call on one employee. The barrier to a devastating vishing attack is now effectively zero.

**The core RelayShield insight:** Dark web monitoring does not detect an active vishing call — that is not the right framing. What it detects is the breach data that makes vishing calls convincing. A caller who knows your name, address, carrier, and last 4 of your account number sounds legitimate. That data comes from breaches. Detect the breach — warn the consumer before the call happens.

**Consumer vishing alert — triggered automatically on breach detection:**

Activated when a breach exposes data classes used to make vishing calls convincing: phone number, address, carrier details, account numbers, SSN partial.

> *"⚠️ The [breach name] breach exposed your [phone number / address / carrier details]. Attackers use this data to call you pretending to be your bank, mobile carrier, or a government agency — using your real name and details to sound legitimate.*
>
> *If you receive any unexpected call in the next 30 days:*
> *→ Never confirm personal details to an inbound caller*
> *→ Never read an OTP code to a caller — no legitimate company will ask for this*
> *→ Hang up and call back on the official number from the company's website*
> *→ If the caller claims urgent action is needed, that urgency is the attack*
>
> *Reply SAFE to confirm you have read this, or CALL if you have already received a suspicious call."*

**Business vishing alert — team-wide, triggered by domain breach:**

Activated when employee credentials or domain data appear in a breach. Admin receives alert plus team briefing to forward.

> *"⚠️ Employee credentials from [domain] were detected in the [breach]. This data is used to run targeted vishing campaigns against employees.*
>
> *Your team may receive calls from:*
> *→ Fake IT helpdesk asking for credentials or remote access*
> *→ Fake CEO or executive requesting urgent wire transfers*
> *→ Fake carrier representative requesting account verification*
> *→ Fake vendor requesting a change of bank account for invoice payments*
>
> *Forward this to your team: If any employee receives an unexpected call requesting credentials, payments, or account changes — hang up and verify through a known internal channel before taking any action.*
>
> *Reply BRIEF to receive a ready-to-forward team briefing, or TRAINING for a full WhatsApp vishing awareness walkthrough."*

**Personal verification protocol — delivered during onboarding:**
- **Callback rule:** Never act on inbound calls for credentials or payments — always call back on the official number
- **OTP rule:** No legitimate company will ever ask you to read out a one-time code
- **Family safe word:** Establish a personal verification code with trusted family members — AI voice cloning makes this essential
- **Wire transfer rule:** Any urgent request for a bank transfer from a voice call is fraud until verified through a separate written channel

**Phase 2 — dark web vishing campaign monitoring via Flare API:**
- Monitor dark web forums for target lists containing monitored emails, domains, or phone numbers packaged for vishing campaigns
- Detect vishing call scripts impersonating specific banks, carriers, or government agencies
- Surface OTP interception service listings — real-time tools sold to enable live vishing attacks
- Alert customers when their data appears in a pre-packaged vishing target list: CRITICAL severity

**Why no competitor does this:**
Every competitor detects the breach and stops. None connect the breach data to the specific downstream attack it enables. None warn consumers that their carrier details are now in the hands of someone who will call them pretending to be AT&T. None deliver a team-wide business briefing when employee credentials are compromised. RelayShield closes this gap in Phase 1 with no new infrastructure — the breach detection trigger already exists, the WhatsApp delivery already exists, the Claude AI prompt is the only addition.

### 9. Session Hijacking Detection Engine — Phase 1 Enhancement
**The only identity protection service that warns consumers and SMBs before a stolen session cookie becomes a full account takeover.**

**Why this matters now:** Tycoon 2FA, EvilProxy, and LummaC2 info-stealer malware have made password-based authentication an unreliable security boundary. Attackers no longer need your password. They steal the authenticated session token — the cookie your browser holds after you log in — and replay it from a different machine. No password required. No 2FA prompt triggered. The breach monitoring layer (HIBP, stealer logs) is the only early warning system that exists before the session theft becomes an account takeover.

**The three attack vectors RelayShield detects and warns against:**

**1. AiTM Phishing (Tycoon 2FA / EvilProxy):**
Adversary-in-the-middle proxy sits between victim and legitimate login page. Victim completes full login including 2FA. Proxy harvests the authenticated session cookie. 2FA is defeated — the attacker has a valid session without ever knowing the password. Tycoon 2FA sells access via Telegram for ~$120/month. No technical expertise required.

**2. Info-Stealer Malware (LummaC2, RedLine, Raccoon, Vidar):**
Malware installed on victim device extracts all browser-saved credentials AND active session cookies simultaneously. Credentials sold on Telegram markets within hours of theft. Credential appears in stealer logs before any public breach database is updated — caught by Flare API (Phase 2), not HIBP.

**3. OAuth Token Abuse:**
Attacker tricks victim into granting OAuth permissions to a malicious app. App retains persistent access via refresh token — survives password resets and 2FA changes. Revocation requires explicit OAuth permissions audit.

**Phase 1 — Detection and awareness (no new infrastructure required):**
- **Session cookie / auth token exposure detection** — Add "Auth tokens" and "Session cookies" to HIGH_VALUE_DATA_CLASSES; when detected in a breach, trigger CRITICAL alert with immediate session revocation steps
- **AiTM awareness block in breach alerts** — when passwords + email are both exposed in a breach, append a targeted Tycoon 2FA warning: "Attackers use exposed credentials to run phishing sites that defeat your 2FA by stealing your session token — change the password AND revoke all active sessions immediately"
- **SESSIONS WhatsApp command** — on-demand guided session audit: check active logins (Google, Microsoft, Facebook, Instagram), revoke OAuth tokens, sign out all unknown devices
- **OAuth token revocation guide** — when a Google or Microsoft-linked account breach is detected, include explicit steps to audit and revoke third-party OAuth app permissions

**Phase 2 — Active session anomaly detection (requires cloud audit log access):**
- Google Workspace audit log monitoring — detect impossible travel (simultaneous logins from geographically separated IPs), mass email deletion (attacker covering tracks), and new device logins at unusual hours
- Microsoft 365 audit log monitoring — same pattern; covers SMB teams on M365
- Concurrent session anomaly alerting — CRITICAL WhatsApp alert when active sessions detected from two or more distinct geographic locations simultaneously
- Stealer log session token detection via Flare API — extend Flare integration to flag when session cookies (not just credentials) appear in stealer logs; tokens have a shorter exploitation window than passwords — alert must fire within minutes

**SMB opportunity:**
Every SMB on Google Workspace or Microsoft 365 is exposed. A single stolen session cookie gives an attacker full access to email, files, and connected apps — without triggering any MFA prompt. The session audit capability positions RelayShield as the only SMB tool that catches what 2FA misses. Direct tie-in to the Tycoon 2FA blog post as lead-gen content.

**Why no competitor does this:**
Aura, Foretrace, and HIBP all stop at credential detection. None warn specifically about session token theft vectors. None deliver a real-time guided session revocation flow via WhatsApp. None connect the breach data to the specific AiTM attack pattern it enables. RelayShield closes this gap in Phase 1 with no new infrastructure.

### 10. AI-Native Architecture and Dataset Moat
**Every interaction builds a proprietary dataset no competitor can replicate from scratch.**

- AI is the engine, not a bolt-on feature
- Every remediation conversation, severity assessment, and sweep outcome is structured and logged
- Dataset becomes independently monetisable: threat intelligence API, industry reports, benchmarks
- Enables predictive breach risk scoring in Phase 3

---

## 5. Breach Intelligence Engine

### Core HIBP API Capabilities

**Email Breach Monitoring** — $4.50/month (Pwned 1, 10 RPM)
- Daily scheduled check per monitored email
- New breach → WhatsApp alert + Claude remediation
- DataClasses field reveals phone number exposure
- Upgrade trigger: Pwned 2 ($22/month, 50 RPM) at 50+ paying customers

**Password Exposure Response** — FREE (no additional API)
- Detection source: HIBP DataClasses field — "Passwords" in breach data = password compromised
- No user password submission required — response triggered by breach data alone
- Cross-account reuse walkthrough delivered via WhatsApp (REUSE command)
- Password manager master password alert when `password_manager_user = True`
- Strategic decision: RelayShield does not implement Pwned Passwords hash checking — detection is not our lane

**Domain Scanner** — Included in Pwned 1
- SMB onboarding → instant domain-wide exposure report
- Returns all breached employee emails for a domain
- 25 breached emails per domain (Pwned 1 limit)
- Weekly re-scan for new employee breaches

### SMS Protection Layer
- Phone number exposure detection (HIBP DataClasses)
- SS7 vulnerability advisory via Claude remediation
- Smishing awareness guidance post-breach
- Carrier change monitoring via Twilio Lookup API (~$0.01/lookup)

---

## 6. Phase 1 AI Remediation Engine

### RelayShield vs HIBP — Why We Win

| Capability | HIBP Free | RelayShield Phase 1 |
|---|---|---|
| Breach lookup | ✅ Manual, one-time | ✅ Automated daily monitoring |
| Alerts | ❌ Email only (ignored) | ✅ WhatsApp (90%+ open rate) |
| Remediation | ❌ None | ✅ Conversational AI step-by-step |
| Breach severity scoring | ❌ None | ✅ Critical/High/Medium/Low |
| Remediation tracking | ❌ None | ✅ Follow-up until resolved |
| Inbox backdoor sweep | ❌ None | ✅ 5-step Email Security Sweep |
| Password checking | ✅ Manual lookup | ✅ Built into onboarding flow |
| Domain scanning | ❌ None | ✅ SMB multi-email monitoring |
| Phone exposure | ❌ None | ✅ DataClasses detection |
| Carrier monitoring | ❌ None | ✅ Twilio Lookup |
| Cross-account password risk | ❌ None | ✅ Guided reuse detection |
| SMB team dashboard | ❌ None | ✅ Phase 1 feature |
| Pricing | Free | $12-$99/month (founding) / $14.99-$99 standard |

**The core distinction:**
> HIBP answers: *"Was I ever breached?"*
> RelayShield answers: *"Am I breached right now — and here is exactly what to do about it."*

---

### Breach Severity Scoring

Every breach alert includes a severity rating before any remediation steps:

```
CRITICAL:   Financial institutions, email providers,
            healthcare, government — act immediately

HIGH:       Social media, e-commerce with saved
            payment cards — act within 24 hours

MEDIUM:     Shopping sites, forums, subscription
            services — act within 1 week

LOW:        Gaming sites, old accounts with
            no PII — note and monitor
```

**Claude system prompt addition:**
```
"Assess the severity of each breach as CRITICAL, HIGH,
MEDIUM, or LOW based on the organisation type and data
classes exposed. Lead every alert with the severity
level. Explain specifically why this breach poses risk
to this user based on their exposed data types. Tell
them which breach to remediate first if multiple are
detected simultaneously."
```

---

### Remediation Status Tracking

Per-breach tracking stored in DynamoDB `relayshield_breach_alerts` table:

```
remediation_status field values:
  "pending"       → Breach detected, alert sent
  "started"       → User replied and began remediation
  "completed"     → User confirmed completion
  "snoozed"       → User requested reminder later
  "ignored"       → No response after 14 days
```

**Follow-up WhatsApp conversation flow:**
```
Day 1:  Alert sent + remediation started
        "Reply START to begin your Email Security Sweep"

Day 3:  Follow-up if status = "pending" or "started"
        "You started remediation for [breach] 3 days ago.
         Have you completed the password reset?
         Reply YES to mark complete or HELP to continue."

Day 7:  Reminder if still outstanding
        "Reminder: [breach] remediation still open.
         Reply STEPS to continue where you left off."

Day 14: Final reminder
        "This is your last reminder about the [breach]
         breach. Reply DONE if resolved or HELP if
         you need assistance."
```

---

### Email Security Sweep — 5-Step Inbox Backdoor Audit

**Triggered automatically on every email breach detection.**

**Why sweep BEFORE password reset:**
```
Changing password without sweeping = changing front door lock
while leaving a window open. Attackers keep access via:
  → Forwarding rules (survive password reset)
  → OAuth tokens (survive password reset)
  → Recovery email changes (survive password reset)
```

**WhatsApp trigger message:**
```
"🔴 RelayShield: [email] was found in the [breach] breach.
[SEVERITY LEVEL]

Before changing your password, I need to check if
attackers already have backdoor access to your inbox.

Reply SWEEP for a 5-minute Email Security Sweep:
✓ Silent forwarding rules (most dangerous)
✓ Unknown recovery options
✓ Malicious inbox filters
✓ Unauthorised app permissions
✓ Active sessions on unknown devices

Completing this sweep BEFORE your password reset
closes every backdoor. Ready? Reply SWEEP."
```

**Step 1 — Silent Forwarding Detection (Most Critical)**
```
Attackers set up auto-forwarding rules so all your
emails are silently copied to them. You never notice
because emails still arrive normally.

Gmail:
→ Settings → See all settings → Forwarding and POP/IMAP
→ Delete any forwarding addresses you did not set up

Yahoo:
→ Settings → More settings → Mailboxes → Forwarding

Outlook:
→ Settings → Mail → Forwarding → Disable unknown rules
```

**Step 2 — Unknown Recovery Options**
```
Attackers add their own recovery email or phone to lock
you out and take over at any time.

Gmail: myaccount.google.com/security
Yahoo: account.yahoo.com/security
→ Remove any recovery email/phone you do not recognise
→ Verify your own recovery options are current
```

**Step 3 — Malicious Inbox Filters**
```
Attackers create rules that delete security alerts,
password reset emails, and bank notifications so you
never see warnings about suspicious activity elsewhere.

Gmail:
→ Settings → Filters and Blocked Addresses
→ Delete any filter that deletes, skips inbox,
  or forwards emails you did not create

Outlook:
→ Settings → Rules → Delete unknown rules
```

**Step 4 — Unauthorised OAuth App Permissions**
```
Attackers grant themselves persistent app access that
survives password resets entirely.

Gmail: myaccount.google.com/permissions
Yahoo: account.yahoo.com/security/connected-apps
→ Review all connected apps
→ Revoke anything unrecognised
```

**Step 5 — Active Sessions on Unknown Devices**
```
Gmail:
→ Scroll to bottom of inbox
→ Click "Details" (bottom right corner)
→ Sign out all other sessions

Yahoo:
→ account.yahoo.com/security/recent-activity
→ Terminate unknown sessions
```

**After sweep completes → password reset begins:**
```
"✅ Email Security Sweep complete. All 5 checks done.
Now let us reset your [breach service] password.

Rule: Use a unique password for every service.
Never reuse passwords across accounts.
Reply RESET for a strong password guide, or
MANAGER for password manager recommendations."
```

---

### Cross-Account Password Risk Detection

Triggered when a breach exposes a password:

```
"[Breach service] exposed your password.

If you used the same password on any of these,
those accounts are also at risk:
  → Gmail or other email providers
  → Your bank or financial accounts
  → Amazon, PayPal, or shopping accounts

Reply CHECK and I will walk you through
each high-risk account one at a time."
```

---

## 7. Exfiltration Detection Engine (Phase 2)

### The Key Distinction
```
DATA EXFILTRATION PREVENTION    Stops data leaving a system in real time
                                 Requires: network agents, endpoint software
                                 → Enterprise DLP territory — NOT RelayShield's lane

DATA EXFILTRATION DETECTION     Identifies that data HAS been stolen
                                 Requires: dark web monitoring, secret scanning,
                                 domain monitoring
                                 → EXACTLY RelayShield's lane
```

### Capability 1 — Secret and API Key Exposure Monitoring
**Tool:** GitGuardian API | **Cost:** Free tier → $29/month

- Monitors GitHub, GitLab, Bitbucket public repositories and Pastebin
- Detects exposed API keys, database credentials, AWS keys, Twilio tokens
- Scans for secrets tied to user's monitored domain
- Returns: exact file, line number, secret type exposed
- Lambda checks GitGuardian API daily
- WhatsApp alert on detection:
  > *"⚠️ An API key linked to yourdomain.com was found in a public GitHub repository. Reply DETAILS for location and immediate revocation steps."*

### Capability 2 — Dark Web Data Sale Monitoring
**Tool:** Flare API | **Cost:** ~$50-100/month SMB tier

- Monitors dark web forums and illicit marketplaces
- Detects data sale listings mentioning user's domain
- Identifies bulk credential dumps containing domain emails
- Flags threat actor posts mentioning company names
- Domain-level scan added to existing HIBP domain check workflow
- WhatsApp alert on detection:
  > *"🔴 Data matching yourdomain.com was detected in a dark web marketplace listing. Reply URGENT for immediate response steps."*

### Capability 3 — Domain Spoofing and Typosquatting Detection
**Tool:** dnstwist (open source Python) | **Cost:** FREE

- Generates 100+ lookalike variations of monitored domain
- Checks which variations are newly registered and active
- Returns: registered lookalikes, IP addresses, mail server configs
- Weekly Lambda function runs dnstwist on each monitored SMB domain
- WhatsApp alert on detection:
  > *"⚠️ A domain impersonating yourdomain.com was registered 3 days ago: y0urdomain.com. This is a common data theft precursor. Reply STEPS for immediate action."*

### Capability 4 — Cloud Account Anomaly Detection
**Tool:** Google Workspace Admin SDK + Microsoft Graph API | **Phase 3**

- Monitors Google Drive and Microsoft 365 audit logs
- Detects unusual bulk downloads, new external sharing, login anomalies
- Flags new country logins and unrecognised device access
- Requires OAuth permissions from SMB admin
- Strong retention driver once implemented

### Phase 2 Additional Monthly Costs

| Capability | Tool | Cost |
|---|---|---|
| Secret/API key scanning | GitGuardian | ~$29/month |
| Dark web data monitoring | Flare API | ~$75/month |
| Domain spoofing detection | dnstwist | FREE |
| **Phase 2 addition** | | **~$104/month** |
| **Phase 2 total running costs** | | **~$139/month** |

Break even at Phase 2: 2 SMB clients at $99 = $198 — covers all costs with margin.

---

## 7. Competitive Analysis

### Competitor Map

| Competitor | Threat Level | Category |
|---|---|---|
| **Aura** | 🔴 High | Identity protection suite |
| **Flare / Foretrace** | 🔴 High | Enterprise dark web intelligence + new B2B2E employee product |
| **LifeLock/Norton** | 🟡 Medium | Consumer brand |
| **HaveIBeenPwned** | 🟡 Medium | Free breach lookup |
| **SpyCloud** | 🟢 Low | Enterprise only ($500+/month) |
| **Incogni** | 🟢 Low | Adjacent category (data broker removal) |
| **IsItDangerous** | 🟢 Low | Different problem, weakening position |

---

### Aura — Primary Competitor

**What they do:** AI-powered all-in-one digital safety platform. Credit monitoring (3-bureau), dark web scanning, financial account monitoring, identity document monitoring, home/property title monitoring, antivirus (10 devices), VPN, password manager, data broker removal (200+ sites), and $1M–$5M fraud insurance.

**Key facts:**
- $1.6B valuation, $672M funding, $300M+ ARR
- 1.1M+ subscribers, 1,700+ employer partners
- Fraud alerts delivered up to 650x faster than competitors (2025 testing)
- March 2026 data breach — 900,000 records exposed (details below)

**March 2026 Breach — Accurate Detail:**
The breach is a trust event, but less catastrophic technically than initially reported:
- **860,000** records were marketing contacts who were never Aura customers (acquired with a 2021 acquisition)
- **~20,000** active customer records exposed: name, email, address, phone, customer service notes only
- **~15,000** former customer records: same fields
- **NOT exposed:** SSNs, passwords, financial data, payment cards — core protection data was not compromised
- **Cause:** Targeted phone phishing attack on an Aura employee → compromised marketing tool access (~1 hour window)

The trust damage is real — an identity protection company that cannot protect its own customer list is a powerful narrative regardless of technical scope. The attack vector (social engineering of an employee) is also ironic given their product category.

**Full Aura Capability Inventory:**

| Capability | Aura Detail |
|---|---|
| Dark web monitoring | Scans dark web marketplaces, forums, criminal chat rooms, breach databases |
| Breach database monitoring | Yes — email, phone, SSN, credit card, DL, passport |
| Credit monitoring | 3-bureau (Experian, TransUnion, Equifax) — alerts in minutes |
| Credit lock | Experian only — must lock TransUnion and Equifax manually |
| Financial account monitoring | Up to 20 linked accounts — bank, credit, investment, 401k |
| Identity document monitoring | SSN, passport, driver's licence, government ID |
| Home/property title monitoring | Home and vehicle title fraud detection |
| Data broker removal | 200+ data broker sites — automated, recurring |
| Fraud insurance | $1M–$5M (one claim per 12-month period, pre-existing fraud excluded) |
| Password manager | Included — OTP/2FA, email alias, file vault |
| VPN | Included — all plans |
| Antivirus | Included — up to 10 devices |
| Alert delivery | Email, SMS, in-app push — one-way only |
| Remediation | 24/7 human phone/chat support, white-glove fraud recovery |
| Social media monitoring | Conflicting reports — likely limited or absent |
| USPS address change | Not monitored |
| Medical ID monitoring | Not monitored |
| SIM swap / telecom | Not monitored |
| Stealer log monitoring | Not confirmed |
| SMB product | No purpose-built SMB offering |
| WhatsApp (two-way) | No |
| Conversational AI remediation | No |
| Exfiltration detection | No |

**Confirmed gaps RelayShield exploits:**

| Aura Gap | RelayShield Advantage |
|---|---|
| Zero SIM swap / eSIM swap detection | SIM/eSIM swap detection on ALL tiers — detection alert (Personal), carrier hardening steps (Business+), SIM lock onboarding (Pro) |
| Zero stealer log / Telegram monitoring | Phase 2 via Flare API |
| One-way alerts only (email/SMS/app) | Two-way WhatsApp conversational AI |
| No Telegram | Phase 2 roadmap |
| No SMB purpose-built product | Core SMB offering at $79–$199/month |
| No breach severity scoring | Critical/High/Medium/Low per breach |
| No Email Security Sweep | 5-step inbox backdoor audit before password reset |
| No remediation tracking / follow-up | Day 1/3/7/14 follow-up until resolved |
| Social engineering vulnerability | Telecom-layer awareness and training built into remediation flows |
| No published accuracy benchmarks | Explicit commitment from Day 1 |
| No predictive analytics | Phase 2-3 roadmap |
| No exfiltration detection | Phase 2 differentiator |
| Billing and cancellation complaints | Self-serve, transparent pricing, no cancellation friction |
| March 2026 breach — trust crisis | Actively monitoring your data while Aura was breached |
| No USPS address change monitoring | Phase 2 roadmap addition (see gap analysis below) |

**Where Aura leads RelayShield (honest gaps to address):**

| Aura Capability | RelayShield Status | Roadmap Response |
|---|---|---|
| 3-bureau credit monitoring | ❌ Not offered | Phase 3 — requires credit bureau partnerships |
| Financial account monitoring (up to 20 accounts) | ❌ Not offered | Phase 2 — Plaid API integration |
| Identity document monitoring (SSN, passport, DL) | ⚠️ Partial — HIBP flags when these appear in breach data | Phase 1 enhancement — explicit SSN/document field in monitoring |
| $1M–$5M fraud insurance | ❌ Not offered | Phase 3 — underwriting partnership |
| Data broker removal (200+ sites) | ❌ Not offered | Phase 2 — partner with Incogni/DeleteMe API rather than build |
| Password manager | ❌ Not built-in | Phase 2 — integrate or recommend 1Password/Bitwarden |
| VPN | ❌ Not offered | Phase 3 — white-label partnership |
| Antivirus (10 devices) | ❌ Not offered | Out of scope — not RelayShield's lane |
| Home/property title monitoring | ❌ Not offered | Phase 3 — public records API |
| 24/7 human fraud support | ❌ AI only | Phase 2 — escalation path to human for complex cases |

**Positioning against Aura:**
> *"Aura was breached by a phishing attack on one of their own employees — the exact attack vector their product is supposed to protect you from. RelayShield's breach detection, Email Security Sweep, and telecom-layer monitoring catch the threats Aura cannot see. And unlike Aura, we walk you through exactly what to do next — right in your WhatsApp, at 3am, without a hold queue."*

**Migration pitch for displaced Aura customers:**
> *"If you were an Aura customer affected by their March 2026 breach, your name, email, and address are now in the hands of the same attackers Aura is supposed to protect you from. RelayShield monitors for exactly this kind of personal data exposure — and when we detect it, we guide you through every remediation step in WhatsApp. No hold queues. No upselling. Just protection."*

---

### Incogni (by Surfshark) — Adjacent Competitor

**What they do:** Automated data broker removal service. Sends legally-binding opt-out requests to 420+ data brokers under GDPR/CCPA. Repeats every 60-90 days.

**Key facts:**
- $7.99/month annual, 245M+ removals
- Deloitte-verified (August 2025)
- No dark web monitoring by design

**Critical vulnerability:**
> Incogni's own Help Center states: *"Once your data is on the dark web, it's too late."*
> RelayShield operates precisely in the space Incogni publicly surrenders.

**Positioning against Incogni:**
> *"Already using a data removal service? Smart start. Now add the protection layer it can't provide."*

**Strategic play:** Target Incogni's 2M+ users as a warm audience — they are already privacy-conscious and paying for security tools.

---

### IsItDangerous — Not a Real Competitor

**What they do:** WhatsApp-based message and URL verification. Forward a suspicious link, receive Safe/Caution/Dangerous verdict. Built on Payemoji platform.

**Why they are not a threat:**
- Reactive (check after receiving a threat) vs RelayShield proactive
- No dark web monitoring, no breach detection, no telecom layer
- Meta launched native WhatsApp anti-scam tools March 2026 — existential threat to IsItDangerous
- No SMB product, no conversational remediation

---

### Flare / Foretrace — Most Significant New Threat (March 2026)

**What they do:** Flare is an enterprise threat exposure management platform. In March 2026 they launched **Foretrace** — a B2B2E (business-to-business-to-employee) product delivering personal identity protection to employees via employer adoption. Foretrace was originally a standalone competitor that Flare acquired in 2024.

**Data infrastructure (critical to understand):**
- 100 million stealer logs monitored
- 57,000+ Telegram dark web channels monitored in real-time
- 20 billion leaked credentials in proprietary database
- Fully independent dataset — does not rely on HIBP
- Detects credential exposure **before it reaches public breach databases**

**Key facts:**
- Launched Foretrace GA: March 26, 2026
- Existing enterprise IEM platform integrates with Microsoft Entra ID (automatic credential disabling)
- Forrester reports 321% ROI on enterprise IEM platform
- No public pricing — enterprise sales only, contact required
- No SIM swap or telecom detection

**Foretrace B2B2E model:**
- Employers adopt Foretrace as a security benefit and enrol employees
- Employees get a **private personal identity profile** — employer cannot view individual data
- Employer gains organisational risk reduction without surveillance of individuals
- Delivered via Flare web platform — no WhatsApp, no conversational AI

**Confirmed gaps RelayShield exploits:**

| Foretrace Gap | RelayShield Advantage |
|---|---|
| No WhatsApp delivery | Two-way WhatsApp AI remediation — 90%+ open rate |
| No conversational AI remediation | Step-by-step Claude-powered guidance |
| No telecom / SIM swap layer | Core Phase 2 capability |
| No SMS / phone number exposure | HIBP DataClasses detection |
| Employer cannot see employee data | RelayShield routes alerts to individuals — owner sees aggregate status only, never individual breach details |
| Requires employer adoption (B2B2E only) | RelayShield reaches individuals directly — no employer needed |
| No breach severity scoring | Critical/High/Medium/Low per breach |
| No remediation follow-up tracking | Day 1/3/7/14 follow-up until resolved |
| No Email Security Sweep | 5-step inbox backdoor audit |
| No pricing transparency | Self-serve, published pricing, no sales call |
| No SMB self-serve | RelayShield direct sign-up at $79/month |

**The critical data gap Foretrace exposes:**

> ⚠️ **HIBP monitors historical public breach databases. Foretrace monitors stealer logs — credentials captured right now by info-stealer malware, sold on Telegram before any public database is updated. These are fundamentally different threat vectors. RelayShield Phase 2 (Flare API integration) closes this gap.**

See Section 7.1 — Breach Intelligence Source Comparison for full analysis.

**Positioning against Foretrace:**
> *"Foretrace requires your employer to adopt it and can't tell you what to do next. RelayShield protects you directly — no employer required — and walks you through exactly what to do in your WhatsApp, including the telecom threats Foretrace cannot see."*

**Strategic play:** Foretrace validates the B2B2E market. Use their launch as proof that employer-sponsored identity protection is a growing category — then differentiate on direct access, conversational AI, and telecom layer. Target SMB owners who want to protect their team without enterprise procurement cycles.

---

### Breach Intelligence Source Comparison — HIBP vs Stealer Logs
*Section 7.1*

Understanding the difference between these two data sources is critical for RelayShield's roadmap and positioning.

#### What HIBP Monitors (RelayShield Phase 1)

| Attribute | Detail |
|---|---|
| **Source type** | Historical public data breaches |
| **How data enters** | Company databases breached → data published or sold → eventually reported to HIBP |
| **Lag time** | Weeks to months between breach occurring and appearing in HIBP |
| **Examples** | LinkedIn 2016, Dropbox 2012, Adobe 2013 — all historical, all public |
| **What it misses** | Credentials captured by malware on a device last week — not yet public |
| **Cost** | $4.50/month (Pwned 1 plan) |
| **Coverage** | 14 billion accounts across thousands of historical breaches |

#### What Stealer Logs Monitor (Foretrace / Flare — Phase 2 target)

| Attribute | Detail |
|---|---|
| **Source type** | Real-time info-stealer malware output (Redline, Vidar, Raccoon, LummaC2) |
| **How data enters** | Malware infects device → captures credentials live → attacker sells log on Telegram/dark web |
| **Lag time** | Hours to days — often available for sale before victim knows anything happened |
| **Examples** | Employee laptop infected → all saved browser passwords stolen → sold on Telegram channel same day |
| **What it catches** | Active, fresh credential theft not yet in any public database |
| **Cost** | Flare API ~$75/month (already in Phase 2 plan) |
| **Coverage** | 100M+ stealer logs, 57K Telegram channels (Flare dataset) |

#### Why Both Sources Are Needed

```
HIBP alone answers:    "Were your credentials ever part of a known public breach?"
Stealer logs answer:   "Are your credentials actively being sold on the dark web right now?"

A user with zero HIBP hits could still have credentials
actively for sale from a stealer log captured yesterday.
Foretrace catches this. RelayShield Phase 1 does not — yet.
```

#### RelayShield Roadmap Response

| Phase | Action | Closes Gap |
|---|---|---|
| Phase 1 (now) | HIBP monitoring — historical public breaches | Partial — high recall on known breaches |
| Phase 2 | Flare API integration — stealer logs + Telegram channel monitoring | Full — adds real-time stealer log coverage |
| Phase 2 | Dark web marketplace monitoring (Flare) | Full — adds data-for-sale detection |
| Phase 2 | Explicit stealer log alert messaging — "Your credentials were found in a fresh stealer log, not just a historical breach" | Differentiates severity messaging |

**Phase 1 honest positioning:** RelayShield Phase 1 catches historical breaches via HIBP. This is the right starting point — HIBP is fast to integrate, low-cost, and catches the vast majority of credential exposure events. Stealer log coverage (Phase 2) elevates RelayShield to Foretrace's data depth while adding everything Foretrace lacks: WhatsApp delivery, conversational AI, telecom layer, and transparent pricing.

---

### Competitive Pricing Comparison

#### Consumer / Individual Tier

| Competitor | Entry Price | Mid Tier | Top Tier | Primary Focus |
|---|---|---|---|---|
| **Aura** | $12/mo (Individual) | $22/mo (Couple) | $32/mo (Family, 5 adults) | Full-stack: credit monitoring, dark web, VPN, antivirus, $1M–$5M fraud insurance |
| **LifeLock / Norton** | $9.99/mo (Select) | ~$16.67/mo (Advantage) | $29.17/mo (Ultimate Plus) | Credit monitoring, ID theft insurance, dark web alerts, antivirus bundle |
| **Identity Guard** | $7.50/mo (Value, annual) | $16.67/mo (Standard) | $25/mo (Ultra) | 3-bureau credit monitoring, dark web, criminal record monitoring, $1M insurance |
| **McAfee+** | $49.99/yr (Premium) | ~$16.67/mo (Advanced) | $23.33/mo (Ultimate) | Antivirus + ID bundle, credit monitoring, data broker removal |
| **Incogni** | $7.99/mo (Standard, annual) | $14.99/mo (Unlimited) | — | Data broker removal only — 420–2,000+ sites, recurring opt-outs |
| **DeleteMe** | $10.75/mo ($129/yr, 1 person) | $19.08/mo ($229/yr, couple) | $27.42/mo ($329/yr, family 4) | Data broker removal — quarterly reports, up to 40 custom removals |
| **Kanary** | $14.99/mo (annual) | $16.99/mo (monthly) | — | Data broker removal — 150+ sites, 14-day trial |
| **HaveIBeenPwned** | Free (manual lookup) | — | — | Breach database lookup only — no monitoring, no remediation |
| **Flare / Foretrace** | Enterprise only (no public pricing) | — | — | B2B2E employee identity protection — stealer logs, Telegram, 20B credentials, employer-sponsored |
| **RelayShield** | **$12/mo founding** | **$14.99/mo standard** | — | **Breach monitoring + WhatsApp AI remediation + telecom layer** |

#### SMB / Business Tier

| Competitor | Entry Price | What's Included | Gaps |
|---|---|---|---|
| **Aura** | No SMB product | Employee benefit program only (per-seat, negotiated) | No team dashboard, no domain monitoring, no admin controls |
| **LifeLock / Norton** | No SMB product | Individual plans only | No multi-seat, no team management |
| **Identity Guard** | No SMB product | Individual/family plans only | No business offering |
| **McAfee+** | No SMB product | Individual/family plans only | No business offering |
| **Incogni** | No SMB product | Family plan only (5 members, $15.99/mo) | Not purpose-built for business |
| **DeleteMe** | Custom (contact sales) | Employee PII scanning, removals, reporting | Removal-only — no breach monitoring |
| **Kanary** | ~$97/mo (11 users, annual) | Bulk user management, branded access, removal tracking | Removal-only — no breach monitoring, no WhatsApp |
| **HaveIBeenPwned** | $379/mo (Pro API) | Domain breach search, 800 domains, 16K RPM | API product only — no alerts, no remediation |
| **Flare / Foretrace** | Enterprise only — contact sales | Employee identity monitoring via employer, stealer logs + Telegram, private employee profiles | No WhatsApp, no conversational AI, no telecom, requires employer adoption, no self-serve |
| **RelayShield** | **$79/mo founding / $99.99 standard** | **Up to 10 seats, domain monitoring, team dashboard, WhatsApp alerts** | — |
| **RelayShield Pro** | **$149/mo founding / $199 standard** | **Up to 25 seats, SIM swap monitoring, priority support** | — |

#### Key Differentiators — Where RelayShield Wins

| Capability | Aura | LifeLock | Foretrace | Incogni | DeleteMe | RelayShield |
|---|---|---|---|---|---|---|
| Breach monitoring (HIBP / historical) | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |
| Stealer log monitoring (real-time) | ❌ | ❌ | ✅ 100M logs | ❌ | ❌ | ✅ Phase 2 (Flare API) |
| Telegram dark web monitoring | ❌ | ❌ | ✅ 57K channels | ❌ | ❌ | ✅ Phase 2 (Flare API) |
| Data broker removal | ✅ | ✅ (Ultimate) | ❌ | ✅ | ✅ | ❌ Phase 3 |
| WhatsApp alerts (two-way) | ❌ one-way | ❌ | ❌ | ❌ | ❌ | ✅ |
| AI conversational remediation | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Breach severity scoring | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Email Security Sweep | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Remediation follow-up tracking | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| SIM/eSIM swap monitoring | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ All tiers (detection); hardening on Business+ |
| SMB team dashboard (admin view) | ❌ | ❌ | ❌ employer-blind | ❌ | ❌ | ✅ |
| Exfiltration / secret scanning | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ Phase 2 |
| Direct self-serve (no employer needed) | ✅ | ✅ | ❌ B2B2E only | ✅ | ✅ | ✅ |
| Transparent published pricing | ✅ | ✅ | ❌ enterprise sales | ✅ | ✅ | ✅ |
| Credit monitoring | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Fraud insurance | ✅ $1–5M | ✅ $1–2M | ❌ | ❌ | ❌ | ❌ |
| SMB self-serve price point | ❌ no product | ❌ no product | ❌ enterprise only | ❌ no product | Custom | **$79–$149/mo** |

**The whitespace RelayShield owns:** No competitor combines real-time breach monitoring + two-way WhatsApp AI remediation + telecom-layer detection + SMB team dashboard + transparent self-serve pricing under $150/month. Foretrace has superior data depth but requires employer adoption, has no WhatsApp delivery, no conversational remediation, no telecom layer, and no published pricing. RelayShield Phase 2 closes the data depth gap via Flare API while maintaining every delivery and usability advantage.

---

## 8. Product Roadmap

### Phase 1 — Validate (Months 1-3) ✅ COMPLETE

**Week 1 — Breach Detection Engine ✅**
- ✅ HIBP API integration — daily breach monitoring per email
- ✅ DynamoDB schema — users, monitored emails, breach alerts tables
- ✅ Lambda function — relayshield-breach-check (Python 3.14)
- ✅ EventBridge scheduler — relayshield-daily-breach-check
- ✅ AWS Secrets Manager — all credentials stored securely
- ✅ 20 breaches detected across 3 test emails — engine confirmed working

**Week 2 — WhatsApp Alert Delivery ✅**
- ✅ Twilio WhatsApp integration — breach alerts delivered via WhatsApp
- ✅ Breach severity scoring — Critical/High/Medium/Low per alert
- ✅ SMS/phone number exposure detection via HIBP DataClasses
- ✅ SSN, passport, driver's licence breach field detection via DataClasses

**Week 3 — AI Remediation Engine ✅**
- ✅ Claude API conversational remediation — step-by-step WhatsApp guidance
- ✅ Email Security Sweep — 5-step inbox backdoor audit delivered via WhatsApp
- ✅ Remediation status tracking — Day 1/3/7/14 follow-up flows

**Remaining Phase 1 tasks:**
- ⬜ Stripe subscription billing (Week 4)
- ⬜ Carrd landing page (Week 4)
- ⬜ Domain scanner for SMB onboarding (Week 5)
- ⬜ SMB tier end-to-end testing (Week 5)
- ⬜ Password breach checking — Pwned Passwords API (Week 5)
- ⬜ Cross-account password risk detection (Week 5)
- ⬜ Fix empty breach_date field in DynamoDB
- ⬜ First paying customer (Week 6)

**Phase 1 enhancements — Vishing Preparedness Engine:**
- ⬜ **Consumer vishing alert** — Claude prompt addition: when breach exposes phone number, address, carrier details, or account numbers → append vishing warning to WhatsApp alert with OTP rule, callback rule, and urgency-as-attack signal
- ⬜ **Business vishing alert** — domain breach triggers team-wide briefing template covering fake helpdesk, CEO fraud, fake vendor, carrier impersonation scenarios; admin receives alert + ready-to-forward team briefing via WhatsApp
- ⬜ **Personal verification protocol** — onboarding WhatsApp flow: callback rule, OTP rule, family safe word, wire transfer rule — delivered to every new subscriber during setup
- ⬜ **SSN/passport/DL vishing escalation** — when these data classes detected in breach, escalate to CRITICAL severity with explicit identity fraud call warning

**Phase 1 enhancements — Session Hijacking Detection Engine:**
- ✅ **Session cookie / auth token data class detection** — "Auth tokens", "Session cookies", "Authentication tokens" added to HIGH_VALUE_DATA_CLASSES; CRITICAL alert with session revocation steps when detected in any breach
- ✅ **AiTM awareness block** — when passwords exposed in breach, Tycoon 2FA / EvilProxy warning appended to Claude response programmatically (reliability guard ensures it appears regardless of Claude's editorial choices)
- ✅ **SESSIONS WhatsApp command** — 4-step guided session revocation: Google device activity, Google OAuth permissions, Microsoft sessions, social media; ordering enforces revocation before password reset
- ✅ **OAuth token revocation guide** — included in SESSIONS command with direct URLs (myaccount.google.com/permissions, account.microsoft.com/privacy/activity)
- ✅ **Two-message breach alert architecture** — template (always delivered, bypasses 24hr session window) + Claude freeform follow-up (sent immediately when active session exists; gracefully skipped on 63016)
- ⬜ **Auto-send Claude analysis on first reply** — when an ACTIVE user messages after a new breach was detected and no freeform follow-up was sent (63016 at alert time), webhook auto-sends the full Claude analysis before handling their command. Ensures the detailed AiTM/session analysis is never more than one reply away regardless of session state

### Phase 2 — Deepen the Moat (Months 4-8)
*Focus: telecom layer, real-time threat intelligence, SMB dashboard. Do not add features that compete with Aura on their ground.*

**Early Phase 2 — Retention & Billing Automation:**
- ⬜ **Annual upsell webhook** — Stripe `invoice.payment_succeeded` webhook triggers WhatsApp message to subscriber after their 2nd monthly payment offering 10% annual discount with direct portal link. Reduces churn by locking customers into annual plans. Priority: first 10 subscribers.

- **Telecom layer — full implementation:**
  - SIM swap detection and real-time WhatsApp alerts via carrier monitoring
  - Port-out fraud detection — number transfer to a different carrier
  - **eSIM unauthorised provisioning detection** — remote eSIM profile issuance to unauthorised device
  - **SIM lock onboarding flow** — WhatsApp-guided setup of carrier SIM lock (AT&T/T-Mobile/Verizon) during customer onboarding — prevention layer on top of monitoring
  - **Authenticator app migration flow** — when SMS 2FA detected on a breached account, guide user to migrate to authenticator app per platform (Gmail, Square, banking)
  - Carrier change monitoring via Twilio Lookup API — detects carrier switch as early warning
  - SS7 vulnerability advisory built into remediation flows
- Telegram Bot integration + agentic remediation workflows
- Stealer log monitoring via Flare API — real-time credential theft, not just historical breaches
- Telegram dark web channel monitoring via Flare API — 57K+ channels
- Dark web marketplace monitoring via Flare API — data listed for sale detection
- **Vishing campaign monitoring via Flare API** — detect target lists, call scripts, and OTP interception services; CRITICAL alert when monitored email/domain/phone appears in a pre-packaged vishing campaign dataset
- Secret and API key exposure monitoring via GitGuardian API
- Domain spoofing and typosquatting detection via dnstwist (free)
- USPS address change monitoring — alert when postal change of address filed
- SMB team dashboard + per-employee risk scoring
- Published accuracy benchmarks — first in category
- Industry breach intelligence reports — first B2B data product
- Close founding member 3-month rate → all new customers on standard pricing
- Self-serve account registration — customer-facing signup flow with email verification
- SSO via Google — OAuth 2.0 login for consumer and SMB onboarding (update Termly privacy policy when implemented)
- Virtual mailbox address — replace placeholder with permanent business mailing address (Anytime Mailbox or iPostal1)
- **Session hijacking — active detection layer:**
  - Google Workspace audit log monitoring — impossible travel detection, mass email deletion, new device logins
  - Microsoft 365 audit log monitoring — same pattern for SMB teams on M365
  - Concurrent session anomaly alerting — CRITICAL WhatsApp alert when simultaneous logins detected from geographically separated IPs
  - Stealer log session token detection via Flare API — extend Flare integration to flag stolen session cookies specifically; short exploitation window requires near-real-time alerting

### Phase 3 — Monetise the Moat (Months 9-18)
*Focus: data products, carrier partnerships, platform licensing. Still not credit monitoring or fraud insurance — those are Aura's battlefield, not ours.*

- Cloud account anomaly detection (Google Workspace + Microsoft 365 audit logs)
- Predictive breach risk scoring — proprietary model from Phase 1-2 dataset
- Threat intelligence API — sell anonymised breach pattern data to SIEMs and insurers
- Agentic Telegram workflows — autonomous breach patrol and risk briefings
- White-label licensing — carriers, cyber insurers, MSP platforms
- Dataset licensing — anonymised risk benchmarks to research partners
- Carrier partnership programme — RelayShield embedded in telco security bundles
- Data broker scan integration — partner with Incogni or DeleteMe API, resell as RelayShield add-on rather than build from scratch

### Identity Exposure Score (Phase 2 → Phase 3)

**What it is:** A proprietary 0-100 risk score generated by RelayShield for every monitored user — consumer and SMB. No credit bureau required. Built entirely from RelayShield's own monitoring signals.

**Score inputs:**
- Number of active breaches (unresolved)
- Severity of data types exposed (passwords > emails > phone numbers > names)
- SIM swap risk flag (phone number in breach corpus)
- Email backdoor status (forwarding rules, linked apps detected)
- Password found in Pwned Passwords corpus
- Time since last breach remediation
- Recency of breach events

**Score tiers:**
| Score | Rating | Meaning |
|---|---|---|
| 0-30 | 🟢 Low Risk | Minimal exposure, remediation complete |
| 31-60 | 🟡 Medium Risk | Active exposure, action recommended |
| 61-85 | 🟠 High Risk | Multiple unresolved breaches or SIM swap risk |
| 86-100 | 🔴 Critical | Immediate action required |

**SMB capability — per-employee + account-level scoring:**
- Every business seat gets an individual Identity Exposure Score
- Business admin sees an **account-level aggregate score** — weighted average across all employees
- **Score trending** — is the business getting safer or more exposed over time?
- Example dashboard view:
```
Business Risk Score: 67/100 — Medium Risk
Employee 1 (owner):   45 — Low    — no active breaches
Employee 2 (manager): 82 — High   — 2 active breaches, SIM swap risk flagged
Employee 3 (stylist):  71 — Medium — password found in breach corpus
```

**Why this is differentiated:**
- No competitor generates a proprietary remediation-weighted risk score
- Aura and LifeLock show breach alerts — they do not score remediation progress
- RelayShield score improves as the user completes remediation steps — creates engagement loop
- SMB account scoring is unique in the market at this price point

**Delivery:**
- Phase 2: Score delivered in WhatsApp weekly summary message
- Phase 3: Score displayed in SMB team dashboard (web UI)
- Future: Score embedded in Stripe customer portal or dedicated RelayShield app

---

## 9. Telegram Agentic Workflows (Phase 2 Roadmap)

- **Autonomous Breach Patrol Bot** — proactively messages users when new breach data detected
- **Scheduled Risk Briefings** — weekly identity risk score summary
- **Interactive Remediation Flows** — rich inline buttons for step-by-step recovery
- **Team Alert Routing** — SMB admins get Telegram notifications, employees get WhatsApp
- **Agentic Identity Audit** — user triggers full scan via Telegram command
- **Threat Intelligence Briefings** — daily/weekly digest of emerging breach campaigns
- **Exfiltration Alert Routing** — secret exposure and dark web sale alerts via Telegram for SMB admins

---

## 10. Revenue Expansion and Monetization Roadmap

Beyond core subscriptions, RelayShield has multiple compounding revenue streams as the moat deepens. Each layer builds on the previous one — the dataset feeds the API, the API enables white-label, the white-label enables carrier partnerships.

### Layer 1 — Subscription Enhancements (Phase 1-2)

**Annual billing discount**
- Offer 2 months free on annual prepay (~17% discount)
- Consumer: $149.99/year (vs $179.88 monthly) — saves $29.89
- Business Shield: $999/year (vs $1,199.88 monthly) — saves $200.88
- Business Shield Pro: $1,990/year (vs $2,388 monthly) — saves $398
- Benefit: improves cash flow, dramatically reduces monthly churn, signals commitment

**Seat overages**
- Business Shield: base 10 seats — charge $8.99/additional seat/month above 10
- Business Shield Pro: base 25 seats — charge $6.99/additional seat/month above 25
- Creates natural expansion revenue as SMB clients hire

**Add-on modules (à la carte, Phase 2)**
| Module | Price | What it adds |
|---|---|---|
| Telecom Shield | Included all tiers | SIM/eSIM swap detection (all tiers); carrier hardening steps (Business+); SIM lock onboarding (Pro) |
| Domain Guard | +$14.99/mo (SMB) | Domain spoofing + typosquatting weekly scan |
| Secret Sentinel | +$19.99/mo (SMB) | API key + credential exposure monitoring (GitGuardian) |
| Dark Web Watch | +$24.99/mo (SMB) | Dark web marketplace monitoring (Flare) |

---

### Layer 2 — B2B Channel Partnerships (Phase 2-3)

**MSP / Reseller Programme**
- Managed Service Providers (MSPs) serve thousands of SMBs
- Offer 30% wholesale discount: MSP pays $69.99/seat (Business Shield), resells at $99.99
- MSP margin: ~$30/client/month with zero acquisition cost on their end
- Target: IT Glue, ConnectWise, Datto partner ecosystems

**Cyber Insurance Partnerships**
- Cyber insurers (Coalition, At-Bay, Cowbell, Corvus) increasingly mandate security controls
- Partner as a preferred vendor: policyholders get discounted RelayShield as part of their policy
- Model: insurer pays per-policyholder licence fee (~$5-10/month), we get volume; insurer reduces claims
- Value prop to insurer: policyholders who actively monitor and remediate breaches have materially lower claims rates

**Employee Benefits Programme**
- HR and benefits managers (Gusto, Rippling, TriNet platforms) bundle personal identity protection as employee benefit
- Company pays: ~$8-10/employee/month for Personal Shield as a perk
- No sales cycle — employees are auto-enrolled, company pays annually
- Similar model to MetLife, LifeLock employer programs — but at SMB price point
- Target: companies with 10-100 employees on Gusto / Rippling

**Telecom Carrier White-label (Phase 3)**
- Carriers (Verizon, T-Mobile, AT&T MVNOs) bundle identity protection as premium add-on
- Model: carrier white-labels RelayShield under their brand, pays per-subscriber fee (~$3-5/month/subscriber)
- Volume play — even 10,000 subscribers at $4/month = $40,000 MRR from one carrier deal
- Founder's 25-year telecom background = credibility and warm intro potential

---

### Layer 3 — Data and Intelligence Products (Phase 2-3)

**Industry Breach Intelligence Reports**
- Quarterly paid reports: "SMB Credential Breach Report — Q2 2026"
- Target buyers: cyber insurance underwriters, MSPs, compliance consultants, VCs doing due diligence
- Pricing: $499-$1,499 per report, or $2,999/year subscription for all verticals
- Data already being collected from Day 1 — zero incremental cost to produce

**Threat Intelligence API**
- Expose anonymized breach pattern data and remediation outcome data via REST API
- Target: SIEMs, security platforms (Splunk, Datadog), insurance actuaries, compliance tools
- Model: $0.01-0.05 per API call, or $299-999/month subscription tier
- Unique data asset: no other provider has breach detection + remediation outcome + telecom signal combined

**Anonymized Risk Benchmarks**
- Sell aggregated risk scoring data to research institutions, regulators, insurance actuaries
- GDPR/CCPA compliant — fully anonymized, cohort-level only
- Model: research partnership agreements, $5,000-25,000/year per institution

**White-label Platform Licensing (Phase 3)**
- License the entire RelayShield platform to large enterprises or government agencies
- They deploy under their own brand, we receive platform licence fee
- Target: national cybersecurity agencies, large banks, telcos operating in markets without a local equivalent
- Model: $10,000-50,000/month platform licence + implementation fee

---

### Layer 4 — Premium Service Tiers (Phase 2-3)

**Breach Response Retainer**
- One-time emergency service: active breach in progress, priority human + AI assistance
- Pricing: $299 one-time incident fee, or included in Business Shield Pro
- Target: SMB owner whose employee credentials are being actively exploited

**Compliance Reporting Add-on**
- Automated GDPR/HIPAA/CCPA breach notification documentation
- Generates audit-ready incident reports from breach detection events
- Pricing: +$29.99/month (SMB add-on)
- Target: SMBs in healthcare, legal, finance that have regulatory notification obligations

---

### Combined Revenue Potential (Phase 3 Scenario)

| Revenue Stream | Conservative MRR | Stretch MRR |
|---|---|---|
| Consumer subscriptions (500 subscribers) | $6,000 | $7,500 |
| SMB Business Shield (50 clients) | $4,000 | $5,000 |
| SMB Business Shield Pro (20 clients) | $2,980 | $3,980 |
| Seat overages | $500 | $1,500 |
| Add-on modules | $1,000 | $3,000 |
| Annual billing cash (amortised) | $800 | $1,500 |
| MSP/reseller channel | $2,000 | $8,000 |
| Cyber insurance partnerships | $1,500 | $5,000 |
| Intelligence reports / API | $1,000 | $4,000 |
| **Total MRR** | **~$19,780** | **~$39,480** |

The $2,500/month target is a 6-week milestone. The platform architecture being built now supports $20,000-$40,000 MRR with no rebuild required — just additional integrations on the same Lambda/DynamoDB/WhatsApp stack.

**Key principle from Day 1:** Instrument everything. Log signals, outcomes, and remediation responses in structured formats. Every interaction builds the proprietary dataset that powers every revenue layer above.

---

## 11. Technical Architecture

### Tech Stack
| Component | Tool |
|---|---|
| Breach monitoring | HaveIBeenPwned API ($4.50/month) |
| Secret scanning | GitGuardian API (Phase 2) |
| Dark web monitoring | Flare API (Phase 2) |
| Domain spoofing | dnstwist open source (Phase 2) |
| Alert delivery | Twilio WhatsApp (existing stack) |
| AI remediation | Claude API (Anthropic) |
| Database | AWS DynamoDB |
| Compute | AWS Lambda |
| Scheduler | AWS EventBridge |
| Payments | Stripe |
| Secrets | AWS Secrets Manager |
| Landing page | Carrd.co ($19/year) |

### DynamoDB Tables
- `relayshield_users`
- `relayshield_monitored_emails`
- `relayshield_breach_alerts`
- `relayshield_sim_swap_alerts` ⬜ Phase 2 — create before deploying SIM swap monitor

### New fields required in relayshield_users (Phase 2)
- `sim_swap_monitoring` Boolean — True to enable monitoring for this user (default False)
- `phone_number` String — E.164 format (+1XXXXXXXXXX); falls back to whatsapp_number if absent
- `subscription_tier` String — personal_shield | business_basic | business_shield | business_shield_pro

### Monthly Running Costs

**Phase 1:**
| Service | Cost |
|---|---|
| HIBP API | $4.50 |
| Twilio WhatsApp (sandbox / early testing) | ~$10 |
| Claude API | ~$15 |
| AWS (Lambda + DynamoDB) | ~$2 |
| Secrets Manager | ~$2 |
| Carrd | $1.58 |
| **Total** | **~$35/month** |

**WhatsApp Business API — Production Upgrade (required before first paying subscriber)**

Currently running on Twilio's WhatsApp Sandbox (development only). Paying subscribers receive messages automatically — no sandbox join required — once migrated to the WhatsApp Business API.

| Component | Cost | Notes |
|---|---|---|
| Twilio per-message fee | $0.005/message | Flat — inbound or outbound |
| Meta utility conversation fee (US) | ~$0.008/24h window | Breach alerts = utility category |
| **Cost per breach alert** | **~$0.013** | One 24h conversation window per alert |
| WhatsApp Business number | $0/month | Shared Twilio number — no monthly fee |

**At scale:**
| Subscribers | Est. alerts/month | WhatsApp cost/month |
|---|---|---|
| 50 | ~75 alerts | ~$1 |
| 250 | ~375 alerts | ~$5 |
| 1,000 | ~1,500 alerts | ~$20 |

> WhatsApp cost is negligible relative to subscription revenue at all realistic subscriber counts. No pricing adjustment needed.

**Migration process:** Submit business details via Twilio → Twilio submits to Meta/WhatsApp → approval in 3–7 business days. Requires Facebook Business Manager account.

> ⚠️ **Kick off this process NOW** — before any founding member or paying subscriber goes live. Sandbox subscribers must manually send a join phrase to receive messages, which is not acceptable for a paid product. Approval takes up to 7 days so start immediately in parallel with remaining build items.

**Current Twilio credit:** $20 purchased for sandbox/trial number. Same balance carries over to production — at $0.013/alert this covers ~1,500 production alerts before a top-up is needed.

**Phase 2 (additional):**
| Service | Cost |
|---|---|
| GitGuardian API | ~$29 |
| Flare API | ~$75 |
| dnstwist | $0 |
| **Phase 2 addition** | **~$104/month** |
| **Phase 2 total** | **~$139/month** |

---

## 12. Backend Security Architecture

### Data Minimisation Principles
- Never store actual passwords
- Stripe handles all payment data (store Stripe customer ID only)
- Use anonymised UUIDs in third-party tools
- No CRM or Salesforce with PII access (Aura's breach vector)
- Encrypt sensitive fields at field level using AWS KMS

### AWS Security Controls
- DynamoDB: AWS KMS Customer Managed Keys
- IAM: Least privilege per Lambda function
- Lambda: Runs inside VPC, private subnet
- API Gateway: AWS WAF enabled
- CloudTrail: All API calls logged
- GuardDuty: Threat detection enabled
- Deletion Protection: ON for all DynamoDB tables
- Point-in-Time Recovery: ON for all DynamoDB tables
- $1 billing alert on all AWS accounts

### Twilio Account Security
- **2FA enabled** on Twilio account (mandatory — Twilio credentials = WhatsApp delivery access)
- **API keys scoped per Lambda** — separate API key for breach monitor vs whatsapp webhook vs sim swap monitor; no shared master credentials in code
- **Webhook signature validation** — all inbound Twilio webhooks verified using Twilio-Signature header before processing; reject any request that fails validation
- **Auth token rotation** — rotate Twilio auth token quarterly; update AWS Secrets Manager; no downtime required
- **Account activity alerts** — enable Twilio account alerts for unusual usage spikes (potential webhook abuse or credential compromise)
- **IP Access Control** — restrict Twilio Console access to known IPs where possible
- ⚠️ **TODO: Migrate from Twilio WhatsApp Sandbox to WhatsApp Business API** before first paying subscriber goes live. Kick off immediately — Meta/WhatsApp approval takes 3–7 business days. Requires Facebook Business Manager account. See Monthly Running Costs section for pricing detail.

### Third-Party Vendor Policy
| Vendor | Access Level |
|---|---|
| Stripe | Payment processing only |
| Twilio | Phone numbers, delivery metadata |
| Anthropic | Breach type/category (no user PII) |
| HIBP | Email addresses for breach lookup |
| GitGuardian | Domain/repo names only (Phase 2) |
| Flare | Domain names for monitoring (Phase 2) |

---

## 13. Landing Page Structure

**Headline:**
> *"Every security service tells you when you've been breached. RelayShield is the only one that fixes it."*

**Sub-headline:**
> *Changing your password after a breach is not enough. Attackers plant backdoors — forwarding rules, OAuth tokens, recovery addresses — that survive a password reset. RelayShield finds them first, guides you through every step in WhatsApp, and follows up until your account is actually secure. No app. No hold queue. No jargon.*

**Hero feature block — Email Security Sweep:**
> *🧹 Before you reset your password, did you check whether attackers already have a backdoor?*
> *RelayShield's Email Security Sweep audits the 5 things that survive a password reset — silent forwarding rules, unknown recovery options, malicious inbox filters, unauthorised app permissions, and active sessions on unknown devices. No other service does this.*

**Feature bullets:**
- 🧹 Email Security Sweep — closes backdoors before you change your password
- 🔴 Breach severity scoring — told exactly which breach to fix first
- 🔄 Remediation tracking — followed up on Day 3, 7, and 14 until you are actually protected
- 📱 Two-way WhatsApp AI — reply to get step-by-step guidance, 24/7, no hold queue
- 📡 Telecom-layer SIM swap detection (Phase 2)
- 🕵️ Real-time stealer log and dark web monitoring (Phase 2)
- 🔐 Secret and API key exposure detection (Phase 2)

**Trust signal:**
> *"Built by a 25-year telecom security professional. Aura and LifeLock tell you about the breach. RelayShield closes it."*

**Founding member urgency block:**
> *"🔒 Founding Member Pricing — First 25 customers only. Lock in your rate for 3 months — $12/month (Personal) or $79/month (Business). Standard price is $14.99/$99.99. Spots remaining: [X]"*

**Dual CTA:**
- "Secure My Account →"
- "Protect My Business →"

---

**How It Works — 3 Steps**

> **Step 1 — Sign up in 2 minutes**
> Enter the email addresses and phone numbers you want monitored. No software to install. No app to download.

> **Step 2 — We monitor 24/7**
> RelayShield watches breach databases and dark web sources around the clock. The moment something is detected, we act — not just alert.

> **Step 3 — Your WhatsApp guides you through the fix**
> You receive a message with a severity rating and a prompt to start your Email Security Sweep. Reply to begin. Every step is explained in plain language. We follow up until it is done.

---

**Pricing**

Three tiers, transparent pricing, no hidden fees:

| | Personal Shield | Business Shield | Business Shield Pro |
|---|---|---|---|
| **Standard price** | $14.99/month | $99.99/month | $199/month |
| **Founding rate** | $12/month | $79/month | $149/month |
| **Founding period** | 3 months | 3 months | 3 months |
| **Seats** | 1 person | Up to 10 employees | Up to 25 employees |
| **WhatsApp alerts** | ✅ | ✅ | ✅ |
| **AI remediation** | ✅ | ✅ | ✅ |
| **Domain monitoring** | ❌ | ✅ | ✅ |
| **Team dashboard** | ❌ | ✅ | ✅ |
| **SIM/eSIM swap detection** | ✅ Alert only | ✅ Alert + carrier hardening | ✅ Alert + hardening + SIM lock onboarding |
| **Priority support** | ❌ | ❌ | ✅ |

> *All plans include a 14-day free trial. Cancel anytime.*

---

**Frequently Asked Questions**

**Is my data safe?**
> RelayShield is built on AWS with encryption at rest and in transit. We never store your passwords. Payment processing is handled entirely by Stripe — we never see your card details. Our security architecture is published openly because we have nothing to hide.

**How is this different from just using HaveIBeenPwned for free?**
> HIBP tells you whether you were breached and stops there. RelayShield monitors daily, sends you a WhatsApp alert the moment a breach is detected, scores the severity, walks you through a 5-step inbox security sweep, tracks your remediation progress, and follows up until you are actually protected. HIBP is a lookup tool. RelayShield is a monitoring and response service.

**Do I need to install an app?**
> No. RelayShield delivers everything through WhatsApp, which you already have. There is nothing to download, install, or configure.

**What if I'm already using Aura or Incogni?**
> Aura focuses on credit monitoring and fraud insurance — it cannot detect SIM swap attacks, email backdoors, or exposed API keys. Incogni removes you from data broker lists but explicitly does not monitor the dark web. RelayShield fills the gaps they leave open. Many customers use both.

**What happens after the 3-month founding rate?**
> At the end of your 3-month founding period, your subscription moves to the standard price ($14.99/month Personal, $99.99/month Business). You will receive an email reminder 14 days before the change. Cancel any time before then with no charge.

**Do you offer refunds?**
> Yes — 14-day free trial on all plans, and we offer a full refund within 30 days of your first charge if RelayShield has not detected any value for you.

---

## 14. Validation Strategy

### Community Targets

**Consumer channels — Email Security Sweep angle:**
| Community | Message Angle |
|---|---|
| r/privacy | "Changing your password after a breach is not enough — here are the 5 backdoors to check first" |
| r/personalfinance | Email account takeover → financial loss ($1,500–$8,000 avg) — cost vs $14.99/month |
| r/scams | Value-first: "5 things to check in your email after any breach notification" |
| r/technology | Email Security Sweep technical walkthrough — credibility audience |
| Facebook: Online Privacy groups | Forwarding rule insight — accessible language, non-technical framing |
| Facebook: Identity Theft Support | Post-breach guidance — value-first, RelayShield as the follow-through tool |
| Twitter/X | Reply to breach announcement threads with the 5-step sweep as free value |

**SMB channels — SIM swap / Square angle:**
| Community | Message Angle |
|---|---|
| r/smallbusiness | Square/SIM swap attack chain — business bank account at risk |
| r/Entrepreneur | Business continuity framing — phone goes dark, sales go elsewhere |
| r/cybersecurity | Architecture credibility + exfiltration detection |
| r/devops | API key and secret exposure monitoring angle |
| Square Seller Community | SIM swap → Square takeover education post |
| Toast / Clover / Zettle communities | Same attack chain, same persona |
| Local business Facebook groups | Peer-to-peer trust — "this happened to someone I know" angle |
| LinkedIn | 25-year telecom expertise + mPOS security threat content |

---

### Consumer Outreach Play — Email Security Sweep (Highest Priority alongside SMB)

The consumer conversion moment is the forwarding rule insight. Most people have changed a password after a breach notification and assumed they were safe. The revelation that attackers plant backdoors that survive password resets is specific, credible, and immediately actionable.

**Post template for r/privacy, r/scams, r/personalfinance:**
> *"If you've ever received a breach notification from Google or Apple and changed your password — good. But here's what most people miss.*
>
> *Before you change your password, attackers often plant backdoors that survive the reset. The most common ones:*
>
> *1. Silent forwarding rule — all your emails are being copied to the attacker. You never notice because they still arrive normally.*
> *2. Unknown recovery phone number — attacker added their number so they can lock you out any time.*
> *3. Inbox filter deleting security alerts — your bank's fraud warnings and password reset confirmations go straight to trash.*
> *4. OAuth app access — attacker granted themselves persistent inbox access that survives your password change entirely.*
> *5. Active session on unknown device — attacker is still logged in.*
>
> *Here's how to check each one: [Gmail / Yahoo / Outlook steps]*
>
> *Check forwarding: Gmail → Settings → See all settings → Forwarding and POP/IMAP*
> *Check recovery options: myaccount.google.com/security*
> *Check filters: Settings → Filters and Blocked Addresses*
> *Check app permissions: myaccount.google.com/permissions*
> *Check active sessions: scroll to bottom of inbox → Details*
>
> *Do this BEFORE you reset your password. Changing the lock while the window is open does nothing.*"*

Value-first, no product mention. Comments and DMs asking "is there a tool that does this automatically?" are your first customers.

### Mobile-Dependent SMB Outreach Play (Equal Priority)

This is the highest-conversion outreach opportunity because the threat is concrete, immediate, and completely unaddressed by any existing tool at this price point.

**Post template for r/smallbusiness and Square Seller Community:**
> *"If you use Square (or any phone-based payment system), here's an attack that can empty your business bank account in under 30 minutes — and most small business owners have never heard of it.*
>
> *It's called a SIM swap. An attacker calls your mobile carrier, pretends to be you using information from a data breach, and transfers your phone number to their device. Your phone goes dark. You assume it's a network issue.*
>
> *Then they go to Square, click 'forgot password', and the verification SMS arrives on their phone. They reset your password, change your payout bank account, and your next day's card sales go to them. By the time you notice — usually on payout day — it's done.*
>
> *The fix isn't complicated: monitor your credentials, set a SIM lock with your carrier, and use an authenticator app instead of SMS for 2FA. Happy to share the full checklist if anyone wants it."*

Value-first, no product pitch. The DMs asking for the checklist are your first customers.

### Aura Breach Timing Play (Active Now — March 2026)
Post on r/personalfinance and r/privacy:
> *"Aura just had a 900,000-record breach. If you're reconsidering your identity protection, here's what RelayShield does differently — including the telecom threats and exfiltration signals Aura still can't detect."*

**Window:** Approximately 60-90 days from March 2026.

### Validation Metrics
| Signal | Meaning |
|---|---|
| 50+ email signups | Strong interest — proceed to MVP |
| 5+ pre-orders | Real validation — build immediately |
| High click, low signup | Messaging problem — tweak headline |
| DMs asking questions | These are your first customers |

---

## 14b. Security Hardening & Continuous Audit Program

*RelayShield sells protection. Our own security posture must be beyond reproach. This section tracks the hardening work required to operate a credible security company.*

### Tier 0 — Immediate (Before First Paying Customer) — Legal & Insurance

**LLC Formation**
- ✅ Form RelayShield LLC in Massachusetts via Massachusetts Secretary of State — approved April 2026
- ⬜ Obtain EIN from IRS (irs.gov/businesses/small-businesses-self-employed/apply-for-an-employer-identification-number-ein-online) — free, instant, required for business bank account
- ⬜ Open a dedicated business bank account — must be separate from personal finances for LLC liability shield to hold
- ✅ Draft a single-member Operating Agreement — signed and stored April 2026

**Terms of Service & Acceptance**
- ✅ Privacy Policy published (Google Docs, linked from landing page)
- ✅ Terms of Service published (Google Docs, linked from landing page — separate from Privacy Policy)
- ⬜ Add ToS acceptance text to Stripe Payment Link (custom text field) — binds users to ToS at point of payment
- ⬜ Confirm ToS liability cap language is in place: 3-month fee cap + $50 floor + consequential damages exclusion

**Cyber Insurance**
- ⬜ Get Tech E&O quote from Coalition (coalition.com) or Embroker (embroker.com) — target: policy active before customer #1 pays; estimated $600–$900/year
- ⬜ Sign policy before customer #2 — non-negotiable threshold

**Insurance Triggers (standing rules — review at each milestone):**
| Trigger | Action |
|---|---|
| First paying customer | Tech E&O policy must be active |
| $500/mo MRR (~33 customers) | Evaluate E&O + Cyber bundle ($1,200–$1,800/year) |
| Any B2B / SMB contract signed | Confirm policy covers business clients before signing |
| 500+ users | Add standalone Cyber Liability for breach notification cost coverage |
| Press coverage or any public mention | Review coverage limits — exposure increases claim risk |

### Tier 1 — Immediate (Before First Paying Customer)

**Secrets & Credential Hygiene**
- ⬜ Audit all AWS Secrets Manager entries — confirm no plaintext secrets exist outside Secrets Manager (no .env files, no hardcoded values in Lambda code, no secrets in CloudWatch logs)
- ⬜ Enable AWS CloudTrail — log all API calls across the RelayShield AWS account for audit trail
- ⬜ Enable AWS Config — track configuration changes to Lambda, DynamoDB, IAM policies
- ⬜ Review IAM policy: relayshield-breach-check-policy — confirm least-privilege (no wildcard * permissions)
- ⬜ Enable DynamoDB encryption at rest — confirm KMS key is applied to all three tables
- ⬜ Rotate all API keys (HIBP, Anthropic, Twilio) — establish 90-day rotation schedule

**Lambda Hardening**
- ⬜ Confirm Lambda function URL is not publicly exposed — function should only trigger via EventBridge
- ⬜ Add input validation to lambda_handler — reject malformed event payloads
- ⬜ Confirm Lambda execution role has no unused permissions
- ⬜ Set Lambda reserved concurrency to prevent runaway invocations

**Dependency & Code Scanning**
- ⬜ Run Bandit (Python SAST tool — free) against relayshield_breach_monitor.py — fix any flagged issues
- ⬜ Set up GitGuardian free tier — connect to any code repository, scan for accidentally committed secrets
- ⬜ Confirm no secrets appear in CloudWatch log output — review existing log groups

### Tier 2 — Within First Month of Paid Subscribers

**Penetration Testing**
- ⬜ Conduct self-directed pen test against the Lambda/DynamoDB surface — test for: unauthorized DynamoDB access, Lambda event injection, Secrets Manager enumeration, IAM privilege escalation
- ⬜ Document findings and remediation in a security log
- ⬜ Schedule external pen test (budget: ~$500-$1,500 via Cobalt.io or HackerOne) before reaching 100 paying customers

**Automated Continuous Scanning**
- ⬜ Set up **GitHub Actions** (or AWS CodePipeline) with automated security checks on every code deploy:
  - Bandit SAST scan
  - Safety (Python dependency vulnerability check)
  - GitGuardian secret scan
  - Deploy blocked if any check fails
- ⬜ Set up **AWS GuardDuty** — managed threat detection for the AWS account (~$1-3/month at this scale). Alerts on suspicious API calls, unauthorized access attempts, compromised credentials
- ⬜ Set up **AWS Security Hub** — aggregates GuardDuty + Config findings into a single security dashboard

**Data Protection**
- ⬜ Confirm PII minimization — relayshield_users and relayshield_breach_alerts tables store only what is necessary
- ⬜ Implement DynamoDB TTL on relayshield_breach_alerts — auto-delete records older than 2 years
- ⬜ Confirm Stripe handles all payment data — verify no card data touches RelayShield infrastructure

### Tier 3 — Phase 2 (Scale)

**Advanced Monitoring**
- ⬜ Upgrade GitGuardian to paid tier ($29/month) — real-time secret detection across all integrations
- ⬜ Integrate Flare API — dark web monitoring for RelayShield's own credentials and infrastructure
- ⬜ Set up AWS WAF if/when a public API or web endpoint is exposed
- ⬜ Establish formal vulnerability disclosure policy and publish on relayshield.net/security

**Compliance**
- ⬜ Document data retention and deletion policy for GDPR/CCPA compliance
- ⬜ Create incident response runbook — what happens if RelayShield itself is breached
- ⬜ Consider SOC 2 Type I audit if pursuing enterprise/insurance channel partnerships

---

## 15. 6-Week MVP Build Plan

### 🚨 Launch Showstoppers — Must Complete Before First Paying Customer

| # | Item | Status |
|---|---|---|
| 1 | **LLC formation** — File RelayShield LLC with Massachusetts Secretary of State ($500 — go to www.sec.state.ma.us → Corporations Division → File Online → Domestic LLC → Certificate of Organization). Personal assets are unprotected until this is done. | ✅ Approved — April 2026 |
| 2 | **Tech E&O insurance** — Obtain policy from Coalition or Embroker before customer #1 pays (~$600–$900/year). Security product E&O exposure begins at first paid subscriber. | ⬜ Blocking |
| 3 | **EIN** — Obtain from IRS (free, instant at irs.gov). Required for business bank account and tax reporting. | ✅ Complete |
| 4 | **Business bank account** — Open dedicated account (Mercury recommended). LLC liability shield is weakened if business and personal funds are commingled. | ⏳ Mercury application pending |

---

| Week | Milestone | Hours | Status |
|---|---|---|---|
| 1 | Breach detection engine (HIBP + Lambda + DynamoDB) | 5 | ✅ Complete |
| 2 | WhatsApp alert delivery (Twilio integration) | 5 | ✅ Complete |
| 3 | Claude AI conversational remediation + Email Security Sweep | 5 | ✅ Complete |
| 4 | Stripe payments + Carrd landing page | 5 | ⬜ Next |
| 5 | SMB tier + end-to-end testing | 5 | ⬜ Pending |
| 6 | First paying customer acquisition | 5 | ⬜ Pending |

**Total: 30 hours across 6 weeks to first revenue**
**Progress: 3 of 6 weeks complete — core product is live and working**

### Week 5 — SMB Tier + SIM Swap + Password Protection + Carrd Expansion

**Priority 1 — SIM/eSIM Swap Monitoring (top priority — validated by salon owner prospect)**

*Detection (ALL tiers including Personal Shield):*
- ⬜ Build `monitor_sim_swap(phone_number)` Lambda function — detect SIM swap and eSIM provisioning events via Twilio Verify SIM Swap API (covers both physical SIM and eSIM changes via IMSI change detection)
- ⬜ Personal Shield alert (detection only): "⚠️ SIM or eSIM change detected on your number. Your phone may be compromised. Call your carrier NOW and check your eSIM profiles in your carrier app."
- ⬜ Detect whether change is likely physical SIM vs eSIM: cross-reference device type flags in Twilio Lookup response; if eSIM-capable device → flag as potential eSIM provisioning event
- ⬜ Store phone numbers in relayshield_users DynamoDB table for all tiers including Personal Shield
- ⬜ Add SIM/eSIM swap monitoring toggle to onboarding flow for all tiers
- ⬜ Schedule `monitor_sim_swap` as a separate EventBridge rule — hourly checks (more frequent than daily breach check given time-sensitivity of SIM swap attacks)

*Carrier Hardening Steps (Business Basic, Business Shield, Business Shield Pro only):*
- ⬜ On SIM swap detection → append carrier-specific hardening steps per carrier:
  - AT&T: Enable Wireless Account Lock in myAT&T app; check for unauthorized eSIM profiles under Account → Device
  - T-Mobile: Enable SIM Protection (requires in-store photo ID to remove); audit eSIM profiles in T-Mobile app → Account → Lines
  - Verizon: Enable Number Lock in My Verizon app; check eSIM provisioning under Device → eSIM Management
- ⬜ On eSIM-flagged event → append eSIM-specific audit step: "Check your carrier app for eSIM profiles you did not add. Revoke any unrecognised profiles immediately."
- ⬜ On eSIM-flagged event → include FCC complaint guidance: "File a complaint at fcc.gov/consumers/guides/filing-informal-complaint — carriers are required to respond within 30 days."
- ⬜ Include port-out fraud detection — if number has transferred to a different carrier, flag as CRITICAL

*SIM Lock Onboarding Flow (Business Shield Pro only):*
- ⬜ During onboarding, walk Pro users through enabling carrier SIM lock via WhatsApp conversation before any breach is detected
- ⬜ Carrier-specific SIM lock steps delivered conversationally (AT&T Wireless Account Lock / T-Mobile SIM Protection / Verizon Number Lock)
- ⬜ Add option to disable eSIM provisioning entirely where carrier supports it (strongest protection)
- ⬜ Authenticator app migration flow — when SMS 2FA detected on a breached account, guide user to migrate to authenticator app per platform

**Priority 2 — Password Exposure Response (response layer only — no detection)**

*Strategic decision: RelayShield does NOT implement Pwned Passwords hash checking or any password detection capability. Detection is commoditised — HIBP, Google, Apple, and Firefox already do it for free. Asking users to submit passwords (even hashed) via any channel puts us in competition with Aura, Norton, and HIBP on their ground. Our value is the response layer: what happens after a password is confirmed exposed in a breach.*

- ⬜ **Password exposure detection from breach DataClasses** — when HIBP returns "Passwords" in DataClasses for a breach, treat the password as compromised and trigger response flow immediately. No user password submission required.
- ⬜ **Severity bump** — any breach exposing passwords is bumped one severity level (MEDIUM→HIGH, HIGH→CRITICAL). If `password_manager_user = True`, bump to HIGH minimum regardless of breach type.
- ⬜ **Cross-account reuse walkthrough (REUSE command)** — when passwords exposed, Claude walks user through high-risk accounts one at a time via WhatsApp: Gmail/Outlook, banking, Amazon/PayPal, Apple ID/Google Account, Facebook/LinkedIn, Square/payment tools. User replies YES/NO per account. Specific reset URL provided for each YES. Ends with password manager recommendation.
- ⬜ **Password Manager Breach Alert** — add opt-in flag `password_manager_user` (boolean) to `relayshield_users` DynamoDB table — default False. During onboarding WhatsApp flow, ask: "Do you use a password manager? Reply YES or NO." When breach fires and `password_manager_user = True` and passwords exposed, append: "🔐 *Password Manager Alert:* Your master password may have been tested against your password manager login. Change it immediately. Enable biometric unlock. Store recovery code offline — not in email."
- ⬜ **MANAGER command** — at end of cross-account walkthrough, user can reply MANAGER for a free Bitwarden setup guide delivered via WhatsApp (5-minute setup, recommended for all users without a password manager)

**Priority 3 — SMB Tier**
- ⬜ Domain scanner for SMB onboarding — check all email addresses on a domain
- ⬜ SMB tier end-to-end testing — multi-seat breach detection and alert routing

**Carrd Landing Page Expansion (SMB Tier)**
When Business Shield launches, expand the existing Carrd single page:
- ⬜ Add **Pricing section** — two-column table: Personal Shield vs Business Shield side by side
- ⬜ Add **"For Teams"** section — highlight team dashboard, per-employee breach response, admin visibility
- ⬜ Add Business Shield Pro payment link button to pricing section

### Phase 2 — Dedicated SMB Page
When SMB revenue justifies a separate buyer journey:
- ⬜ Create `/business` sub-page in Carrd (Pro Standard supports multiple pages on one site)
- ⬜ Separate SMB pitch: team dashboard demo, per-seat pricing, IT admin features
- ⬜ Link from main relayshield.net homepage to `/business` page

### On First Paying Customer — Admin Tasks
- ⬜ Set up virtual mailbox — recommended provider: Anytime Mailbox or iPostal1 (~$10/month). Use for Stripe customer support address and business mailing address. Complete before or on first customer acquisition.
- ✅ Obtain EIN (Employer Identification Number) from IRS — complete
- ✅ Google Voice set up — number +13392987368, inbox at voice.google.com, linked to relayshieldadmin@gmail.com. Added as recovery phone in Google Security. Updated as Stripe customer support number. Personal mobile removed from relayshieldadmin@gmail.com account.
- ⬜ Set up custom billing domain — replace billing.stripe.com with billing.relayshield.net. Requires DNS configuration in Namecheap. Complete within first month of paid subscribers.
- ⬜ Create brand assets — minimum required: logo/wordmark, primary brand color (suggested: navy #0F2D52 + electric blue #0066FF), favicon 32x32px. Use Canva (free). Apply to Stripe branding settings and Carrd landing page. Complete before or on first customer acquisition.

---

## 16. Account and Infrastructure Setup

### Accounts Created
- ✅ relayshieldadmin@gmail.com — secured with MFA + authenticator
- ✅ HIBP API key — purchased ($4.50/month, Pwned 1)
- ✅ HIBP API key stored in AWS Secrets Manager (relayshield/hibp_api_key)
- ⬜ relayshield.ai — register on Namecheap
- ✅ relayshield.net — purchased (1-year, March 2026)
- ✅ Anthropic account — API key created, $4.85 credit, billing active
- ⬜ Stripe account (Week 4)
- ⬜ Carrd account (Week 4)
- ⬜ GitGuardian account (Phase 2)
- ⬜ Flare account (Phase 2)

### AWS Resources (SmartAsst account, tagged Project: RelayShield)
- ✅ relayshield_users (DynamoDB)
- ✅ relayshield_monitored_emails (DynamoDB)
- ✅ relayshield_breach_alerts (DynamoDB)
- ⬜ relayshield_sim_swap_alerts (DynamoDB) — create before SIM swap deploy
- ✅ relayshield-breach-check (Lambda, Python 3.14)
- ⬜ relayshield-sim-swap-monitor (Lambda, Python 3.14) — new, deploy from relayshield_sim_swap_monitor.py
- ✅ relayshield/hibp_api_key (Secrets Manager)
- ✅ IAM policy: relayshield-breach-check-policy
- ⬜ IAM policy: relayshield-sim-swap-monitor-policy — needs DynamoDB read/write on users + sim_swap_alerts tables; Secrets Manager read on Twilio secrets
- ✅ Lambda timeout: 3 minutes
- ✅ EventBridge scheduler: relayshield-daily-breach-check
- ⬜ EventBridge scheduler: relayshield-hourly-sim-swap-check — rate(1 hour)
- ✅ Test records added — 20 breaches detected across 2 emails
- ✅ Weeks 1–3 complete — core product live and working

### Week 1 — Breach Detection Engine ✅
- ✅ relayshield_users, relayshield_monitored_emails, relayshield_breach_alerts (DynamoDB)
- ✅ relayshield-breach-check Lambda (Python 3.14, 3-min timeout)
- ✅ relayshield/hibp_api_key (Secrets Manager)
- ✅ relayshield-daily-breach-check (EventBridge scheduler, 1-day rate)
- ✅ 20 breaches detected across 3 test emails

### Week 2 — WhatsApp Alert Delivery ✅
- ✅ relayshield/twilio_account_sid, twilio_auth_token, twilio_whatsapp_number (Secrets Manager)
- ✅ RelayShieldSecretsPolicy on Lambda role (relayshield-breach-check-role-1sapnwdl)
- ✅ Lambda updated — Twilio REST API via urllib.request (no SDK, no Layer)
- ✅ Breach severity scoring live — Critical/High/Medium/Low in every WhatsApp alert
- ✅ End-to-end confirmed: breach detected → WhatsApp message received
- ✅ breach_date: falls back to AddedDate when BreachDate null
- ✅ relayshield.net purchased (1-year, March 2026)

### Week 3 — AI Remediation + Email Security Sweep ✅
- ✅ Claude API conversational remediation live in WhatsApp
- ✅ Email Security Sweep — 5-step inbox backdoor audit delivered via WhatsApp
- ✅ Remediation status tracking — Day 1/3/7/14 follow-up flows in DynamoDB
- ✅ Cross-account password risk detection
- ✅ SSN, passport, driver's licence breach field detection via HIBP DataClasses
- ✅ relayshield/anthropic_api_key (Secrets Manager)

---

## 17. Secrets Manager Keys

| Secret Name | Status |
|---|---|
| relayshield/hibp_api_key | ✅ Created |
| relayshield/twilio_account_sid | ✅ Created |
| relayshield/twilio_auth_token | ✅ Created |
| relayshield/twilio_whatsapp_number | ✅ Created |
| relayshield/anthropic_api_key | ✅ Created |
| relayshield/stripe_secret_key | ⬜ Week 4 |
| relayshield/gitguardian_api_key | ⬜ Phase 2 |
| relayshield/flare_api_key | ⬜ Phase 2 |
