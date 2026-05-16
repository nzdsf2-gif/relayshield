# The Security Layer EDR and MDR Can't See

Your endpoint detection tool is excellent at what it does. It watches processes, memory, file system activity, and network connections on the devices it covers. Your MDR provider watches logs, correlates alerts, and hunts threats across your environment.

Neither of them watches your phone carrier.

That gap — between your telecom layer and your sensitive accounts — is where some of the most damaging attacks in the current threat landscape operate. Understanding why that gap exists, and what lives in it, is the first step to closing it.

---

## What EDR and MDR Were Built to Protect

EDR (Endpoint Detection and Response) tools instrument your devices. They see processes spawning child processes, binaries executing from unusual paths, lateral movement across the network, ransomware encrypting files. When an attacker lands on an endpoint and starts moving, EDR is designed to catch it.

MDR (Managed Detection and Response) extends this with human analysts — correlating alerts, triaging incidents, and hunting for threats that automated tools miss. The best MDR providers bring threat intelligence, playbooks, and 24/7 coverage to organisations that can't staff a full SOC.

Both operate on a shared assumption: the threat is somewhere in your environment, touching a device or a network that you control and can instrument.

That assumption breaks down for an entire class of attacks.

---

## The Attacks That Live Outside Your Environment

### SIM Swap

A SIM swap attack doesn't touch your devices. The attacker calls your mobile carrier, social-engineers or bribes a representative, and convinces them to transfer your phone number to a SIM card the attacker controls. From that moment, every SMS sent to your number — including 2FA codes, bank OTPs, password reset links — goes to the attacker.

Your endpoint is clean. Your network is clean. EDR sees nothing. MDR has nothing to correlate. Your email account, your bank account, your crypto wallet, your Okta account are all now accessible to someone who never touched a single device in your environment.

SIM swap has been used to compromise executives at publicly traded companies, drain crypto wallets of six and seven figure sums, and bypass 2FA on enterprise SaaS platforms. It is not a theoretical threat.

### SS7 Exploitation

SS7 is the signalling protocol that connects telephone networks globally. Vulnerabilities in SS7 allow nation-state actors and well-resourced criminal groups to intercept SMS messages in transit — including 2FA codes — without ever performing a SIM swap. The victim's phone continues working normally. There is no carrier interaction to detect. The interception is invisible.

EDR cannot see SS7 traffic. It operates below the level of any device you own.

### Credential Exposure from Third-Party Breaches

When a third-party service your employees or customers use suffers a breach, their credentials end up in criminal forums. The attack that follows — credential stuffing, targeted phishing, account takeover — often happens weeks or months after the breach, long after the initial exposure.

Your EDR didn't see the breach. It happened somewhere else. Your MDR may eventually see the login attempt, but by then the attacker already has a valid session.

The monitoring gap is between the breach event and the attack that follows it. That window — sometimes 90 days, sometimes longer — is where identity protection operates.

---

## What the Telecom Layer Covers

RelayShield operates at the intersection of telecom intelligence and identity protection. It monitors signals that EDR and MDR have no visibility into:

**SIM/eSIM swap detection** — live carrier network queries via Twilio Lookup v2 detect when a phone number has been ported or reassigned. Alerts fire within minutes of the swap, before an attacker has time to use the compromised number to access accounts. Users receive step-by-step guidance: freeze the number, contact the carrier, rotate credentials on every SMS-2FA-protected account immediately.

**Email breach monitoring** — continuous monitoring against 13 billion+ compromised records from known breaches. When a monitored email appears in a new breach, the alert includes the specific data classes exposed, severity context, and remediation guidance tailored to what was leaked.

**Domain lookalike detection** — typosquat and homoglyph domains registered against your business domain are detected via DNS, certificate transparency logs, and threat intelligence feeds. The first sign of a phishing campaign targeting your customers is often a domain registration, not a phishing email — lookalike monitoring catches it before the campaign launches.

**OAuth supply chain watchlist** — monitors for signs that high-risk OAuth-capable SaaS apps in your environment have been compromised, triggering a prompt to audit active OAuth grants before an attacker pivots through them.

---

## How the Layers Fit Together

Think of it as three concentric rings of protection:

| Layer | What it covers | Tools |
|---|---|---|
| **Endpoint** | Device, process, file system, memory | EDR |
| **Network/SOC** | Traffic, logs, alerts, threat hunting | MDR / SIEM |
| **Telecom/Identity** | Carrier layer, breach exposure, domain threats | RelayShield |

These layers are complementary, not competitive. An MDR provider watching your Okta logs will see the login attempt after a SIM swap. RelayShield fires the alert at the moment of the swap — before the attacker uses the compromised number to authenticate. The two signals together give your SOC a complete picture.

For organisations running an MDR program, RelayShield's API (available on RapidAPI or via x402 USDC micropayments) can feed SIM swap and breach signals directly into your SIEM or SOAR platform, enabling automated playbook triggers: freeze the account, notify the user, require step-up authentication.

---

## The Employee Protection Use Case

The most immediate enterprise use case is executive and high-privilege employee protection. CFOs, IT administrators, M&A teams, and anyone with access to financial systems or sensitive data are high-value SIM swap targets.

A single successful SIM swap against your CFO, combined with a targeted phishing email arriving while their 2FA is compromised, can result in a wire transfer authorisation that no EDR tool will ever flag.

Monitoring the phone numbers and email addresses of your highest-risk employees for SIM swap activity and breach exposure is a low-cost, high-value control that sits entirely outside the coverage of your existing security stack.

---

## Where to Start

RelayShield offers three access models:

- **Consumer / individual** — WhatsApp or Telegram alerts, subscription tiers from free to Business Shield Pro
- **Developer API** — RapidAPI subscription, REST endpoints for breach, SIM swap, domain lookalike, OAuth watchlist, URL/file scanning, and wallet risk
- **Pay-as-you-go** — x402 USDC micropayments on Base, no subscription required, per-call pricing for agent and automation use cases

The bot is [@RelayShield_bot](https://t.me/RelayShield_bot). The API is at [relayshield.net](https://relayshield.net).

If you're running an MDR program and want to discuss feeding telecom-layer signals into your existing SIEM or SOAR, reach out directly.

---

*RelayShield is a security intelligence platform monitoring the telecom and identity layer — the gap between your carrier and your accounts that EDR and MDR cannot see.*
