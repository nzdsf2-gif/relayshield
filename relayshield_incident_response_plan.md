# RelayShield — Incident Response Plan

**Version:** 1.0  
**Effective Date:** May 2026  
**Owner:** Andrew Gibbs, Founder — RelayShield LLC  
**Review Cycle:** Annually or after any declared incident  

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

Third-party escalation contacts:
- **AWS Support:** console.aws.amazon.com/support (activate Business Support if P1)
- **Twilio Security:** security@twilio.com
- **Stripe Security:** security@stripe.com
- **HIBP (Troy Hunt):** via haveibeenpwned.com/API
- **Legal / breach notification:** retained attorney (to be identified before first paying customer)

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

For all P1/P2 incidents:
- Export relevant CloudTrail logs to S3 before any remediation that might overwrite them
- Screenshot CloudWatch metrics showing anomalous period
- Do not delete or rotate compromised IAM keys until after exporting their CloudTrail activity
- Preserve Lambda function versions — do not overwrite until evidence captured

---

## 9. Plan Maintenance

| Trigger | Action |
|---|---|
| Annual review (May each year) | Review and update all sections; confirm contact details current |
| After any P1 or P2 incident | Post-incident review within 5 days; update procedures based on findings |
| Significant architecture change | Review affected sections and update |
| New third-party integration added | Add to Detection Sources (Section 4) and relevant Scenarios (Section 7) |

---

*RelayShield LLC — Confidential*  
*This document should be provided to cyber insurance underwriters upon request.*
