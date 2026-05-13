# RelayShield — Open Items

*Last updated: May 10 2026*
*Legend: 🚨 Blocking · ⚡ High Priority · 🔄 In Progress · ⬜ Pending · 🔮 Future*

---

## ⚡ Pre-Revenue — Insurance + Meta

| # | Item | Status |
|---|---|---|
| 1 | **Tech E&O + Cyber insurance** — Vouch quote confirmed: **$188.24/month** (Cyber $1M limit $84.02/mo + E&O $1M limit/$5K OOP $107.50/mo; taxes/fees $7.24; 10% partner discount -$20.11). Effective date May 10 2026. **Activate on first paying customer.** Security posture: IRP ✅, FileVault ✅, DynamoDB PITR ✅, Secrets Manager ✅, OIDC ✅, SAST CI ✅. GuardDuty pending AWS billing conversion. **Crypto coverage resolved — no add-on needed:** x402 payments received to Coinbase Exchange address are covered under Coinbase's $320M custodial crime insurance policy. Vouch E&O covers software liability. Gap is closed. | ⬜ Pending — activate at first customer |
| 2 | **Facebook Business verification** — Submitted as RelayShield LLC, relayshield.net domain verified, EIN + MA filing docs uploaded. Under review by Meta as of May 9 2026. | 🔄 Under review — awaiting Meta |

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
| 0d | **Post relayshield-mcp to r/ClaudeAI** — HN Show HN blocked for new accounts (needs karma first). Post same content to r/ClaudeAI today as alternative. Title: "I built an MCP server for real-time identity threat detection (breach, SIM swap, phishing)" — body same as HN draft. Drop RapidAPI link in first comment. | ⬜ Pending — today May 5 |
| 0a | **Publish Show HN post — relayshield-mcp** — Post to news.ycombinator.com. Title: "Show HN: RelayShield MCP – identity threat detection tools for Claude and AI agents." Body covers 6 tools (check_breach, check_sim_swap, check_domain_lookalikes, scan_url, scan_file, check_scan_result), install (`pip install relayshield-mcp`), RapidAPI link for REST, solo founder on AWS Lambda + API Gateway. Schedule: **Tuesday May 5 2026 morning** (peak HN traffic). | ⬜ Pending — tomorrow morning |
| 0b | **AWS Marketplace listing — RelayShield Security Intelligence API** — Register and publish RelayShield B2A REST API on AWS Marketplace. Puts RelayShield in front of enterprise AWS customers. Highest B2A revenue path. Partner Central Identity ✅ + Business ✅ verification complete. Resume at `console.aws.amazon.com/partnercentral/verification/status` once account converts. Enable GuardDuty at the same time. **AWS account converts free → paid in ~60 days (~July 2026).** | ⏸️ On hold — AWS free-to-paid conversion ~July 2026 |
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
| 21 | **Predictive alerts — pre-chain warnings** — `check_and_warn_predictive()` implemented in breach monitor. Appends forward-looking warning when first signal in known chain is recorded (e.g. breach → SIM swap warning within 72 hrs). All 4 chains covered. Deployed May 2026. | ✅ Complete — deployed May 2026 |
| 22 | **WASCAM — browser social engineering block** — `msg_wascam_part3()` added covering fake CAPTCHA SMS charge fraud, fake browser security alerts, and ClickFix paste-and-run attacks. Wired as third message in WASCAM handler. Closing rule: "legitimate services never ask you to send a text, run a command, or call a number to prove you are human." | ✅ Complete — deployed May 2026 |

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
| 6 | **Secrets Manager for OAuth tokens (Phase 2 prerequisite)** — Architecture decided: each OAuth token stored in Secrets Manager under `relayshield/oauth/{user_id}/{provider}`. DynamoDB stores only the ARN reference. Implementation deferred until Phase 2 OAuth token collection begins. | ✅ Architecture decided — implement at Phase 2 OAuth build |

---

## 📣 Marketing — Focus Shifted (May 2026 beta learning)

*Beta confirmed: consumer identity protection faces category resistance — consumers lump new entrants with VPNs/password managers/credit monitoring regardless of differentiation. Primary acquisition investment redirected to SMB B2B, Crypto Shield, and B2A. Consumer Personal Shield served on organic inbound only — no dedicated acquisition spend.*

### ✅ Completed
| # | Item | Status |
|---|---|---|
| 2 | **Tycoon 2FA blog post** — Published to RelayShield LinkedIn April 19 2026 | ✅ Published |
| 6 | **OAuth supply chain LinkedIn post** — "The Vercel Hack Wasn't About a Stolen Password." April 26 2026 | ✅ Published |
| 7 | **Aura LinkedIn article** — "The Identity Protection Industry Has a Structural Flaw." May 1 2026 | ✅ Published |
| 8 | **PyPI supply chain blog** — Posted LinkedIn + r/netsec + r/Python May 2026 | ✅ Published |

### 🏢 SMB Acquisition Channels (primary)
| # | Item | Status |
|---|---|---|
| SMB-1 | **Reddit SMB posts** — r/smallbusiness, r/Entrepreneur, r/freelance, r/msp. Drafts in `reddit_marketing_drafts.md`. Focus on domain hijack and employee breach scenarios, not generic identity protection. | 🔄 Drafts ready — post manually |
| SMB-2 | **Salon owner (Rebecca) conversion** — Send Business Starter payment link when beta ends | ⬜ Pending |
| SMB-3 | **IoT cellular backdoor blog** — r/smallbusiness, r/msp. Establishes telecom authority. No product to build. | ⬜ Pending |
| SMB-4 | **LinkedIn SMB content cadence** — Frame content around employee breach liability, domain lookalike attacks on SMBs, SIM swap as business continuity risk. Avoid generic "identity protection" framing entirely. | ⬜ Pending |
| SMB-5 | **Facebook Business verification** — Monitor Meta approval (submitted April 2026) | 🔄 In progress |

### 🪙 Crypto Shield Acquisition Channels (primary)
| # | Item | Status |
|---|---|---|
| CS-1 | **Activation condition** — 3 of 5 crypto features live ✅ (all 6 now live). Begin crypto channel outreach. | ✅ Activated |
| CS-2 | **X/Twitter thread** — Real wallet drainer caught in real time. TX hash verifiable on-chain. This is the viral hook. | ⬜ Pending — need real incident or staged demo |
| CS-3 | **Telegram DeFi/trading groups** — Organic demo in relevant groups. Focus on drainer detection and SIM swap prevention, not generic "security". | ⬜ Pending |
| CS-4 | **Farcaster post** — Short demo with on-chain proof. Web3-native credibility signal. | ⬜ Pending |
| CS-5 | **Mirror.xyz post** — "How wallet drainers actually work and how to detect them in real time." One post, evergreen. | ⬜ Pending |

### 🔧 B2A / Developer Channels (primary)
| # | Item | Status |
|---|---|---|
| BA-1 | **Show HN post** — relayshield-mcp. Pending karma threshold or post to r/ClaudeAI as alternative. | ⬜ Pending |
| BA-2 | **MCP registries** — mcp.so (submitted, in review), glama.ai, mcphub.net, Anthropic directory. Post after x402 confirmed end-to-end. | ⬜ Pending — see MCP sprint items |

### 🔑 Maintenance
| # | Item | Status |
|---|---|---|
| M-1 | **PyPI token rotation** — Rotate `relayshield/pypi_api_token` by **August 2 2026** | ⬜ Due August 2 2026 |

---

## ⚖️ Intellectual Property

| # | Item | Status |
|---|---|---|
| 1 | **Provisional patent — ordered remediation sequence** — Claude to draft provisional patent overview covering the core method: breach detection → session revocation before password reset → ordered 5-layer sweep → follow-up until confirmed. Take to patent attorney for review and filing. | 🔄 Draft complete — `relayshield_provisional_patent_overview.md` — take to attorney |
| 2 | **Consult patent attorney** — Seek attorney specialising in software/fintech patents. Present provisional overview. Evaluate cost/benefit of full utility patent vs. provisional only. Budget: $1,500–$3,000 for provisional filing. | ⬜ Pending |
| 3 | **Attack chain correlation engine** — Secondary patent candidate: method of mapping specific breach data classes to downstream attack vectors and triggering corresponding remediation paths. Include in attorney consultation. | ⬜ Pending |

---

## ⚡ Next Sprint — Telegram Feature Completion + Account Delegation

*Added May 8 2026*

| # | Item | Notes |
|---|---|---|
| TG-1 | **Monthly digest — add Telegram delivery path** — `relayshield-digest-sender` Lambda currently WA-only. Add Telegram `send_message()` branch: if `delivery_channels` includes `telegram` and `telegram_chat_id` set, send digest via Bot API. No new template needed — Telegram is freeform. | Deferred from May 2026 session |
| TG-2 | **Day 3 sender — add Telegram delivery path** — `relayshield-day3-sender` Lambda WA-only. Same pattern as TG-1. Fix IAM PassRole permission on Stripe Lambda at same time (currently blocking Day 3 scheduler). | IAM PassRole bug — fix together |
| TG-3 | **Quarterly sweep sender — add Telegram delivery path** — `relayshield-quarterly-sweep-sender` currently WA-only. Same delivery branch pattern. | Deferred from May 2026 session |
| DEL-1 | **Account delegation — WhatsApp** — `DELEGATE +1XXXXXXXXXX` grants deputy admin access (addmember, removemember, status). `REVOKE` removes it. Stored as `delegated_admin_ids: [user_id]` on admin DynamoDB record. Delegate auth check added to ADD/REMOVE/STATUS handlers (check caller in admin's `delegated_admin_ids` OR caller is `team_id`). `REVOKE` clears the list. | ⬜ Pending — build for Business Basic+ |
| DEL-2 | **Account delegation — Telegram** — Mirror of DEL-1. `/delegate @username` and `/revoke` commands for Business tier admins. Telegram handler checks `delegated_admin_ids` same as WA. Build together with DEL-1 as a single Lambda deploy. | ⬜ Pending — build with DEL-1 |
| MSP-1 | **MSP multi-tenancy layer — UUID tenant isolation** — `org_id = uuid.uuid4()` generated at enterprise creation (fully independent of any user's ID). MSP admin: `is_msp_admin: True`, `managed_orgs: ["org-uuid-1", ...]`. Enterprise admin: `org_id: "org-uuid-1"`, `is_team_admin: True`, `parent_msp_id: msp_user_id`. Employee: `org_id: "org-uuid-1"`, `team_id: ent_admin_user_id`. All DynamoDB team queries filter BOTH `org_id` AND `team_id` (belt-and-suspenders isolation). MSP admin cannot see data across enterprise boundaries. New commands: `/addenterprise` (MSP only — creates org UUID, issues enterprise-admin invite), `/enterprises` (MSP only — lists orgs + seat count), `/removeenterprise` (cascades deactivation to all org members). WA equivalents: `ADDENTERPRISE`, `ENTERPRISES`. All alerts DM-only — no shared group channels. **Trigger: first real MSP / Business Shield Pro prospect.** | ⬜ Pending — trigger-based |
| TEST-1 | **Verify Android SWEEP instructions on real device** — Android Chrome (`⋮` top-right → Request Desktop Site) and Android Firefox (`⋮` → Request Desktop Site). iOS instructions live-tested May 8 2026. | Needs Android device |

---

## ⚡ MCP Discovery + x402 Integration Sprint

*Added May 10 2026*

**Payment architecture decision (Option C):** x402 per-call for developer/agent PAYG (crypto, zero collection risk). Stripe subscription for B2A committed customers (existing RapidAPI tiers). Stripe Metered Billing backburnered — not removed; revisit as reduced-friction MSP onboarding path when first MSP prospect arrives. No per-transaction card charges at sub-$1 prices under any circumstances.

**scan-url / scan-file on x402:** Same "coming soon" treatment as RapidAPI. VT commercial licensing constraint applies regardless of payment rail. Wire a "coming soon" response on both tools. Trigger to activate: 5+ customers OR 2,000+ scans/month — contact VT at that point.

| # | Item | Status |
|---|---|---|
| MCP-1 | **mcp.so listing — awaiting manual review** — Submitted May 6 2026, status "created." No further action available — mcp.so uses a manual review queue before publishing. If still unpublished after 2 weeks, contact mcp.so support to ask about review status. | ⏸️ Waiting — mcp.so review queue |
| MCP-2 | **Use Coinbase Exchange deposit address for x402 payments** — Use existing CB Pro/Advanced Trade USDC deposit address as x402 receiving address. Funds received are immediately custodied under Coinbase's $320M crime insurance — no separate crypto coverage needed. No sweep discipline required; funds are covered on receipt. Hardcode this address into x402 payment instructions. No code — retrieve address from CB account. 5 minutes. | ⬜ Pending — before MCP-3 |
| MCP-3 | **x402 pass-through in `relayshield_mcp_server.py`** — ✅ Code complete May 10 2026. Architecture: x402 verification lives at API Gateway Lambda (MCP-4), not the MCP server (stdio transport — no HTTP layer to intercept). MCP server changes: (1) `RELAYSHIELD_API_KEY` no longer required — API URL only mandatory; (2) `RELAYSHIELD_X_PAYMENT` env var passes x402 payment proof header to API Gateway; (3) 402 responses returned as structured JSON with price, network, payment_requirements header, and instructions; (4) `scan_url`/`scan_file` return "coming soon" for PAYG callers; (5) `check_oauth_watchlist` tool added (calls `/v1/oauth-watchlist`); (6) PAYG success responses include conversion advisory. **Remaining:** MCP-4 (x402 verification at API Gateway Lambda) must be built before PAYG calls actually work end-to-end. | ✅ MCP server code done — needs MCP-4 to go live |
| MCP-4 | **x402 on `relayshield-api` Lambda + API Gateway PAYG routes** — ✅ Lambda code complete May 10 2026. New PAYG endpoints: `/v1/payg/breach` ($0.10), `/v1/payg/sim-swap` ($0.25), `/v1/payg/domain` ($0.50), `/v1/payg/oauth-watchlist` ($0.15), `/v1/payg/result/{id}` (free). `handle_oauth_watchlist` added (HIBP × OAuth watchlist cross-reference). x402 verification calls `https://x402.org/facilitator/verify` — no SDK dependency. **Deployment steps (AWS Console — must be done before PAYG goes live):** (1) Set Lambda env var `RELAYSHIELD_X402_WALLET` = CB Exchange USDC deposit address. (2) In API Gateway: create resource `/v1/payg`, then child resources `breach`, `sim-swap`, `domain`, `oauth-watchlist`, `result/{analysis_id}`. (3) Add POST method to each (GET for result) — integration type Lambda proxy → `relayshield-api`, auth = NONE (no API key). (4) Enable CORS on PAYG resources. (5) Deploy to `prod` stage. (6) Test: call `/v1/payg/breach` with no X-PAYMENT → confirm 402 + PAYMENT-REQUIRED header returned. | ✅ Code done — deployment steps pending |
| MCP-5 | **Publish updated `relayshield-mcp` to PyPI** — Bump version. Update README to document x402 PAYG (no-account instructions, wallet address, supported networks = Base/USDC). README is the ad on PyPI. ~30 min. | ⬜ Pending — after MCP-3 |
| MCP-6 | **Submit to glama.ai** — After x402 live. Lead description with "pay-per-call, no account required, USDC on Base." | ⬜ Pending — after MCP-5 |
| MCP-7 | **Submit to mcphub.net** — Same as MCP-6, same timing. | ⬜ Pending — after MCP-5 |
| MCP-8 | **Submit to Anthropic MCP directory** — Highest-value listing (Claude users are primary MCP audience). Check submission process at modelcontextprotocol.io. Submit after x402 confirmed end-to-end. | ⬜ Pending — after MCP-5 |
| MCP-9 | **Conversion prompt in API responses** — After check #10 from a PAYG x402 caller, append to response: `"advisory": "You've run 10 pay-as-you-go checks. The Growth plan ($29/month) includes 5,000 checks — 96% lower per-check cost. rapidapi.com/relayshield"`. Lightweight Lambda change. | ⬜ Pending — after MCP-4 |
| MCP-10 | **Multi-agent orchestration listings (secondary)** — Submit RelayShield as a tool/agent to CrewAI tool registry, LangChain tool hub, and AutoGen community tools. These frameworks index available tools for coordinator agents to recommend. Lower priority than MCP registries — do after MCP-6/7/8. | ⬜ Backburner — after primary registries |
| MCP-11 | **Stripe Metered Billing (backburnered)** — Not removed. Revisit as reduced-friction onboarding path for MSPs who want fiat PAYG without committing to a RapidAPI subscription tier. Potential trigger: first MSP prospect asks for it. Architecture: $0/month base plan, usage events reported per check, $25 billing threshold to cap exposure window. | ⏸️ Backburnered — trigger: first MSP PAYG request |

---

## 🪙 Crypto Shield — Vertical Build + Verification

*Added May 10 2026. No serious red flags identified from any third party. Build sequence: verify items first → CRYPTO-1 → CRYPTO-2 → integrate with MCP-3 (x402 shared payment rail).*

**Pricing:** $19.99/month · $199.99/year (~$16.67/month, 17% off)
**Payment rail:** Coinbase Commerce (recurring USDC subscriptions) → CB Exchange (covered under CB $320M custodial crime insurance). Completely separate from Stripe fiat rail. No Vouch crypto endorsement needed.
**x402 funnel:** PAYG checks at $0.20–$0.50 USDC → conversion prompt at check #8 → Crypto Shield subscription.

**Services included in Crypto Shield:**
- Real-time wallet monitoring — Alchemy Notify webhooks (ETH + BTC MVP; Polygon/Solana Phase 3)
- Counterparty screening — GoPlus Security API on every transaction counterparty (phishing/scam/rug pull/sanctions)
- Exchange breach alerts — HIBP alert when a crypto exchange appears in breach data
- SIM swap monitoring (every 4 hours) — most crypto thefts start here
- Credential breach monitoring (2 email addresses — exchange login credentials)
- Domain lookalike scanning — fake exchange/DeFi phishing sites
- OAuth watchlist monitoring — connected apps that can access exchange accounts
- Full attack chain correlation + predictive alerts
- Telegram delivery (primary)

**Alchemy webhook constraint:** Free tier = 5 webhooks (5 wallets max — internal testing only). Pay as You Go = 100 webhooks, 300M CU/month included, ~$0/month at MVP CU levels. Contact Alchemy sales at ~30 Crypto Shield subscribers (99 wallets) before hitting 100-webhook ceiling. At $19.99/subscriber, 30 subs = $600 MRR — reasonable trigger for that conversation.

**Unit economics (per $19.99/month subscriber):**

| Payment rail | Fee | Net | Notes |
|---|---|---|---|
| Coinbase Business (USDC/Base) | $0.20 (1%) | **$19.79** | Confirmed May 2026 — 1% applies to USDC on Base |
| Stripe equivalent (for comparison) | $0.88 (2.9% + $0.30) | $19.11 | Still better on CB rail by $0.68/subscriber/month |

**Annual subscriber net:** $199.99 − $2.00 (1%) = **$197.99/year**

| # | Item | Status |
|---|---|---|
| VERIFY-1 | **CB Commerce / Coinbase Business fee — confirmed May 2026** — 1% on all USDC transactions including Base network. No 0% promotional rate active. Coinbase is migrating Commerce into **Coinbase Business** — migration docs reference "1% for migrating merchants." Set up new account under Coinbase Business (not legacy Commerce) to be on the current platform from day one. Net per Crypto Shield subscriber: $19.79/month, $197.99/year. | ✅ Confirmed — May 2026 |
| VERIFY-2 | **Confirm GoPlus commercial use ToS** — Email support@gopluslabs.io: *"We use your address_security API to power counterparty screening within our SaaS product — results are consumed by our service, not re-exposed as a raw data feed. Is this permitted on the free tier?"* No serious red flags expected based on current review; this is a formal confirmation before launch. | ⬜ Pending — email GoPlus |
| VERIFY-3 | **Confirm Alchemy Pay as You Go base cost** — Verify alchemy.com/pricing: confirm Pay as You Go has no monthly base fee (pay only for CU overages beyond 300M/month). If correct, upgrade from free tier (5 webhooks) to Pay as You Go (100 webhooks) as soon as first Crypto Shield subscriber onboards. | ⬜ Pending — manual |
| CRYPTO-1 | **Coinbase Business setup — Crypto Shield subscription products** — Create account under **Coinbase Business** (not legacy Commerce — migration in progress as of May 2026). Configure two charge products: Crypto Shield Monthly ($19.99 USDC) and Crypto Shield Annual ($199.99 USDC). Wire Coinbase Business payment webhook to new `relayshield-coinbase-webhook` Lambda. Lambda mirrors `relayshield-stripe-webhook` architecture: verify webhook signature → create/update DynamoDB subscriber record with `tier=crypto_shield`, `delivery_channels=[telegram]` → trigger Telegram onboarding flow. 1% fee deducted at settlement — net $19.79/month, $197.99/year. ~3–4 hrs. | ⬜ Pending |
| CRYPTO-2 | **x402 wallet check PAYG + conversion funnel** — Wire x402 pricing for wallet checks: wallet address scan $0.35 USDC, counterparty check $0.20 USDC. At check #8, append conversion prompt to response: *"You've run 8 pay-as-you-go checks. Crypto Shield ($19.99/month) includes continuous monitoring of 3 wallets, SIM swap protection, and breach alerts — less than 8 one-off scans."* Requires MCP-3 complete. Add `/addwallet 0x...` command to Telegram webhook. Alchemy Notify webhook registered per new wallet. GoPlus called on every inbound counterparty. ~4–6 hrs. | ⬜ Pending — after MCP-3 + CRYPTO-1 |

---

## 🧠 Crypto Shield — Risk Intelligence (build before lifecycle messages)

*Added May 2026. Competitive strategy: Webacy and De.fi are web dashboards users rarely visit. RelayShield's superpower is messaging-first push delivery. Portfolio tracking belongs on a web UI — not in a bot. Risk intelligence (on-demand scores + passive flags) is the right direction: point-in-time answers to specific questions, natively in Telegram, requiring no visual interface. Build this layer first — Day 3, monthly digest, and quarterly sweep are intentionally deferred until risk intelligence exists so they ship enriched, not retrofitted. See Strategy doc Section 21 for full competitive rationale.*

**GoPlus APIs used:** Token Security, NFT Security, dApp/contract security (all free tier)

| # | Item | Status |
|---|---|---|
| RISK-1 | **`/checktoken 0x...` — on-demand token risk** — Call GoPlus Token Security API (`/api/v1/token_security/1?contract_addresses={addr}`). Parse key flags: `is_honeypot`, `is_mintable` (unlimited supply risk), `buy_tax` / `sell_tax` (>10% suspicious, >50% critical), `cannot_sell_all` (honeypot variant), `is_blacklisted`, `is_open_source`, `is_proxy`, `owner_change_balance`. Format as Telegram message: overall risk level (Low/Medium/High/Critical) + bulleted flags + "do not interact" warning if critical. Register `/checktoken` in Telegram webhook command dispatcher and `/help` menu. Crypto Shield tier-gated + PAYG fallback. ~2–3 hrs. | ⬜ Pending — next build |
| RISK-2 | **`/checknft 0x...` — on-demand NFT collection risk** — Call GoPlus NFT Security API (`/api/v1/nft_security/1?contract_addresses={addr}`). Parse flags: `is_transferable` (soulbound/non-transferable), `malicious_contract`, `nft_proxy`, `privileged_burn` (owner can destroy holdings), `stolen_nft` (known stolen), `fake_token` (counterfeit collection). Same Low/Medium/High/Critical format. Register `/checknft` in dispatcher + help. Crypto Shield tier-gated + PAYG fallback. ~2 hrs. | ⬜ Pending — after RISK-1 |
| RISK-3 | **`/riskcheck` — aggregate wallet risk score** — Run three checks in parallel: (1) GoPlus address_security on the monitored wallet itself; (2) count of active unlimited approvals via Alchemy `alchemy_getAssetTransfers` (filter approve() selector); (3) Aave V3 health factor if wallet has a position. Synthesise into a single risk score (1–10) with top 3 findings. Format: score badge (🟢 Low / 🟡 Medium / 🔴 High) + top issues + recommended actions. Register `/riskcheck` in dispatcher + help. Crypto Shield only. ~4 hrs. | ⬜ Pending — after RISK-1/2 |
| RISK-4 | **Passive inbound token risk alerts** — On every inbound transfer detected by Alchemy webhook, call GoPlus Token Security API on the token contract address. If `is_honeypot=1` or `buy_tax>50` or `cannot_sell_all=1`, fire a Telegram alert before the user interacts with the token: "⚠️ High-risk token received — do not sell or approve until reviewed." This is the moat feature: Webacy/De.fi require you to check; RelayShield warns you before you act. ~2–3 hrs. | ⬜ Pending — after RISK-3 |
| RISK-5 | **`/checkvault 0x...` — DeFi protocol/vault risk on demand** — Call GoPlus dApp Security API (`/api/v1/dapp_security?url={contract_or_url}`). Parse flags: `is_audit` (audited?), `audit_info` (auditor names), `is_open_source`, `risky_signature` (dangerous admin functions), `risky_approval` (approval required before use), `unsafe_source` (known malicious). Format as Low/Medium/High/Critical with bulleted findings. Completes the DeFi lifecycle story: `/checkvault` before depositing → liquidation monitor after. Register `/checkvault` in Telegram webhook dispatcher + `/help`. Crypto Shield tier-gated. ~2 hrs. | ⬜ Pending — after RISK-4 |

### Lifecycle messages — deferred until risk intelligence layer complete

| # | Item | Notes |
|---|---|---|
| TG-1 | **Monthly digest — Telegram delivery + risk intelligence enrichment** — Add Telegram delivery branch (no template needed — freeform). Enrich content: wallet risk score delta, new high-risk approvals detected, flagged inbound tokens received. Deferred from May 2026 — build after RISK-1 through RISK-4 so digest ships enriched. | ⬜ Pending — after RISK-4 |
| TG-2 | **Day 3 sender — Telegram delivery + baseline risk snapshot** — Add Telegram delivery branch. Enrich with a one-time wallet risk baseline: run `/riskcheck` equivalent at Day 3 and include results in the onboarding follow-up. Fix IAM PassRole permission on Stripe Lambda at same time. Deferred — build after RISK-3. | ⬜ Pending — after RISK-3 |
| TG-3 | **Quarterly sweep — Telegram delivery + full wallet audit** — Add Telegram delivery branch. Enrich as a full security audit: GoPlus token security on all held tokens, unlimited approval count, Aave health factor, top 3 risks. The "annual security review" framing that justifies the subscription. Deferred — build after RISK-4. | ⬜ Pending — after RISK-4 |

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
| 16 | **OAuth supply chain attack detection — SaaS breach watchlist** — Poll HIBP `/api/v3/breaches` daily for new breaches. Cross-reference against internal watchlist of high-risk OAuth-capable apps (Slack, Notion, GitHub, Zapier, Linear, Vercel, Loom, HubSpot, AI tools). When watched app newly indexed, fire WhatsApp alert to affected users. Triggered by Vercel/Context.ai breach April 2026 — attacker stole OAuth tokens from breached SaaS, pivoted into Google Workspace without ever touching user credentials. Lambda `relayshield-oauth-watchlist-monitor` confirmed operational in AWS console May 9 2026. | ✅ Live — confirmed May 9 2026 |
| 17 | **OAuth grant inventory at onboarding** — During SWEEP, prompt user to run one-time OAuth audit at myaccount.google.com/permissions and self-report connected apps. Store in DynamoDB user record. Cross-reference against breach watchlist when SaaS app is compromised. Foundation for supply chain breach alerts. | 🔮 Phase 2 |
| 18 | **Proactive monthly OAuth audit reminder** — EventBridge monthly trigger for Business Basic+ subscribers. WhatsApp message: "Monthly security check — review your connected apps at myaccount.google.com/permissions. Reply OAUTH for a guided walkthrough." Differentiates business tiers from Personal Shield reactive-only model. Template `relayshield_oauth_reminder` approved Meta April 27 2026. SID `HXddda44b6746ae34ecf184a6ada284cc7` wired. Lambda `relayshield-monthly-oauth-reminder` deployed. EventBridge schedule `relayshield-monthly-oauth-reminder` created `rate(30 days)`. | ✅ Complete — April 2026 |
| 19 | **Claude system prompt — SaaS/productivity tool breach detection** — ✅ Implemented April 2026. When breach source matches SaaS/productivity/developer/AI tool profile, Claude appends OAuth revocation guidance: myaccount.google.com/permissions + myapps.microsoft.com. Directly addresses supply chain OAuth attack vector. | ✅ Complete |
| 21 | **Agentic Identity Protection — agent credential monitoring** — Phase 3. Extend HIBP breach monitoring to cover API keys, OAuth tokens, and service account credentials used by AI tools and automated systems on behalf of users. Alert human principal when agent credentials appear in breach data. Same engine as human credential monitoring — new credential type inputs. Foundation: Phase 2 OAuth supply chain watchlist. Informed by a16z agentic economy research April 2026. See strategy doc Phase 3 Agentic Identity Protection Engine. | 🔮 Phase 3 |
| 22 | **Agentic Identity Protection — principal-agent breach alert** — Phase 3. When a deployed AI agent/tool is itself breached (Context.ai at scale), fire targeted WhatsApp alert to human principal with specific credential revocation steps. Extends Phase 2 supply chain breach alerts to cover autonomous agents, not just SaaS tools. | 🔮 Phase 3 |
| 23 | **Agentic Identity Protection — agentic OAuth scope auditing** — Phase 3. Periodic audit of OAuth scopes granted to AI agents. Flag over-scoped agents. WhatsApp alert with tightening guidance. Business Basic+. Extends Phase 2 monthly OAuth audit to cover agent grants specifically. | 🔮 Phase 3 |
| 24 | **Agentic Identity Protection — service account credential monitoring** — Phase 3. SMBs run automated systems (bots, scheduled jobs, integrations) holding long-lived API keys. Monitor these service credentials for exposure in breach data. Targets the non-human identity attack surface. Business Shield+. | 🔮 Phase 3 |
| 20 | **RSS feed polling for SaaS breach intelligence** — Implement alongside Phase 2 OAuth audit engine. Lambda polls RSS feeds from BleepingComputer, Krebs on Security, and The Hacker News on a daily EventBridge schedule. Parser extracts breach announcements and cross-references against internal SaaS OAuth app watchlist. When a match is found, fires WhatsApp alert to affected users to revoke OAuth grant immediately. Supplements HIBP Breaches API polling — catches breaches before HIBP indexes them. Feeds: bleepingcomputer.com/feed, krebsonsecurity.com/feed, feeds.feedburner.com/TheHackersNews | 🔮 Phase 2 — build alongside OAuth supply chain watchlist (TODO item 16) |
| 26 | **Telegram native Stripe payments** — Telegram Payments 2.0 API supports Stripe natively in-bot. When Phase 2 Telegram channel ships, build payment flow so users can subscribe (plan selection → Stripe invoice message → Apple/Google Pay or card) entirely within Telegram without visiting relayshield.net. Same Stripe webhook backend fires on payment — zero backend changes needed. No Telegram commission — standard Stripe fees only. Eliminates landing page redirect for Telegram-acquired users. Build alongside core bot registration. Reference: core.telegram.org/bots/features#payments | 🔮 Phase 2 — build alongside Telegram bot |
| 27 | **Crypto vertical — wallet address monitoring + onboarding rail (Telegram MVP)** — **Insurance blocker resolved May 10 2026:** x402 payments received to CB Exchange address are covered under Coinbase's $320M custodial crime policy. No Vouch crypto endorsement needed. **Two-layer detection architecture:** (1) **Alchemy Notify** (free tier, 100M compute units/month) — webhook fires on any transaction to/from monitored wallet; (2) **GoPlus Security API** (free) — checks counterparty against phishing/scam/rug pull/sanctions databases. Supplement with **Etherscan API** (free) for address labeling and transaction history. **Crypto onboarding rail:** user subscribes via Telegram → USDC payment to CB Exchange deposit address → registers wallet(s) via `/addwallet 0x...` → Alchemy monitors → Lambda fires on transaction → GoPlus checks counterparty → Telegram alert. Existing SIM swap + breach + domain monitoring runs in parallel — crypto holders are the prime SIM swap target demographic. **MVP chains:** Ethereum + Bitcoin only. Polygon/Solana Phase 3. **Go-to-market:** crypto security consultants as channel partners; Telegram is the natural channel. **Build sequence prerequisite:** x402 integration (MCP-3) complete first — the payment rail is shared. | ⚡ Unparked — build after x402 sprint |
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
