"""
RelayShield KMS Phone Migration Lambda
=======================================
One-time migration: encrypts plaintext phone_number / whatsapp_number fields
in relayshield_users using the relayshield-data-key KMS key and writes a
SHA-256 phone_hash for GSI-based lookups.

Background
----------
Before field-level KMS encryption was introduced for phone numbers, user
records stored whatsapp_number (e.g. "whatsapp:+19785013199") and phone_number
(e.g. "+19785013199") as plaintext. The updated webhook Lambdas now write
phone_encrypted (KMS ciphertext) and phone_hash (SHA-256) for all new records,
and fall back to the legacy whatsapp_number field for existing ones.

This migration brings existing beta records into the new schema:
  BEFORE: { user_id, whatsapp_number: "whatsapp:+1...", phone_number: "+1...", ... }
  AFTER:  { user_id, phone_encrypted: "<b64 ciphertext>", phone_hash: "<sha256>", ... }
  (whatsapp_number and phone_number fields removed after successful encryption)

Usage
-----
Deploy as a Lambda (relayshield-kms-phone-migration) and invoke once:

  aws lambda invoke \\
      --function-name relayshield-kms-phone-migration \\
      --payload '{"dry_run": false}' \\
      response.json && cat response.json

Dry run (no writes — safe to run any time):
  --payload '{"dry_run": true}'

Safety properties
-----------------
- Skips records that already have phone_encrypted   (idempotent)
- Skips records with no phone_number/whatsapp_number to migrate (safe no-op)
- If KMS encrypt fails for a record, logs the error and continues
- Plaintext fields only REMOVED after verified successful encrypt + update
- ConditionExpression prevents concurrent write conflicts
- Returns full summary: migrated / skipped / failed counts
- Can be re-run safely — already-migrated records are skipped

Required IAM permissions:
  kms:Encrypt, kms:Decrypt, kms:GenerateDataKey, kms:DescribeKey
  on arn:aws:kms:us-east-1:239677749008:key/1479c3fa-88e9-4096-a736-32968ba5812f
  dynamodb:Scan, dynamodb:UpdateItem on relayshield_users

Deployment steps
----------------
1. Deploy this file as Lambda: relayshield-kms-phone-migration
2. Execution role: relayshield-breach-check-role-1sapnwdl
   (add inline policy relayshield-phone-migration-policy with Scan + UpdateItem
   on relayshield_users if not already present)
3. Memory: 256 MB, Timeout: 5 minutes
4. Handler: relayshield_kms_phone_migration.lambda_handler
5. Invoke with dry_run: true first — review log output
6. Invoke with dry_run: false to perform the migration
7. Re-invoke with dry_run: true to confirm 0 legacy records remain
8. Delete this Lambda once migration is confirmed complete
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

dynamodb   = boto3.resource("dynamodb")
kms_client = boto3.client("kms")

USERS_TABLE         = "relayshield_users"
KMS_PHONE_KEY_ALIAS = "alias/relayshield-data-key"


# ---------------------------------------------------------------------------
# Helpers (mirrors whatsapp_webhook — must stay in sync)
# ---------------------------------------------------------------------------

def hash_phone(phone: str) -> str:
    """SHA-256 of normalised E.164 phone — deterministic GSI lookup key."""
    normalised = phone.strip().replace("whatsapp:", "")
    return hashlib.sha256(normalised.encode()).hexdigest()


def encrypt_phone(phone: str) -> str:
    """Encrypt normalised E.164 phone via KMS. Returns base64-encoded ciphertext."""
    normalised = phone.strip().replace("whatsapp:", "")
    response = kms_client.encrypt(
        KeyId=KMS_PHONE_KEY_ALIAS,
        Plaintext=normalised.encode(),
    )
    return base64.b64encode(response["CiphertextBlob"]).decode()


def decrypt_phone(ciphertext_b64: str) -> str:
    """Decrypt KMS-encrypted phone ciphertext (base64). Returns E.164 string."""
    response = kms_client.decrypt(
        CiphertextBlob=base64.b64decode(ciphertext_b64),
    )
    return response["Plaintext"].decode()


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------

def scan_legacy_records() -> list[dict]:
    """
    Return all user records that still have a plaintext phone_number or
    whatsapp_number field (i.e. not yet migrated to phone_encrypted).
    """
    table  = dynamodb.Table(USERS_TABLE)
    items: list[dict] = []
    kwargs: dict = {
        "FilterExpression": Attr("phone_number").exists() | Attr("whatsapp_number").exists()
    }

    while True:
        response = table.scan(**kwargs)
        # Only keep records that don't already have phone_encrypted
        for item in response.get("Items", []):
            if "phone_encrypted" not in item:
                items.append(item)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return items


def migrate_record(record: dict, dry_run: bool) -> str:
    """
    Encrypt the phone number on a single user record.

    Returns one of: "migrated" | "skipped_already_encrypted" |
                    "skipped_no_phone" | "failed"
    """
    user_id = record.get("user_id", "unknown")

    # Guard: skip if already encrypted
    if "phone_encrypted" in record:
        logger.info("user_id=%s — already encrypted, skipping.", user_id)
        return "skipped_already_encrypted"

    # Resolve plaintext phone from whatsapp_number or phone_number
    raw_phone = (
        record.get("phone_number")
        or record.get("whatsapp_number", "")
    ).strip().replace("whatsapp:", "")

    if not raw_phone:
        logger.warning("user_id=%s — no phone_number or whatsapp_number, skipping.", user_id)
        return "skipped_no_phone"

    if dry_run:
        logger.info(
            "DRY RUN — would encrypt user_id=%s (phone omitted from log).", user_id
        )
        return "migrated"

    # Encrypt
    try:
        ciphertext_b64 = encrypt_phone(raw_phone)
    except Exception as exc:
        logger.exception(
            "KMS encrypt failed for user_id=%s: %s — skipping.", user_id, exc
        )
        return "failed"

    # Verify round-trip before committing
    try:
        decrypted = decrypt_phone(ciphertext_b64)
        if decrypted != raw_phone:
            logger.error(
                "Round-trip verification failed for user_id=%s — "
                "encrypted value does not decrypt to original. Skipping.",
                user_id,
            )
            return "failed"
    except Exception as exc:
        logger.exception(
            "Round-trip decrypt failed for user_id=%s: %s — skipping.", user_id, exc
        )
        return "failed"

    # Write phone_encrypted + phone_hash, remove plaintext fields atomically
    table = dynamodb.Table(USERS_TABLE)
    try:
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression=(
                "SET phone_encrypted = :enc, phone_hash = :hsh "
                "REMOVE phone_number, whatsapp_number"
            ),
            ExpressionAttributeValues={
                ":enc": ciphertext_b64,
                ":hsh": hash_phone(raw_phone),
            },
            # Safety: only update if plaintext fields still exist (prevent concurrent writes)
            ConditionExpression=(
                Attr("phone_number").exists() | Attr("whatsapp_number").exists()
            ),
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        logger.warning(
            "user_id=%s was already updated by a concurrent process — skipping.",
            user_id,
        )
        return "skipped_already_encrypted"
    except Exception as exc:
        logger.exception(
            "DynamoDB update failed for user_id=%s: %s", user_id, exc
        )
        return "failed"

    logger.info(
        "Migrated user_id=%s — plaintext phone fields removed.", user_id
    )
    return "migrated"


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    dry_run: bool = event.get("dry_run", True)  # Default to dry run — must opt in

    mode = "DRY RUN" if dry_run else "LIVE"
    logger.info("=== RelayShield KMS Phone Migration — %s ===", mode)

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
    logger.info("Found %d legacy plaintext phone record(s) to migrate.", total)

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
    counts = {
        "migrated": 0,
        "skipped_already_encrypted": 0,
        "skipped_no_phone": 0,
        "failed": 0,
    }

    for record in legacy_records:
        result = migrate_record(record, dry_run=dry_run)
        counts[result] = counts.get(result, 0) + 1

    skipped = counts["skipped_already_encrypted"] + counts["skipped_no_phone"]
    summary = {
        "mode":       mode,
        "total_found": total,
        "migrated":   counts["migrated"],
        "skipped":    skipped,
        "failed":     counts["failed"],
    }

    if counts["failed"] > 0:
        logger.error(
            "Migration completed with %d failure(s). Re-run to retry failed records.",
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
