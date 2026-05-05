# RelayShield — Open Items

*Last updated: May 2026*
*Legend: 🚨 Blocking · ⚡ High Priority · 🔄 In Progress · ⬜ Pending · 🔮 Future*

---

## 🚨 Launch Blockers — Must Complete Before First Paying Customer

| # | Item | Status |
|---|---|---|
| 1 | **Tech E&O + Cyber insurance** — Embroker application submitted April 2026 — slow to respond. Coalition rejected May 2026 (misclassified as MSP — rebuttal sent). **Next: At-Bay application** — strongest fit for SaaS/API companies, tech-savvy underwriting. Security posture: IRP ✅, FileVault ✅, DynamoDB PITR ✅ (all 4 tables confirmed On), Secrets Manager ✅, OIDC ✅, SAST CI ✅. GuardDuty pending billing fix. No EDR — disclose honestly, not disqualifying at this revenue level. | 🔄 Apply At-Bay next |
| 2 | **Facebook Business verification** — Submitted as sole proprietor. Monitoring for Meta approval. | 🔄 Submitted — awaiting Meta |

---

## 🔄 Beta Testing — Active

| # | Item | Status |
|---|---|---|
| 1 | **Salon owner (Rebecca) onboarded** — Active. HELP confirmed. | ✅ Active |
| 2 | **Tester 2 onboarded** — Cybersecurity background (Equifax). Active. HELP confirmed. Email Security Sweep completed ✅ | ✅ Active |
| 3 | **Additional beta testers** — Tester 3 (brother) onboarded April 2026. HELP confirmed. 3 active beta testers total. | ✅ Active |
| 4 | **Beta feedback form** — Built and published. Link: https://docs.google.com/forms/d/e/1FAIpQLSeZ8G7Bj_gfrTybnFk8R8AQyxRXGi6kQo_7V7CnqASF1Kg6rw/viewform?usp=publish-editor — Sent via WhatsApp to all 3 active testers April 2026. Responses land in relayshieldadmin@gmail.com Google Forms. | ✅ Sent — awaiting responses |
| 5 | **Collect beta feedback** — Form sent to all 3 active testers April 2026. Monitor relayshieldadmin@gmail.com Google Forms Responses tab. Target signal: value perception at price point, sweep completion rate, differentiation validation from tester 2 (Equifax background). | 🔄 Awaiting responses |
| 6 | **Referral program** — Post-launch Phase 2 item. Validate organic advocacy first (Q9 of feedback form). If strong, build referral incentive mechanic (e.g. one free month per converted referral). | 🔮 Phase 2 |

---

## ⚡ High Priority — Pre-Revenue

| # | Item | Status |
|---|---|---|
| 0c | **Contact VirusTotal re: commercial licensing for B2A** — Free VT API ToS prohibits reselling/redistributing scan results through a commercial API. B2A `/scan_url` and `/scan_file` endpoints must stay "coming soon" on RapidAPI until a commercial license is confirmed. Contact VT via virustotal.com/gui/contact-us → "I have a commercial inquiry" → ask about startup/commercial licensing for a SaaS security platform redistributing scan results via REST API. B2C WhatsApp usage (users scanning their own content) is defensible on free tier — add per-user 5 scans/day rate limit to Lambda as cost control. **Deferred — contact only when first B2A prospect specifically requests scan features.** | 🔮 Deferred — trigger: first B2A prospect asks for scan features |
| 0a | **Publish Show HN post — relayshield-mcp** — Post to news.ycombinator.com. Title: "Show HN: RelayShield MCP – identity threat detection tools for Claude and AI agents." Body covers 6 tools (check_breach, check_sim_swap, check_domain_lookalikes, scan_url, scan_file, check_scan_result), install (`pip install relayshield-mcp`), RapidAPI link for REST, solo founder on AWS Lambda + API Gateway. Schedule: **Tuesday May 5 2026 morning** (peak HN traffic). | ⬜ Pending — tomorrow morning |
| 0b | **AWS Marketplace listing — RelayShield Security Intelligence API** — Register and publish RelayShield B2A REST API on AWS Marketplace. Puts RelayShield in front of enterprise AWS customers. Highest B2A revenue path. **Blocked:** Partner Central registration requires paid AWS account in good standing — same billing propagation issue as GuardDuty. Identity ✅ + Business ✅ verification both complete. Resume at `console.aws.amazon.com/partnercentral/verification/status` → Continue registration once account converts. GuardDuty enable at same time. | 🔄 Blocked — awaiting AWS paid account conversion |
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
| 1 | **Auto-send Claude analysis on first reply** — When ACTIVE user messages after breach and no freeform was sent (63016), webhook auto-sends full Claude analysis before handling their command. REMOVE used to clear pending_analysis field; early return prevents unknown-command message from firing. | ✅ Complete — deployed April 2026 |
| 2 | **Fix empty breach_date field in DynamoDB** | ✅ Complete — code already handles via BreachDate→AddedDate fallback. Empty values are legacy beta test records only. |
| 3 | **Password breach checking** — Deprioritised April 2026. RelayShield never stores or handles passwords — Pwned Passwords API requires knowing the password string to check. HIBP already flags "Passwords" as a DataClass in breach alerts, and REUSE command handles downstream risk. No incremental value to build. | ❌ Deprioritised |
| 4 | **Cross-account password risk detection** — REUSE command walks through 6 cross-account services (YES/NO per service). YES answers tracked in `reuse_flagged` (JSON list in DynamoDB). Personalised completion summary: "No reused passwords flagged" (clean) or named flagged services with change prompt (flagged). State auto-resets after completion. REUSE added to breach alert closing CTA for all breach types, not just password-exposed breaches. | ✅ Complete — April 2026 |
| 5 | **Business Starter webhook code update** — TIER_STARTER constant, EMAIL_LIMITS (3 emails = owner + 2 slots), SEAT_LIMITS (2 ADD slots = owner + 2 people covered), BUSINESS_TIERS membership, phone hardening at Starter/Basic level. | ✅ Complete — deployed April 2026 |
| 5a | **Business Starter — 2 contractor/employee seats via ADD** — Owner can ADD up to 2 people (employees or contractors) via ADD command. Seat limit enforced at 2. Clear upsell to Business Basic (5 seats). | ✅ Complete — deployed April 2026 |
| 5b | **All tiers — Quarterly proactive sweep reminder** — Lambda `relayshield-quarterly-sweep-sender` deployed April 24 2026. EventBridge schedule `relayshield-quarterly-sweep` enabled `rate(90 days)`. Template `relayshield_quarterly_sweep` approved Meta April 24 2026. SID `HX2ec6e31204006775cb86fb5dbc1739d3`. Single-user test confirmed April 24 2026: `sent=1 skipped=0 failed=0`, WhatsApp delivery verified. | ✅ Complete — April 2026 |
| 5b-fix | **Digest + Day3 phone field bug** — Fixed April 2026. Both Lambdas updated: `kms_client` added, `decrypt_phone()` + `get_user_whatsapp_number()` helpers added, legacy `whatsapp_number` lookup replaced with KMS primary path + plaintext fallback. Upload `relayshield_digest_sender.zip` → `relayshield-digest-sender` Lambda and `relayshield_day3_sender.zip` → `relayshield-day3-sender` Lambda. | ✅ Complete — upload zips to deploy |
| 5c | **All tiers — Monthly WhatsApp Security Digest** — Lambda deployed. EventBridge trigger wired. Template approved UTILITY. SID `HX58cb69a1f9de4793ae225015d186c8e6` in code. `test_user_id` parameter added for safe founder-only testing. Single-user test confirmed April 2026: `sent=1 skipped=0 failed=0`, delivered to +19785013199 status `queued`. `relayshield-digest-scan` IAM inline policy added to `relayshield-breach-check-role-1sapnwdl` (Scan on all 3 tables). **May 2026 fix:** month label corrected to previous month (was showing May on May 1st instead of April), `days_in_month` corrected to previous month's days, breach language updated to "known breaches on record — remediation steps sent for all new detections" to avoid alarming customers. | ✅ Complete — May 2026 |
| 5d | **Welcome message — all tiers** — WhatsApp template `relayshield_welcome` approved by Meta April 2026. Stripe webhook updated to send via Twilio Content API (HX45e6bac7d790f79414f7b067e1a3edd9). Manual DynamoDB onboarding (beta) uses ad-hoc WhatsApp contact — no automated send needed for beta path. | ✅ Complete — production path done |
| 5e | **Day 3 onboarding follow-up template** — Template `relayshield_day3` approved by Meta as UTILITY April 2026. SID `HXb8e3c80de422dae90addf0bd6561b2b4` in code. Lambda `relayshield-day3-sender` deployed. IAM role `relayshield-scheduler-invoke-day3` created (trust: scheduler.amazonaws.com, inline policy: lambda:InvokeFunction). `scheduler:CreateSchedule` added to stripe-webhook IAM policy. Env vars `DAY3_LAMBDA_ARN` + `DAY3_SCHEDULER_ROLE_ARN` set on stripe-webhook Lambda. `relayshield-day3-dynamodb` inline policy added to `relayshield-breach-check-role-1sapnwdl`. Single-user test confirmed April 2026 — WhatsApp delivery to founder verified. | ✅ Complete — April 2026 |
| 6 | **Consumer vishing alert** — Append vishing warning to WhatsApp alert when breach exposes phone/address/carrier/account numbers | ✅ Complete — in Claude system prompt |
| 9a | **Disappearing WhatsApp message awareness** — Added to onboarding completion message. Three rules: RelayShield never asks for OTP/PIN, screenshot urgent messages, urgency is the attack. Introduces WASCAM and OTP commands. | ✅ Complete |
| 9b | **OTP command — WhatsApp-specific guidance** — Extended OTP response to cover WhatsApp OTP takeover consequences: full account takeover, contact list exploitation, chain attacks. Two-Step Verification prompt added. | ✅ Complete |
| 9c | **WASCAM command** — New command for suspicious WhatsApp messages. Leads with bank/financial fraud, carrier impersonation, then Hi Mum/Dad family scam, disappearing message tactics, verification steps. Added to HELP menu. | ✅ Complete |
| 7 | **Personal verification protocol** — `VERIFY` command built and deployed. Four rules: callback rule (hang up + call official number), OTP rule (no legit org asks you to read it back), family safe word (must say it or hang up), wire transfer rule (always call a known number to verify). Added to HELP menu all tiers. Referenced in onboarding completion message. `msg_verify()` function added to webhook. | ✅ Complete — April 2026 |
| 8 | **SSN/passport/DL vishing escalation** — CRITICAL severity when these data classes detected | ✅ Complete — in Claude system prompt |
| 9 | **Smishing — phone number breach escalation** — Detect "Phone numbers" in HIBP DataClasses → append smishing warning to existing breach alert. ~1–2 hrs. All tiers. | ✅ Complete |
| 10 | **Smishing — carrier PIN hardening messaging** — `msg_phone_hardening()` updated with smishing context. Carriers never text/call asking for PIN framing added. All tiers. | ✅ Complete |
| 11 | **Smishing — OTP warning flow** — `OTP` command added. `msg_unexpected_otp()` function built. HELP menu updated. Account lockdown + SIM swap precursor guidance. All tiers. | ✅ Complete |
| 12 | **Smishing — suspicious SMS analysis (Phase 1 stub)** — `SMS <text>` command added. Returns immediate guidance + carrier reporting steps (7726). TODO stub in code for Google Safe Browsing URL analysis. Full URL analysis is next build item. | ✅ Complete — URL analysis live (see item 13) |
| 13 | **Smishing — URL analysis (Google Safe Browsing)** — Complete the SMS command: extract URLs from forwarded text, check via Google Safe Browsing API, return safe/suspicious/malicious verdict + remediation. ~3–4 hrs. | ✅ Complete |
| 14 | **EMAIL command — phishing email URL analysis** — `EMAIL <text>` command: user pastes email body text into WhatsApp, RelayShield extracts URLs + runs Google Safe Browsing check, returns verdict with email-specific framing (sender spoofing warning, do-not-click guidance, report-to-IT steps for business tiers). Reuses existing `extract_urls()` + `check_urls_safe_browsing()` + `build_sms_analysis_response()` pipeline entirely — new response builder for email context only. Add to HELP menu. ~30 min. Engagement driver: keeps users interacting with RelayShield for threats that aren't breach-driven. | ✅ Complete — April 2026 |
| 15 | **ATTACH command — VirusTotal attachment scanning** — Deployed April 2026. `ATTACH` (no content): usage guidance + Gmail copy-link-address tip. `ATTACH <url>`: submits URL to VT `/urls`, polls `/analyses/{id}` up to 20 s, returns malicious/suspicious/clean verdict. WhatsApp file attachment: Lambda receives `NumMedia` + `MediaUrl0` from Twilio, downloads binary, submits to VT `/files`, polls up to 35 s, returns verdict. `build_vt_verdict_response()` handles all outcomes including timeout. HELP menu updated. **Prerequisites before deploy:** (1) Add `relayshield/virustotal_api_key` secret to Secrets Manager with key `virustotal_api_key`; (2) Add `secretsmanager:GetSecretValue` on that secret to whatsapp-webhook IAM policy; (3) Set Lambda timeout to 60 s (Configuration → General → Edit). | ✅ Complete — deploy after Secrets Manager setup |
| 16 | **Coordinated Attack Detection** — Temporal signal correlation engine. Maintains a `recent_signals` list on each user record (72-hr rolling window, self-pruning). Records signal types: `breach_alert`, `sim_swap`, `port_out`, `suspicious_sms`, `otp_warning`. Three attack chains: (1) smishing → SIM swap (CRITICAL), (2) breach + SIM swap (CRITICAL), (3) breach + OTP interception (HIGH). When chain is matched, fires composite coordinated attack alert with cross-signal remediation sequence. 48-hr dedup per user. `last_coordinated_alert_at` field on user record. Shared helpers (`record_signal`, `check_and_fire_correlation`, `_build_coordinated_alert`, `_send_coordinated`) added to breach monitor, SIM swap monitor, and WhatsApp webhook. All three zips deployed to AWS April 2026. Patentable — documented in `relayshield_provisional_patent_overview.md` Component 3. **Strategic value:** Foundation for multi-signal threat intelligence API and dataset monetisation. | ✅ Complete — deployed April 2026 |
| 16b | **VirusTotal per-user daily scan rate limit (B2C)** — Add `vt_scans_today` counter + `vt_scan_date` field to `relayshield_users` DynamoDB record. On each ATTACH or SMS/EMAIL URL scan via VT: check counter, reject with friendly message if ≥5 scans today, otherwise increment and proceed. Resets daily. Protects free tier (500/day across all users) until commercial license obtained. ~1 hr. | ⬜ Pending |
| 17 | **Breach velocity alert** — If the same monitored email appears in 3+ distinct breaches within a 30-day rolling window, fire a CRITICAL compound exposure alert: "Your email has appeared in N separate breaches this month — this pattern suggests active credential trading." Query `relayshield_breach_alerts` table by `email_hash` with date filter before each alert. Swap in compound template when threshold crossed. Strong upsell trigger Personal Shield → Business Basic. ~2 hrs. | ⬜ Pending |
| 18 | **Employee offboarding security checklist** — When admin fires REMOVE command, after confirming removal, send a second WhatsApp message with a structured post-offboarding checklist: deactivate company email, remove from shared accounts, rotate any shared credentials, revoke OAuth access at myaccount.google.com, check admin rights to SaaS tools. ~30 min addition to REMOVE handler in webhook. Zero infrastructure cost. High SMB retention value. | ⬜ Pending |
| 19 | **Certificate Transparency log monitoring** — Extend domain monitor with daily crt.sh API query per registered domain. Catches phishing infrastructure (TLS certs issued for lookalike domains) before DNS propagation. Free API. Alert: "A TLS certificate was issued for [domain] — attackers may be standing up a phishing site." ~3 hrs. Strongest Phase 1.5 feature for converting Business Starter + Domain → Business Basic. | ✅ Complete — April 2026 (Build B, shipped with GSB + RDAP enrichment in domain monitor) |
| 20 | **SMS fallback delivery** — All code complete and tested. SIM swap template wired as primary delivery (bypasses 63016). Port-out + coordinated attack alerts write `pending_sms_fallback` to DynamoDB. `relayshield-sms-fallback-sender` Lambda deployed, EventBridge `rate(4 hours)` live, webhook clears flag on inbound message. **Blocked on US A2P 10DLC registration** (Twilio error 30034 — carrier filters unregistered SMS). Cost: ~$4 one-time brand registration + ~$10/month campaign fee. Alternatively buy a toll-free number (~$2/month) and submit toll-free verification (faster approval). **Activate after first 1–2 paying customers.** | ⏸️ Parked — pending 10DLC registration |
| 21 | **Predictive alerts — pre-chain warnings** — Invert the `ATTACK_CHAINS` correlation logic: when the first signal in a known chain is recorded, append a forward-looking warning to the primary alert before the second signal arrives. Example: breach alert fires → append "SIM swap attempts commonly follow credential breaches within 72 hours — consider locking your SIM now." No new infrastructure required — lightweight addition to each Lambda's alert delivery path alongside the existing `record_signal()` call. All 4 chains covered: smishing→SIM swap, breach+SIM swap, breach+OTP interception, domain phishing→breach. ~1–2 hrs. | ⬜ Pending |
| 22 | **WASCAM — browser social engineering block** — `msg_wascam_part3()` added covering fake CAPTCHA SMS charge fraud, fake browser security alerts, and ClickFix paste-and-run attacks. Wired as third message in WASCAM handler. Closing rule: "legitimate services never ask you to send a text, run a command, or call a number to prove you are human." | ✅ Complete — deploy pending |

---

## 🏢 Business Tier MVP — Pre-Revenue (Business Basic + Business Shield)

*These four items are required to make Business Basic ($89.99) and Business Shield ($139.99) defensible at their price points. Without them, business admins have no visibility or control after onboarding employees.*

| # | Item | Status |
|---|---|---|
| 1 | **`REMOVE` command — employee offboarding** — `REMOVE +16175551234`: finds employee by phone hash + admin ownership check, sets `active=False`, deactivates all monitored emails. Confirms to admin with name + email count. Second message sends 6-step post-offboarding security checklist (deactivate email, shared accounts, rotate credentials, revoke OAuth, audit SaaS admin rights, recover devices). Deployed and tested May 4 2026. | ✅ Complete — May 2026 |
| 1a | **AWS OIDC IAM role setup** — OIDC provider `token.actions.githubusercontent.com` created. Role `relayshield-github-deploy` created with trust policy scoped to `nzdsf2-gif/relayshield`. Policy `relayshield-lambda-deploy` attached. GitHub Actions `deploy_lambdas.yml` live — workflow passed in 16 seconds May 2026. | ✅ Complete — May 2026 |
| 2 | **`STATUS` command — WhatsApp-native admin dashboard** — `STATUS`: returns seat usage (X of Y), per-employee onboarding state (✅ Active / ⏳ Onboarding), emails monitored count, ADD/REMOVE instructions. Business admin only. Deployed April 2026. | ✅ Complete — April 2026 |
| 3 | **Admin breach co-notification** — When employee breach fires and alert is successfully delivered, second WhatsApp alert sent to admin with employee name (if stored), breach names, and severity label. Cached admin record lookup. `get_whatsapp_number_from_record()` fixed to use KMS `phone_encrypted` primary path + legacy fallback. Deployed April 2026. | ✅ Complete — April 2026 |
| 4 | **Employee name on `ADD` command** — `ADD +16175551234 John Smith` stores `employee_name` on the record. Admin confirmation and STATUS display use name. Backward-compatible (ADD without name still works). Deployed April 2026. | ✅ Complete — April 2026 |

---

## 🌐 Domain Monitoring — Business Basic / Shield / Shield Pro

| # | Item | Status |
|---|---|---|
| 1 | **`relayshield_domain_monitor.py` Lambda built** — Daily EventBridge scan for all Business Basic+ admins with registered domains. Three checks per domain: typosquat/lookalike (custom permutation + parallel socket DNS, no library deps), MX record change (Cloudflare DoH), expiry risk (RDAP API — 30/14/7 day thresholds). Admin co-notification pattern applied. Template-gated: alerts fire once SIDs are filled. | ✅ Code complete — deploy pending |
| 2 | **`DOMAIN` command added to webhook** — DOMAIN (status), DOMAIN SCAN (on-demand full check, freeform), DOMAIN REGISTER, DOMAIN REMOVE. Tier-gated to DOMAIN_TIERS. Employees get read-only access (status + scan against admin's domains). Auto-extraction at onboarding: first email with a business domain auto-registers — free providers (Gmail etc.) skipped. | ✅ Complete — April 2026 |
| 3 | **HELP menu updated** — DOMAIN + DOMAIN SCAN added for all Business tiers. DOMAIN REGISTER shown for admins only. | ✅ Complete — April 2026 |
| 4 | **Deploy whatsapp webhook** — zip + upload updated `relayshield_whatsapp_webhook.py` (adds DOMAIN command, auto-extraction hook, domain helpers). MX language updated to customer-friendly "email configuration" framing — confirmed working April 2026. | ✅ Complete — April 2026 |
| 5 | **Deploy domain monitor Lambda** — `relayshield-domain-monitor` deployed. Handler: `relayshield_domain_monitor.lambda_handler`. 300s/256MB. IAM: `relayshield-breach-check-role-1sapnwdl` with `relayshield-breach-check-policy` updated to correct account `239677749008` ARNs. | ✅ Complete — April 2026 |
| 6 | **EventBridge schedule — rate(1 day)** — `relayshield-domain-monitor` schedule created. | ✅ Complete — April 2026 |
| 7 | **Force-test domain monitor** — Test confirmed April 2026. `statusCode: 200`, `relayshield.net` scanned, lookalike alert (`relayshield.com`) delivered via approved Meta template. State saved to DynamoDB. | ✅ Complete — April 2026 |
| 8 | **Submit 3 Meta templates + wire SIDs** — All 3 approved April 27 2026. `DOMAIN_LOOKALIKE_TEMPLATE_SID = HX5c71336145c248642ec864a53a0320cf`, `DOMAIN_MX_CHANGE_TEMPLATE_SID = HXaa1912f2a81ca440b025f61d5f6b51e8`, `DOMAIN_EXPIRY_TEMPLATE_SID = HXc5b861da1c21d8097e0d8830ed663d96`. All wired in `relayshield_domain_monitor.py`. | ✅ Complete — April 2026 |
| 9 | **Register existing Business Basic+ admin domains via DOMAIN REGISTER** — For any existing paying Business Basic+ admins at launch, manually send DOMAIN REGISTER via admin WhatsApp session OR update DynamoDB directly to set `monitored_domains`. | ⬜ Pending — at customer acquisition |

---

## 📱 SIM Swap Monitor — Phase 1

| # | Item | Status |
|---|---|---|
| 1 | **`relayshield_sim_swap_monitor.py` Lambda built** — Twilio Lookup v2, covers physical SIM + eSIM (IMSI change). Tiered alerts: Personal (carrier numbers), Business Basic/Shield (carrier-specific hardening + eSIM audit), Business Shield Pro (+ eSIM disable + FCC complaint). Port-out detection via carrier tracking. Admin co-notification for business-tier employees. KMS phone decryption. Force-test mode. | ✅ Code complete — deploy pending |
| 2 | **Personal Shield alert on SIM swap detection** — Included in Lambda. Carrier callback numbers + SWEEP/PHONE reply prompts. | ✅ Complete (in Lambda) |
| 3 | **Phone numbers in relayshield_users** — All records have `phone_encrypted` (KMS) + `phone_hash`. Lambda uses KMS primary path + legacy fallback. | ✅ Complete |
| 4 | **EventBridge schedule — rate(4 hours)** — `relayshield-hourly-sim-swap-check` enabled. | ✅ Complete — April 2026 |
| 5 | **Carrier-specific hardening steps (Business Basic+)** — AT&T, T-Mobile, Verizon specific steps in Lambda. Falls back to generic multi-carrier block for unknown carriers. | ✅ Complete (in Lambda) |
| 6 | **Port-out fraud detection — CRITICAL** — Carrier name change between checks triggers CRITICAL alert. `last_known_carrier` tracked on user record. Bypass dedup window (always fires). | ✅ Complete (in Lambda) |
| 7 | **Deploy `relayshield-sim-swap-monitor` Lambda** — Upload zip, set handler `relayshield_sim_swap_monitor.lambda_handler`, 300s timeout, 128MB. IAM: DynamoDB Scan+GetItem+UpdateItem on `relayshield_users`, Secrets Manager GetSecretValue for Twilio creds, KMS Decrypt on `alias/relayshield-data-key`. | ✅ Complete — April 2026 |
| 8 | **Submit `relayshield_sim_swap` template to Meta** — Template `relayshield_sim_swap_alert` approved UTILITY April 9 2026. SID `HX9df8877e110384af8835931dfeeff954` wired into deployed Lambda. | ✅ Complete — April 2026 |

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
| 1 | **Move relayshield-stripe-webhook behind API Gateway** — Currently using direct Lambda URL with Stripe signature verification as protection. Move to API Gateway + delete Lambda function URL before scaling beyond beta. | ✅ Complete |
| 2 | **Delete relayshield-whatsapp-webhook Lambda function URL** — ⚠️ Twilio is currently pointing directly at the Lambda URL (confirmed April 2026). Must move behind API Gateway and update Twilio webhook URL first, then delete Lambda URL. Do not delete until Twilio is updated. | ✅ Complete |

---

## 🔐 Security Hardening — Phase 1 Active Build

*Build now — competitive differentiator and direct response to customer concern about PII storage.*

| # | Item | Status |
|---|---|---|
| 1 | **Field-level KMS encryption for email addresses** — KMS key `relayshield-data-key` (`arn:aws:kms:us-east-1:239677749008:key/1479c3fa-88e9-4096-a736-32968ba5812f`) created and enabled. IAM policy `relayshield-kms-field-encryption` on all 3 Lambda roles. breach-monitor + whatsapp-webhook Lambdas deployed April 2026. Migration Lambda ran successfully — 13 beta records migrated, 0 failed, 0 plaintext records remaining (confirmed by dry-run). Migration Lambda and temp IAM policy deleted post-migration. All future records encrypted at creation. | ✅ Complete — April 2026 |
| 2 | **Customer Managed KMS Key (CMK) for DynamoDB table encryption** — All 3 tables (`relayshield_users`, `relayshield_monitored_emails`, `relayshield_breach_alerts`) confirmed using CMK `relayshield-dynamodb-key` (`arn:aws:kms:us-east-1:239677749008:key/2ece080e-0cb0-499e-b2d1-6a496bbb4a1a`). `smartasst-dev-us-east-2-lambdaRole` removed as unauthorised key administrator. | ✅ Complete — April 2026 |
| 3 | **Field-level KMS encryption for phone numbers + token-based hash lookup** — GSI `phone_hash-index` created on `relayshield_users`. `encrypt_phone()`, `decrypt_phone()`, `hash_phone()`, `get_user_whatsapp_number()` helpers added to both webhooks. `get_user_by_whatsapp()` replaced full table scan with GSI query + legacy fallback. `create_user_record()` and `create_employee_record()` write `phone_encrypted` + `phone_hash` — no plaintext stored. Migration Lambda ran successfully — 6 beta records migrated, 0 failed, 0 plaintext records remaining (confirmed by dry-run). Migration Lambda and temp IAM policy deleted post-migration. All future records encrypted at creation. | ✅ Complete — April 2026 |

---

## 🔐 Security Hardening — Tier 2 (Within First Month of Paid Subscribers)

| # | Item | Status |
|---|---|---|
| 1 | Self-directed pen test — Lambda/DynamoDB surface | ⬜ Pending |
| 2 | Set up GitHub Actions CI with Bandit + Safety + open-source secret scanner | ✅ Complete — `.github/workflows/security_audit.yml` runs Bandit (HIGH severity gate), Safety (CVE check), and Gitleaks (secret scan) on every push to main |
| 3 | **Set up AWS GuardDuty (~$1–3/month)** — Navigate to GuardDuty in AWS console → Get Started → Enable GuardDuty. **Blocked:** account 239677749008 billing setup incomplete (free plan limitation). Complete AWS registration / verify payment method first, then one-click enable. Update IRP Section 4 detection sources once live. | 🔄 Blocked — complete AWS billing setup first |
| 4 | Confirm PII minimization across DynamoDB tables | ⬜ Pending |
| 5 | **Implement DynamoDB TTL on relayshield_breach_alerts** — `expires_at` epoch field added to `write_breach_alert()` in breach monitor (now + 2 years). Enable on table: `aws dynamodb update-time-to-live --table-name relayshield_breach_alerts --time-to-live-specification "Enabled=true, AttributeName=expires_at" --region us-east-1` — run once then done. Legacy beta records without the field are unaffected. | ✅ Complete — April 2026 |
| 6 | **Secrets Manager for OAuth tokens (Phase 2 prerequisite)** — Never store OAuth tokens in DynamoDB. When Phase 2 OAuth monitoring ships, each token stored in Secrets Manager under `relayshield/oauth/{user_id}/{provider}`. DynamoDB stores only the ARN reference — useless to an attacker without separate IAM access to Secrets Manager. Build this architecture before first OAuth token is collected. | ⬜ Pending — required before Phase 2 OAuth |

---

## 📣 Marketing — Backburned Until Beta Ends

| # | Item | Status |
|---|---|---|
| 1 | **Reddit marketing blitz** — u/BothFan5617 warmed up. Draft posts written for r/smallbusiness, r/Entrepreneur, r/freelance, r/msp, r/digitalnomad, r/banking — see `reddit_marketing_drafts.md` (created this session). Andrew posts manually. | 🔄 Drafts written — pending manual post |
| 2 | **Tycoon 2FA blog post** — Published to RelayShield LinkedIn April 19 2026. Pending publication to relayshield.net | ✅ Complete |
| 6 | **OAuth supply chain LinkedIn post** — Published April 26 2026. Title: "The Vercel Hack Wasn't About a Stolen Password." Feature shipped same day as article. | ✅ Published |
| 7 | **Aura LinkedIn article** — Published May 1 2026. Title: "The Identity Protection Industry Has a Structural Flaw. Here's What It Is." Covers ordered remediation sequence, session token blindness, SMB gap. | ✅ Published |
| 8 | **PyPI supply chain blog — publish to LinkedIn** — Wednesday May 6 2026. Title: "Your AI Stack Just Became a Credential Harvester." Draft: `relayshield_pypi_supply_chain_blog.md`. Also post to r/netsec and r/Python same day. Put RapidAPI link in first comment on LinkedIn. | ⬜ Pending — Wednesday May 6 |
| 9 | **PyPI token rotation — relayshield-mcp-v1** — Token scoped to relayshield-mcp, stored in AWS Secrets Manager `relayshield/pypi_api_token`. Rotate by **August 2 2026**: create new scoped token on PyPI, update Secrets Manager, delete old token. | ⬜ Pending — due August 2 2026 |
| 3 | **Salon owner conversion** — Send Business Starter payment link when beta period ends | ⬜ Pending |
| 4 | **Facebook Business verification follow-up** — Monitor Meta approval (submitted April 2026) | 🔄 In progress |
| 5 | **IoT cellular backdoor blog post** — Write plain-language breakdown of CPU-to-modem interface attack (Rapid7 research). Audience: r/smallbusiness, r/msp. Establishes telecom expertise authority. No product to build — purely a content play. | ⬜ Backburned |

---

## ⚖️ Intellectual Property

| # | Item | Status |
|---|---|---|
| 1 | **Provisional patent — ordered remediation sequence** — Claude to draft provisional patent overview covering the core method: breach detection → session revocation before password reset → ordered 5-layer sweep → follow-up until confirmed. Take to patent attorney for review and filing. | 🔄 Draft complete — `relayshield_provisional_patent_overview.md` — take to attorney |
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
| 7 | **Compliance reporting add-on — auditability engine** — Full evidence trail per incident: signal (breach detected) → decision (severity scored, attack vector mapped) → action (remediation steps delivered) → outcome (user confirmation or follow-up triggered). Surfaced as GDPR/HIPAA/CCPA-ready incident report document. Pricing: +$29.99/month SMB add-on. Target: healthcare, legal, finance SMBs with regulatory notification obligations. Foundation data already exists in CloudWatch + DynamoDB — build is primarily a report generation and delivery layer. | 🔮 Phase 2 |
| 8 | **Seat expansion upsell** — Auto-prompt to upgrade tier when seat limit reached | 🔮 Phase 2 |
| 9 | **Dedicated SMB Carrd page** — /business sub-page when SMB revenue justifies it | 🔮 Phase 2 |
| 10 | **Business Basic+ differentiation** — Develop additional capabilities exclusive to Business Basic and higher to drive upsell from Business Starter. Candidates: priority incident response SLA, aggregate team risk dashboard, organisational OAuth audit, Google Workspace / M365 monitoring, compliance reporting add-on | 🔮 Phase 2 |
| 11 | **Smishing — predictive campaign monitoring (Flare API)** — Extends Flare add-on: monitor Telegram channels for smishing target lists containing monitored phone numbers. Fire CRITICAL alert before campaign reaches user. BB add-on, BS add-on, BS Pro bundled. No additional API cost — same Flare subscription. | 🔮 Phase 2 |
| 12 | **Smishing — team propagation alert** — When one employee number appears in Telegram smishing list, alert team admin. Business Basic and higher. | 🔮 Phase 2 |
| 13 | **Smishing — SIM swap correlation alert** — When SIM swap detected, check if suspicious SMS analysis submitted in prior 48–72 hrs. If yes, escalate to CRITICAL coordinated attack chain alert. Business Shield and Pro only. | 🔮 Phase 2 |
| 14 | **SIM/IMEI anomaly detection via carrier APIs** — Phase 3 research item. Extends Phase 2 SIM swap monitor to detect anomalous carrier traffic patterns (unexpected APN routing, traffic volume spikes, AT command abuse on IoT cellular devices). Targets Business Shield and Pro tiers with IoT-connected operations. Leverages 25-year telecom expertise as moat — no competitor has attempted this. | 🔮 Phase 3 |
| 15 | **Family Shield / Senior Medicare protection** — Two prerequisites: (1) vishing engine built out with Medicare-specific guidance (CMS never calls unsolicited, free equipment = fraud, never give MBI over phone); (2) SMS delivery channel live. Then: Family Shield positioning on landing page targeting adult children buying for senior parents. Medicare number breach escalation to CRITICAL. Medicare-specific CALL and WASCAM response variants. See strategy doc Section 3b. | 🔮 Phase 2 — after vishing engine + SMS channel |
| 16 | **OAuth supply chain attack detection — SaaS breach watchlist** — Poll HIBP `/api/v3/breaches` daily for new breaches. Cross-reference against internal watchlist of high-risk OAuth-capable apps (Slack, Notion, GitHub, Zapier, Linear, Vercel, Loom, HubSpot, AI tools). When watched app newly indexed, fire WhatsApp alert to affected users. Triggered by Vercel/Context.ai breach April 2026 — attacker stole OAuth tokens from breached SaaS, pivoted into Google Workspace without ever touching user credentials. See strategy doc Phase 2 OAuth Supply Chain section. | ✅ Live April 2026 |
| 17 | **OAuth grant inventory at onboarding** — During SWEEP, prompt user to run one-time OAuth audit at myaccount.google.com/permissions and self-report connected apps. Store in DynamoDB user record. Cross-reference against breach watchlist when SaaS app is compromised. Foundation for supply chain breach alerts. | 🔮 Phase 2 |
| 18 | **Proactive monthly OAuth audit reminder** — EventBridge monthly trigger for Business Basic+ subscribers. WhatsApp message: "Monthly security check — review your connected apps at myaccount.google.com/permissions. Reply OAUTH for a guided walkthrough." Differentiates business tiers from Personal Shield reactive-only model. Template `relayshield_oauth_reminder` approved Meta April 27 2026. SID `HXddda44b6746ae34ecf184a6ada284cc7` wired. Lambda `relayshield-monthly-oauth-reminder` deployed. EventBridge schedule `relayshield-monthly-oauth-reminder` created `rate(30 days)`. | ✅ Complete — April 2026 |
| 19 | **Claude system prompt — SaaS/productivity tool breach detection** — ✅ Implemented April 2026. When breach source matches SaaS/productivity/developer/AI tool profile, Claude appends OAuth revocation guidance: myaccount.google.com/permissions + myapps.microsoft.com. Directly addresses supply chain OAuth attack vector. | ✅ Complete |
| 21 | **Agentic Identity Protection — agent credential monitoring** — Phase 3. Extend HIBP breach monitoring to cover API keys, OAuth tokens, and service account credentials used by AI tools and automated systems on behalf of users. Alert human principal when agent credentials appear in breach data. Same engine as human credential monitoring — new credential type inputs. Foundation: Phase 2 OAuth supply chain watchlist. Informed by a16z agentic economy research April 2026. See strategy doc Phase 3 Agentic Identity Protection Engine. | 🔮 Phase 3 |
| 22 | **Agentic Identity Protection — principal-agent breach alert** — Phase 3. When a deployed AI agent/tool is itself breached (Context.ai at scale), fire targeted WhatsApp alert to human principal with specific credential revocation steps. Extends Phase 2 supply chain breach alerts to cover autonomous agents, not just SaaS tools. | 🔮 Phase 3 |
| 23 | **Agentic Identity Protection — agentic OAuth scope auditing** — Phase 3. Periodic audit of OAuth scopes granted to AI agents. Flag over-scoped agents. WhatsApp alert with tightening guidance. Business Basic+. Extends Phase 2 monthly OAuth audit to cover agent grants specifically. | 🔮 Phase 3 |
| 24 | **Agentic Identity Protection — service account credential monitoring** — Phase 3. SMBs run automated systems (bots, scheduled jobs, integrations) holding long-lived API keys. Monitor these service credentials for exposure in breach data. Targets the non-human identity attack surface. Business Shield+. | 🔮 Phase 3 |
| 20 | **RSS feed polling for SaaS breach intelligence** — Implement alongside Phase 2 OAuth audit engine. Lambda polls RSS feeds from BleepingComputer, Krebs on Security, and The Hacker News on a daily EventBridge schedule. Parser extracts breach announcements and cross-references against internal SaaS OAuth app watchlist. When a match is found, fires WhatsApp alert to affected users to revoke OAuth grant immediately. Supplements HIBP Breaches API polling — catches breaches before HIBP indexes them. Feeds: bleepingcomputer.com/feed, krebsonsecurity.com/feed, feeds.feedburner.com/TheHackersNews | 🔮 Phase 2 — build alongside OAuth supply chain watchlist (TODO item 16) |
| 26 | **Telegram native Stripe payments** — Telegram Payments 2.0 API supports Stripe natively in-bot. When Phase 2 Telegram channel ships, build payment flow so users can subscribe (plan selection → Stripe invoice message → Apple/Google Pay or card) entirely within Telegram without visiting relayshield.net. Same Stripe webhook backend fires on payment — zero backend changes needed. No Telegram commission — standard Stripe fees only. Eliminates landing page redirect for Telegram-acquired users. Build alongside core bot registration. Reference: core.telegram.org/bots/features#payments | 🔮 Phase 2 — build alongside Telegram bot |
| 27 | **Crypto vertical — wallet address monitoring (Telegram MVP)** — New Phase 2 feature targeting crypto users via Telegram channel. Two-layer architecture: (1) **Alchemy Notify** (free tier, 100M compute units/month) — webhook fires on any transaction to/from monitored wallet address, Lambda receives and processes; (2) **GoPlus Security API** (free) — checks counterparty address against known phishing, scam, rug pull, and sanctions databases. Flow: user registers wallet via Telegram bot → Alchemy monitors activity → Lambda fires on transaction → GoPlus checks counterparty → Telegram alert if suspicious. **MVP chains:** Ethereum + Bitcoin only. Polygon/Solana in Phase 3. **Go-to-market:** crypto security consultants as channel partners (friend/consultant lead flagged May 2026); Telegram is the natural channel — crypto communities live there. RelayShield already covers top 3 crypto attack vectors (SIM swap, phishing URLs, domain lookalikes) — wallet monitoring completes the picture. | 🔮 Phase 2 — build alongside Telegram bot |
| 25 | **Telegram — Phase 2 second delivery channel + Agentic Breach Response Engine** — Signal evaluated and ruled out April 2026 (no official bot API). Telegram is the Phase 2 choice: official Bot API with webhook support, free, 950M+ users. **Pricing:** No extra charge. All tiers get WhatsApp OR Telegram. Business Basic+ gets dual delivery simultaneously — channel redundancy against account takeover. **New customer onboarding (Telegram-first):** Telegram Payments 2.0 + Stripe — full signup without leaving Telegram. Phone number collected via `request_contact` button (Telegram does not expose phone to bots automatically) — user taps Share, Lambda receives, confirms number, KMS encrypts, stores. Email addresses collected explicitly during onboarding (ask per tier limit). Confirm phone number before storing — user's Telegram-registered number may differ from the SIM they want monitored. **WA→Telegram linking:** User sends TELEGRAM via WhatsApp → Lambda generates 6-digit code (10 min expiry, single-use) → user opens bot, enters code → Lambda links telegram_chat_id to existing record → confirms on both channels. **New DynamoDB fields:** `telegram_chat_id`, `preferred_channel`, `delivery_channels` (list), `deep_link_token`, `deep_link_expires_at`, `telegram_link_code`, `telegram_link_expiry`. **Agentic workflows (confirmation-gated via inline keyboard buttons, prerequisite: OAuth token storage):** (1) OAuth token revocation; (2) Active session revocation; (3) Email forwarding rule audit and removal — killer feature, no competitor automates this; (4) Inbox filter audit and removal; (5) Recovery contact verification; (6) Active device session audit; (7) Microsoft Graph equivalent. **Build sequence:** (1) @BotFather registration + bot token to Secrets Manager; (2) `relayshield_telegram_webhook` Lambda + API Gateway endpoint; (3) Register webhook URL with Telegram API; (4) New customer onboarding flow (payments → phone → email); (5) WA→Telegram linking flow; (6) Port all WhatsApp commands to Telegram handler; (7) Agentic workflows (OAuth prerequisite). See Strategy doc Section 9 for full architecture. | 🔮 Phase 2 |

---

## ✅ Recently Completed

- ✅ RelayShield LLC approved — Massachusetts, April 2026
- ✅ EIN obtained
- ✅ Operating agreement signed
- ✅ Relay Financial business bank account opened and connected to Stripe
- ✅ Terms of Service published and linked on landing page
- ✅ ToS acceptance notice added above payment buttons on Carrd
- ✅ Domain monitor fully live — Lambda deployed, EventBridge daily schedule, all 3 Meta templates approved and wired, force-test confirmed April 27 2026
- ✅ Monthly OAuth audit reminder — Lambda deployed, EventBridge live, Meta template approved April 27 2026
- ✅ Cross-account password risk detection (REUSE) — YES/NO tracking, personalised completion summary, flagged services listed, state auto-reset, REUSE added to all breach alert CTAs — breach monitor zip deployed April 2026
- ✅ Personal verification protocol (VERIFY command) — four rules: callback, OTP, family safe word, wire transfer. HELP menu updated, onboarding completion message updated. Deployed April 2026
- ✅ Business Starter + Domain Monitoring tier — code deployed, Stripe payment links live ($24.99/mo, $269.99/yr), Carrd pricing table and payment buttons updated April 2026
- ✅ Facebook Business verification resubmitted — corrected to RelayShield LLC, relayshield.net domain verified, EIN + MA filing docs uploaded. Under review April 28 2026 (2-day turnaround)
- ✅ Business Starter tier created — Stripe monthly + annual payment links live
- ✅ Pricing table added to Carrd landing page
- ✅ Business Starter button added to Carrd SELECT A PLAN section
- ✅ Per-seat pricing rationale updated in strategy doc
- ✅ All 4 CloudWatch alarms operational in correct AWS account
- ✅ Session hijacking Ph1 — SESSIONS command, AiTM alerts, two-message architecture
- ✅ Facebook Business verification submitted
- ✅ Salon owner (Rebecca) beta account created in DynamoDB
