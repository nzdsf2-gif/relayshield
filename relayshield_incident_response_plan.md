# RelayShield — Incident Response Plan

**Version:** 1.1 DRAFT (v1.0 adopted May 2026; v1.1 takes effect when the owner adopts it)  
**Effective Date:** May 2026 (v1.0)  
**Owner:** Andrew Gibbs, Founder — RelayShield LLC  
**Review Cycle:** Annually or after any declared incident  
**Changes in v1.1 (2026-11-24):** named backup contact and legal counsel (section 3); playbooks (section 7); forensics plan and evidence tool (section 8); responder access and annual simulation (section 9). CONFIRM items are marked.  

---

## 1. Purpose and Scope

This Incident Response Plan (IRP) defines the procedures RelayShield LLC follows to detect, contain, eradicate, and recover from security incidents affecting its SaaS identity protection platform. It covers all RelayShield infrastructure (AWS Lambda, DynamoDB, API Gateway, Twilio, Stripe), customer data, and third-party integrations.

RelayShield is a SaaS platform. It does not have remote access to customer networks, does not install agents on customer systems, and does not hold privileged credentials to customer infrastructure. The customer data RelayShield holds is limited to encrypted phone numbers, encrypted email addresses, and breach alert history.

---

## 2. Incident Severity Classification

| Severity | Definition | Target Response Time | Target Resolution |
|---|---|---|---|
| **P1 — Critical** | Customer PII exposed; production service down; active unauthorized access to AWS environment; payment data compromise | 1 hour | 4 hours |
| **P2 — High** | Suspected unauthorized access; API key compromise; Twilio or Stripe account anomaly; single Lambda function unavailable | 4 hours | 24 hours |
| **P3 — Medium** | Anomalous CloudWatch alert; failed authentication spike; dependency vulnerability (CVE) with no confirmed exploit | 24 hours | 72 hours |
| **P4 — Low** | Policy violation with no data impact; non-critical misconfiguration detected; routine security finding | 72 hours | 2 weeks |

---

## 3. Incident Response Team

RelayShield operates as a sole-founder company. All incident response responsibilities are held by:

**Incident Commander:** Andrew Gibbs  
**Contact:** relayshieldadmin@gmail.com  
**Backup notification channel:** AWS CloudWatch alarms → relayshieldadmin@gmail.com  

**Backup contact:** a trusted person named in the private contact sheet (kept outside this repository; see below). Their role is to reach the Incident Commander if he cannot be reached by the normal channel, and to act as scribe in exercises. They have **no AWS access and no authority to change production**.  
**Legal counsel and breach-notification contact:** a licensed attorney admitted in Massachusetts, named in the private contact sheet. Called before any regulatory notification and whenever customer data may be exposed. Counsel's written acceptance of this role is kept with the contact sheet. This replaces the line below that said counsel was to be identified before the first paying customer.  
**Private contact sheet:** names, phone numbers and email addresses for the two roles above are kept in the Incident Commander's private documents, not in this public repository, and are reviewed at each annual review. CONFIRM: the sheet exists and both people hold a copy.  

Third-party escalation contacts:
- **AWS Support:** console.aws.amazon.com/support (activate Business Support if P1)
- **Twilio Security:** security@twilio.com
- **Stripe Security:** security@stripe.com
- **HIBP (Troy Hunt):** via haveibeenpwned.com/API
- **Legal / breach notification:** the attorney named in the private contact sheet, see above

---

## 4. Detection Sources

| Source | What It Detects |
|---|---|
| AWS CloudWatch Alarms | Lambda errors, DynamoDB throttling, API Gateway 5xx spikes, unusual invocation counts |
| AWS CloudTrail | All AWS API calls — unauthorized IAM actions, unusual resource access, privilege escalation attempts |
| AWS Config | Configuration changes to Lambda, DynamoDB, IAM, API Gateway |
| GitHub Actions CI | SAST findings (Bandit), CVE alerts (Safety), secret leakage (Gitleaks) on every push |
| Twilio Console | Webhook delivery failures, unusual message volume, account access alerts |
| Stripe Dashboard | Webhook signature failures, unusual payment events, dispute spikes |
| RapidAPI Dashboard | API usage anomalies, quota abuse, unusual endpoint access patterns |

---

## 5. Incident Response Procedures

### 5.1 Detection and Initial Assessment

1. Receive alert (CloudWatch, email, third-party notification, or self-discovery)
2. Log the incident: date/time, detection source, initial description
3. Assign severity (P1–P4) using Section 2 criteria
4. For P1/P2: begin containment immediately — do not wait for full assessment

### 5.2 Containment

**AWS environment compromise (any severity):**
- Rotate or disable the suspected compromised IAM access key immediately in IAM console
- Review CloudTrail for all actions taken by the compromised identity in the preceding 72 hours
- If Lambda function suspected: publish a new version rolled back to last known-good code
- If DynamoDB suspected: review Access Analyzer findings and restrict table policy

**API key compromise (B2A customer key):**
- Disable the affected API Gateway usage plan key immediately
- Review API Gateway access logs for scope of abuse
- Notify affected customer via email within 24 hours
- Issue new key and update customer

**Twilio account anomaly:**
- Log in to Twilio console → review messaging logs for unauthorized sends
- Rotate Twilio Auth Token in Secrets Manager
- Notify Twilio security if unauthorized access is confirmed

**Stripe webhook compromise:**
- Rotate Stripe webhook signing secret
- Review Stripe dashboard for unauthorized payment events
- If payment data exposure is suspected, notify Stripe security immediately

**Supply chain / dependency compromise (e.g. malicious PyPI package):**
- Identify affected package and version window
- Assume all environment variables and secrets in the Lambda execution environment during the window are compromised
- Rotate: Anthropic API key, HIBP API key, Twilio credentials, VirusTotal API key, Google Safe Browsing key, Stripe secret key — all via Secrets Manager
- Redeploy all Lambda functions from known-clean source
- Review CloudTrail for any anomalous outbound API calls during the window

### 5.3 Eradication

1. Identify and eliminate the root cause (patch, rotate credential, remove malicious code)
2. Verify no persistence mechanisms remain (unauthorized IAM users, Lambda layers, EventBridge rules)
3. Re-run GitHub Actions security audit pipeline against all Lambda source files
4. Confirm Bandit, Safety, and Gitleaks return clean results before redeployment

### 5.4 Recovery

1. Redeploy affected Lambda functions via GitHub Actions OIDC pipeline
2. Restore DynamoDB data from point-in-time recovery if data integrity is in question
3. Confirm all CloudWatch alarms return to normal state
4. Run end-to-end smoke test: inbound WhatsApp message → webhook → DynamoDB → response
5. Confirm API Gateway endpoints returning 200 on health checks

### 5.5 Post-Incident Review

Within 5 business days of P1/P2 resolution:
1. Document: timeline, root cause, impact scope, containment actions, recovery steps
2. Identify control gaps that allowed the incident to occur
3. Update this IRP if procedures were found to be insufficient
4. Update TODO.md with any remediation items

---

## 6. Customer Notification Procedures

### When notification is required
- Confirmed exposure of encrypted customer PII (phone numbers, email addresses) — notify within 72 hours of confirmation
- Confirmed unauthorized access to breach alert history — notify within 72 hours
- Service outage exceeding 4 hours — notify via WhatsApp to all active subscribers

### Notification content (data breach)
1. What happened and when
2. What data was involved (note: phone and email are field-encrypted with AWS KMS — exposed data is ciphertext without the KMS key)
3. What RelayShield has done to contain the incident
4. What customers should do (if any action required)
5. Contact for questions: relayshieldadmin@gmail.com

### Regulatory notification
- Massachusetts data breach law (201 CMR 17.00) requires notification to affected MA residents and the MA Attorney General if unencrypted personal information is accessed
- RelayShield stores all PII with field-level KMS encryption — notification obligations depend on whether the KMS key was also compromised
- Consult retained attorney before filing any regulatory notification

---

## 7. Specific Incident Scenarios

Step-by-step playbooks, with commands, are in `docs/security/incident_playbooks.md` (PB-1 to PB-8). The short scenarios below say what to recognise; the playbooks say what to do. Playbooks are DRAFT until adopted.

### Scenario A — DynamoDB Unauthorized Read
**Indicators:** CloudTrail shows GetItem/Scan calls from unexpected IAM principal or IP  
**Actions:** Disable IAM entity → assess scope via CloudTrail → note all data accessed is KMS-encrypted → rotate data key if key access is also suspected → notify customers if exposure confirmed

### Scenario B — Lambda Function Code Replaced (Supply Chain)
**Indicators:** CloudTrail shows UpdateFunctionCode from unexpected principal; GitHub Actions deployment not triggered; anomalous outbound network calls in Lambda logs  
**Actions:** Immediately disable Lambda function trigger (EventBridge, API Gateway) → roll back to previous version → rotate all secrets → audit CloudTrail for data exfiltration → redeploy from clean source via OIDC pipeline

### Scenario C — API Gateway Key Abuse
**Indicators:** RapidAPI dashboard shows quota exhaustion from single key; unusual endpoint access pattern  
**Actions:** Disable key in API Gateway → review access logs → contact RapidAPI to identify subscriber → notify subscriber of key compromise → issue new key

### Scenario D — Twilio WhatsApp Number Compromise
**Indicators:** Unexpected outbound messages in Twilio logs; customer reports receiving messages not sent by RelayShield  
**Actions:** Disable Twilio webhook URL → rotate Auth Token → contact Twilio security → notify all active subscribers via email that WhatsApp channel is temporarily suspended → restore service after credentials rotated and webhook re-secured

### Scenario E — Stripe Webhook Replay Attack
**Indicators:** Duplicate subscription creation events; unexpected DynamoDB user records; webhook signature verification failures in CloudWatch logs  
**Actions:** Stripe webhook Lambda validates signatures on every call — replay attacks are rejected by signature check. If signature validation code is found to be bypassed: disable Lambda trigger → audit DynamoDB for fraudulent records → restore correct state → re-enable with patched code

---

## 8. Evidence Preservation

The full forensics plan is `docs/security/forensics_plan.md`; evidence is captured with `tools/ir_capture_evidence.py` BEFORE containment. For all P1/P2 incidents:
- Export relevant CloudTrail logs to S3 before any remediation that might overwrite them
- Screenshot CloudWatch metrics showing anomalous period
- Do not delete or rotate compromised IAM keys until after exporting their CloudTrail activity
- Preserve Lambda function versions — do not overwrite until evidence captured

---

## 9. Plan Maintenance

**Responder access.** A read-only role, `relayshield-ir-responder` (MFA required), is created ahead of time by `tools/apply_ir_responder_role.sh` so investigation never waits on someone granting access mid-incident.

**Simulation.** One tabletop exercise per year, and after any change to section 3 or a new playbook. The script and record form are `docs/security/tabletop_exercise_1.md`. Findings are fixed within a week and the commit cited in the record.

| Trigger | Action |
|---|---|
| Annual review (May each year) | Review and update all sections; confirm contact details current |
| After any P1 or P2 incident | Post-incident review within 5 days; update procedures based on findings |
| Significant architecture change | Review affected sections and update |
| New third-party integration added | Add to Detection Sources (Section 4) and relevant Scenarios (Section 7) |

---

*RelayShield LLC — Confidential*  
*This document should be provided to cyber insurance underwriters upon request.*
