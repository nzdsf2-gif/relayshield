"""
RelayShield KMS Email Migration Lambda
=======================================
One-time migration: encrypts plaintext email_address fields in
relayshield_monitored_emails using the relayshield-data-key KMS key.

Background
----------
Before field-level KMS encryption was introduced, monitored email addresses
were stored in plaintext under the 'email_address' attribute. The breach
monitor Lambda now writes 'email_encrypted' (KMS ciphertext) and
'email_hash' (SHA-256) for all new records, and falls back to the legacy
'email_address' field for existing ones.

This migration brings existing beta records into the new schema:
  BEFORE: { email_id, user_id, email_address: "user@example.com", ... }
  AFTER:  { email_id, user_id, email_encrypted: "<b64 ciphertext>",
             email_hash: "<sha256>", ... }
  (email_address field removed after successful encryption)

Usage
-----
Deploy as a Lambda (relayshield-kms-email-migration) and invoke once:

  aws lambda invoke \
      --function-name relayshield-kms-email-migration \
      --payload '{"dry_run": false}' \
      response.json && cat response.json

Dry run (no writes — safe to run any time):
  --payload '{"dry_run": true}'

Safety properties
-----------------
- Skips records that already have email_encrypted  (idempotent)
- Skips records with no email_address to migrate    (safe no-op)
- If KMS encrypt fails for a record, logs the error and continues
- email_address is only REMOVED after a verified successful encrypt + update
- Returns a full summary: migrated / skipped / failed counts
- Can be re-run safely — already-migrated records are skipped

Required IAM permissions (already added via relayshield-kms-field-encryption):
  kms:Encrypt, kms:Decrypt, kms:GenerateDataKey, kms:DescribeKey
  on arn:aws:kms:us-east-1:239677749008:key/1479c3fa-88e9-4096-a736-32968ba5812f

Deployment steps
----------------
1. Deploy this file as Lambda: relayshield-kms-email-migration
2. Attach the same execution role as relayshield-breach-check-role-1sapnwdl
   (already has KMS + DynamoDB permissions)
3. Invoke with dry_run: true first — review the log output
4. Invoke with dry_run: false to perform the migration
5. Re-invoke with dry_run: true to confirm 0 legacy records remain
6. Delete this Lambda once migration is confirmed complete
"""

import base64
import hashlib
import json
import logging

import boto3
from boto3.dynamodb.conditions import Attr

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

dynamodb      = boto3.resource("dynamodb")
kms_client    = boto3.client("kms")

MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"
KMS_EMAIL_KEY_ALIAS    = "alias/relayshield-data-key"


# ---------------------------------------------------------------------------
# Helpers (mirrors breach monitor — must stay in sync)
# ---------------------------------------------------------------------------

def hash_email(email: str) -> str:
    """SHA-256 of normalised email."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def encrypt_email(email: str) -> str:
    """Encrypt normalised email via KMS. Returns base64-encoded ciphertext."""
    response = kms_client.encrypt(
        KeyId=KMS_EMAIL_KEY_ALIAS,
        Plaintext=email.strip().lower().encode(),
    )
    return base64.b64encode(response["CiphertextBlob"]).decode()


def decrypt_email(ciphertext_b64: str) -> str:
    """Decrypt KMS-encrypted email. Used to verify round-trip after encrypt."""
    response = kms_client.decrypt(
        CiphertextBlob=base64.b64decode(ciphertext_b64),
    )
    return response["Plaintext"].decode()


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------

def scan_legacy_records() -> list[dict]:
    """
    Return all records in relayshield_monitored_emails that still have a
    plaintext email_address field (i.e. not yet migrated).
    """
    table  = dynamodb.Table(MONITORED_EMAILS_TABLE)
    items: list[dict] = []
    kwargs: dict = {
        "FilterExpression": Attr("email_address").exists()
    }

    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return items


def migrate_record(record: dict, dry_run: bool) -> str:
    """
    Encrypt the email_address on a single record.

    Returns one of: "migrated" | "skipped_already_encrypted" |
                    "skipped_no_email" | "failed"
    """
    email_id = record.get("email_id", "unknown")
    user_id  = record.get("user_id",  "unknown")

    # Guard: skip if already encrypted (should be filtered by scan, but be safe)
    if "email_encrypted" in record:
        logger.info(
            "email_id=%s user_id=%s — already encrypted, skipping.",
            email_id, user_id,
        )
        return "skipped_already_encrypted"

    plaintext_email = record.get("email_address", "").strip().lower()
    if not plaintext_email:
        logger.warning(
            "email_id=%s user_id=%s — no email_address to migrate, skipping.",
            email_id, user_id,
        )
        return "skipped_no_email"

    if dry_run:
        logger.info(
            "DRY RUN — would encrypt email_id=%s user_id=%s (email omitted from log).",
            email_id, user_id,
        )
        return "migrated"

    # Encrypt
    try:
        ciphertext_b64 = encrypt_email(plaintext_email)
    except Exception as exc:
        logger.exception(
            "KMS encrypt failed for email_id=%s user_id=%s: %s — skipping.",
            email_id, user_id, exc,
        )
        return "failed"

    # Verify round-trip before committing
    try:
        decrypted = decrypt_email(ciphertext_b64)
        if decrypted != plaintext_email:
            logger.error(
                "Round-trip verification failed for email_id=%s — "
                "encrypted value does not decrypt to original. Skipping.",
                email_id,
            )
            return "failed"
    except Exception as exc:
        logger.exception(
            "Round-trip decrypt failed for email_id=%s: %s — skipping.",
            email_id, exc,
        )
        return "failed"

    # Write email_encrypted + email_hash, remove email_address atomically
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    try:
        table.update_item(
            Key={"email_id": email_id, "user_id": user_id},
            UpdateExpression=(
                "SET email_encrypted = :enc, email_hash = :hsh "
                "REMOVE email_address"
            ),
            ExpressionAttributeValues={
                ":enc": ciphertext_b64,
                ":hsh": hash_email(plaintext_email),
            },
            # Safety: only update if email_address still exists (no concurrent writes)
            ConditionExpression=Attr("email_address").exists(),
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        logger.warning(
            "email_id=%s was already updated by a concurrent process — skipping.",
            email_id,
        )
        return "skipped_already_encrypted"
    except Exception as exc:
        logger.exception(
            "DynamoDB update failed for email_id=%s user_id=%s: %s",
            email_id, user_id, exc,
        )
        return "failed"

    logger.info(
        "Migrated email_id=%s user_id=%s — plaintext field removed.",
        email_id, user_id,
    )
    return "migrated"


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    dry_run: bool = event.get("dry_run", True)  # Default to dry run — must opt in

    mode = "DRY RUN" if dry_run else "LIVE"
    logger.info("=== RelayShield KMS Email Migration — %s ===", mode)

    # Scan for legacy records
    try:
        legacy_records = scan_legacy_records()
    except Exception as exc:
        logger.exception("Failed to scan legacy records: %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }

    total = len(legacy_records)
    logger.info("Found %d legacy plaintext record(s) to migrate.", total)

    if total == 0:
        logger.info("Nothing to migrate — all records already encrypted.")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "mode": mode,
                "total_found": 0,
                "migrated": 0,
                "skipped": 0,
                "failed": 0,
                "message": "All records already encrypted. Migration complete.",
            }),
        }

    # Migrate each record
    counts = {"migrated": 0, "skipped_already_encrypted": 0,
              "skipped_no_email": 0, "failed": 0}

    for record in legacy_records:
        result = migrate_record(record, dry_run=dry_run)
        counts[result] = counts.get(result, 0) + 1

    skipped = counts["skipped_already_encrypted"] + counts["skipped_no_email"]
    summary = {
        "mode":     mode,
        "total_found": total,
        "migrated": counts["migrated"],
        "skipped":  skipped,
        "failed":   counts["failed"],
    }

    if counts["failed"] > 0:
        logger.error(
            "Migration completed with %d failure(s). "
            "Re-run to retry failed records.",
            counts["failed"],
        )
        status = 207  # Partial success
    else:
        logger.info(
            "Migration %s complete — migrated=%d skipped=%d failed=0",
            mode, counts["migrated"], skipped,
        )
        status = 200

    if dry_run:
        summary["message"] = (
            "Dry run complete — no changes written. "
            "Re-invoke with dry_run: false to migrate."
        )

    logger.info("Summary: %s", json.dumps(summary))
    return {"statusCode": status, "body": json.dumps(summary)}
