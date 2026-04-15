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
| 1 | **Salon owner (Rebecca) onboarded** — DynamoDB records created. Awaiting her HELP confirmation via WhatsApp. | 🔄 In progress |
| 2 | **Additional beta testers** — Recruit 2–3 more testers. Add DynamoDB records using beta template. | ⬜ Pending |
| 3 | **Collect beta feedback** — Was the breach alert clear? Was remediation actionable? Would you pay $14.99/month? | ⬜ Pending |

---

## ⚡ High Priority — Pre-Revenue

| # | Item | Status |
|---|---|---|
| 1 | **Update landing page markdown in Git** — Sync relayshield_landing_page.md with all Carrd changes made today (pricing table, Business Starter button, benefit tagline, ToS links) | ⬜ Pending |
| 2 | **Stripe annual plans TODO** — Confirm all tiers have annual payment links active (Personal Shield, Business Basic, Business Shield, Business Shield Pro, Business Starter) | ✅ Complete |
| 3 | **Stripe legal entity** — Update to RelayShield LLC in business details | ✅ Complete |
| 4 | **Relay Financial bank account** — Connected to Stripe as default payout | ✅ Complete |
| 5 | **Annual Stripe TODO note** — Remove the ⬜ TODO note in strategy doc re: annual plans | ⬜ Pending |

---

## 📦 Product — Phase 1 Remaining

| # | Item | Status |
|---|---|---|
| 1 | **Auto-send Claude analysis on first reply** — When ACTIVE user messages after breach and no freeform was sent (63016), webhook auto-sends full Claude analysis before handling their command | ⬜ Pending |
| 2 | **Fix empty breach_date field in DynamoDB** | ⬜ Pending |
| 3 | **Password breach checking** — Pwned Passwords API integration | ⬜ Pending |
| 4 | **Cross-account password risk detection** | ⬜ Pending |
| 5 | **Business Starter webhook code update** — Add TIER_STARTER constant, EMAIL_LIMITS entry, phone hardening parity with business tiers | ⬜ Pending (not blocking for beta) |
| 6 | **Consumer vishing alert** — Append vishing warning to WhatsApp alert when breach exposes phone/address/carrier/account numbers | ⬜ Pending |
| 7 | **Personal verification protocol** — Onboarding WhatsApp flow: callback rule, OTP rule, family safe word, wire transfer rule | ⬜ Pending |
| 8 | **SSN/passport/DL vishing escalation** — CRITICAL severity when these data classes detected | ⬜ Pending |

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
| 1 | Audit AWS Secrets Manager — confirm no plaintext secrets in code or logs | ⬜ Pending |
| 2 | Enable AWS CloudTrail — audit trail for all API calls | ⬜ Pending |
| 3 | Enable AWS Config — track Lambda/DynamoDB/IAM configuration changes | ⬜ Pending |
| 4 | Review IAM policy relayshield-breach-check-policy — confirm least-privilege | ⬜ Pending |
| 5 | Enable DynamoDB encryption at rest — confirm KMS applied to all tables | ⬜ Pending |
| 6 | Rotate all API keys (HIBP, Anthropic, Twilio) — establish 90-day rotation | ⬜ Pending |
| 7 | Confirm Lambda function URL not publicly exposed | ⬜ Pending |
| 8 | Run Bandit SAST against relayshield_breach_monitor.py | ⬜ Pending |
| 9 | Set up GitGuardian free tier | ⬜ Pending |
| 10 | Confirm no secrets in CloudWatch log output | ⬜ Pending |

---

## 🔐 Security Hardening — Tier 2 (Within First Month of Paid Subscribers)

| # | Item | Status |
|---|---|---|
| 1 | Self-directed pen test — Lambda/DynamoDB surface | ⬜ Pending |
| 2 | Set up GitHub Actions CI with Bandit + Safety + GitGuardian | ⬜ Pending |
| 3 | Set up AWS GuardDuty (~$1–3/month) | ⬜ Pending |
| 4 | Confirm PII minimization across DynamoDB tables | ⬜ Pending |
| 5 | Implement DynamoDB TTL on relayshield_breach_alerts (2-year auto-delete) | ⬜ Pending |

---

## 📣 Marketing — Backburned Until Beta Ends

| # | Item | Status |
|---|---|---|
| 1 | **Reddit marketing blitz** — u/BothFan5617 warmed up, posts ready for r/smallbusiness, r/Entrepreneur, r/freelance, r/msp, r/digitalnomad, r/banking | ⬜ Backburned |
| 2 | **Tycoon 2FA blog post** — Draft exists, pending publication to relayshield.net | ⬜ Backburned |
| 3 | **Salon owner conversion** — Send Business Starter payment link when beta period ends | ⬜ Pending |
| 4 | **Facebook Business verification follow-up** — Monitor Meta approval (submitted April 2026) | 🔄 In progress |

---

## 🔮 Phase 2 Features

| # | Item | Status |
|---|---|---|
| 1 | **Annual upsell webhook** — After 2nd monthly payment, WhatsApp offer for annual plan | 🔮 Phase 2 |
| 2 | **SMB account management dashboard** — Seat status, aggregate risk, onboarding completion | 🔮 Phase 2 |
| 3 | **Flare API integration** — Dark web stealer log monitoring, session token detection | 🔮 Phase 2 |
| 4 | **Financial account monitoring** — Plaid API integration | 🔮 Phase 2 |
| 5 | **Data broker removal** — Partner with Incogni/DeleteMe API | 🔮 Phase 2 |
| 6 | **Google Workspace / M365 audit log monitoring** — Concurrent session anomaly detection | 🔮 Phase 2 |
| 7 | **Compliance reporting add-on** — GDPR/HIPAA/CCPA breach notification docs ($29.99/month) | 🔮 Phase 2 |
| 8 | **Seat expansion upsell** — Auto-prompt to upgrade tier when seat limit reached | 🔮 Phase 2 |
| 9 | **Dedicated SMB Carrd page** — /business sub-page when SMB revenue justifies it | 🔮 Phase 2 |

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
