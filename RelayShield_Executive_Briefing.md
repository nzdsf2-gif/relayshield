# RelayShield — Executive Briefing Talking Points

---

## Mission Statement

> **RelayShield detects identity attacks the moment they start and delivers plain-English guidance to stop them — before the damage is done.**

---

## Are SIM Swaps Really That Urgent?

Most people think of cybersecurity as antivirus and firewalls — software protecting a device. SIM swap is different. It attacks your *identity*, not your device, and it bypasses every piece of software security you have.

| Malware / Virus | SIM Swap |
|---|---|
| Attacks your device | Attacks your phone number — the master key to every account |
| Requires you to click something | Happens at the carrier — you do nothing wrong |
| Antivirus can catch it | No software on earth detects it — your carrier just reroutes your number |
| Takes time to spread | Account takeover completes in under 10 minutes |
| Affects one device | Unlocks your bank, email, crypto, business accounts simultaneously |

> "A virus gets into your computer. A SIM swap gets into your life."

The attacker calls your carrier, impersonates you, and within minutes your phone goes dead and every two-factor authentication code — for your bank, your email, your business systems — goes to them. By the time you realise what happened, your accounts are drained and your passwords are changed.

---

## What Does RelayShield Actually Protect Against?

Six attack types, all live today:

1. **SIM Swap & Port-Out Fraud** — We detect the moment your number is hijacked at the carrier level and fire an alert before the attacker reaches your accounts
2. **Data Breach Exposure** — Your email and credentials appear in a breach. We tell you within hours: what was exposed, how serious it is, what to change first
3. **Phishing & Lookalike Domains** — Someone registers `yourcompany-support.com` to scam your customers. You hear about it the same day
4. **OTP Interception / Smishing** — Fake "your bank needs verification" texts designed to steal one-time codes. We detect the pattern and warn you
5. **OAuth Token Theft** — Third-party apps connected to your Google, Microsoft, or Slack accounts get breached. We flag which tokens are now compromised and tell you exactly which app to revoke
6. **Coordinated Multi-Vector Attacks** — A breach today followed by a SIM swap attempt 48 hours later isn't coincidence — it's a planned attack chain. We connect those dots and warn before the second move lands

---

## Where You're Exposed and Don't Know It

Most executives are surprised by these:

- **Your phone number IS your password.** Every "forgot my password" flow, every bank login, every 2FA code goes to your number. One carrier call from an attacker and they own everything
- **Breached passwords you're still using.** 13 billion credentials are in circulation right now. Yours are probably in there. Most people never find out until the account is already taken
- **Fake versions of your company website.** Attackers register near-identical domains to target your customers or staff. You'd never know unless someone is watching
- **Apps still connected to your accounts.** Every "Sign in with Google" you've ever clicked left a token. Old apps get breached. That token still works. We watch the breach databases for them
- **Employee offboarding gaps.** A departing employee who still has OAuth access to company tools is a live attack surface. Most businesses have dozens of these open right now

---

## How Is RelayShield Different?

| The Competition | RelayShield |
|---|---|
| Alerts you *after* an account is taken over | Alerts you *while* the attack is forming — before it completes |
| Requires an app download or portal login | Lives in WhatsApp or Telegram — where your people already are |
| Reports incidents | Tells you exactly what to do in the next 10 minutes, in plain English |
| Monitors one threat type | Correlates breach + SIM swap + phishing as a single coordinated attack |
| Watches your device | Watches your identity — the layer carriers and apps don't protect |
| Built by software engineers | Built on 25 years of carrier-layer expertise — we understand the telco attack surface from the inside |

---

## What Does the Experience Actually Look Like?

No app. No dashboard. No training required.

A customer signs up in under 2 minutes via WhatsApp or Telegram. From that point:

- **Normal days:** Silence. No noise.
- **When something is detected:** A plain-English message arrives. Example:

> *"⚠️ SIM Swap Alert — Your number showed a carrier change event 4 minutes ago. If you didn't request this, call AT&T Fraud at 877-844-5584 immediately and say 'I need to report a SIM swap.' Lock your SIM PIN at att.com/simprotection. Your bank accounts and email passwords should be changed now."*

- **The customer acts within minutes**, not days. Most competitive products send a weekly digest email that gets ignored.

---

## Audience-Specific One-Liners

**Telcos:**
> "You currently get the complaint call after the hijack. We get you the prevention call before it. That's the difference between a fraud claim and a loyalty moment."

**Enterprise IT Teams:**
> "You can patch every server in your environment. You cannot patch an employee's phone number. We cover the gap you can't."

**SMB Business Owners:**
> "Your bank account, your email, your point-of-sale system — all one phone call to your carrier away from being stolen. We're the alarm that fires the moment that call happens."

**MSPs / MSSPs:**
> "Identity monitoring is the line item your clients expect on every proposal and the one most stacks don't have. We're API-first, multi-tenant, and structured for resale. You can be live this week."

---

## Universal Objection Handlers

**"We already have antivirus / EDR / a SIEM."**
> "Those protect your devices and network. We protect your identity — the layer that bypasses all of those controls when it's compromised."

**"Is this just a breach monitoring service?"**
> "Breach monitoring tells you what already happened. We correlate what's happening *now* — breach exposure followed by a SIM swap attempt is an active attack in progress. We flag it mid-chain."

**"Our employees are trained on phishing."**
> "Training helps. It doesn't stop your carrier from being socially engineered by an attacker who already bought your employee's credentials from a breach database."

**"We're too small to be a target."**
> "The attacks are automated. You're not targeted because of who you are — you're targeted because your credentials are in a database. Every business with a phone number qualifies."

**"What does it cost?"**
> "Personal protection starts at $14.99/month. Business from $19.99. Less than one fraudulent transaction, one hour of IT recovery time, or one wire transfer reversal attempt."
