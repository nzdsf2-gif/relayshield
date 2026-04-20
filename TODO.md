# RelayShield — Open Items

*Last updated: April 2026*
*Legend: 🚨 Blocking · ⚡ High Priority · 🔄 In Progress · ⬜ Pending · 🔮 Future*

---

## 🚨 Launch Blockers — Must Complete Before First Paying Customer

| # | Item | Status |
|---|---|---|
| 1 | **Tech E&O insurance** — Embroker application submitted April 2026. $1M limit, $1M 1st party, $10K retention, Standard coverage. Quote expected via email in 1–2 days. Sign policy before first paying customer. | 🔄 Quote pending |
| 2 | **Facebook Business verification** — Submitted as sole proprietor. Monitoring for Meta approval. | 🔄 Submitted — awaiting Meta |

---

## 🔄 Beta Testing — Active

| # | Item | Status |
|---|---|---|
| 1 | **Salon owner (Rebecca) onboarded** — Active. HELP confirmed. | ✅ Active |
| 2 | **Tester 2 onboarded** — Cybersecurity background (Equifax). Active. HELP confirmed. Email Security Sweep completed ✅ | ✅ Active |
| 3 | **Additional beta testers** — 1 confirmed ready to onboard, potentially more in the works. Target: 4–5 total. | 🔄 In progress |
| 4 | **Beta feedback form** — Built and published. Link: https://docs.google.com/forms/d/e/1FAIpQLSeZ8G7Bj_gfrTybnFk8R8AQyxRXGi6kQo_7V7CnqASF1Kg6rw/viewform?usp=publish-editor — Send via WhatsApp to all testers at end of beta. | 🔄 Ready to send |
| 5 | **Collect beta feedback** — Send form link via WhatsApp to all testers. Target signal: value perception at price point, sweep completion rate, differentiation validation from tester 2 (Equifax background). | ⬜ Pending |
| 6 | **Referral program** — Post-launch Phase 2 item. Validate organic advocacy first (Q9 of feedback form). If strong, build referral incentive mechanic (e.g. one free month per converted referral). | 🔮 Phase 2 |

---

## ⚡ High Priority — Pre-Revenue

| # | Item | Status |
|---|---|---|
| 1 | **Update landing page markdown in Git** — Sync relayshield_landing_page.md with all Carrd changes made today (pricing table, Business Starter button, benefit tagline, ToS links) | ✅ Complete |
| 2 | **Stripe annual plans TODO** — Confirm all tiers have annual payment links active (Personal Shield, Business Basic, Business Shield, Business Shield Pro, Business Starter) | ✅ Complete |
| 3 | **Stripe legal entity** — Update to RelayShield LLC in business details | ✅ Complete |
| 4 | **Relay Financial bank account** — Connected to Stripe as default payout. Verified April 2026 — Thread Bank (Relay) ••••6633 confirmed as USD default payout account. | ✅ Complete |
| 5 | **Annual Stripe TODO note** — Remove the ⬜ TODO note in strategy doc re: annual plans | ✅ Complete |

---

## 🚀 Production Onboarding Flow

| # | Item | Status |
|---|---|---|
| 1 | **End-to-end Stripe → welcome message test** — Verified April 2026. Signature verification, DynamoDB record creation, tier detection, and Twilio API call all confirmed working. WhatsApp delivery to new users requires approved template (Twilio 24hr window rule). Welcome message template submitted to Meta for approval. | ✅ Complete |
| 2 | **Carrd copy — WhatsApp contact instruction** — Add explicit instruction on landing page: "Before completing payment, save the RelayShield WhatsApp number as a contact on your phone" — required for message delivery | ✅ Complete |
| 3 | **Phone number mismatch mitigation** — Added "WhatsApp phone number" custom field (Text, Optional) to all 8 payment links in Stripe. Reduces risk of Stripe number differing from WhatsApp number. | ✅ Complete |

---

## 📦 Product — Phase 1 Remaining

| # | Item | Status |
|---|---|---|
| 1 | **Auto-send Claude analysis on first reply** — When ACTIVE user messages after breach and no freeform was sent (63016), webhook auto-sends full Claude analysis before handling their command | ⬜ Pending |
| 2 | **Fix empty breach_date field in DynamoDB** | ✅ Complete — code already handles via BreachDate→AddedDate fallback. Empty values are legacy beta test records only. |
| 3 | **Password breach checking** — Pwned Passwords API integration | ⬜ Pending |
| 4 | **Cross-account password risk detection** | ⬜ Pending |
| 5 | **Business Starter webhook code update** — Add TIER_STARTER constant, EMAIL_LIMITS entry (3 emails), phone hardening parity with business tiers | ⬜ Pending (post-beta) |
| 5a | **Business Starter — 1 contractor seat** — Add TIER_STARTER to BUSINESS_TIERS, set SEAT_LIMIT of 1. Enables ADD command for one employee/contractor. Upsell path to Business Basic (5 seats). | ⬜ Pending (post-beta) |
| 5b | **Business Starter+ — Quarterly proactive sweep reminder** — EventBridge scheduled rule per Business Starter, Basic, Shield, Pro subscriber. WhatsApp message every 90 days: "Time for your quarterly security sweep — no breach needed. Reply SWEEP to start." Differentiates all business tiers from Personal Shield reactive-only model. | ⬜ Pending (post-beta) |
| 5c | **Business Starter+ — Monthly WhatsApp Security Digest** — EventBridge monthly trigger for all business tiers. Lambda queries DynamoDB for breach history, open remediation items. Sends formatted summary: breach count, all-clear confirmation, one rotating business-specific security tip. Send one digest to beta testers before conversion ask. | ⬜ Pending (post-beta) |
| 5d | **Welcome message — all tiers** — WhatsApp template `relayshield_welcome` approved by Meta April 2026. Stripe webhook updated to send via Twilio Content API (HX45e6bac7d790f79414f7b067e1a3edd9). Manual DynamoDB onboarding (beta) uses ad-hoc WhatsApp contact — no automated send needed for beta path. | ✅ Complete — production path done |
| 6 | **Consumer vishing alert** — Append vishing warning to WhatsApp alert when breach exposes phone/address/carrier/account numbers | ✅ Complete — in Claude system prompt |
| 9a | **Disappearing WhatsApp message awareness** — Added to onboarding completion message. Three rules: RelayShield never asks for OTP/PIN, screenshot urgent messages, urgency is the attack. Introduces WASCAM and OTP commands. | ✅ Complete |
| 9b | **OTP command — WhatsApp-specific guidance** — Extended OTP response to cover WhatsApp OTP takeover consequences: full account takeover, contact list exploitation, chain attacks. Two-Step Verification prompt added. | ✅ Complete |
| 9c | **WASCAM command** — New command for suspicious WhatsApp messages. Leads with bank/financial fraud, carrier impersonation, then Hi Mum/Dad family scam, disappearing message tactics, verification steps. Added to HELP menu. | ✅ Complete |
| 7 | **Personal verification protocol** — Onboarding WhatsApp flow: callback rule, OTP rule, family safe word, wire transfer rule | ⬜ Pending |
| 8 | **SSN/passport/DL vishing escalation** — CRITICAL severity when these data classes detected | ✅ Complete — in Claude system prompt |
| 9 | **Smishing — phone number breach escalation** — Detect "Phone numbers" in HIBP DataClasses → append smishing warning to existing breach alert. ~1–2 hrs. All tiers. | ✅ Complete |
| 10 | **Smishing — carrier PIN hardening messaging** — `msg_phone_hardening()` updated with smishing context. Carriers never text/call asking for PIN framing added. All tiers. | ✅ Complete |
| 11 | **Smishing — OTP warning flow** — `OTP` command added. `msg_unexpected_otp()` function built. HELP menu updated. Account lockdown + SIM swap precursor guidance. All tiers. | ✅ Complete |
| 12 | **Smishing — suspicious SMS analysis (Phase 1 stub)** — `SMS <text>` command added. Returns immediate guidance + carrier reporting steps (7726). TODO stub in code for Google Safe Browsing URL analysis. Full URL analysis is next build item. | 🔄 Stub live — URL analysis pending |
| 13 | **Smishing — URL analysis (Google Safe Browsing)** — Complete the SMS command: extract URLs from forwarded text, check via Google Safe Browsing API, return safe/suspicious/malicious verdict + remediation. ~3–4 hrs. | ✅ Complete |

---

## 📱 SIM Swap Monitor — Phase 1

| # | Item | Status |
|---|---|---|
| 1 | Build `monitor_sim_swap()` Lambda — Twilio Verify SIM Swap API, covers physical SIM + eSIM | ⬜ Pending |
| 2 | Personal Shield alert on SIM swap detection | ⬜ Pending |
| 3 | Store phone numbers in relayshield_users for all tiers | ⬜ Pending |
| 4 | EventBridge hourly schedule for SIM swap monitor | ⬜ Pending |
| 5 | Carrier-specific hardening steps on detection (Business Basic+) | ⬜ Pending |
| 6 | Port-out fraud detection — flag as CRITICAL | ⬜ Pending |

---

## 🔐 Security Hardening — Tier 1 (Before First Paying Customer)

| # | Item | Status |
|---|---|---|
| 1 | Audit AWS Secrets Manager — confirm no plaintext secrets in code or logs | ✅ Complete |
| 2 | Enable AWS CloudTrail — audit trail for all API calls | ✅ Complete |
| 3 | Enable AWS Config — track Lambda/DynamoDB/IAM configuration changes | ✅ Complete |
| 4 | Review IAM policy relayshield-breach-check-policy — confirm least-privilege | ✅ Complete |
| 5 | Enable DynamoDB encryption at rest — confirm KMS applied to all tables | ✅ Complete |
| 6 | Rotate all API keys (HIBP, Anthropic, Twilio) — update Secrets Manager, set 90-day calendar reminder for each | ✅ Complete |
| 7 | Confirm Lambda function URL not publicly exposed | ✅ Complete — stripe-webhook uses direct Lambda URL (Auth: None) protected by Stripe signature verification. Move behind API Gateway at production launch. |
| 8 | Run Bandit SAST against relayshield_breach_monitor.py | ✅ Complete |
| 9 | Secret scanning — open-source tool (GitGuardian replacement) configured | ✅ Complete |
| 10 | Confirm no secrets in CloudWatch log output | ✅ Complete |

---

## 🚀 Production Launch — Security

| # | Item | Status |
|---|---|---|
| 1 | **Move relayshield-stripe-webhook behind API Gateway** — Currently using direct Lambda URL with Stripe signature verification as protection. Move to API Gateway + delete Lambda function URL before scaling beyond beta. | ⬜ Pending |
| 2 | **Delete relayshield-whatsapp-webhook Lambda function URL** — ⚠️ Twilio is currently pointing directly at the Lambda URL (confirmed April 2026). Must move behind API Gateway and update Twilio webhook URL first, then delete Lambda URL. Do not delete until Twilio is updated. | ⬜ Blocked — do API Gateway first |

---

## 🔐 Security Hardening — Tier 2 (Within First Month of Paid Subscribers)

| # | Item | Status |
|---|---|---|
| 1 | Self-directed pen test — Lambda/DynamoDB surface | ⬜ Pending |
| 2 | Set up GitHub Actions CI with Bandit + Safety + open-source secret scanner | ⬜ Pending |
| 3 | Set up AWS GuardDuty (~$1–3/month) | ⬜ Pending |
| 4 | Confirm PII minimization across DynamoDB tables | ⬜ Pending |
| 5 | Implement DynamoDB TTL on relayshield_breach_alerts (2-year auto-delete) | ⬜ Pending |

---

## 📣 Marketing — Backburned Until Beta Ends

| # | Item | Status |
|---|---|---|
| 1 | **Reddit marketing blitz** — u/BothFan5617 warmed up, posts ready for r/smallbusiness, r/Entrepreneur, r/freelance, r/msp, r/digitalnomad, r/banking | ⬜ Backburned |
| 2 | **Tycoon 2FA blog post** — Published to RelayShield LinkedIn April 19 2026. Pending publication to relayshield.net | ✅ LinkedIn live |
| 3 | **Salon owner conversion** — Send Business Starter payment link when beta period ends | ⬜ Pending |
| 4 | **Facebook Business verification follow-up** — Monitor Meta approval (submitted April 2026) | 🔄 In progress |
| 5 | **IoT cellular backdoor blog post** — Write plain-language breakdown of CPU-to-modem interface attack (Rapid7 research). Audience: r/smallbusiness, r/msp. Establishes telecom expertise authority. No product to build — purely a content play. | ⬜ Backburned |

---

## ⚖️ Intellectual Property

| # | Item | Status |
|---|---|---|
| 1 | **Provisional patent — ordered remediation sequence** — Claude to draft provisional patent overview covering the core method: breach detection → session revocation before password reset → ordered 5-layer sweep → follow-up until confirmed. Take to patent attorney for review and filing. | ⬜ Pending |
| 2 | **Consult patent attorney** — Seek attorney specialising in software/fintech patents. Present provisional overview. Evaluate cost/benefit of full utility patent vs. provisional only. Budget: $1,500–$3,000 for provisional filing. | ⬜ Pending |
| 3 | **Attack chain correlation engine** — Secondary patent candidate: method of mapping specific breach data classes to downstream attack vectors and triggering corresponding remediation paths. Include in attorney consultation. | ⬜ Pending |

---

## 🔮 Phase 2 Features

| # | Item | Status |
|---|---|---|
| 1 | **Annual upsell webhook** — After 2nd monthly payment, WhatsApp offer for annual plan | 🔮 Phase 2 |
| 2 | **SMB account management dashboard** — Seat status, aggregate risk, onboarding completion | 🔮 Phase 2 |
| 3 | **Flare API integration** — Dark web stealer log monitoring, Telegram channel monitoring, session token detection. Offered as paid add-on: BB (~$10/mo optional), BS (~$10/mo optional), BS Pro (bundled). Breaks even at 8 add-on subscribers. API cost ~$79/mo — revenue neutral at 4–5 add-on subscribers. Flare is lead candidate; evaluate Breachsense at scale for MSP pricing. See strategy doc Section 7 — Stealer Log Intelligence Add-On. | 🔮 Phase 2 |
| 4 | **Financial account monitoring** — Plaid API integration | 🔮 Phase 2 |
| 5 | **Data broker removal** — Partner with Incogni/DeleteMe API | 🔮 Phase 2 |
| 6 | **Google Workspace / M365 audit log monitoring** — Concurrent session anomaly detection | 🔮 Phase 2 |
| 7 | **Compliance reporting add-on** — GDPR/HIPAA/CCPA breach notification docs ($29.99/month) | 🔮 Phase 2 |
| 8 | **Seat expansion upsell** — Auto-prompt to upgrade tier when seat limit reached | 🔮 Phase 2 |
| 9 | **Dedicated SMB Carrd page** — /business sub-page when SMB revenue justifies it | 🔮 Phase 2 |
| 10 | **Business Basic+ differentiation** — Develop additional capabilities exclusive to Business Basic and higher to drive upsell from Business Starter. Candidates: priority incident response SLA, aggregate team risk dashboard, organisational OAuth audit, Google Workspace / M365 monitoring, compliance reporting add-on | 🔮 Phase 2 |
| 11 | **Smishing — predictive campaign monitoring (Flare API)** — Extends Flare add-on: monitor Telegram channels for smishing target lists containing monitored phone numbers. Fire CRITICAL alert before campaign reaches user. BB add-on, BS add-on, BS Pro bundled. No additional API cost — same Flare subscription. | 🔮 Phase 2 |
| 12 | **Smishing — team propagation alert** — When one employee number appears in Telegram smishing list, alert team admin. Business Basic and higher. | 🔮 Phase 2 |
| 13 | **Smishing — SIM swap correlation alert** — When SIM swap detected, check if suspicious SMS analysis submitted in prior 48–72 hrs. If yes, escalate to CRITICAL coordinated attack chain alert. Business Shield and Pro only. | 🔮 Phase 2 |
| 14 | **SIM/IMEI anomaly detection via carrier APIs** — Phase 3 research item. Extends Phase 2 SIM swap monitor to detect anomalous carrier traffic patterns (unexpected APN routing, traffic volume spikes, AT command abuse on IoT cellular devices). Targets Business Shield and Pro tiers with IoT-connected operations. Leverages 25-year telecom expertise as moat — no competitor has attempted this. | 🔮 Phase 3 |
| 15 | **Family Shield / Senior Medicare protection** — Two prerequisites: (1) vishing engine built out with Medicare-specific guidance (CMS never calls unsolicited, free equipment = fraud, never give MBI over phone); (2) SMS delivery channel live. Then: Family Shield positioning on landing page targeting adult children buying for senior parents. Medicare number breach escalation to CRITICAL. Medicare-specific CALL and WASCAM response variants. See strategy doc Section 3b. | 🔮 Phase 2 — after vishing engine + SMS channel |
| 16 | **OAuth supply chain attack detection — SaaS breach watchlist** — Poll HIBP `/api/v3/breaches` daily for new breaches. Cross-reference against internal watchlist of high-risk OAuth-capable apps (Slack, Notion, GitHub, Zapier, Linear, Vercel, Loom, HubSpot, AI tools). When watched app newly indexed, fire WhatsApp alert to affected users. Triggered by Vercel/Context.ai breach April 2026 — attacker stole OAuth tokens from breached SaaS, pivoted into Google Workspace without ever touching user credentials. See strategy doc Phase 2 OAuth Supply Chain section. | 🔮 Phase 2 |
| 17 | **OAuth grant inventory at onboarding** — During SWEEP, prompt user to run one-time OAuth audit at myaccount.google.com/permissions and self-report connected apps. Store in DynamoDB user record. Cross-reference against breach watchlist when SaaS app is compromised. Foundation for supply chain breach alerts. | 🔮 Phase 2 |
| 18 | **Proactive monthly OAuth audit reminder** — EventBridge monthly trigger for Business Basic+ subscribers. WhatsApp message: "Monthly security check — review your connected apps at myaccount.google.com/permissions. Reply OAUTH for a guided walkthrough." Differentiates business tiers from Personal Shield reactive-only model. | 🔮 Phase 2 |
| 19 | **Claude system prompt — SaaS/productivity tool breach detection** — ✅ Implemented April 2026. When breach source matches SaaS/productivity/developer/AI tool profile, Claude appends OAuth revocation guidance: myaccount.google.com/permissions + myapps.microsoft.com. Directly addresses supply chain OAuth attack vector. | ✅ Complete |
| 21 | **Agentic Identity Protection — agent credential monitoring** — Phase 3. Extend HIBP breach monitoring to cover API keys, OAuth tokens, and service account credentials used by AI tools and automated systems on behalf of users. Alert human principal when agent credentials appear in breach data. Same engine as human credential monitoring — new credential type inputs. Foundation: Phase 2 OAuth supply chain watchlist. Informed by a16z agentic economy research April 2026. See strategy doc Phase 3 Agentic Identity Protection Engine. | 🔮 Phase 3 |
| 22 | **Agentic Identity Protection — principal-agent breach alert** — Phase 3. When a deployed AI agent/tool is itself breached (Context.ai at scale), fire targeted WhatsApp alert to human principal with specific credential revocation steps. Extends Phase 2 supply chain breach alerts to cover autonomous agents, not just SaaS tools. | 🔮 Phase 3 |
| 23 | **Agentic Identity Protection — agentic OAuth scope auditing** — Phase 3. Periodic audit of OAuth scopes granted to AI agents. Flag over-scoped agents. WhatsApp alert with tightening guidance. Business Basic+. Extends Phase 2 monthly OAuth audit to cover agent grants specifically. | 🔮 Phase 3 |
| 24 | **Agentic Identity Protection — service account credential monitoring** — Phase 3. SMBs run automated systems (bots, scheduled jobs, integrations) holding long-lived API keys. Monitor these service credentials for exposure in breach data. Targets the non-human identity attack surface. Business Shield+. | 🔮 Phase 3 |
| 20 | **RSS feed polling for SaaS breach intelligence** — Implement alongside Phase 2 OAuth audit engine. Lambda polls RSS feeds from BleepingComputer, Krebs on Security, and The Hacker News on a daily EventBridge schedule. Parser extracts breach announcements and cross-references against internal SaaS OAuth app watchlist. When a match is found, fires WhatsApp alert to affected users to revoke OAuth grant immediately. Supplements HIBP Breaches API polling — catches breaches before HIBP indexes them. Feeds: bleepingcomputer.com/feed, krebsonsecurity.com/feed, feeds.feedburner.com/TheHackersNews | 🔮 Phase 2 — build alongside OAuth supply chain watchlist (TODO item 16) |

---

## ✅ Recently Completed

- ✅ RelayShield LLC approved — Massachusetts, April 2026
- ✅ EIN obtained
- ✅ Operating agreement signed
- ✅ Relay Financial business bank account opened and connected to Stripe
- ✅ Terms of Service published and linked on landing page
- ✅ ToS acceptance notice added above payment buttons on Carrd
- ✅ Business Starter tier created — Stripe monthly + annual payment links live
- ✅ Pricing table added to Carrd landing page
- ✅ Business Starter button added to Carrd SELECT A PLAN section
- ✅ Per-seat pricing rationale updated in strategy doc
- ✅ All 4 CloudWatch alarms operational in correct AWS account
- ✅ Session hijacking Ph1 — SESSIONS command, AiTM alerts, two-message architecture
- ✅ Facebook Business verification submitted
- ✅ Salon owner (Rebecca) beta account created in DynamoDB
