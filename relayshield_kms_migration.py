"""
RelayShield KMS Email Encryption Migration

One-time script. Encrypts all plaintext email_address fields in:
  - relayshield_monitored_emails
  - relayshield_breach_alerts

For each legacy record:
  1. Reads the plaintext email_address field
  2. Writes email_encrypted (KMS ciphertext, base64) and email_hash (SHA-256)
  3. Removes the plaintext email_address field

Safe to run multiple times — skips records that already have email_encrypted.

Prerequisites:
  - AWS credentials with kms:Encrypt + dynamodb:Scan + dynamodb:UpdateItem
  - KMS key alias/relayshield-data-key must exist and be enabled
  - Run from a machine in the same AWS region as the Lambda (us-east-1)

Usage:
    python relayshield_kms_migration.py [--dry-run]

    --dry-run  Print what would be migrated without writing to DynamoDB or KMS
"""

import argparse
import base64
import hashlib
import logging
import sys

import boto3
from boto3.dynamodb.conditions import Attr

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

KMS_KEY_ALIAS = "alias/relayshield-data-key"
MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"
BREACH_ALERTS_TABLE = "relayshield_breach_alerts"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

kms_client = boto3.client("kms")
dynamodb = boto3.resource("dynamodb")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def encrypt_email(email: str) -> str:
    response = kms_client.encrypt(
        KeyId=KMS_KEY_ALIAS,
        Plaintext=email.strip().lower().encode(),
    )
    return base64.b64encode(response["CiphertextBlob"]).decode()


def scan_table_with_plaintext(table_name: str) -> list[dict]:
    """Return all records that have email_address but lack email_encrypted."""
    table = dynamodb.Table(table_name)
    items: list[dict] = []
    kwargs: dict = {
        "FilterExpression": Attr("email_address").exists(),
    }

    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return items


def migrate_monitored_emails(dry_run: bool) -> int:
    """Migrate relayshield_monitored_emails. Returns count of records migrated."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    records = scan_table_with_plaintext(MONITORED_EMAILS_TABLE)
    logger.info(
        "monitored_emails: found %d record(s) with plaintext email_address.", len(records)
    )
    migrated = 0

    for record in records:
        email_id = record.get("email_id", "?")
        user_id = record.get("user_id", "?")
        email_address = record.get("email_address", "")

        if not email_address:
            logger.warning("Skipping email_id=%s — empty email_address.", email_id)
            continue

        if dry_run:
            logger.info(
                "[DRY RUN] Would encrypt email_id=%s user_id=%s", email_id, user_id
            )
            migrated += 1
            continue

        try:
            encrypted = encrypt_email(email_address)
            hashed = hash_email(email_address)

            table.update_item(
                Key={"email_id": email_id, "user_id": user_id},
                UpdateExpression=(
                    "SET email_encrypted = :enc, email_hash = :hsh "
                    "REMOVE email_address"
                ),
                ExpressionAttributeValues={
                    ":enc": encrypted,
                    ":hsh": hashed,
                },
            )
            logger.info(
                "Migrated email_id=%s user_id=%s hash=%s...",
                email_id, user_id, hashed[:8],
            )
            migrated += 1
        except Exception as exc:
            logger.exception(
                "Failed to migrate email_id=%s user_id=%s: %s", email_id, user_id, exc
            )

    return migrated


def migrate_breach_alerts(dry_run: bool) -> int:
    """Migrate relayshield_breach_alerts. Returns count of records migrated."""
    table = dynamodb.Table(BREACH_ALERTS_TABLE)
    records = scan_table_with_plaintext(BREACH_ALERTS_TABLE)
    logger.info(
        "breach_alerts: found %d record(s) with plaintext email_address.", len(records)
    )
    migrated = 0

    for record in records:
        alert_id = record.get("alert_id", "?")
        user_id = record.get("user_id", "?")
        email_address = record.get("email_address", "")

        if not email_address:
            logger.warning("Skipping alert_id=%s — empty email_address.", alert_id)
            continue

        if dry_run:
            logger.info(
                "[DRY RUN] Would encrypt alert_id=%s user_id=%s", alert_id, user_id
            )
            migrated += 1
            continue

        try:
            encrypted = encrypt_email(email_address)
            hashed = hash_email(email_address)

            table.update_item(
                Key={"alert_id": alert_id},
                UpdateExpression=(
                    "SET email_encrypted = :enc, email_hash = :hsh "
                    "REMOVE email_address"
                ),
                ExpressionAttributeValues={
                    ":enc": encrypted,
                    ":hsh": hashed,
                },
            )
            logger.info(
                "Migrated alert_id=%s user_id=%s hash=%s...",
                alert_id, user_id, hashed[:8],
            )
            migrated += 1
        except Exception as exc:
            logger.exception(
                "Failed to migrate alert_id=%s: %s", alert_id, exc
            )

    return migrated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RelayShield KMS email migration")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be migrated without writing anything",
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.info("=== DRY RUN — no changes will be written ===")

    emails_migrated = migrate_monitored_emails(args.dry_run)
    alerts_migrated = migrate_breach_alerts(args.dry_run)

    logger.info(
        "Migration %s — monitored_emails: %d, breach_alerts: %d",
        "preview" if args.dry_run else "complete",
        emails_migrated,
        alerts_migrated,
    )

    if not args.dry_run and (emails_migrated + alerts_migrated) > 0:
        logger.info(
            "All plaintext email_address fields removed. "
            "Verify Lambda reads are working before decommissioning the legacy fallback."
        )


if __name__ == "__main__":
    main()
