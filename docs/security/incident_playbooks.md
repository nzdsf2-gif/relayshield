# RelayShield Incident Playbooks

| | |
|---|---|
| **Status** | **DRAFT, not adopted.** Written 2026-11-24 by Claude from the repo. **No command here has been run against AWS.** Test each in the tabletop or a quiet hour before an incident needs it |
| **Owner** | Andrew Gibbs, Incident Commander |
| **Part of** | `relayshield_incident_response_plan.md` v1.1, section 7; WAFR SEC 10 "Develop and test security incident response playbooks" |

## How to read this

The commands below are a reference for an incident. They are NOT a block to paste in one go: run one at a time, read the
output, then run the next. Placeholders such as `AKIA...` or `FUNCTION` are values to fill in from the incident. Every AWS
command assumes `AWS_PROFILE=relayshield` and `--no-cli-pager`. Check the account first:

```text
AWS_PROFILE=relayshield aws sts get-caller-identity --query Account --output text
```

It must print 239677749008. If it prints 620534471984 you are in the pre-audit account and nothing below will find anything.

**Every playbook starts the same way.** Step 0 is capture, using `tools/ir_capture_evidence.py` (`docs/security/forensics_plan.md`),
before any containment. Then log the incident (time, source, description) and assign P1 to P4 from section 2 of the plan.

## PB-1. AWS access key exposed or misused (plan scenario A, and 5.2 "AWS environment compromise")

**Triggers:** a researcher or a scanner reports a key; CloudTrail shows calls from an unknown IP; GitHub secret scanning alerts.

1. Capture: `--lookup AccessKeyId=AKIA... --iam-user NAME`.
2. Find the owner of the key:
```text
aws iam get-access-key-last-used --access-key-id AKIA...
```
3. Disable it (do not delete: the id is evidence):
```text
aws iam update-access-key --user-name NAME --access-key-id AKIA... --status Inactive
```
4. If the credential was a role session or you cannot tell, revoke every session the user or role holds by attaching an inline
   deny for anything issued before now. Use the current UTC time:
```text
aws iam put-user-policy --user-name NAME --policy-name incident-revoke-sessions --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Deny","Action":"*","Resource":"*","Condition":{"DateLessThan":{"aws:TokenIssueTime":"2026-01-01T00:00:00Z"}}}]}'
```
   For a role use `put-role-policy --role-name`. Replace the date with now. Remove the policy once new credentials are in use.
5. Look for what the key did: the capture's CloudTrail file. Look specifically for `CreateAccessKey`, `CreateUser`, `AttachUserPolicy`,
   `PutRolePolicy`, `UpdateFunctionCode`, `CreateFunction`, `PutRule`, `PutBucketPolicy`. Any of these is persistence: remove it (PB-2 for code).
6. Rotate whatever the key could read, starting with Secrets Manager secrets and the API keys they hold.
7. Decide notification (section 6 of the plan) from what CloudTrail shows was READ.
8. Close: issue a replacement key if needed, secret-scan the repo, write the post-incident review within 5 business days.

## PB-2. Lambda code replaced or suspect (plan scenario B)

**Triggers:** `lambda_drift_check.yml` opens a `lambda-drift` issue and nobody deployed; CloudTrail shows `UpdateFunctionCode` from a
principal that is not the deploy role; odd outbound calls in logs.

1. Capture: `--function NAME --lookup ResourceName=NAME`.
2. Confirm it is not your own hand deploy: check the `lambda-drift` issue and `git log` on main.
3. Stop the function taking traffic without deleting it. This is a reversible stop (restore the value afterwards: 100 for the API, 10 for
   fulfillment and the Stripe webhook, per `tools/wafr_hardening_spec.json`):
```text
aws lambda put-function-concurrency --function-name FUNCTION --reserved-concurrent-executions 0
```
4. Roll back: Actions, "Rollback Lambda", pick the function and `previous` (functions it supports: api, bundle-fulfillment, stripe-webhook, mcp-http).
   For any other function redeploy from main with the normal deploy workflow.
5. Treat every secret the function could read as exposed. Rotate them (PB-1 step 6).
6. Restore concurrency to its value. Check the drift workflow goes green.
7. Find how the code was replaced: that is PB-1 if a key did it.

## PB-3. Customer API key abuse (plan scenario C)

**Triggers:** quota exhausted by one key; odd endpoint pattern; RapidAPI or Stripe usage anomaly.

1. Capture the API Gateway access log window for the key (export from CloudWatch Logs; the tool does not cover this).
2. Disable the key in API Gateway:
```text
aws apigateway update-api-key --api-key KEYID --patch-operations op=replace,path=/enabled,value=false
```
3. Establish scope: which endpoints, how many calls, any sign it read other customers' data (it should not be able to).
4. Email the customer within 24 hours, issue a new key.
5. If the abuse exploited a bug, that is a P2 and a code fix, not just a key swap.

## PB-4. Customer data exposed or read by an unauthorised party (plan scenario A, section 6)

**Triggers:** CloudTrail shows `GetItem`, `Scan` or `Query` from an unknown principal or IP; a customer reports their data elsewhere.

1. Capture first. If the principal is an IAM identity, PB-1 steps 3 and 4 now.
2. Establish what was readable: DynamoDB values for phone and email are field-encrypted with KMS; check CloudTrail for `Decrypt` calls by the same
   principal. Ciphertext alone is not exposed data; ciphertext plus decrypt rights is.
3. If integrity is in doubt, restore the table to a NEW table from point-in-time recovery and compare (never restore over the original):
```text
aws dynamodb restore-table-to-point-in-time --source-table-name TABLE --target-table-name TABLE-restore-check --use-latest-restorable-time
```
4. Notification decision within 72 hours of confirmation, with legal counsel (section 6 of the plan). Write down the decision and its reason either way.
5. Stop deleting anything (forensics plan section 6).

## PB-5. Stripe webhook compromise or replay (plan scenario E)

**Triggers:** duplicate subscription events; signature failures spiking; unexpected user records.

1. Capture the function and log window (`--function relayshield-stripe-webhook`).
2. Rotate the webhook signing secret in the Stripe dashboard (Developers, Webhooks, the endpoint, roll secret) and update the secret in Secrets Manager.
3. If payment data exposure is suspected, tell Stripe security the same hour.
4. Reconcile Stripe events against DynamoDB records for the window; remove or correct fraudulent records.
5. Do not turn queue mode on or off in the middle of an incident; it is a separate change (`tools/wafr_stripe_queue.py`).

## PB-6. Twilio WhatsApp account compromise (plan scenario D)

**Triggers:** unexpected outbound messages in Twilio logs; a customer reports a message we did not send.

1. Export the Twilio message logs for the window from the console before changing anything.
2. Rotate the Auth Token in the Twilio console and in Secrets Manager.
3. Point the number's webhook away from production until secured; tell Twilio security.
4. Email active subscribers that the WhatsApp channel is paused, and again when restored.

## PB-7. Secret committed to the repository or pasted publicly

**Triggers:** GitGuardian or Gitleaks alert; a researcher report; a chat paste.

1. Treat the secret as compromised from the moment it was public. Removing it from git does not un-publish it.
2. Rotate it at the source first (the provider's console), then in Secrets Manager.
3. Search CloudTrail or the provider's logs for use since the exposure date.
4. Only then remove it from the repository, and check the history and forks.

## PB-8. Malicious or compromised dependency (plan 5.2 "Supply chain")

**Triggers:** an advisory for a package we use; a failing safety check; odd behaviour after a dependency bump.

1. Identify the package, versions and the window they were deployed (git history of the requirements files and the deploy runs).
2. Assume every secret in the environment of every function deployed in the window is compromised. Rotate all of them.
3. Redeploy every function from a pinned, known-clean dependency set.
4. Review CloudTrail and logs for outbound calls during the window.

## What every playbook ends with

Within 5 business days: the post-incident review (plan 5.5), the notification decision on record, the plan or playbook changed
for anything that was wrong, and the evidence directories listed with their manifest hashes.
