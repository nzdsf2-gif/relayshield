# RelayShield Forensics Plan

| | |
|---|---|
| **Status** | **DRAFT, not adopted.** Written 2026-11-24 by Claude from the repo. Becomes real when Andrew adopts it and answers the CONFIRM items |
| **Owner** | Andrew Gibbs, Incident Commander |
| **Part of** | `relayshield_incident_response_plan.md` v1.1, section 8 |
| **Covers** | WAFR SEC 10 "Prepare forensic capabilities" |

## 1. The rule

Capture first, contain second. Containment (rotating a key, rolling back a Lambda, setting concurrency to 0) overwrites or
hides the evidence that says what happened. The capture takes minutes; do it for every P1 and P2 before the first
containment action, unless data is actively leaving and every minute costs more than the evidence is worth. If you skip it,
write down that you did and why.

## 2. What evidence exists, and how long it lasts

| Source | What it answers | Lifetime | Status |
|---|---|---|---|
| CloudTrail event history | which identity called which AWS API, from which IP, when | 90 days, built in | confirmed running in the 2026-11-20 evidence run |
| CloudTrail trail to S3 | the same, beyond 90 days, with log file validation | until the bucket's lifecycle deletes it | CONFIRM the bucket name, lifecycle and that object lock or a second copy exists |
| Lambda versions and aliases | exactly what code was live, and when it changed | kept until deleted; each deploy publishes a version | in place after `apply_deploy_versions_policy.sh` |
| CloudWatch Logs | what each function did and said | 90 days once `wafr_hardening.py --step retention` is applied, forever before | CONFIRM applied |
| DynamoDB point-in-time recovery | the state of a table at a past second, restorable to a NEW table | 35 days | CONFIRM enabled on every table (`protect_dynamodb_tables.sh`) |
| API Gateway access logs | who called which endpoint | per the log group above | CONFIRM enabled on the stage |
| Third-party consoles | Twilio message logs, Stripe events, RapidAPI usage | the vendor's retention | export from each console, screenshots count |
| Git history | what the code was supposed to be | permanent | `lambda_drift_check.yml` compares live to it daily |

A gap in this table is a gap in the plan. The CONFIRM rows are the ones to check first.

## 3. The capability: `tools/ir_capture_evidence.py`

Read-only. Needs `AWS_PROFILE=relayshield`, or the responder role in section 5. It saves, into a new directory:
CloudTrail events for each identity or resource you name, the full state of each named Lambda (configuration, versions,
aliases, concurrency; the presigned download link is removed), the access keys of each named IAM user with last-used,
and a SHA-256 manifest of every file. It records its own failures in the file instead of hiding them. It refuses to
reuse a directory and refuses the wrong account.

Example, for a leaked access key and a Lambda you think was changed (reference only, not a block to paste as is):

```text
AWS_PROFILE=relayshield python3 tools/ir_capture_evidence.py --lookup AccessKeyId=AKIA... --function relayshield-api --iam-user the-user
```

It does not capture DynamoDB contents, third-party consoles or log groups; those are in sections 2 and 4.

## 4. Chain of custody

1. Run the capture first. Note the directory name and the UTC time it printed.
2. Copy the directory, unchanged, to a place you cannot overwrite by accident. CONFIRM where: a second S3 bucket with
   object lock is the proper answer; a dated archive on a separate drive is the minimum.
3. Verify the copy with `shasum -a 256 -c SHA256SUMS` inside it. Every line must say OK.
4. Never edit the originals. Notes go in the incident record, not in the evidence directory.
5. The incident record (section 5.1 of the plan) lists each evidence directory, its manifest hash, and who copied it where.
6. The evidence directory is confidential. Do not commit it, email it or paste it into a chat.

## 5. Access during an incident

The read-only role `relayshield-ir-responder` is created by `tools/apply_ir_responder_role.sh`. It can read CloudTrail, IAM
metadata, Lambda configuration and logs, and change nothing. It needs MFA within the last hour. Use it for the capture and
the investigation; use normal admin access only for the containment step that needs it. Until the script has been run the
role does not exist and this section is not true.

## 6. Legal hold and notification

If customer data may be exposed, stop deleting anything (log retention changes, table cleanups, old Lambda versions) and
call legal counsel before any regulatory notification, as the plan already says. Keep evidence at least 12 months after the
incident closes. CONFIRM with counsel that 12 months is enough.

## 7. CONFIRM list (only Andrew can answer)

1. CloudTrail trail S3 bucket: name, lifecycle, object lock.
2. Is `wafr_hardening.py --step retention` applied, and is PITR on for every table?
3. Where does the evidence copy live?
4. Evidence retention period: Andrew considers 12 months acceptable (2026-11-24); counsel to confirm.
